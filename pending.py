"""Вспомогательные функции для очереди на публикацию (pending_items)."""
from __future__ import annotations

import json
import sqlite3

from sources.base import MediaItem, MediaType, NewsItem


def serialize_media(media_items: list[MediaItem]) -> list[dict]:
    return [
        {"type": m.type.value, "url": m.url, "local_path": m.local_path} for m in media_items
    ]


def _deserialize_media(media_json: str) -> list[MediaItem]:
    data = json.loads(media_json or "[]")
    return [
        MediaItem(type=MediaType(m["type"]), url=m.get("url"), local_path=m.get("local_path"))
        for m in data
    ]


class PendingPost:
    """Обёртка над строкой pending_items, совместимая по атрибутам с NewsItem
    настолько, насколько это нужно formatter.format_post и publisher.publish."""

    def __init__(self, row: sqlite3.Row):
        self.id: int = row["id"]
        self.source_name: str = row["source_name"]
        self.category_tag: str = row["category_tag"]
        self.title: str = row["title"] or ""
        self.description: str = row["description"] or ""
        self.source_url: str = row["source_url"] or ""
        self.media: list[MediaItem] = _deserialize_media(row["media_json"])
        self.status: str = row["status"]
        self.found_at: int = row["found_at"]
        self.item_published_at: int = row["item_published_at"]
        self.display_source: str = row["display_source"] or ""


def short_preview(item: NewsItem | PendingPost, max_len: int = 90) -> str:
    text = (item.title or item.description or "").strip().replace("\n", " ")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text or "(без текста)"
