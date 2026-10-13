from __future__ import annotations
import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from ..db import UserRepo

logger = logging.getLogger(__name__)


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user:
            try:
                user = await UserRepo.get_by_tg_id(from_user.id)
                if user and user["is_banned"]:
                    if isinstance(event, CallbackQuery):
                        await event.answer("Вы заблокированы в этом боте.", show_alert=True)
                    elif isinstance(event, Message):
                        await event.answer("Вы заблокированы в этом боте.")
                    return
            except Exception as exc:
                logger.error("BanCheckMiddleware error: %s", exc)

        if isinstance(event, Message) and event.from_user:
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
