"""Загрузка конфигурации из .env в единый объект."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    val = os.getenv(name, "")
    return [x.strip() for x in val.split(",") if x.strip()]


@dataclass
class Config:
    # Telegram publisher
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    target_channel: str = os.getenv("TARGET_CHANNEL", "")

    # Telegram reader (Telethon)
    telegram_api_id: int = int(os.getenv("TELEGRAM_API_ID", "0") or 0)
    telegram_api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    telethon_session_name: str = os.getenv("TELETHON_SESSION_NAME", "pharita_bot_session")
    # Для деплоя без постоянного диска (напр. Render) — сессия строкой, см. login_telethon.py
    telethon_session_string: str = os.getenv("TELETHON_SESSION_STRING", "")
    source_tg_channels: list[str] = field(default_factory=lambda: _list("SOURCE_TG_CHANNELS"))

    # YouTube
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    youtube_channel_id: str = os.getenv("YOUTUBE_CHANNEL_ID", "")

    # Source toggles
    enable_telegram_source: bool = _bool("ENABLE_TELEGRAM_SOURCE", True)
    enable_youtube_source: bool = _bool("ENABLE_YOUTUBE_SOURCE", True)
    enable_news_rss_source: bool = _bool("ENABLE_NEWS_RSS_SOURCE", True)
    enable_twitter_source: bool = _bool("ENABLE_TWITTER_SOURCE", False)
    enable_instagram_source: bool = _bool("ENABLE_INSTAGRAM_SOURCE", False)
    enable_tiktok_source: bool = _bool("ENABLE_TIKTOK_SOURCE", False)
    enable_weverse_source: bool = _bool("ENABLE_WEVERSE_SOURCE", False)

    # Twitter
    twitter_search_queries: list[str] = field(default_factory=lambda: _list("TWITTER_SEARCH_QUERIES"))

    # Instagram
    instagram_login: str = os.getenv("INSTAGRAM_LOGIN", "")
    instagram_password: str = os.getenv("INSTAGRAM_PASSWORD", "")
    instagram_profiles: list[str] = field(default_factory=lambda: _list("INSTAGRAM_PROFILES"))
    instagram_mom_profile: str = os.getenv("INSTAGRAM_MOM_PROFILE", "")

    # TikTok
    tiktok_ms_token: str = os.getenv("TIKTOK_MS_TOKEN", "")
    tiktok_usernames: list[str] = field(default_factory=lambda: _list("TIKTOK_USERNAMES"))

    # Weverse
    weverse_email: str = os.getenv("WEVERSE_EMAIL", "")
    weverse_password: str = os.getenv("WEVERSE_PASSWORD", "")
    # Bearer-токен из браузера — обходит логин+пароль, если Weverse требует код с почты
    weverse_auth_token: str = os.getenv("WEVERSE_AUTH_TOKEN", "")
    weverse_community: str = os.getenv("WEVERSE_COMMUNITY", "BABYMONSTER")

    # News RSS (Google News агрегатор + произвольные RSS-ленты)
    news_rss_queries: list[str] = field(
        default_factory=lambda: _list("NEWS_RSS_QUERIES") or ["BABYMONSTER Pharita", "BABYMONSTER 파리타"]
    )
    news_rss_extra_feeds: list[str] = field(default_factory=lambda: _list("NEWS_RSS_EXTRA_FEEDS"))
    news_rss_lang: str = os.getenv("NEWS_RSS_LANG", "en-US")

    # Misc
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))
    db_path: str = os.getenv("DB_PATH", "data/seen_items.sqlite3")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Админ-бот: меню, ручная публикация, статистика
    admin_chat_id: int = int(os.getenv("ADMIN_CHAT_ID", "0") or 0)
    daily_post_min: int = int(os.getenv("DAILY_POST_MIN", "4"))
    daily_post_max: int = int(os.getenv("DAILY_POST_MAX", "10"))
    hourly_digest_seconds: int = int(os.getenv("HOURLY_DIGEST_SECONDS", "3600"))

    # Переписывание текста, взятого из Telegram-каналов (Google Gemini, бесплатный уровень)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # Медиа-посты из Telegram без подписи: сколько ждать текст из другого
    # источника, прежде чем публиковать просто как "Фото"/"Видео"
    telegram_hold_minutes: int = int(os.getenv("TELEGRAM_HOLD_MINUTES", "90"))
    telegram_hold_max_minutes: int = int(os.getenv("TELEGRAM_HOLD_MAX_MINUTES", "120"))


CONFIG = Config()
