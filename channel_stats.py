"""Реальная статистика Telegram-канала — только то, что Telegram
действительно предоставляет. Никаких выдуманных цифр.

Источники данных:
- Число подписчиков — через MTProto (Telethon), с фолбэком на Bot API.
- Подписчиков пришло/ушло сегодня — считаем сами, слушая chat_member
  апдейты (Bot API) пока бот работает (см. admin_bot.py).
- Просмотры сегодняшних постов — забираем через Telethon (MTProto даёт
  реальные views у сообщений канала; обычный Bot API этого не отдаёт).
- Реакции ("лайки") сегодня — тоже считаем сами по message_reaction_count
  апдейтам, пока бот работает.
- Официальная расширенная статистика Telegram (стата роста, % включённых
  уведомлений и т.п.) доступна только у каналов от ~500 подписчиков и
  показывается лучшим эффортом — если Telegram её не отдаёт, честно
  сообщаем об этом, а не подставляем нули.

Специально НЕ показываем: "заблокировавшие подписчики" и "активные /
неактивные подписчики" — таких данных не существует ни в одном API
Telegram, официальном или нет.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telethon.tl.functions.channels import GetFullChannelRequest

logger = logging.getLogger(__name__)


def _start_of_today_ts() -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


async def _get_subscriber_count(client, channel_entity) -> int | None:
    try:
        full = await client(GetFullChannelRequest(channel=channel_entity))
        return full.full_chat.participants_count
    except Exception:
        logger.exception("channel_stats: не удалось получить число подписчиков")
        return None


async def _refresh_today_views(client, channel_entity, storage, since_ts: int) -> None:
    try:
        async for message in client.iter_messages(channel_entity, limit=100):
            if message.date.timestamp() < since_ts:
                break
            if message.views is not None:
                storage.upsert_post_views(message.id, int(message.date.timestamp()), message.views)
    except Exception:
        logger.exception("channel_stats: не удалось обновить просмотры постов")


async def _try_broadcast_stats(client, channel_entity) -> dict | None:
    """Официальная статистика Telegram — доступна не всем каналам (нужно
    от ~500 подписчиков и минимум сутки существования). Best-effort:
    структура ответа может отличаться между версиями Telethon/Bot API,
    поэтому берём поля через getattr и не падаем, если чего-то нет."""
    try:
        from telethon.tl.functions.stats import GetBroadcastStatsRequest

        stats = await client(GetBroadcastStatsRequest(channel=channel_entity))
    except Exception:
        return None

    result: dict = {}
    notif = getattr(stats, "enabled_notifications", None)
    if notif is not None and getattr(notif, "total", 0):
        result["notifications_pct"] = round(100 * notif.part / notif.total, 1)

    top_posts = getattr(stats, "recent_posts_interactions", None) or []
    if top_posts:
        best = max(top_posts, key=lambda p: getattr(p, "views", 0) or 0)
        result["top_post_views"] = getattr(best, "views", None)
        result["top_post_forwards"] = getattr(best, "forwards", None)

    return result or None


async def build_stats_message(client, target_channel: str, storage) -> str:
    since_ts = _start_of_today_ts()

    try:
        channel_entity = await client.get_entity(target_channel)
    except Exception:
        logger.exception("channel_stats: не удалось получить канал %s", target_channel)
        return "Не получилось получить доступ к каналу — проверь, что аккаунт для чтения состоит в канале."

    subscriber_count = await _get_subscriber_count(client, channel_entity)
    await _refresh_today_views(client, channel_entity, storage, since_ts)

    post_rows = storage.get_post_stats_since(since_ts)
    views_today = sum(row["views"] for row in post_rows)
    reactions_today = sum(row["reactions"] for row in post_rows)
    posts_today = len(post_rows)

    joined_today, left_today = storage.count_member_events_since(since_ts)

    broadcast = await _try_broadcast_stats(client, channel_entity)

    lines = [
        "🖤 <b>Статистика канала за сегодня</b> 🩷",
        "",
        f"✮ Подписчиков всего: {subscriber_count if subscriber_count is not None else 'н/д'}",
        f"✮ Пришло сегодня: {joined_today}",
        f"✮ Ушло сегодня: {left_today}",
        f"✮ Постов сегодня: {posts_today}",
        f"✮ Просмотров у сегодняшних постов: {views_today}",
        f"✮ Реакций сегодня: {reactions_today}",
    ]

    if broadcast:
        lines.append("")
        lines.append("📊 <i>Официальная статистика Telegram:</i>")
        if "notifications_pct" in broadcast:
            lines.append(f"— Уведомления включены у {broadcast['notifications_pct']}% подписчиков")
        if "top_post_views" in broadcast:
            lines.append(
                f"— Лучший пост периода: {broadcast['top_post_views']} просмотров, "
                f"{broadcast.get('top_post_forwards', 0)} репостов"
            )
    else:
        lines.append("")
        lines.append(
            "📊 <i>Расширенная статистика Telegram пока недоступна</i> — "
            "открывается автоматически, когда у канала будет от ~500 подписчиков "
            "и он просуществует больше суток."
        )

    lines.append("")
    lines.append(
        "ℹ️ Показатели «заблокировали бота» и «активные/неактивные подписчики» "
        "Telegram не предоставляет ни одному боту в принципе — такие данные "
        "физически недоступны, это не ограничение бота."
    )

    return "\n".join(lines)
