"""Чтение постов из публичных Telegram-каналов о BABYMONSTER.

Работает через Telethon (user-аккаунт), т.к. обычный бот не может читать
историю произвольного публичного канала, не будучи туда добавленным
администратором. Telethon подключается как обычный пользователь Telegram
(нужны бесплатные api_id/api_hash с https://my.telegram.org/apps) и просто
читает публичные посты — это ничем не отличается от обычного чтения канала
человеком в приложении Telegram.

При первом запуске Telethon попросит авторизацию (номер телефона + код из
Telegram) прямо в консоли — это разовая операция, дальше используется
сохранённый файл сессии.
"""
from __future__ import annotations

import logging
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem
from storage import make_fingerprint

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 6  # окно, за которое проверяем новые посты при каждом опросе
TMP_FILE_MAX_AGE_HOURS = LOOKBACK_HOURS + 1  # старше — точно больше не нужен


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
        # storage используется, чтобы НЕ скачивать медиа повторно для постов,
        # которые уже видели на прошлых циклах опроса (без этого /tmp быстро
        # переполняется — один и тот же пост в окне LOOKBACK_HOURS иначе
        # перекачивается заново каждые 15 минут, пока не выйдет из окна)
        self.storage = storage
        self._tmp_dir = Path(tempfile.gettempdir()) / "pharita_bot_media"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup_old_files(self) -> None:
        cutoff = time.time() - TMP_FILE_MAX_AGE_HOURS * 3600
        try:
            for f in self._tmp_dir.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
        except Exception:
            logger.exception("Telegram source: не удалось почистить временные файлы")

    async def fetch(self) -> list[NewsItem]:
        self._cleanup_old_files()
        items: list[NewsItem] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        for channel in self.channels:
            try:
                items.extend(await self._fetch_channel(channel, cutoff))
            except Exception:
                logger.exception("Telegram source: ошибка чтения канала %s", channel)
        return items

    async def _fetch_channel(self, channel: str, cutoff: datetime) -> list[NewsItem]:
        results: list[NewsItem] = []
        entity = await self.client.get_entity(channel)

        async for message in self.client.iter_messages(entity, limit=30):
            if message.date < cutoff:
                break
            if not message.text and not message.media:
                continue

            text = message.text or ""
            title, _, rest = text.partition("\n")
            title = title.strip()[:200]
            description = (rest or text).strip()

            dedup_key = f"Telegram: {channel}:{message.id}"
            if self.storage is not None and self.storage.is_duplicate(
                dedup_key, make_fingerprint(title, description)
            ):
                continue  # уже публиковали/видели — не тратим трафик и диск на медиа

            media_items = []
            if message.photo or message.video:
                media_type = MediaType.VIDEO if message.video else MediaType.PHOTO
                path = await self.client.download_media(
                    message, file=str(self._tmp_dir / f"{channel}_{message.id}")
                )
                if path:
                    media_items.append(MediaItem(type=media_type, local_path=path))

            is_mom = channel.lower().lstrip("@") in self.mom_usernames

            item = NewsItem(
                source_name=f"Telegram: {channel}",
                external_id=str(message.id),
                title=title,
                description=description,
                source_url=f"https://t.me/{channel}/{message.id}",
                published_at=message.date,
                media=media_items,
                is_priority=is_mom,
            )
            item.category_tag = guess_category_tag(item)
            results.append(item)

        return results
