from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import Message

from ..config import Config
from ..db import UserRepo
from ..utils.telegram import send_message_with_topic


def display_name(user) -> str:
    if not user:
        return "?"
    name = user.full_name or str(user.id)
    if user.username:
        name += f" (@{user.username})"
    return name


async def resolve_target_label(target_id: int, reply_msg: Message | None = None) -> str:
    if reply_msg and reply_msg.from_user:
        user = reply_msg.from_user
        name = user.full_name or str(user.id)
        if user.username:
            name += f" (@{user.username})"
        return f"<a href='tg://user?id={user.id}'>{name}</a>"

    try:
        user = await UserRepo.get_by_tg_id(target_id)
        if user and user["tg_name"]:
            return f"<a href='tg://user?id={target_id}'>{user['tg_name']}</a>"
    except Exception:
        pass
    return f"<code>{target_id}</code>"


def parse_reply_or_id(message: Message, args: list[str]) -> tuple[int | None, list[str]]:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id, args
    if args:
        try:
            return int(args[0]), args[1:]
        except ValueError:
            pass
    return None, args


async def safe_delete_messages(*messages: Message) -> None:
    for message in messages:
        if not message:
            continue
        try:
            await message.delete()
        except Exception:
            pass


async def send_moderation_alert(
    bot: Bot,
    config: Config,
    logger: logging.Logger,
    text: str,
    forward: Message | None = None,
) -> None:
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.notify_topic_id or None,
            topic_name="NOTIFY_TOPIC_ID",
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
        )
        if forward:
            try:
                await forward.forward(chat_id=config.moderation_chat_id)
            except Exception:
                pass
    except Exception as exc:
        logger.error("Moderation alert failed: %s", exc)


def scope_ok(chat_type: str, scope: str) -> bool:
    is_private = chat_type == "private"
    if scope == "PRIVATE":
        return is_private
    if scope == "PUBLIC":
        return not is_private
    if scope == "OFF":
        return False
    return True
