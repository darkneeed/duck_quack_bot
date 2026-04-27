from __future__ import annotations

import json
import logging
from typing import Optional

from .models import get_db

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24


class S21CacheRepo:

    @staticmethod
    async def get(login: str) -> Optional[dict]:
        async with get_db() as db:
            async with db.execute(
                "SELECT data_json, updated_at FROM s21_cache WHERE login = ?",
                (login,),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["data_json"])
        except Exception:
            return None

    @staticmethod
    async def get_with_age(login: str) -> tuple[Optional[dict], Optional[str]]:
        async with get_db() as db:
            async with db.execute(
                "SELECT data_json, updated_at FROM s21_cache WHERE login = ?",
                (login,),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None, None
        try:
            return json.loads(row["data_json"]), row["updated_at"]
        except Exception:
            return None, None

    @staticmethod
    async def is_fresh(login: str, ttl_hours: int = _CACHE_TTL_HOURS) -> bool:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT 1 FROM s21_cache
                WHERE login = ?
                  AND updated_at >= datetime('now', ? || ' hours')
                """,
                (login, f"-{ttl_hours}"),
            ) as cur:
                return await cur.fetchone() is not None

    @staticmethod
    async def set(login: str, data: dict, updated_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO s21_cache (login, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(login) DO UPDATE SET
                    data_json  = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (login, json.dumps(data, ensure_ascii=False), updated_at),
            )
            await db.commit()

    @staticmethod
    async def delete(login: str) -> None:
        async with get_db() as db:
            await db.execute("DELETE FROM s21_cache WHERE login = ?", (login,))
            await db.commit()

    @staticmethod
    async def get_all_logins() -> list[str]:
        async with get_db() as db:
            async with db.execute("SELECT login FROM s21_cache") as cur:
                rows = await cur.fetchall()
        return [r["login"] for r in rows]

    @staticmethod
    async def count() -> int:
        async with get_db() as db:
            async with db.execute("SELECT COUNT(*) FROM s21_cache") as cur:
                row = await cur.fetchone()
                return row[0] if row else 0
