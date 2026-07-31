"""Новостные сайты через RSS — без платных API.

Google News RSS — бесплатный полнотекстовый поиск по тысячам новостных
сайтов сразу (аналог "новостные сайты и другие открытые источники" из
задачи). Плюс можно добавить произвольные официальные RSS-ленты
(агентства, фан-сайты и т.п.) через NEWS_RSS_EXTRA_FEEDS.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 12
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl={lang}&gl=US&ceid=US:en"


class NewsRSSSource(BaseSource):
    name = "news_rss"

    def __init__(self, queries: list[str], extra_feeds: list[str], lang: str = "en-US"):
        self.queries = queries
        self.extra_feeds = extra_feeds
        self.lang = lang

    def _feed_urls(self) -> list[str]:
        urls = [
            GOOGLE_NEWS_RSS.format(query=quote(q), lang=self.lang) for q in self.queries
        ]
        urls.extend(self.extra_feeds)
        return urls

    async def _fetch_og_image(self, session: aiohttp.ClientSession, url: str) -> str | None:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(errors="ignore")
        except Exception:
            return None

        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        return tag["content"] if tag and tag.get("content") else None

    async def fetch(self) -> list[NewsItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []

        async with aiohttp.ClientSession() as session:
            for feed_url in self._feed_urls():
                try:
                    parsed = feedparser.parse(feed_url)
                except Exception:
                    logger.exception("News RSS: не удалось разобрать %s", feed_url)
                    continue

                for entry in parsed.entries[:15]:
                    published = entry.get("published_parsed")
                    if not published:
                        continue
                    published_at = datetime(*published[:6], tzinfo=timezone.utc)
                    if published_at < cutoff:
                        continue

                    link = entry.get("link", "")
                    title = entry.get("title", "").strip()
                    summary = BeautifulSoup(entry.get("summary", ""), "lxml").get_text().strip()
                    source_title = entry.get("source", {}).get("title", "") if entry.get("source") else ""

                    image_url = await self._fetch_og_image(session, link) if link else None

                    item = NewsItem(
                        source_name=f"News: {source_title or feed_url}",
                        external_id=entry.get("id", link) or f"{title}-{published_at.isoformat()}",
                        title=title,
                        description=summary[:600],
                        source_url=link,
                        published_at=published_at,
                        media=[MediaItem(type=MediaType.PHOTO, url=image_url)] if image_url else [],
                    )
                    item.category_tag = guess_category_tag(item)
                    results.append(item)

        return results
