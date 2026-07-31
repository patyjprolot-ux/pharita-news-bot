"""Weverse — БЕСПЛАТНО, но неофициально и наименее документировано.

У Weverse нет публичного бесплатного API. Библиотека `Weverse` на PyPI —
неофициальная обёртка, требующая логин фан-аккаунта (email/пароль) и
периодически ломающаяся при изменениях на стороне Weverse. Отсюда:

⚠️ Выключен по умолчанию (ENABLE_WEVERSE_SOURCE=false). Включайте, только
если готовы использовать отдельный фан-аккаунт (не личный) и иногда
чинить интеграцию вручную при обновлениях библиотеки — см. README.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 12


class WeverseSource(BaseSource):
    name = "weverse"

    def __init__(self, email: str, password: str, community: str):
        self.email = email
        self.password = password
        self.community = community

    async def fetch(self) -> list[NewsItem]:
        if not self.email or not self.password:
            logger.warning("Weverse source: логин/пароль не заданы, источник пропущен")
            return []

        try:
            from Weverse import WeverseClientAsync
        except Exception:
            logger.warning("Weverse source: библиотека Weverse не установлена, источник пропущен")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []

        try:
            client = WeverseClientAsync(email=self.email, password=self.password)
            await client.start()

            community = next(
                (c for c in client.communities if c.name.lower() == self.community.lower()),
                None,
            )
            if community is None:
                logger.warning("Weverse source: сообщество '%s' не найдено среди подписок аккаунта", self.community)
                return []

            for post in getattr(community, "posts", [])[:15]:
                post_date = getattr(post, "time", None)
                if not post_date:
                    continue
                if post_date.tzinfo is None:
                    post_date = post_date.replace(tzinfo=timezone.utc)
                if post_date < cutoff:
                    continue

                media_items = []
                for photo in getattr(post, "photos", []) or []:
                    url = getattr(photo, "original_img_url", None) or getattr(photo, "url", None)
                    if url:
                        media_items.append(MediaItem(type=MediaType.PHOTO, url=url))
                video_url = getattr(post, "video_url", None)
                if video_url:
                    media_items.append(MediaItem(type=MediaType.VIDEO, url=video_url))

                body = getattr(post, "body", "") or ""
                item = NewsItem(
                    source_name=f"Weverse: {self.community}",
                    external_id=str(getattr(post, "post_id", post_date.isoformat())),
                    title=(getattr(post, "author", "") or "")[:200],
                    description=body[:600],
                    source_url=getattr(post, "share_url", "") or "https://weverse.io",
                    published_at=post_date,
                    media=media_items,
                )
                item.category_tag = guess_category_tag(item)
                results.append(item)

            await client.close()
        except Exception:
            logger.exception("Weverse source: общий сбой (нестабильный неофициальный API)")

        return results
