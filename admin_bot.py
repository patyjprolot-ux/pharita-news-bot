"""Интерактивный админ-бот: меню с кнопками, ручная публикация, статистика,
часовая сводка и автоматическая публикация со случайным дневным лимитом
(4-10 в сутки по умолчанию).

Доступ к кнопкам управления — только у ADMIN_CHAT_ID из .env.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import date, datetime, timezone

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    TypeHandler,
)
from telegram.ext import filters as tg_filters

import channel_stats
import daily_slots
import source_label
import telethon_client
from config import CONFIG
from filters import is_important
from formatter import format_post
from pending import PendingPost, serialize_media, short_preview
from rewrite import rewrite_text
from sources_factory import build_sources
from storage import Storage, make_fingerprint
from telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)

storage = Storage(CONFIG.db_path)
publisher = TelegramPublisher(CONFIG.telegram_bot_token, CONFIG.target_channel)
active_sources: list = []  # заполняется в post_init, после подключения Telethon


def _is_admin(update: Update) -> bool:
    chat = update.effective_chat
    return bool(CONFIG.admin_chat_id) and bool(chat) and chat.id == CONFIG.admin_chat_id


PERSISTENT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🩷 Меню")]], resize_keyboard=True, is_persistent=True
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    pending_count = storage.count_pending()
    buttons = [
        [InlineKeyboardButton(f"🩷 Очередь ({pending_count})", callback_data="menu:queue")],
        [InlineKeyboardButton("💗 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton("🌸 Сводка за час", callback_data="menu:digest")],
        [InlineKeyboardButton("🩷🔄 Проверить источники сейчас", callback_data="menu:refresh")],
    ]
    return InlineKeyboardMarkup(buttons)


async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    logger.info(
        "RAW UPDATE: chat_id=%s user_id=%s username=%s text=%r",
        chat.id if chat else None,
        user.id if user else None,
        user.username if user else None,
        update.effective_message.text if update.effective_message else None,
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        chat = update.effective_chat
        logger.warning("cmd_menu: доступ отклонён для chat_id=%s (ожидался %s)", chat.id if chat else None, CONFIG.admin_chat_id)
        return
    await update.effective_chat.send_message(
        "🩷 <b>PHARITA / BABYMONSTER bot</b> 🩷\nПанель управления:",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    await update.effective_chat.send_message(
        "🩷 Кнопка меню теперь всегда под рукой снизу экрана 🩷",
        reply_markup=PERSISTENT_KEYBOARD,
    )
    await cmd_menu(update, context)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _is_admin(update):
        await query.answer("Доступ ограничен", show_alert=True)
        return
    await query.answer()

    data = query.data
    if data == "menu:back":
        await query.edit_message_text(
            "🖤 <b>PHARITA / BABYMONSTER bot</b> 🩷\nПанель управления:",
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    elif data == "menu:queue":
        await show_queue(query)
    elif data == "menu:stats":
        await show_stats(query)
    elif data == "menu:digest":
        await show_digest(query)
    elif data == "menu:refresh":
        await query.edit_message_text("🔄 Проверяю источники...")
        await fetch_cycle()
        await query.edit_message_text("✅ Проверка завершена.", reply_markup=main_menu_keyboard())
    elif data.startswith("publish:"):
        await publish_pending_item(query, int(data.split(":", 1)[1]))


async def show_queue(query) -> None:
    rows = storage.get_pending(limit=8)
    if not rows:
        await query.edit_message_text(
            "Очередь пуста — новых важных новостей пока нет.",
            reply_markup=main_menu_keyboard(),
        )
        return

    buttons = []
    for row in rows:
        post = PendingPost(row)
        tag_bit = post.display_source or f"#{post.category_tag}"
        label = f"{tag_bit} — {short_preview(post, 35)}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"publish:{post.id}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="menu:back")])

    await query.edit_message_text(
        "🩷 Очередь на публикацию — нажми, чтобы опубликовать вручную:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def publish_pending_item(query, item_id: int) -> None:
    row = storage.get_pending_by_id(item_id)
    if not row or row["status"] != "pending":
        await query.answer("Этот пост уже опубликован или не найден", show_alert=True)
        return

    post = PendingPost(row)
    text = format_post(post, channel_handle=CONFIG.target_channel or "@world_pharita")
    try:
        await publisher.publish(post, text)
        storage.mark_pending_published(post.id)
        await query.edit_message_text("✅ Опубликовано вручную.", reply_markup=main_menu_keyboard())
    except Exception:
        logger.exception("Не удалось опубликовать вручную пост %s", item_id)
        await query.edit_message_text(
            "⚠️ Не получилось опубликовать, смотри логи.", reply_markup=main_menu_keyboard()
        )


async def show_stats(query) -> None:
    await query.edit_message_text("🩷 Считаю статистику...")
    authorized = await telethon_client.ensure_connected()
    if not authorized:
        await query.edit_message_text(
            "⚠️ Аккаунт для чтения Telegram не авторизован — статистика недоступна.",
            reply_markup=main_menu_keyboard(),
        )
        return
    text = await channel_stats.build_stats_message(telethon_client.get_client(), CONFIG.target_channel, storage)
    await query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)


def format_digest(rows) -> str:
    if not rows:
        return "За последний час новых упоминаний не найдено."

    lines = ["🩷 <b>Сводка за последний час</b> 🩷", ""]
    for row in rows:
        post = PendingPost(row)
        if post.media:
            media_mark = "📸" if post.media[0].type.value == "photo" else "🎥"
        else:
            media_mark = "🚫"
        if post.status == "published":
            status_mark = "✅ опубликовано"
        elif post.status == "waiting_for_text":
            status_mark = "⏳ ждём текст из другого источника"
        else:
            status_mark = "🗂 в очереди"
        source_bit = f" {post.display_source}" if post.display_source else ""
        lines.append(f"{media_mark}{source_bit} <b>{post.source_name}</b> — {short_preview(post)} ({status_mark})")
        if post.source_url:
            lines.append(post.source_url)
        lines.append("")
    return "\n".join(lines).strip()


async def show_digest(query) -> None:
    since_ts = int(datetime.now(timezone.utc).timestamp()) - CONFIG.hourly_digest_seconds
    rows = storage.get_items_found_since(since_ts)
    await query.edit_message_text(
        format_digest(rows), reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML
    )


async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cmu = update.chat_member
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status
    was_member = old_status in ("member", "administrator", "creator")
    is_member = new_status in ("member", "administrator", "creator")
    user_id = cmu.new_chat_member.user.id
    if is_member and not was_member:
        storage.record_member_event(user_id, "joined")
    elif was_member and not is_member:
        storage.record_member_event(user_id, "left")


async def track_reactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mrc = update.message_reaction_count
    if mrc is None:
        return
    total = sum(r.total_count for r in mrc.reactions)
    storage.set_post_reactions(mrc.message_id, int(mrc.date.timestamp()), total)


async def gather_all() -> list:
    all_items = []
    for source in active_sources:
        try:
            items = await source.fetch()
            logger.info("Источник %s вернул %d записей", source.name, len(items))
            all_items.extend(items)
        except Exception:
            logger.exception("Источник %s упал целиком, пропускаем", getattr(source, "name", source))
    return all_items


DONOR_SEARCH_WINDOW_SECONDS = 4 * 3600  # ищем текст-донор в пределах +-4ч от медиа-поста


async def _ingest_item(item) -> None:
    """Кладёт новую важную новость в очередь: Telegram-медиа без подписи
    уходит в ожидание текста, остальное — сразу с подобранным источником
    (и рерайтом, если текст скопирован из Telegram-поста)."""
    if source_label.needs_hold_for_text(item):
        storage.add_pending(item, serialize_media(item.media), status="waiting_for_text")
        return

    display_source = source_label.compute_display_source(item)
    if source_label.needs_rewrite(item):
        original = item.description.strip() or item.title.strip()
        item.description = await rewrite_text(original, item.category_tag)
        item.title = ""

    post_tag = source_label.compute_post_tag(display_source, item.category_tag)
    storage.add_pending(item, serialize_media(item.media), status="pending", display_source=post_tag)


async def process_waiting_items() -> None:
    """Медиа-посты из Telegram без подписи: раз в цикл проверяем, не появился
    ли за это время текст в другом источнике, чтобы использовать его вместо
    точной копии Telegram-поста. Если ждём слишком долго — публикуем как
    просто "Фото"/"Видео"."""
    now = datetime.now(timezone.utc)
    hold_seconds = CONFIG.telegram_hold_minutes * 60
    max_hold_seconds = CONFIG.telegram_hold_max_minutes * 60

    for row in storage.get_waiting_for_text():
        post = PendingPost(row)
        elapsed = now.timestamp() - post.found_at
        if elapsed < hold_seconds:
            continue

        donor_row = storage.find_donor_candidate(
            post.item_published_at, DONOR_SEARCH_WINDOW_SECONDS, exclude_id=post.id
        )
        if donor_row:
            donor = PendingPost(donor_row)
            display_source = source_label.compute_display_source(donor)
            post_tag = source_label.compute_post_tag(display_source, post.category_tag)
            storage.resolve_waiting_item(post.id, donor.title, donor.description, post_tag)
            storage.mark_donor_used(donor.id)
            logger.info("Медиа-пост Telegram id=%s дополнен текстом из %s", post.id, display_source)
        elif elapsed >= max_hold_seconds:
            media_label = "Видео" if post.media and post.media[0].type.value == "video" else "Фото"
            post_tag = source_label.compute_post_tag(media_label, post.category_tag)
            storage.resolve_waiting_item(post.id, "", "", post_tag)
            logger.info("Медиа-пост Telegram id=%s публикуется без текста (%s)", post.id, media_label)
        # иначе продолжаем ждать следующего цикла


def _source_category(source_name: str) -> str:
    """'Telegram: world_babymonster' -> 'Telegram', 'YouTube: BABYMONSTER' -> 'YouTube' и т.д."""
    return source_name.split(":", 1)[0]


async def run_daily_autopublish() -> None:
    """Публикует не больше одной "порции" за раз, ровно по числу слотов
    времени, которые уже наступили — это и даёт равномерный разброс
    4-10 публикаций по всем суткам вместо пачки подряд.

    Дополнительно: не даёт одному источнику (например Telegram) занять
    весь день — при выборе следующего поста из очереди предпочитает
    источник, отличный от предыдущей публикации и ещё не выбравший свою
    "квоту" (не больше половины дневного лимита на один источник, если
    в очереди есть альтернативы)."""
    today = date.today()
    now = datetime.now(timezone.utc)
    state = storage.get_daily_state(today)

    if state is None:
        target = random.randint(CONFIG.daily_post_min, CONFIG.daily_post_max)
        slots = daily_slots.generate_slots(target, already_published=0, now=now)
        storage.set_daily_target(today, target, daily_slots.serialize_slots(slots))
        state = storage.get_daily_state(today)
        logger.info("Новый дневной лимит автопубликаций: %d", target)
    elif not state["slot_times_json"]:
        slots = daily_slots.generate_slots(
            state["target_count"], already_published=state["published_count"], now=now
        )
        storage.set_daily_slots(today, daily_slots.serialize_slots(slots))
        state = storage.get_daily_state(today)

    slots = daily_slots.deserialize_slots(state["slot_times_json"])
    due = daily_slots.count_due(slots, now)
    remaining = due - state["published_count"]
    if remaining <= 0:
        return

    today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    category_counts: dict[str, int] = {}
    for row in storage.get_published_since(int(today_start.timestamp())):
        cat = _source_category(row["source_name"])
        category_counts[cat] = category_counts.get(cat, 0) + 1

    last_row = storage.get_last_published()
    last_category = _source_category(last_row["source_name"]) if last_row else None
    soft_cap = max(1, -(-state["target_count"] // 2))  # источник не больше половины дневного лимита

    for _ in range(remaining):
        candidates = storage.get_pending(limit=20)
        if not candidates:
            break

        def _score(row):
            cat = _source_category(row["source_name"])
            return (category_counts.get(cat, 0) >= soft_cap, cat == last_category)

        chosen = min(candidates, key=_score)
        post = PendingPost(chosen)
        text = format_post(post, channel_handle=CONFIG.target_channel or "@world_pharita")
        try:
            await publisher.publish(post, text)
            storage.mark_pending_published(post.id)
            storage.increment_daily_published(today)
            cat = _source_category(post.source_name)
            category_counts[cat] = category_counts.get(cat, 0) + 1
            last_category = cat
            await asyncio.sleep(3)
        except Exception:
            logger.exception("Не удалось автоматически опубликовать пост %s", post.id)


async def fetch_cycle() -> None:
    items = await gather_all()
    items = [i for i in items if i.media]
    items = [i for i in items if is_important(i)]
    items.sort(key=lambda i: i.published_at)

    new_count = 0
    for item in items:
        fingerprint = make_fingerprint(item.title, item.description)
        if storage.is_duplicate(item.dedup_key, fingerprint):
            continue
        storage.mark_seen(item.dedup_key, fingerprint, item.source_name)
        await _ingest_item(item)
        new_count += 1
    logger.info("Цикл сбора: найдено %d новых важных записей", new_count)

    await process_waiting_items()
    await run_daily_autopublish()


async def job_fetch_cycle(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await fetch_cycle()
    except Exception:
        logger.exception("job_fetch_cycle: необработанная ошибка")
    storage.purge_old()


async def job_hourly_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not CONFIG.admin_chat_id:
        return
    since_ts = int(datetime.now(timezone.utc).timestamp()) - CONFIG.hourly_digest_seconds
    rows = storage.get_items_found_since(since_ts)
    try:
        await context.bot.send_message(
            chat_id=CONFIG.admin_chat_id, text=format_digest(rows), parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.exception("job_hourly_digest: не удалось отправить сводку")


async def post_init(application: Application) -> None:
    global active_sources
    authorized = await telethon_client.ensure_connected()
    if not authorized:
        logger.warning(
            "Telethon-аккаунт не авторизован — Telegram-источник и статистика работать не будут. "
            "Выполни разовый вход (см. README, раздел про Telethon)."
        )
    active_sources = build_sources(telethon_client.get_client())
    logger.info("Активные источники: %s", ", ".join(s.name for s in active_sources) or "нет")

    await application.bot.set_my_commands([BotCommand("menu", "🩷 Открыть меню")])


def build_application() -> Application:
    if not CONFIG.telegram_bot_token or not CONFIG.target_channel:
        raise SystemExit("Заполните TELEGRAM_BOT_TOKEN и TARGET_CHANNEL в .env")

    application = ApplicationBuilder().token(CONFIG.telegram_bot_token).post_init(post_init).build()

    application.add_handler(TypeHandler(Update, log_all_updates), group=-1)
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("menu", cmd_menu))
    application.add_handler(MessageHandler(tg_filters.Text(["🩷 Меню"]), cmd_menu))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(
        MessageReactionHandler(
            track_reactions, message_reaction_types=MessageReactionHandler.MESSAGE_REACTION_COUNT_UPDATED
        )
    )

    jq = application.job_queue
    jq.run_repeating(job_fetch_cycle, interval=CONFIG.poll_interval_seconds, first=10)
    jq.run_repeating(job_hourly_digest, interval=CONFIG.hourly_digest_seconds, first=CONFIG.hourly_digest_seconds)

    return application
