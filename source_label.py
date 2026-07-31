"""Определение подписи источника для итогового поста.

Правила (по итоговой договорённости с заказчиком):
- Взято из Telegram-канала:
  - если пост содержит только медиа без текста — публикация откладывается
    (см. admin_bot: waiting_for_text), чтобы попробовать найти текст в
    другом источнике; если не найдётся — в конце публикуется просто как
    "Фото"/"Видео" без утверждения об источнике;
  - если в тексте самого Telegram-поста явно указан источник (Weverse,
    Twitter/X, Instagram, YouTube, TikTok) — используем этот источник;
  - если источник в посте не указан — по явному решению заказчика
    подписываем как "YouTube" (так и должно быть, это не баг).
- Взято напрямую из другого источника (YouTube/Twitter/Instagram/
  Weverse/TikTok/новости) — подписываем настоящей платформой.
"""
from __future__ import annotations

import re

_CITATION_PATTERNS = [
    (re.compile(r"weverse|위버스", re.IGNORECASE), "Weverse"),
    (re.compile(r"twitter|x\.com|твиттер", re.IGNORECASE), "Твиттер"),
    (re.compile(r"instagram|инстаграм", re.IGNORECASE), "Instagram"),
    (re.compile(r"youtube|youtu\.be|ютуб", re.IGNORECASE), "YouTube"),
    (re.compile(r"tiktok|тикток", re.IGNORECASE), "TikTok"),
]

TELEGRAM_PREFIX = "Telegram:"
DEFAULT_TELEGRAM_FALLBACK = "YouTube"

_SOURCE_PREFIX_MAP = [
    ("YouTube:", "YouTube"),
    ("X (Twitter):", "Твиттер"),
    ("Instagram:", "Instagram"),
    ("Weverse:", "Weverse"),
    ("TikTok:", "TikTok"),
    ("News:", "Новости"),
]


def _detect_cited_source(text: str) -> str | None:
    for pattern, label in _CITATION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def has_text(item) -> bool:
    return bool((item.title or "").strip() or (item.description or "").strip())


def needs_hold_for_text(item) -> bool:
    """True, если это Telegram-медиа без единого слова текста — такой пост
    нужно придержать и попробовать найти текст в другом источнике."""
    return item.source_name.startswith(TELEGRAM_PREFIX) and not has_text(item)


def needs_rewrite(item) -> bool:
    """Своими словами переписываем только то, что реально скопировано из
    чужого Telegram-поста (и там есть что переписывать)."""
    return item.source_name.startswith(TELEGRAM_PREFIX) and has_text(item)


def compute_display_source(item) -> str:
    if item.source_name.startswith(TELEGRAM_PREFIX):
        cited = _detect_cited_source(f"{item.title} {item.description}")
        return cited or DEFAULT_TELEGRAM_FALLBACK

    for prefix, label in _SOURCE_PREFIX_MAP:
        if item.source_name.startswith(prefix):
            return label

    return "Новости"


# Заголовок поста ("➣ <эмодзи> ┉ #<тег>") — вместо отдельной строки
# "Источник: ...". Тег определяется источником, кроме новостей про
# чарты/награды — там всегда "#statistics" независимо от источника.
_SOURCE_TAG_MAP = {
    "Weverse": ("📝", "weverse"),
    "Твиттер": ("🛎", "twitter"),
    "Instagram": ("📷", "instagram"),
    "YouTube": ("🎥", "youtube"),
    "TikTok": ("🎬", "tiktok"),
    "Новости": ("🛎", "news"),
    "Видео": ("📹", "video"),
    "Фото": ("📷", "photo"),
}
STATISTICS_TAG = ("📊", "statistics")
SNS_FALLBACK_TAG = ("🎀", "sns")  # на случай источника, которого нет в карте выше


def compute_post_tag(display_source: str, category_tag: str) -> str:
    if category_tag == "Award":
        emoji, tag = STATISTICS_TAG
    else:
        emoji, tag = _SOURCE_TAG_MAP.get(display_source, SNS_FALLBACK_TAG)
    return f"{emoji} ┉ #{tag}"
