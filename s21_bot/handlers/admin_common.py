from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from ..config import Config


class IsModeratorInModChat(Filter):
    async def __call__(self, message: Message, config: Config) -> bool:
        if not message.from_user:
            return False
        return (
            message.from_user.id in config.admin_ids
            and message.chat.id == config.moderation_chat_id
        )


class IsModeratorInModChatCB(Filter):
    async def __call__(self, callback: CallbackQuery, config: Config) -> bool:
        if not callback.from_user or not callback.message:
            return False
        return (
            callback.from_user.id in config.admin_ids
            and callback.message.chat.id == config.moderation_chat_id
        )


class IsAdminInPrivateChat(Filter):
    async def __call__(self, message: Message, config: Config) -> bool:
        if not message.from_user:
            return False
        return (
            message.from_user.id in config.admin_ids
            and message.chat.type == "private"
        )


class IsAdminInPrivateChatCB(Filter):
    async def __call__(self, callback: CallbackQuery, config: Config) -> bool:
        if not callback.from_user or not callback.message:
            return False
        return (
            callback.from_user.id in config.admin_ids
            and callback.message.chat.type == "private"
        )
