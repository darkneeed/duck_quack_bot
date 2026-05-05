from __future__ import annotations

from ..utils.helpers import now_iso
from .models import get_db


class BotSettingsRepo:
    @staticmethod
    async def get_all() -> dict[str, str]:
        async with get_db() as db:
            async with db.execute("SELECT key, value FROM bot_settings") as cur:
                rows = await cur.fetchall()
        return {row["key"]: row["value"] for row in rows}

    @staticmethod
    async def set_value(key: str, value: str, updated_by: int | None = None) -> None:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO bot_settings(key, value, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (key, value, now_iso(), updated_by),
            )
            await db.commit()
