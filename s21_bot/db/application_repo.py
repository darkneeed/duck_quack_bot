from __future__ import annotations

from typing import Optional

import aiosqlite

from .models import get_db


class ApplicationRepo:
    @staticmethod
    async def create(tg_id, tg_name, school_login, user_comment, submitted_at, coalition=None) -> int:
        async with get_db() as db:
            cur = await db.execute(
                "INSERT INTO applications (tg_id, tg_name, school_login, user_comment, submitted_at, coalition) "
                "VALUES (?,?,?,?,?,?)",
                (tg_id, tg_name, school_login, user_comment, submitted_at, coalition),
            )
            await db.commit()
            return cur.lastrowid

    @staticmethod
    async def get(app_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM applications WHERE id=?", (app_id,)) as cur:
                return await cur.fetchone()

    @staticmethod
    async def set_status(app_id: int, status: str) -> None:
        async with get_db() as db:
            await db.execute("UPDATE applications SET status=? WHERE id=?", (status, app_id))
            await db.commit()

    @staticmethod
    async def get_pending_for_user(tg_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM applications WHERE tg_id=? AND status='pending'",
                (tg_id,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def set_moderation_msg_id(app_id: int, msg_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE applications SET moderation_msg_id=? WHERE id=?",
                (msg_id, app_id),
            )
            await db.commit()

    @staticmethod
    async def approve(app_id: int, moderator_id: int, moderator_name: str, decision_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE applications SET status='approved', moderator_id=?, moderator_name=?, decision_at=? WHERE id=?",
                (moderator_id, moderator_name, decision_at, app_id),
            )
            await db.commit()

    @staticmethod
    async def reject(app_id, moderator_id, moderator_name, decision_at, reject_reason) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE applications SET status='rejected', moderator_id=?, moderator_name=?, "
                "decision_at=?, reject_reason=? WHERE id=?",
                (moderator_id, moderator_name, decision_at, reject_reason, app_id),
            )
            await db.commit()

    @staticmethod
    async def try_claim_and_approve(app_id: int, moderator_id: int, moderator_name: str, decision_at: str) -> bool:
        async with get_db() as db:
            cur = await db.execute(
                "UPDATE applications SET status='approved', moderator_id=?, moderator_name=?, decision_at=? "
                "WHERE id=? AND status IN ('pending', 'waiting_votes')",
                (moderator_id, moderator_name, decision_at, app_id),
            )
            await db.commit()
            return cur.rowcount > 0

    @staticmethod
    async def try_claim_and_reject(app_id: int, moderator_id: int, moderator_name: str, decision_at: str, reject_reason: Optional[str]) -> bool:
        async with get_db() as db:
            cur = await db.execute(
                "UPDATE applications SET status='rejected', moderator_id=?, moderator_name=?, "
                "decision_at=?, reject_reason=? WHERE id=? AND status IN ('pending', 'waiting_votes')",
                (moderator_id, moderator_name, decision_at, reject_reason, app_id),
            )
            await db.commit()
            return cur.rowcount > 0

    @staticmethod
    async def get_all_for_export() -> tuple[list[str], list[aiosqlite.Row]]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM applications ORDER BY id") as cur:
                rows = await cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                return cols, rows
