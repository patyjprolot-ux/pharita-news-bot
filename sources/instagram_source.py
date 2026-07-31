"""Instagram — БЕСПЛАТНО, но неофициально, через instaloader.

⚠️ Ограничения (см. README):
- Instagram активно противодействует автоматическому чтению: без логина
  анонимные запросы быстро упираются в лимиты; с логином риск временной
  (реже — постоянной) блокировки аккаунта. Рекомендуется заводить
  ОТДЕЛЬНЫЙ "запасной" аккаунт для бота, не личный.
- Если INSTAGRAM_LOGIN не задан, источник работает в анонimном режиме
  (менее надёжно, может вообще не отвечать периодами).

Аккаунт мамы Фариты (INSTAGRAM_MOM_PROFILE) публикуется ВСЕГДА, вне
зависимости от ключевых слов — с явным указанием источника, как просил
пользователь.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from filters import guess_category_tag
from sources.base import BaseSource, MediaItem, MediaType, NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 12


class InstagramSource(BaseSource):
    name = "instagram"

    def __init__(
        self,
        profiles: list[str],
        mom_profile: str = "",
        login: str = "",
        password: str = "",
    ):
        self.profiles = profiles
        self.mom_profile = mom_profile.strip().lstrip("@")
        self.login = login
        self.password = password
        self._tmp_dir = Path(tempfile.gettempdir()) / "pharita_bot_instagram"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    def _fetch_sync(self) -> list[NewsItem]:
        try:
            import instaloader
        except Exception:
            logger.warning("Instagram source: instaloader не установлен, источник пропущен")
            return []

        loader = instaloader.Instaloader(
            download_comments=False,
            save_metadata=False,
            download_geotags=False,
            post_metadata_txt_pattern="",
            quiet=True,
        )
        if self.login and self.password:
            try:
                loader.login(self.login, self.password)
            except Exception:
                logger.exception("Instagram source: не удалось залогиниться, продолжаем анонимно")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        results: list[NewsItem] = []
        all_profiles = list(dict.fromkeys(self.profiles + ([self.mom_profile] if self.mom_profile else [])))

        for username in all_profiles:
            try:
                profile = instaloader.Profile.from_username(loader.context, username)
            except Exception:
                logger.exception("Instagram source: не удалось открыть профиль %s", username)
                continue

            is_mom = username == self.mom_profile
            try:
                for post in profile.get_posts():
                    post_date = post.date_utc.replace(tzinfo=timezone.utc)
                    if post_date < cutoff:
                        break
                    results.append(self._build_item(loader, post, username, is_mom))
            except Exception:
                logger.exception("Instagram source: сбой чтения постов %s", username)

        return results

    def _build_item(self, loader, post, username: str, is_mom: bool) -> NewsItem:
        post_dir = self._tmp_dir / f"{username}_{post.shortcode}"
        post_dir.mkdir(parents=True, exist_ok=True)
        media_items: list[MediaItem] = []

        try:
            loader.dirname_pattern = str(post_dir)
            loader.download_post(post, target=str(post_dir))
            for f in sorted(post_dir.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    media_items.append(MediaItem(type=MediaType.PHOTO, local_path=str(f)))
                elif f.suffix.lower() == ".mp4":
                    media_items.append(MediaItem(type=MediaType.VIDEO, local_path=str(f)))
        except Exception:
            logger.exception("Instagram source: не удалось скачать медиа поста %s", post.shortcode)
            shutil.rmtree(post_dir, ignore_errors=True)

        caption = (post.caption or "").strip()
        title, _, rest = caption.partition("\n")

        item = NewsItem(
            source_name=f"Instagram: @{username}",
            external_id=post.shortcode,
            title=title[:200],
            description=(rest or caption)[:600],
            source_url=f"https://www.instagram.com/p/{post.shortcode}/",
            published_at=post.date_utc.replace(tzinfo=timezone.utc),
            media=media_items,
            is_priority=is_mom,
        )
        item.category_tag = guess_category_tag(item)
        return item

    async def fetch(self) -> list[NewsItem]:
        return await asyncio.to_thread(self._fetch_sync)
