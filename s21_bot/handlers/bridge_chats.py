from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.types import ChatMemberUpdated

if TYPE_CHECKING:
    from s21_bot.services.bridge_client import BridgeClient

logger = logging.getLogger(__name__)

router = Router(name="bridge_chats")


@router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated,
    bridge_client: BridgeClient | None = None,
) -> None:
    """Handle bot membership updates in chats and report them to the Kryaken Bridge."""
    if not event.chat or not event.old_chat_member or not event.new_chat_member:
        return

    # Ignore private chats (managed chats are strictly group, supergroup, or channel)
    if event.chat.type == "private":
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    action: str | None = None

    if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
        action = "added"
    elif new_status in ("left", "kicked"):
        action = "removed"
    elif old_status in ("member", "administrator") and new_status in ("member", "administrator"):
        action = "rights_changed"

    if action is None:
        logger.debug("ChatMemberUpdated transition %s -> %s ignored", old_status, new_status)
        return

    if bridge_client is None:
        logger.warning("bridge_client not provided to on_my_chat_member for chat %s", event.chat.id)
        return

    report_fn = getattr(bridge_client, "report_chat_event", None) or getattr(bridge_client, "post_chat_event", None)
    if report_fn is not None:
        title = event.chat.title or getattr(event.chat, "full_name", None) or f"Chat {event.chat.id}"
        await report_fn(
            tg_chat_id=event.chat.id,
            title=title,
            chat_type=event.chat.type,
            action=action,
        )
