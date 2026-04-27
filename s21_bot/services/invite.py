from __future__ import annotations
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)


async def create_one_time_invite(
    bot: Bot,
    chat_id: int,
    expire_seconds: int = 86400,
    name: str = "",
) -> str:
    try:
        link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=name or None,
            expire_date=None,
            member_limit=1,
            creates_join_request=False,
        )
        logger.info("Created invite link for chat %d: %s", chat_id, link.invite_link)
        return link.invite_link
    except TelegramBadRequest as exc:
        logger.error("Failed to create invite link for chat %d: %s", chat_id, exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error creating invite link: %s", exc)
        raise
