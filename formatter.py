"""Форматирование поста строго по шаблону, заданному пользователем:

➣ <эмодзи> ┉ #<источник>

• <Информация о новости>

#PHARITA #BABYMONSTER ✮ @world_pharita
─── ⋆⋅☆⋅⋆ ─

Заголовок строки ("➣ ...") показывает ИСТОЧНИК новости (не тему) —
например "🎥 ┉ #youtube" или "📝 ┉ #weverse". Отдельной строки
"Источник: ..." больше нет — она заменена этим заголовком (см.
source_label.compute_post_tag, где формируется item.display_source).
"""
from __future__ import annotations

from sources.base import NewsItem


def format_post(item: NewsItem, channel_handle: str) -> str:
    description = (item.description or "").strip()
    title = (item.title or "").strip()
    if title and title not in description:
        info_block = f"{title}\n{description}" if description else title
    else:
        info_block = description or title

    header_tag = getattr(item, "display_source", "") or f"📸 ┉ #{item.category_tag}"

    lines = [f"➣ {header_tag}", ""]
    if info_block:
        lines.append(f"• {info_block}")
        lines.append("")

    lines.extend([f"#PHARITA #BABYMONSTER ✮ {channel_handle}", "─── ⋆⋅☆⋅⋆ ─"])
    return "\n".join(lines)
