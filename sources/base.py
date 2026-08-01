"""Общий интерфейс источников новостей."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"


@dataclass
class MediaItem:
    type: MediaType
    url: str | None = None        # прямая публичная ссылка (Telegram сам её скачает)
    local_path: str | None = None  # локальный файл, если ссылка недоступна публично

    def __post_init__(self) -> None:
        if not self.url and not self.local_path:
            raise ValueError("MediaItem требует url или local_path")


@dataclass
class NewsItem:
    source_name: str          # человекочитаемое имя источника, напр. "Telegram: bm_updates"
    external_id: str          # уникальный id внутри источника (id поста/видео/твита)
    title: str
    description: str
    source_url: str
    published_at: datetime
    media: list[MediaItem] = field(default_factory=list)
    category_tag: str = "News"  # для строки "➣ 📸 ┉ #<tag>"
    is_priority: bool = False   # напр. пост мамы Фариты — публикуется всегда

    # Заполняется только для Telegram-источника: если задано, публикация
    # идёт через нативную пересылку оригинального сообщения (без рерайта,
    # без своего оформления) вместо обычного форматированного поста.
    forward_chat: str | None = None
    forward_message_ids: list[int] = field(default_factory=list)

    @property
    def dedup_key(self) -> str:
        return f"{self.source_name}:{self.external_id}"


class BaseSource:
    """Базовый класс источника. fetch() должен вернуть список NewsItem."""

    name: str = "base"

    async def fetch(self) -> list[NewsItem]:
        raise NotImplementedError
