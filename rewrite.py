"""Переписывание текста, взятого из Telegram-каналов, своими словами —
через бесплатный уровень Google Gemini API. Требование задачи: нельзя
публиковать точную копию чужого поста, только пересказ в собственном стиле.

Если Gemini недоступен (нет ключа, кончилась бесплатная квота, сетевой
сбой) — используем исходный текст как есть, но громко предупреждаем в
логах: это осознанный компромисс (не блокировать публикацию совсем),
а не попытка выдать оригинал за рерайт.
"""
from __future__ import annotations

import logging

import aiohttp

from config import CONFIG

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)

PROMPT_TEMPLATE = (
    "Перепиши следующий текст новости о K-pop группе BABYMONSTER своими словами, "
    "сохранив все факты (даты, названия, цифры) без искажений. "
    "Пиши коротко (2-4 предложения), в нейтральном новостном стиле на русском языке, "
    "без хэштегов и без markdown-разметки. Не добавляй ничего от себя, только пересказ.\n\n"
    "Категория новости: {category}\n"
    "Исходный текст:\n{text}"
)


async def rewrite_text(original_text: str, category_tag: str) -> str:
    original_text = (original_text or "").strip()
    if not original_text:
        return original_text

    if not CONFIG.gemini_api_key:
        logger.warning("rewrite_text: GEMINI_API_KEY не задан — публикуем исходный текст без рерайта")
        return original_text

    url = GEMINI_URL.format(model=CONFIG.gemini_model, key=CONFIG.gemini_api_key)
    payload = {
        "contents": [
            {"parts": [{"text": PROMPT_TEMPLATE.format(category=category_tag, text=original_text)}]}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "rewrite_text: Gemini вернул статус %s (%s) — публикуем исходный текст",
                        resp.status,
                        body[:300],
                    )
                    return original_text
                data = await resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            logger.warning("rewrite_text: Gemini не вернул кандидатов — публикуем исходный текст")
            return original_text

        parts = candidates[0].get("content", {}).get("parts") or []
        rewritten = "".join(p.get("text", "") for p in parts).strip()
        return rewritten or original_text

    except Exception:
        logger.exception("rewrite_text: сбой запроса к Gemini — публикуем исходный текст")
        return original_text
