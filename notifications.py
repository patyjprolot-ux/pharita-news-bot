"""Уведомления админу в Telegram при сбоях источников.

Троттлинг: одна и та же проблема не шлётся чаще раза в час — иначе при
затяжном сбое (например, у Weverse) бот засыпал бы админа одинаковыми
сообщениями каждые 15 минут."""
from __future__ import annotations

import logging
import time

from config import CONFIG

logger = logging.getLogger(__name__)

NOTIFY_COOLDOWN_SECONDS = 3600
_last_notified: dict[str, float] = {}

# Особые, более "человечные" сообщения для конкретных источников
_FRIENDLY_MESSAGES = {
    "weverse": "🎀 Иди к Максу, WEVERSE не фурычит 😢",
}


def _friendly_message(source_name: str, error_summary: str) -> str:
    custom = _FRIENDLY_MESSAGES.get(source_name.lower())
    if custom:
        return custom
    return f"⚠️ Источник «{source_name}» упал: {error_summary}"


async def notify_source_error(bot, source_name: str, error: Exception) -> None:
    if not CONFIG.admin_chat_id or bot is None:
        return

    key = f"source:{source_name}"
    now = time.time()
    if now - _last_notified.get(key, 0) < NOTIFY_COOLDOWN_SECONDS:
        return
    _last_notified[key] = now

    error_summary = f"{type(error).__name__}: {error}"[:200]
    text = _friendly_message(source_name, error_summary)
    try:
        await bot.send_message(chat_id=CONFIG.admin_chat_id, text=text)
    except Exception:
        logger.exception("notify_source_error: не удалось отправить уведомление админу")
