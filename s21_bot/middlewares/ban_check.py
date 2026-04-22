from __future__ import annotations
import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from ..db import UserRepo

logger = logging.getLogger(__name__)
_RATE_LIMIT = 3
_RATE_WINDOW = 5.0
_user_timestamps: dict[int, list[float]] = defaultdict(list)

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
        uid = event.from_user.id
        now = time.monotonic()
        config = data.get("config")
        if config and uid in config.admin_ids:
            pass
        else:
            _user_timestamps[uid] = [t for t in _user_timestamps[uid] if now - t < _RATE_WINDOW]
            if len(_user_timestamps[uid]) >= _RATE_LIMIT:
                try:
                    await event.answer("🚦 Вы отправляете сообщения слишком быстро. Подождите немного.")
                except Exception:
                    pass
                return
            _user_timestamps[uid].append(now)
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
