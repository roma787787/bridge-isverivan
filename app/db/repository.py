from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS query_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    matched INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_log_created_at ON query_log(created_at);
"""


@dataclass(frozen=True)
class Stats:
    total_users: int
    queries_today: int
    queries_month: int
    top_today: list[tuple[str, int]]
    top_month: list[tuple[str, int]]


def _day_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


class Storage:
    """SQLite-backed storage for user profiles and query logs/stats."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._path != ":memory:":
            parent = os.path.dirname(self._path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def touch_user(self, user_id: int, username: str | None) -> None:
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO users (user_id, username, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                last_seen = excluded.last_seen
            """,
            (user_id, username, now, now),
        )
        await self._db.commit()

    async def log_query(self, user_id: int, ticker: str, matched: bool) -> None:
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO query_log (user_id, ticker, matched, created_at) VALUES (?, ?, ?, ?)",
            (user_id, ticker, int(matched), now),
        )
        await self._db.commit()

    async def get_stats(self) -> Stats:
        assert self._db is not None
        day_start = _day_start_iso()
        month_start = _month_start_iso()

        cursor = await self._db.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0]

        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM query_log WHERE created_at >= ?", (day_start,)
        )
        queries_today = (await cursor.fetchone())[0]

        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM query_log WHERE created_at >= ?", (month_start,)
        )
        queries_month = (await cursor.fetchone())[0]

        cursor = await self._db.execute(
            """
            SELECT ticker, COUNT(*) AS c FROM query_log
            WHERE created_at >= ?
            GROUP BY ticker ORDER BY c DESC LIMIT 5
            """,
            (day_start,),
        )
        top_today = [tuple(row) for row in await cursor.fetchall()]

        cursor = await self._db.execute(
            """
            SELECT ticker, COUNT(*) AS c FROM query_log
            WHERE created_at >= ?
            GROUP BY ticker ORDER BY c DESC LIMIT 5
            """,
            (month_start,),
        )
        top_month = [tuple(row) for row in await cursor.fetchall()]

        return Stats(
            total_users=total_users,
            queries_today=queries_today,
            queries_month=queries_month,
            top_today=top_today,
            top_month=top_month,
        )
