from __future__ import annotations

from typing import Optional

import aiosqlite

from .models import get_db


class VerificationVerifierRepo:

    @staticmethod
    async def create(
        verification_request_id: int,
        verifier_user_id: int,
        verifier_school_login: str,
        source_teammate_auto: bool = False,
        source_inline_selected: bool = False,
    ) -> int:
        async with get_db() as db:
            cur = await db.execute(
                """
                INSERT INTO verification_verifiers
                    (verification_request_id, verifier_user_id, verifier_school_login,
                     source_teammate_auto, source_inline_selected, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    verification_request_id,
                    verifier_user_id,
                    verifier_school_login,
                    1 if source_teammate_auto else 0,
                    1 if source_inline_selected else 0,
                ),
            )
            await db.commit()
            return cur.lastrowid

    @staticmethod
    async def set_teammate_auto_flag(record_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE verification_verifiers SET source_teammate_auto=1 WHERE id=?",
                (record_id,),
            )
            await db.commit()

    @staticmethod
    async def set_notification_sent(record_id: int, sent_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE verification_verifiers SET notification_sent_at=? WHERE id=?",
                (sent_at, record_id),
            )
            await db.commit()

    @staticmethod
    async def record_vote(record_id: int, vote: str, voted_at: str) -> None:
        """vote: 'confirm' | 'decline' | 'suspicious'"""
        async with get_db() as db:
            await db.execute(
                "UPDATE verification_verifiers SET vote=?, voted_at=? WHERE id=?",
                (vote, voted_at, record_id),
            )
            await db.commit()

    @staticmethod
    async def get_by_request_and_user(
        verification_request_id: int,
        verifier_user_id: int,
    ) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM verification_verifiers "
                "WHERE verification_request_id=? AND verifier_user_id=?",
                (verification_request_id, verifier_user_id),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_verifier_and_request(
        verifier_user_id: int,
        verification_request_id: int,
    ) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM verification_verifiers "
                "WHERE verifier_user_id=? AND verification_request_id=?",
                (verifier_user_id, verification_request_id),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_id(record_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM verification_verifiers WHERE id=?",
                (record_id,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_pending_notifications(
        verification_request_id: int,
    ) -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM verification_verifiers "
                "WHERE verification_request_id=? AND notification_sent_at IS NULL AND is_active=1",
                (verification_request_id,),
            ) as cur:
                return await cur.fetchall()

    @staticmethod
    async def get_vote_summary(verification_request_id: int) -> dict[str, int]:
        async with get_db() as db:
            async with db.execute(
                "SELECT vote, COUNT(*) as cnt FROM verification_verifiers "
                "WHERE verification_request_id=? AND is_active=1 "
                "GROUP BY vote",
                (verification_request_id,),
            ) as cur:
                rows = await cur.fetchall()

        summary: dict[str, int] = {"confirm": 0, "decline": 0, "suspicious": 0, "pending": 0}
        for row in rows:
            key = row["vote"] if row["vote"] in summary else "pending"
            summary[key] += row["cnt"]
        return summary

    @staticmethod
    async def get_all_for_request(verification_request_id: int) -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM verification_verifiers "
                "WHERE verification_request_id=? ORDER BY id",
                (verification_request_id,),
            ) as cur:
                return await cur.fetchall()
