from __future__ import annotations

from ..utils.helpers import now_iso
from .models import get_db


class JoinMessageRepo:
    @staticmethod
    async def add(chat_id: int, message_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT OR IGNORE INTO join_messages(chat_id, message_id, created_at) VALUES(?, ?, ?)",
                (chat_id, message_id, now_iso()),
            )
            await db.commit()

    @staticmethod
    async def get_recent(chat_id: int, limit: int = 200) -> list[tuple[int, int]]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT chat_id, message_id
                FROM join_messages
                WHERE chat_id=?
                ORDER BY message_id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [(row["chat_id"], row["message_id"]) for row in rows]

    @staticmethod
    async def remove(chat_id: int, message_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                "DELETE FROM join_messages WHERE chat_id=? AND message_id=?",
                (chat_id, message_id),
            )
            await db.commit()
