"""Публикация отформатированных постов в целевой Telegram-канал."""
from __future__ import annotations

import logging
from contextlib import ExitStack

from telegram import Bot, InputMediaPhoto, InputMediaVideo

from sources.base import MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # жёсткий лимит Telegram для подписи к медиа


def _media_payload(m: MediaItem, stack: ExitStack):
    """Возвращает то, что можно передать в send_photo/video/InputMedia*:
    открытый файловый объект для локальных файлов, либо прямую ссылку."""
    if m.local_path:
        f = stack.enter_context(open(m.local_path, "rb"))
        return f
    return m.url


class TelegramPublisher:
    def __init__(self, bot_token: str, target_channel: str):
        self.bot = Bot(token=bot_token)
        self.target_channel = target_channel

    async def publish(self, item: NewsItem, text: str) -> None:
        media = item.media[:10]  # Telegram допускает максимум 10 элементов в альбоме

        if not media:
            await self.bot.send_message(
                chat_id=self.target_channel, text=text, parse_mode=None
            )
            return

        caption = text if len(text) <= CAPTION_LIMIT else None
        overflow_text = text if caption is None else None

        with ExitStack() as stack:
            if len(media) == 1:
                m = media[0]
                payload = _media_payload(m, stack)
                if m.type == MediaType.VIDEO:
                    await self.bot.send_video(
                        chat_id=self.target_channel, video=payload, caption=caption
                    )
                else:
                    await self.bot.send_photo(
                        chat_id=self.target_channel, photo=payload, caption=caption
                    )
            else:
                group = []
                for i, m in enumerate(media):
                    cap = caption if i == 0 else None
                    payload = _media_payload(m, stack)
                    if m.type == MediaType.VIDEO:
                        group.append(InputMediaVideo(media=payload, caption=cap))
                    else:
                        group.append(InputMediaPhoto(media=payload, caption=cap))
                await self.bot.send_media_group(chat_id=self.target_channel, media=group)

        if overflow_text:
            # Подпись не влезла в лимит медиа — досылаем полный текст отдельным сообщением
            await self.bot.send_message(chat_id=self.target_channel, text=overflow_text)
