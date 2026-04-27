from __future__ import annotations
from typing import Optional
import aiosqlite
from .models import get_db


class InviteCodeRepo:
    @staticmethod
    async def create(
        code: str,
        creator_user_id: int,
        created_at: str,
        expires_at: Optional[str] = None,
        usage_limit: int = 1,
        campus_id: Optional[str] = None,
        wave_id: Optional[str] = None,
    ) -> int:
        async with get_db() as db:
            cur = await db.execute(
                """
                INSERT INTO invite_codes
                    (code, creator_user_id, created_at, expires_at,
                     usage_limit, campus_id, wave_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (code, creator_user_id, created_at, expires_at,
                 usage_limit, campus_id, wave_id),
            )
            await db.commit()
            return cur.lastrowid

    @staticmethod
    async def mark_used(
        code_id: int,
        used_by_user_id: int,
        used_at: str,
    ) -> None:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE invite_codes
                SET used_count       = used_count + 1,
                    used_by_user_id  = COALESCE(used_by_user_id, ?),
                    used_at          = COALESCE(used_at, ?)
                WHERE id = ?
                """,
                (used_by_user_id, used_at, code_id),
            )
            await db.commit()

    @staticmethod
    async def deactivate(code_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE invite_codes SET is_active = 0 WHERE id = ?",
                (code_id,),
            )
            await db.commit()

    @staticmethod
    async def attach_to_application(app_id: int, code_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE applications SET invite_code_id = ? WHERE id = ?",
                (code_id, app_id),
            )
            await db.commit()

    # ── Read ───────────────────────────────────────────────────────

    @staticmethod
    async def get_by_code(code: str) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM invite_codes WHERE code = ?", (code,)
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_id(code_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM invite_codes WHERE id = ?", (code_id,)
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_creator(creator_user_id: int) -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM invite_codes WHERE creator_user_id = ? ORDER BY id DESC",
                (creator_user_id,),
            ) as cur:
                return await cur.fetchall()

    @staticmethod
    async def get_application_code_id(app_id: int) -> Optional[int]:
        async with get_db() as db:
            async with db.execute(
                "SELECT invite_code_id FROM applications WHERE id = ?", (app_id,)
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    return None
                return row["invite_code_id"]
