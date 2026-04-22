from __future__ import annotations
from typing import Optional
import aiosqlite
from .models import get_db


class GuestInviteRepo:

    @staticmethod
    async def create(
        tg_id: int,
        school_login: str,
        home_campus: str,
        invite_link: str,
        created_by: int,
        created_at: str,
    ) -> int:
        async with get_db() as db:
            cur = await db.execute(
                """
                INSERT INTO guest_invites
                    (tg_id, school_login, home_campus, invite_link, created_by, created_at, used)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (tg_id, school_login, home_campus, invite_link, created_by, created_at),
            )
            await db.commit()
            return cur.lastrowid

    @staticmethod
    async def get_by_tg_id(tg_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM guest_invites WHERE tg_id = ? ORDER BY id DESC LIMIT 1",
                (tg_id,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_invite_link(invite_link: str) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM guest_invites WHERE invite_link = ?",
                (invite_link,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def mark_used(invite_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE guest_invites SET used = 1 WHERE id = ?",
                (invite_id,),
            )
            await db.commit()

    @staticmethod
    async def get_pending_for_tg_id(tg_id: int) -> Optional[aiosqlite.Row]:
        """Get unused invite for this tg_id."""
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM guest_invites WHERE tg_id = ? AND used = 0 ORDER BY id DESC LIMIT 1",
                (tg_id,),
            ) as cur:
                return await cur.fetchone()
