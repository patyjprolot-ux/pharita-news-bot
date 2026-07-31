"""Точка входа.

Запускает интерактивного Telegram-бота (меню/кнопки — см. admin_bot.py)
и фоновые задачи через встроенный JobQueue:
- периодический опрос источников + автопубликация со случайным дневным
  лимитом (по умолчанию 4-10 постов в сутки);
- часовая сводка найденного администратору.

Ошибка в одном источнике не роняет остальные и не роняет процесс —
она логируется, и цикл продолжается (см. admin_bot.gather_all).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update

from admin_bot import build_application
from config import CONFIG

logging.basicConfig(
    level=CONFIG.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pharita_bot")


class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PHARITA bot is running")

    def log_message(self, format, *args):
        pass  # не засоряем логи health-check запросами


def start_health_server() -> None:
    """HTTP-сервер для Render: бесплатный тариф там есть только для типа
    Web Service, который обязан слушать HTTP и получать запросы — иначе
    Render усыпляет сервис примерно через 15 минут простоя. Сам по себе
    сервер не мешает засыпанию — нужен внешний пинг раз в 10 минут
    (см. README, раздел деплоя на Render)."""
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Health-check сервер слушает 0.0.0.0:%s", port)


def main() -> None:
    # Python 3.14 больше не создаёт event loop неявно — PTB 21.4 всё ещё
    # рассчитывает на старое поведение asyncio.get_event_loop(), поэтому
    # создаём и выставляем loop заранее.
    asyncio.set_event_loop(asyncio.new_event_loop())

    if os.environ.get("PORT"):
        # PORT задаёт сам Render — локально просто не запускаем лишний сервер
        start_health_server()

    application = build_application()
    logger.info("Бот запущен, ждём обновления...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
