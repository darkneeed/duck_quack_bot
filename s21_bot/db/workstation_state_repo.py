from __future__ import annotations

from typing import Optional
import aiosqlite
from .models import get_db


class WorkstationStateRepo:

    @staticmethod
    async def get(login: str) -> Optional[str]:
        async with get_db() as db:
            async with db.execute(
                "SELECT seat FROM workstation_state WHERE login = ?", (login,)
            ) as cur:
                row = await cur.fetchone()
        return row["seat"] if row else None

    @staticmethod
    async def set(login: str, seat: Optional[str], updated_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO workstation_state (login, seat, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(login) DO UPDATE SET
                    seat       = excluded.seat,
                    updated_at = excluded.updated_at
                """,
                (login, seat, updated_at),
            )
            await db.commit()

    @staticmethod
    async def delete(login: str) -> None:
        async with get_db() as db:
            await db.execute(
                "DELETE FROM workstation_state WHERE login = ?", (login,)
            )
            await db.commit()

    @staticmethod
    async def delete_old(days: int = 7) -> int:
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM workstation_state WHERE updated_at < datetime('now', ? || ' days')",
                (f"-{days}",),
            )
            await db.commit()
            return cur.rowcount

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM workstation_state") as cur:
                return await cur.fetchall()
