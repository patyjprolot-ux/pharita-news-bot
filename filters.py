"""Фильтрация «важности» новости по ключевым словам (без платных LLM).

Логика:
- PHARITA_KEYWORDS — если ни одного из этих слов нет в тексте, новость
  почти наверняка не о Фарите/BABYMONSTER вообще -> отбрасываем.
- TOPIC_KEYWORDS — концерты, туры, интервью, реклама и т.д. Если хотя бы
  одно совпадение — считаем новость важной.
- NOISE_KEYWORDS — маркеры "шума", который часто заливает каналы
  (репосты мемов, фан-арт, голосования, магазин мерча и т.п.) — снижают
  приоритет, если нет явного совпадения по TOPIC_KEYWORDS.
- Посты с аккаунта мамы Фариты (whitelisted username) — публикуются
  ВСЕГДА, независимо от ключевых слов (is_priority=True).
"""
from __future__ import annotations

import re

from sources.base import NewsItem

PHARITA_KEYWORDS = [
    "pharita", "파리타", "farita", "фарита",
]

GROUP_KEYWORDS = [
    "babymonster", "베이비몬스터", "бейбимонстр", "baby monster",
]

TOPIC_KEYWORDS = [
    # концерты / туры / фестивали
    "concert", "concerts", "tour", "world tour", "festival", "fan meeting",
    "fanmeeting", "fan-con", "showcase", "live", "stage", "encore",
    "концерт", "тур", "фестиваль", "фанмитинг", "выступление",
    # мероприятия / релизы
    "comeback", "mv", "music video", "album", "single", "release", "teaser",
    "камбэк", "клип", "альбом", "сингл", "релиз", "тизер",
    # интервью / реклама
    "interview", "interview", "campaign", "brand", "ambassador", "cf",
    "commercial", "magazine", "pictorial", "endorsement",
    "интервью", "кампания", "реклама", "амбассадор", "бренд",
    # награды / чарты
    "award", "awards", "chart", "billboard", "win", "победа", "награда", "чарт",
]

NOISE_KEYWORDS = [
    "fan art", "fanart", "edit", "edits", "meme", "memes", "giveaway",
    "poll", "vote now", "quiz", "merch shop", "reprint",
]


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def is_important(item: NewsItem, priority_authors: set[str] | None = None) -> bool:
    """Возвращает True, если новость стоит публиковать."""
    if item.is_priority:
        return True

    text = f"{item.title} {item.description}"

    mentions_group_or_star = _contains_any(text, PHARITA_KEYWORDS) or _contains_any(
        text, GROUP_KEYWORDS
    )
    if not mentions_group_or_star:
        return False

    # Прямое упоминание Фариты почти всегда важно, если ещё и есть медиа
    mentions_pharita = _contains_any(text, PHARITA_KEYWORDS)
    mentions_topic = _contains_any(text, TOPIC_KEYWORDS)
    is_noisy = _contains_any(text, NOISE_KEYWORDS) and not mentions_topic

    if is_noisy:
        return False

    return mentions_pharita or mentions_topic


def guess_category_tag(item: NewsItem) -> str:
    text = f"{item.title} {item.description}".lower()
    mapping = [
        (["concert", "tour", "fanmeeting", "fan-con", "showcase", "концерт", "тур"], "Concert"),
        (["interview", "интервью"], "Interview"),
        (["comeback", "mv", "album", "single", "teaser", "камбэк", "клип"], "Comeback"),
        (["campaign", "brand", "ambassador", "cf", "commercial", "реклама", "бренд"], "Campaign"),
        (["award", "chart", "billboard", "награда", "чарт"], "Award"),
    ]
    for keys, tag in mapping:
        if any(k in text for k in keys):
            return tag
    return "News"
