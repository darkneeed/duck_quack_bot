from __future__ import annotations

from aiogram import Bot

from ..db.join_message_repo import JoinMessageRepo


async def delete_tracked_join_messages(bot: Bot, chat_id: int, limit: int = 200) -> tuple[int, int]:
    rows = await JoinMessageRepo.get_recent(chat_id, limit=limit)
    deleted = 0
    failed = 0
    for row_chat_id, message_id in rows:
        try:
            await bot.delete_message(row_chat_id, message_id)
            deleted += 1
        except Exception:
            failed += 1
        finally:
            await JoinMessageRepo.remove(row_chat_id, message_id)
    return deleted, failed
