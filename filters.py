"""Фильтрация «важности» новости по ключевым словам (без платных LLM).

Логика (строгая, по требованию: публикуем только то, что реально о PHARITA):
- PHARITA_KEYWORDS — обязательное условие. Если ни одного из этих слов нет
  в тексте, новость НЕ публикуется — даже если это новость о BABYMONSTER
  в целом (концерт, чарт и т.п.), но без явного упоминания Фариты.
- TOPIC_KEYWORDS используется только для тега категории (Concert/Interview/
  ...), не как отдельная причина публикации.
- NOISE_KEYWORDS — маркеры "шума" (фан-арт, голосования, мерч) — такие
  посты отбрасываются, даже если Фарита упомянута мельком.
- Посты с аккаунта мамы Фариты (whitelisted username) — публикуются
  ВСЕГДА, независимо от ключевых слов (is_priority=True).

Ограничение (честно, не баг): если пост описывает событие словами вроде
"все участницы"/"группа" без явного имени "Фарита" — фильтр его не
пропустит, даже если Фарита там тоже участвует. Различить это без ручного
просмотра фото/видео (которого у бота нет) невозможно.
"""
from __future__ import annotations

import re

from sources.base import NewsItem

PHARITA_KEYWORDS = [
    "pharita", "파리타", "farita", "фарита",
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
    """Возвращает True, если новость стоит публиковать.

    Строго: без явного упоминания Фариты в тексте — не публикуем, даже если
    это новость о BABYMONSTER в целом. Единственное исключение — is_priority
    (пост с аккаунта мамы Фариты), он всегда проходит."""
    if item.is_priority:
        return True

    text = f"{item.title} {item.description}"

    if not _contains_any(text, PHARITA_KEYWORDS):
        return False

    if _contains_any(text, NOISE_KEYWORDS) and not _contains_any(text, TOPIC_KEYWORDS):
        return False

    return True


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
