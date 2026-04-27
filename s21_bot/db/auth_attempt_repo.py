from __future__ import annotations

import aiosqlite

from .models import get_db


class AuthAttemptRepo:
    @staticmethod
    async def log(tg_id: int, tg_name: str, login: str, result: str, reason: str | None, attempted_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO auth_attempts (tg_id, tg_name, login, result, reason, attempted_at) VALUES (?,?,?,?,?,?)",
                (tg_id, tg_name, login, result, reason, attempted_at),
            )
            await db.commit()

    @staticmethod
    async def delete_by_tg_id(tg_id: int) -> None:
        async with get_db() as db:
            await db.execute("DELETE FROM auth_attempts WHERE tg_id=?", (tg_id,))
            await db.commit()

    @staticmethod
    async def get_recent_failed(tg_id: int, minutes: int = 60) -> list[aiosqlite.Row]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM auth_attempts WHERE tg_id=? AND result='failed' "
                "AND attempted_at >= datetime('now', ? || ' minutes') ORDER BY attempted_at DESC",
                (tg_id, f"-{minutes}"),
            ) as cur:
                return list(await cur.fetchall())

    @staticmethod
    async def get_recent_logins(tg_id: int, minutes: int = 30) -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT DISTINCT login FROM auth_attempts "
                "WHERE tg_id=? AND attempted_at > datetime('now', ? || ' minutes') "
                "ORDER BY attempted_at DESC",
                (tg_id, f"-{minutes}"),
            ) as cur:
                return await cur.fetchall()

    @staticmethod
    async def get_history(tg_id: int, limit: int = 20) -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM auth_attempts WHERE tg_id=? ORDER BY attempted_at DESC LIMIT ?",
                (tg_id, limit),
            ) as cur:
                return await cur.fetchall()
