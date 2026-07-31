"""X (Twitter) — БЕСПЛАТНО, но неофициально, через snscrape.

⚠️ Важно понимать ограничения (см. README):
X с 2023 года активно блокирует анонимный/гостевой доступ, которым
пользуется snscrape. Официальный бесплатный уровень X API вообще не даёт
читать чужие посты (только публикация от имени приложения). Поэтому этот
источник — "лучшее, что можно сделать бесплатно": он может периодически
переставать работать без каких-либо действий с нашей стороны (X меняет
защиту). Код написан так, чтобы сбой этого источника не ронял всего бота
и не мешал остальным источникам работать.

Если понадобится более надёжный вариант — единственный по-настоящему
стабильный путь это платный X API (Basic/Pro tier).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 6


class TwitterSource(BaseSource):
    name = "twitter"

    def __init__(self, search_queries: list[str]):
        self.search_queries = search_queries

    def _fetch_sync(self) -> list[NewsItem]:
        try:
            import snscrape.modules.twitter as sntwitter
        except Exception:
            logger.warning(
                "Twitter source: snscrape недоступен/сломан из-за изменений на стороне X. "
                "Источник пропущен на этот раз."
            )
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []

        for query in self.search_queries:
            try:
                scraper = sntwitter.TwitterSearchScraper(f"{query} since_time:{int(cutoff.timestamp())}")
                for i, tweet in enumerate(scraper.get_items()):
                    if i >= 30:
                        break
                    if tweet.date < cutoff:
                        continue

                    media_items = []
                    if tweet.media:
                        for m in tweet.media:
                            if hasattr(m, "fullUrl"):
                                media_items.append(MediaItem(type=MediaType.PHOTO, url=m.fullUrl))
                            elif hasattr(m, "variants"):
                                variants = [v for v in m.variants if getattr(v, "contentType", "") == "video/mp4"]
                                if variants:
                                    best = max(variants, key=lambda v: getattr(v, "bitrate", 0) or 0)
                                    media_items.append(MediaItem(type=MediaType.VIDEO, url=best.url))

                    item = NewsItem(
                        source_name=f"X (Twitter): @{tweet.user.username}",
                        external_id=str(tweet.id),
                        title="",
                        description=tweet.rawContent,
                        source_url=tweet.url,
                        published_at=tweet.date,
                        media=media_items,
                    )
                    item.category_tag = guess_category_tag(item)
                    results.append(item)
            except Exception:
                logger.exception("Twitter source: сбой при запросе '%s' (типично для snscrape/X)", query)

        return results

    async def fetch(self) -> list[NewsItem]:
        return await asyncio.to_thread(self._fetch_sync)
