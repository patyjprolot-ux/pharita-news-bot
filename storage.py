"""SQLite-хранилище: дедупликация, очередь на публикацию, дневной лимит,
события подписчиков и статистика постов (просмотры/реакции).

Дедупликация работает в два уровня:
1. По точному ключу (source + external_id) — не публиковать один и тот же
   пост дважды, даже если бот перезапустится.
2. По текстовому "отпечатку" (нормализованный хэш заголовка+описания) —
   чтобы не публиковать одну и ту же новость, если её независимо
   продублировали несколько Telegram-каналов или источников.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import date as date_cls
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    dedup_key TEXT PRIMARY KEY,
    fingerprint TEXT,
    source TEXT,
    published_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fingerprint ON seen_items(fingerprint);

CREATE TABLE IF NOT EXISTS pending_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key TEXT,
    source_name TEXT,
    category_tag TEXT,
    title TEXT,
    description TEXT,
    source_url TEXT,
    item_published_at INTEGER,
    media_json TEXT,
    status TEXT DEFAULT 'pending',
    found_at INTEGER,
    channel_message_id TEXT,
    display_source TEXT,
    donor_used INTEGER DEFAULT 0,
    published_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_items(status);
CREATE INDEX IF NOT EXISTS idx_pending_found_at ON pending_items(found_at);

CREATE TABLE IF NOT EXISTS daily_state (
    date TEXT PRIMARY KEY,
    target_count INTEGER,
    published_count INTEGER DEFAULT 0,
    slot_times_json TEXT
);

CREATE TABLE IF NOT EXISTS member_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    user_id INTEGER,
    event_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_member_events_at ON member_events(event_at);

CREATE TABLE IF NOT EXISTS post_stats (
    message_id INTEGER PRIMARY KEY,
    posted_at INTEGER,
    views INTEGER DEFAULT 0,
    reactions INTEGER DEFAULT 0,
    updated_at INTEGER
);
"""

# Сколько дней хранить отпечатки для проверки повторов (потом можно чистить)
FINGERPRINT_TTL_DAYS = 30


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-z0-9а-яёa-zЀ-ӿ가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_fingerprint(title: str, description: str) -> str:
    normalized = _normalize(f"{title} {description}")[:400]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_MIGRATIONS = [
    "ALTER TABLE pending_items ADD COLUMN display_source TEXT",
    "ALTER TABLE pending_items ADD COLUMN donor_used INTEGER DEFAULT 0",
    "ALTER TABLE daily_state ADD COLUMN slot_times_json TEXT",
    "ALTER TABLE pending_items ADD COLUMN published_at INTEGER",
]


