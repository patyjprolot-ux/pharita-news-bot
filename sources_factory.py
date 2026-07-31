"""Сборка списка активных источников по настройкам из .env."""
from __future__ import annotations

from config import CONFIG


def build_sources(telethon_client) -> list:
    sources = []

    if CONFIG.enable_telegram_source and CONFIG.source_tg_channels:
        from sources.telegram_source import TelegramChannelSource

        sources.append(
            TelegramChannelSource(client=telethon_client, channels=CONFIG.source_tg_channels)
        )

    if CONFIG.enable_youtube_source and CONFIG.youtube_api_key:
        from sources.youtube_source import YouTubeSource

        sources.append(
            YouTubeSource(
                api_key=CONFIG.youtube_api_key,
                channel_ids=[CONFIG.youtube_channel_id] if CONFIG.youtube_channel_id else [],
            )
        )

    if CONFIG.enable_news_rss_source:
        from sources.news_rss_source import NewsRSSSource

        sources.append(
            NewsRSSSource(
                queries=CONFIG.news_rss_queries,
                extra_feeds=CONFIG.news_rss_extra_feeds,
                lang=CONFIG.news_rss_lang,
            )
        )

    if CONFIG.enable_twitter_source and CONFIG.twitter_search_queries:
        from sources.twitter_source import TwitterSource

        sources.append(TwitterSource(search_queries=CONFIG.twitter_search_queries))

    if CONFIG.enable_instagram_source and (CONFIG.instagram_profiles or CONFIG.instagram_mom_profile):
        from sources.instagram_source import InstagramSource

        sources.append(
            InstagramSource(
                profiles=CONFIG.instagram_profiles,
                mom_profile=CONFIG.instagram_mom_profile,
                login=CONFIG.instagram_login,
                password=CONFIG.instagram_password,
            )
        )

    if CONFIG.enable_tiktok_source and CONFIG.tiktok_usernames:
        from sources.tiktok_source import TikTokSource

        sources.append(TikTokSource(ms_token=CONFIG.tiktok_ms_token, usernames=CONFIG.tiktok_usernames))

    if CONFIG.enable_weverse_source:
        from sources.weverse_source import WeverseSource

        sources.append(
            WeverseSource(
                email=CONFIG.weverse_email,
                password=CONFIG.weverse_password,
                community=CONFIG.weverse_community,
            )
        )

    return sources
