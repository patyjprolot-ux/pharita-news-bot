"""Равномерное распределение автопубликаций по суткам.

Вместо публикации всех доступных постов подряд в рамках одного цикла
опроса, на день заранее генерируется набор случайных "временных слотов"
(по числу — дневной лимит, 4-10). Автопубликация в fetch_cycle разрешена
только тогда, когда наступило время очередного слота — это даёт
равномерный разброс публикаций в течение суток, а не пачку сразу.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone


def _end_of_day(now: datetime) -> datetime:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start + timedelta(days=1)


def generate_slots(target: int, already_published: int, now: datetime) -> list[datetime]:
    """already_published слотов считаются уже "наступившими" (для случая,
    когда лимит на день создаётся не с полуночи, а посреди дня, в том
    числе при миграции уже частично отработанного дня на новую схему)."""
    already_published = min(already_published, target)
    past_slots = [now - timedelta(seconds=i + 1) for i in range(already_published)]

    remaining = target - already_published
    day_end = _end_of_day(now)
    window_seconds = max(int((day_end - now).total_seconds()), 1)
    future_slots = sorted(now + timedelta(seconds=random.uniform(0, window_seconds)) for _ in range(remaining))

    return sorted(past_slots + future_slots)


def serialize_slots(slots: list[datetime]) -> str:
    return json.dumps([s.isoformat() for s in slots])


def deserialize_slots(raw: str | None) -> list[datetime]:
    if not raw:
        return []
    return [datetime.fromisoformat(s) for s in json.loads(raw)]


def count_due(slots: list[datetime], now: datetime) -> int:
    return sum(1 for s in slots if s <= now)
