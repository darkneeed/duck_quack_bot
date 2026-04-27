from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

from .models import get_db

logger = logging.getLogger(__name__)


class OTPSessionRepo:
    @staticmethod
    async def create(
        tg_id: int,
        rc_username: str,
        code_hash: str,
        secret: str,
        created_at: str,
        ttl_seconds: int,
    ) -> int:
        async with get_db() as db:
            await db.execute(
                "UPDATE otp_sessions SET used=1 WHERE tg_id=? AND used=0",
                (tg_id,),
            )
            cur = await db.execute(
                """
                INSERT INTO otp_sessions
                    (tg_id, rc_username, code_hash, secret, attempts, created_at, expires_at, used)
                VALUES
                    (?, ?, ?, ?, 0, ?, datetime(?, ? || ' seconds'), 0)
                """,
                (tg_id, rc_username, code_hash, secret, created_at, created_at, str(ttl_seconds)),
            )
            await db.commit()
            return cur.lastrowid

    @staticmethod
    async def get_live(tg_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT * FROM otp_sessions
                WHERE tg_id=? AND used=0 AND expires_at > datetime('now')
                ORDER BY id DESC LIMIT 1
                """,
                (tg_id,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def increment_attempts(session_id: int) -> int:
        async with get_db() as db:
            await db.execute(
                "UPDATE otp_sessions SET attempts = attempts + 1 WHERE id=?",
                (session_id,),
            )
            await db.commit()
            async with db.execute(
                "SELECT attempts FROM otp_sessions WHERE id=?", (session_id,)
            ) as cur:
                row = await cur.fetchone()
                return row["attempts"] if row else 0

    @staticmethod
    async def mark_used(session_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE otp_sessions SET used=1 WHERE id=?", (session_id,)
            )
            await db.commit()

    @staticmethod
    async def invalidate_all(tg_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE otp_sessions SET used=1 WHERE tg_id=? AND used=0", (tg_id,)
            )
            await db.commit()