class Storage:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()
            for statement in _MIGRATIONS:
                try:
                    conn.execute(statement)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # колонка уже существует — база создана более новой версией схемы

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------------------------------------------------------------- dedup

    def is_duplicate(self, dedup_key: str, fingerprint: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT 1 FROM seen_items WHERE dedup_key = ? LIMIT 1", (dedup_key,)
            )
            if cur.fetchone():
                return True
            cutoff = int(time.time()) - FINGERPRINT_TTL_DAYS * 86400
            cur = conn.execute(
                "SELECT 1 FROM seen_items WHERE fingerprint = ? AND published_at >= ? LIMIT 1",
                (fingerprint, cutoff),
            )
            return cur.fetchone() is not None

    def mark_seen(self, dedup_key: str, fingerprint: str, source: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_items (dedup_key, fingerprint, source, published_at) "
                "VALUES (?, ?, ?, ?)",
                (dedup_key, fingerprint, source, int(time.time())),
            )
            conn.commit()

    def purge_old(self, days: int = 90) -> None:
        cutoff = int(time.time()) - days * 86400
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM seen_items WHERE published_at < ?", (cutoff,))
            conn.commit()

    # ------------------------------------------------------------- pending

    def add_pending(
        self,
        item,
        media_payload: list[dict],
        status: str = "pending",
        display_source: str | None = None,
    ) -> int:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "INSERT INTO pending_items "
                "(dedup_key, source_name, category_tag, title, description, source_url, "
                " item_published_at, media_json, status, found_at, display_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.dedup_key,
                    item.source_name,
                    item.category_tag,
                    item.title,
                    item.description,
                    item.source_url,
                    int(item.published_at.timestamp()),
                    json.dumps(media_payload),
                    status,
                    int(time.time()),
                    display_source,
                ),
            )
            conn.commit()
            return cur.lastrowid

    def get_pending(self, limit: int = 10) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT * FROM pending_items WHERE status = 'pending' "
                "ORDER BY found_at ASC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def get_pending_by_id(self, item_id: int) -> sqlite3.Row | None:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM pending_items WHERE id = ?", (item_id,))
            return cur.fetchone()

    def count_pending(self) -> int:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT COUNT(*) AS c FROM pending_items WHERE status = 'pending'")
            return cur.fetchone()["c"]

    def mark_pending_published(self, item_id: int, channel_message_id: str | None = None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE pending_items SET status = 'published', channel_message_id = ?, published_at = ? "
                "WHERE id = ?",
                (channel_message_id, int(time.time()), item_id),
            )
            conn.commit()

    def get_last_published(self) -> sqlite3.Row | None:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT * FROM pending_items WHERE status = 'published' "
                "ORDER BY published_at DESC LIMIT 1"
            )
            return cur.fetchone()

    def get_published_since(self, ts: int) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT * FROM pending_items WHERE status = 'published' AND published_at >= ?",
                (ts,),
            )
            return cur.fetchall()

    def get_items_found_since(self, ts: int) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT * FROM pending_items WHERE found_at >= ? ORDER BY found_at ASC", (ts,)
            )
            return cur.fetchall()

    # ------------------------------------------- Telegram media без текста

    def get_waiting_for_text(self) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT * FROM pending_items WHERE status = 'waiting_for_text' ORDER BY found_at ASC"
            )
            return cur.fetchall()

    def find_donor_candidate(self, around_ts: int, window_seconds: int, exclude_id: int) -> sqlite3.Row | None:
        """Ищет ближайший по времени пост НЕ из Telegram, ещё не использованный
        как донор текста для другого медиа-поста."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT * FROM pending_items "
                "WHERE id != ? AND donor_used = 0 AND status IN ('pending', 'published') "
                "AND source_name NOT LIKE 'Telegram:%' "
                "AND ABS(item_published_at - ?) <= ? "
                "AND TRIM(COALESCE(title, '') || COALESCE(description, '')) != '' "
                "ORDER BY ABS(item_published_at - ?) ASC LIMIT 1",
                (exclude_id, around_ts, window_seconds, around_ts),
            )
            return cur.fetchone()

    def mark_donor_used(self, item_id: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute("UPDATE pending_items SET donor_used = 1 WHERE id = ?", (item_id,))
            conn.commit()

    def resolve_waiting_item(
        self, item_id: int, title: str | None, description: str | None, display_source: str
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE pending_items SET title = ?, description = ?, display_source = ?, "
                "status = 'pending' WHERE id = ?",
                (title, description, display_source, item_id),
            )
            conn.commit()

    # --------------------------------------------------------- daily state

    def get_daily_state(self, day: date_cls) -> sqlite3.Row | None:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM daily_state WHERE date = ?", (day.isoformat(),))
            return cur.fetchone()

    def set_daily_target(self, day: date_cls, target: int, slot_times_json: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO daily_state (date, target_count, published_count, slot_times_json) "
                "VALUES (?, ?, 0, ?)",
                (day.isoformat(), target, slot_times_json),
            )
            conn.commit()

    def set_daily_slots(self, day: date_cls, slot_times_json: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE daily_state SET slot_times_json = ? WHERE date = ?",
                (slot_times_json, day.isoformat()),
            )
            conn.commit()

    def increment_daily_published(self, day: date_cls) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE daily_state SET published_count = published_count + 1 WHERE date = ?",
                (day.isoformat(),),
            )
            conn.commit()

    # ------------------------------------------------------------ members

    def record_member_event(self, user_id: int, event_type: str, ts: int | None = None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO member_events (event_type, user_id, event_at) VALUES (?, ?, ?)",
                (event_type, user_id, ts or int(time.time())),
            )
            conn.commit()

    def count_member_events_since(self, ts: int) -> tuple[int, int]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT event_type, COUNT(*) AS c FROM member_events "
                "WHERE event_at >= ? GROUP BY event_type",
                (ts,),
            )
            joined = left = 0
            for row in cur.fetchall():
                if row["event_type"] == "joined":
                    joined = row["c"]
                elif row["event_type"] == "left":
                    left = row["c"]
            return joined, left

    # -------------------------------------------------------- post stats

    def upsert_post_views(self, message_id: int, posted_at: int, views: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO post_stats (message_id, posted_at, views, reactions, updated_at) "
                "VALUES (?, ?, ?, 0, ?) "
                "ON CONFLICT(message_id) DO UPDATE SET views = excluded.views, updated_at = excluded.updated_at",
                (message_id, posted_at, views, int(time.time())),
            )
            conn.commit()

    def set_post_reactions(self, message_id: int, posted_at: int, reactions: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO post_stats (message_id, posted_at, views, reactions, updated_at) "
                "VALUES (?, ?, 0, ?, ?) "
                "ON CONFLICT(message_id) DO UPDATE SET reactions = excluded.reactions, updated_at = excluded.updated_at",
                (message_id, posted_at, reactions, int(time.time())),
            )
            conn.commit()

    def get_post_stats_since(self, ts: int) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM post_stats WHERE posted_at >= ?", (ts,))
            return cur.fetchall()
