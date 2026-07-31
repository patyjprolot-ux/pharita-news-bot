"""Новые видео с YouTube-каналов через официальный бесплатный Data API v3.

Квота бесплатного ключа — 10 000 unit/день, этого более чем достаточно для
проверки одного-нескольких каналов раз в 15 минут (search.list стоит 100
unit за вызов, так что смотрим uploads-плейлист напрямую — это дешевле).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 6


class YouTubeSource(BaseSource):
    name = "youtube"

    def __init__(self, api_key: str, channel_ids: list[str]):
        self.api_key = api_key
        self.channel_ids = channel_ids

    def _uploads_playlist_id(self, youtube, channel_id: str) -> str | None:
        resp = youtube.channels().list(part="contentDetails", id=channel_id).execute()
        items = resp.get("items", [])
        if not items:
            return None
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def _fetch_sync(self) -> list[NewsItem]:
        youtube = build("youtube", "v3", developerKey=self.api_key)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []

        for channel_id in self.channel_ids:
            try:
                playlist_id = self._uploads_playlist_id(youtube, channel_id)
                if not playlist_id:
                    continue
                resp = youtube.playlistItems().list(
                    part="snippet", playlistId=playlist_id, maxResults=10
                ).execute()
                for entry in resp.get("items", []):
                    snippet = entry["snippet"]
                    published_at = datetime.fromisoformat(
                        snippet["publishedAt"].replace("Z", "+00:00")
                    )
                    if published_at < cutoff:
                        continue
                    video_id = snippet["resourceId"]["videoId"]
                    thumb = (
                        snippet.get("thumbnails", {}).get("high")
                        or snippet.get("thumbnails", {}).get("default")
                        or {}
                    ).get("url")

                    item = NewsItem(
                        source_name=f"YouTube: {snippet['channelTitle']}",
                        external_id=video_id,
                        title=snippet["title"],
                        description=(snippet.get("description") or "")[:600],
                        source_url=f"https://www.youtube.com/watch?v={video_id}",
                        published_at=published_at,
                        media=[MediaItem(type=MediaType.PHOTO, url=thumb)] if thumb else [],
                    )
                    item.category_tag = guess_category_tag(item)
                    results.append(item)
            except Exception:
                logger.exception("YouTube source: ошибка для канала %s", channel_id)

        return results

    async def fetch(self) -> list[NewsItem]:
        return await asyncio.to_thread(self._fetch_sync)
