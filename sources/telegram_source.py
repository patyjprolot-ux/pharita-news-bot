"""Чтение постов из публичных Telegram-каналов о BABYMONSTER.

Работает через Telethon (user-аккаунт), т.к. обычный бот не может читать
историю произвольного публичного канала, не будучи туда добавленным
администратором. Telethon подключается как обычный пользователь Telegram
(нужны бесплатные api_id/api_hash с https://my.telegram.org/apps) и просто
читает публичные посты — это ничем не отличается от обычного чтения канала
человеком в приложении Telegram.

Публикация постов из Telegram-каналов идёт через НАТИВНУЮ ПЕРЕСЫЛКУ
(Telegram forward), а не пересказ своими словами — по явному требованию:
сохранить оригинальный текст, фото/видео и оформление один в один. Поэтому
здесь НЕ скачиваются никакие файлы — просто запоминаются id сообщений,
пересылкой занимается telegram_publisher.py в момент публикации.

При первом запуске Telethon попросит авторизацию (номер телефона + код из
Telegram) прямо в консоли — это разовая операция, дальше используется
сохранённый файл сессии.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from filters import guess_category_tag
from sources.base import BaseSource, NewsItem
from storage import make_fingerprint

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 6  # окно, за которое проверяем новые посты при каждом опросе


class TelegramChannelSource(BaseSource):
    """Использует общий Telethon-клиент (telethon_client.client) — он должен
    быть уже подключён и авторизован до вызова fetch()."""

    name = "telegram"

    def __init__(
        self,
        client,
        channels: list[str],
        mom_usernames: set[str] | None = None,
        storage=None,
    ):
        self.client = client
        self.channels = channels
        self.mom_usernames = {u.lower().lstrip("@") for u in (mom_usernames or set())}
        # storage используется, чтобы не пересматривать посты, которые уже
        # видели на прошлых циклах опроса (не тратим время на дубликаты)
        self.storage = storage

    async def fetch(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        for channel in self.channels:
            try:
                items.extend(await self._fetch_channel(channel, cutoff))
            except Exception:
                logger.exception("Telegram source: ошибка чтения канала %s", channel)
        return items

    @staticmethod
    def _group_messages(messages: list) -> list[list]:
        """Собирает фото-альбомы (несколько сообщений с одним grouped_id) в
        один "пост" — иначе каждое фото альбома трактуется как отдельная
        новость и при пересылке уходит только одно фото вместо всех."""
        groups: dict[int, list] = {}
        standalone: list[list] = []
        for m in messages:
            if m.grouped_id:
                groups.setdefault(m.grouped_id, []).append(m)
            else:
                standalone.append([m])
        all_groups = list(groups.values()) + standalone
        for g in all_groups:
            g.sort(key=lambda m: m.id)
        return all_groups

    async def _fetch_channel(self, channel: str, cutoff: datetime) -> list[NewsItem]:
        results: list[NewsItem] = []
        entity = await self.client.get_entity(channel)

        raw_messages = []
        async for message in self.client.iter_messages(entity, limit=40):
            if message.date < cutoff:
                break
            if not message.text and not message.media:
                continue
            raw_messages.append(message)

        for group in self._group_messages(raw_messages):
            if not any(m.photo or m.video for m in group):
                continue  # без фото/видео не публикуем (общее правило для всех источников)

            text = next((m.text for m in group if m.text), "") or ""
            title, _, rest = text.partition("\n")
            title = title.strip()[:200]
            description = (rest or text).strip()

            first_id = group[0].id
            dedup_key = f"Telegram: {channel}:{first_id}"
            if self.storage is not None and self.storage.is_duplicate(
                dedup_key, make_fingerprint(title, description)
            ):
                continue  # уже видели — не обрабатываем повторно

            is_mom = channel.lower().lstrip("@") in self.mom_usernames

            item = NewsItem(
                source_name=f"Telegram: {channel}",
                external_id=str(first_id),
                title=title,
                description=description,
                source_url=f"https://t.me/{channel}/{first_id}",
                published_at=group[0].date,
                is_priority=is_mom,
                forward_chat=f"@{channel}",
                forward_message_ids=[m.id for m in group],
            )
            item.category_tag = guess_category_tag(item)
            results.append(item)

        return results
