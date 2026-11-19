from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import ChatMemberUpdated, TelegramObject

if TYPE_CHECKING:
    from s21_bot.services.bridge_state import BridgeState

logger = logging.getLogger(__name__)


class ChatApprovalMiddleware(BaseMiddleware):
    """Enforces chat approval policy.

    In unapproved groups, supergroups, and channels, incoming events are silently
    dropped without any response, delete, or handler invocation. In approved chats,
    the chat-specific configuration is injected into handler context data.
    """

    def __init__(self, bridge_state: BridgeState) -> None:
        super().__init__()
        self.bridge_state = bridge_state

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Pass my_chat_member updates unconditionally so bot addition/removal can be tracked
        if isinstance(event, ChatMemberUpdated):
            return await handler(event, data)

        if getattr(event, "my_chat_member", None) is not None:
            return await handler(event, data)

        # Extract chat from event or wrapped message
        chat = getattr(event, "chat", None)
        if chat is None and hasattr(event, "message"):
            chat = getattr(event.message, "chat", None)

        # If event has no associated chat, pass through
        if chat is None:
            return await handler(event, data)

        # Private chats are always allowed
        chat_type = getattr(chat, "type", "")
        if chat_type == "private":
            return await handler(event, data)

        # For group, supergroup, or channel, verify approval status
        chat_id = getattr(chat, "id", None)
        if chat_id is None:
            return await handler(event, data)

        if not self.bridge_state.is_chat_approved(chat_id):
            # Silently drop update without answering, replying, or deleting
            logger.debug("Silently dropping update from unapproved chat %s (%s)", chat_id, getattr(chat, "title", ""))
            return None

        # Inject chat-specific configuration into handler context
        chat_config = self.bridge_state.get_chat_config(chat_id)
        data["chat_config"] = chat_config

        return await handler(event, data)
