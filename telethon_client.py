"""Единственный на весь процесс экземпляр Telethon-клиента.

Используется и для чтения каналов-источников, и для получения статистики
канала — два отдельных TelegramClient с одним и тем же файлом сессии
будут конфликтовать (Telethon хранит сессию в sqlite и не рассчитан на
одновременное подключение из разных объектов), поэтому клиент здесь один,
подключается один раз при старте бота и переиспользуется везде.

Клиент создаётся лениво (при первом вызове get_client()), а не при
импорте модуля — TelegramClient требует существующий event loop на
момент создания, а на момент импорта модуля loop ещё может не быть запущен.

Хранение сессии — два варианта:
- Локально: обычный файл сессии (TELETHON_SESSION_NAME).
- На Render (и любом хостинге без постоянного диска): файл на диске
  пропадает при каждом передеплое/рестарте, поэтому сессия хранится в
  переменной окружения TELETHON_SESSION_STRING (StringSession) — она
  сохраняется как часть конфигурации сервиса, а не файловой системы.
"""
from __future__ import annotations

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import CONFIG

_client: TelegramClient | None = None


def _make_session():
    if CONFIG.telethon_session_string:
        return StringSession(CONFIG.telethon_session_string)
    return CONFIG.telethon_session_name


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(_make_session(), CONFIG.telegram_api_id, CONFIG.telegram_api_hash)
    return _client


async def ensure_connected() -> bool:
    """Подключается, если ещё не подключён. Возвращает True, если авторизован."""
    client = get_client()
    if not client.is_connected():
        await client.connect()
    return await client.is_user_authorized()


async def forward(from_chat: str, message_ids: list[int], target_chat: str) -> None:
    """Пересылка через сам Telethon-аккаунт, а не через бота.

    Bot API не может пересылать сообщения из канала, в котором бот не
    состоит участником (даже если канал публичный) — а наш бот не состоит
    в чужих Telegram-каналах вроде world_babymonster. Обычный пользователь
    (наш Telethon-аккаунт) может читать любой публичный канал без вступления
    и пересылать оттуда, но для публикации в целевой канал ему самому
    нужны права администратора там же, где и у бота."""
    client = get_client()
    await client.forward_messages(target_chat, message_ids, from_chat)
