from __future__ import annotations

from typing import Optional
import aiosqlite
from .models import get_db


class ModeratorRepo:

    @staticmethod
    async def add(tg_id: int, tg_name: str, added_by: int, added_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO moderators (tg_id, tg_name, added_by, added_at) "
                "VALUES (?, ?, ?, ?)",
                (tg_id, tg_name, added_by, added_at),
            )
            await db.commit()

    @staticmethod
    async def remove(tg_id: int) -> bool:
        """Returns True if a row was deleted."""
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM moderators WHERE tg_id = ?", (tg_id,)
            )
            await db.commit()
            return cur.rowcount > 0

    @staticmethod
    async def is_moderator(tg_id: int) -> bool:
        async with get_db() as db:
            async with db.execute(
                "SELECT 1 FROM moderators WHERE tg_id = ?", (tg_id,)
            ) as cur:
                return await cur.fetchone() is not None

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM moderators ORDER BY added_at DESC"
            ) as cur:
                return await cur.fetchall()

    @staticmethod
    async def get(tg_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM moderators WHERE tg_id = ?", (tg_id,)
            ) as cur:
                return await cur.fetchone()
