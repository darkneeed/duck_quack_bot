from __future__ import annotations
import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from ..db import UserRepo

logger = logging.getLogger(__name__)

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
        uid = event.from_user.id
        try:
            user = await UserRepo.get_by_tg_id(uid)
            if user and user["is_banned"]:
                await event.answer("🚫 Вы заблокированы в этом боте.")
                return
        except Exception as exc:
            logger.error("BanCheckMiddleware error: %s", exc)

        config = data.get("config")
        bot = data.get("bot")
        if config and bot and event.chat.id == config.community_chat_id:
            try:
                from ..services.antispam import check_message
                handled = await check_message(event, bot, config)
                if handled:
                    return
            except Exception as exc:
                logger.error("Antispam error: %s", exc)

        return await handler(event, data)
