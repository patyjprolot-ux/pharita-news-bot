"""Разовый вход в Telegram-аккаунт для чтения каналов-источников и
статистики канала. Запускать один раз, вручную, в обычном терминале:

    python login_telethon.py

Спросит номер телефона, затем код из Telegram (и пароль, если включена
двухфакторная аутентификация). После успешного входа:

- Локально (без TELETHON_SESSION_STRING в .env) создаётся файл сессии
  (TELETHON_SESSION_NAME), и `main.py` дальше просто его переиспользует.
- Для деплоя на хостинг без постоянного диска (Render и т.п.) скрипт
  дополнительно печатает "session string" — её нужно один раз скопировать
  в переменную окружения TELETHON_SESSION_STRING на хостинге, тогда сессия
  переживёт передеплой (файл на диске там не сохраняется).
"""
from __future__ import annotations

import asyncio

from telethon.sessions import StringSession

from telethon_client import get_client


async def main() -> None:
    client = get_client()
    await client.start()
    me = await client.get_me()
    print(f"Успешно вошли как: {me.first_name} (id={me.id})")

    session_string = StringSession.save(client.session)
    print("\nДля деплоя на Render (или другой хостинг без диска) скопируй это значение")
    print("в переменную окружения TELETHON_SESSION_STRING:\n")
    print(session_string)
    print(
        "\n⚠️ Это как пароль от аккаунта — никому не показывай и не публикуй, "
        "храни только в секретных переменных окружения хостинга."
    )

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
