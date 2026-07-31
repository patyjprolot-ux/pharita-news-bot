"""TikTok — БЕСПЛАТНО, но неофициально и наименее стабильно из всех источников.

⚠️ У TikTok нет бесплатного публичного API для чтения чужих аккаунтов.
Библиотека TikTokApi работает через Playwright (реальный headless-браузер)
и требует ms_token — токен, извлечённый из cookie реального браузера,
залогиненного на tiktok.com (см. README, раздел TikTok). Этот токен
периодически "протухает", и его нужно обновлять вручную.

Выключен по умолчанию (ENABLE_TIKTOK_SOURCE=false) именно поэтому —
включайте, только если готовы иногда обновлять ms_token руками.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 12


class TikTokSource(BaseSource):
    name = "tiktok"

    def __init__(self, ms_token: str, usernames: list[str]):
        self.ms_token = ms_token
        self.usernames = usernames

    async def fetch(self) -> list[NewsItem]:
        if not self.ms_token:
            logger.warning("TikTok source: TIKTOK_MS_TOKEN не задан, источник пропущен")
            return []

        try:
            from TikTokApi import TikTokApi
        except Exception:
            logger.warning("TikTok source: TikTokApi/Playwright не установлены, источник пропущен")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []

        try:
            async with TikTokApi() as api:
                await api.create_sessions(
                    ms_tokens=[self.ms_token], num_sessions=1, sleep_after=3
                )
                for username in self.usernames:
                    try:
                        user = api.user(username)
                        async for video in user.videos(count=10):
                            data = video.as_dict
                            create_time = datetime.fromtimestamp(
                                data.get("createTime", 0), tz=timezone.utc
                            )
                            if create_time < cutoff:
                                continue

                            cover = data.get("video", {}).get("cover") or data.get("video", {}).get(
                                "originCover"
                            )
                            play_url = data.get("video", {}).get("playAddr")
                            media_items = []
                            if play_url:
                                media_items.append(MediaItem(type=MediaType.VIDEO, url=play_url))
                            elif cover:
                                media_items.append(MediaItem(type=MediaType.PHOTO, url=cover))

                            desc = data.get("desc", "")
                            item = NewsItem(
                                source_name=f"TikTok: @{username}",
                                external_id=data.get("id", video.id),
                                title="",
                                description=desc,
                                source_url=f"https://www.tiktok.com/@{username}/video/{data.get('id', video.id)}",
                                published_at=create_time,
                                media=media_items,
                            )
                            item.category_tag = guess_category_tag(item)
                            results.append(item)
                    except Exception:
                        logger.exception("TikTok source: сбой для @%s", username)
        except Exception:
            logger.exception("TikTok source: общий сбой (частая ситуация для TikTokApi)")

        return results
