"""Weverse — БЕСПЛАТНО, но неофициально и наименее документировано.

У Weverse нет публичного бесплатного API. Библиотека `Weverse` на PyPI —
неофициальная обёртка. Важное ограничение: она умеет логиниться только
по логину+паролю и НЕ умеет проходить код подтверждения с почты, который
Weverse теперь запрашивает при новом входе. Поэтому есть два режима:

- WEVERSE_EMAIL/WEVERSE_PASSWORD — сработает только если Weverse не
  просит код с почты для этого аккаунта (не гарантировано).
- WEVERSE_AUTH_TOKEN — Bearer-токен, добытый вручную из браузера после
  обычного входа с кодом (см. README, раздел Weverse). Не протухает
  мгновенно, но и не обновляется автоматически — рано или поздно
  понадобится обновить вручную тем же способом.

⚠️ Выключен по умолчанию (ENABLE_WEVERSE_SOURCE=false). Включайте, только
если готовы иногда чинить интеграцию вручную при обновлениях библиотеки
или протухании токена — см. README.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 12


def _parse_created_at(value) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        # Weverse отдаёт created_at в миллисекундах с эпохи
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


class WeverseSource(BaseSource):
    name = "weverse"

    def __init__(self, email: str, password: str, auth_token: str, community: str):
        self.email = email
        self.password = password
        self.auth_token = auth_token
        self.community = community

    async def fetch(self) -> list[NewsItem]:
        if not self.auth_token and not (self.email and self.password):
            logger.warning("Weverse source: не заданы ни токен, ни логин/пароль — источник пропущен")
            return []

        try:
            from Weverse import WeverseClientAsync
        except Exception:
            logger.warning("Weverse source: библиотека Weverse не установлена, источник пропущен")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []
        client = None

        try:
            kwargs = {"verbose": False}
            if self.auth_token:
                kwargs["authorization"] = self.auth_token
            else:
                kwargs["username"] = self.email
                kwargs["password"] = self.password

            client = WeverseClientAsync(**kwargs)
            await client.start(create_old_posts=True, create_notifications=False, create_media=False)

            community = next(
                (c for c in client.all_communities.values() if (c.name or "").lower() == self.community.lower()),
                None,
            )
            if community is None:
                logger.warning(
                    "Weverse source: сообщество '%s' не найдено среди подписок аккаунта", self.community
                )
                return []

            for post in list(client.all_posts.values())[:30]:
                if post.community_tab_id is None:
                    continue
                post_date = _parse_created_at(post.created_at)
                if post_date < cutoff:
                    continue

                media_items = []
                for photo in post.photos or []:
                    url = photo.original_img_url or photo.thumbnail_img_url
                    if url:
                        media_items.append(MediaItem(type=MediaType.PHOTO, url=url))
                for video in post.videos or []:
                    if video.video_url:
                        media_items.append(MediaItem(type=MediaType.VIDEO, url=video.video_url))

                item = NewsItem(
                    source_name=f"Weverse: {community.name}",
                    external_id=str(post.id),
                    title="",
                    description=(post.body or "")[:600],
                    source_url="https://weverse.io",
                    published_at=post_date,
                    media=media_items,
                )
                item.category_tag = guess_category_tag(item)
                results.append(item)

        except Exception:
            logger.exception("Weverse source: общий сбой (нестабильный неофициальный API)")
        finally:
            if client is not None:
                try:
                    await client.stop()
                except Exception:
                    pass

        return results
