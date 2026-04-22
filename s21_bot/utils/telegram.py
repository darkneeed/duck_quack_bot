from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, MessageEntity
from aiogram.utils.text_decorations import add_surrogates, remove_surrogates

logger = logging.getLogger(__name__)

_STALE_CALLBACK_MARKERS = (
    "query is too old",
    "response timeout expired",
    "query id is invalid",
)
_THREAD_NOT_FOUND_MARKER = "message thread not found"


def is_stale_callback_error(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _STALE_CALLBACK_MARKERS)


def is_message_thread_not_found_error(exc: TelegramBadRequest) -> bool:
    return _THREAD_NOT_FOUND_MARKER in str(exc).lower()


async def safe_callback_answer(
    callback: CallbackQuery,
    *args: Any,
    **kwargs: Any,
) -> bool:
    try:
        await callback.answer(*args, **kwargs)
        return True
    except TelegramBadRequest as exc:
        if not is_stale_callback_error(exc):
            raise
        logger.warning(
            "Ignored stale callback answer: tg_id=%s data=%r error=%s",
            callback.from_user.id if callback.from_user else None,
            callback.data,
            exc,
        )
        return False


async def _send_with_topic(
    sender: Callable[..., Awaitable[Message]],
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_name: str,
    fallback_to_chat: bool = False,
    topic_logger: logging.Logger | None = None,
    **kwargs: Any,
) -> Message | None:
    send_kwargs = dict(kwargs)
    if message_thread_id:
        send_kwargs["message_thread_id"] = message_thread_id

    active_logger = topic_logger or logger
    try:
        return await sender(chat_id=chat_id, **send_kwargs)
    except TelegramBadRequest as exc:
        if not message_thread_id or not is_message_thread_not_found_error(exc):
            raise

        active_logger.warning(
            "Telegram topic %s is invalid: chat_id=%s thread_id=%s error=%s",
            topic_name,
            chat_id,
            message_thread_id,
            exc,
        )
        if not fallback_to_chat:
            return None

        active_logger.warning(
            "Retrying message without message_thread_id for topic %s",
            topic_name,
        )
        send_kwargs.pop("message_thread_id", None)
        return await sender(chat_id=chat_id, **send_kwargs)


async def send_message_with_topic(
    bot: Bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_name: str,
    fallback_to_chat: bool = False,
    topic_logger: logging.Logger | None = None,
    **kwargs: Any,
) -> Message | None:
    return await _send_with_topic(
        bot.send_message,
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        topic_name=topic_name,
        fallback_to_chat=fallback_to_chat,
        topic_logger=topic_logger,
        **kwargs,
    )


async def send_photo_with_topic(
    bot: Bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_name: str,
    fallback_to_chat: bool = False,
    topic_logger: logging.Logger | None = None,
    **kwargs: Any,
) -> Message | None:
    return await _send_with_topic(
        bot.send_photo,
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        topic_name=topic_name,
        fallback_to_chat=fallback_to_chat,
        topic_logger=topic_logger,
        **kwargs,
    )


async def send_document_with_topic(
    bot: Bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_name: str,
    fallback_to_chat: bool = False,
    topic_logger: logging.Logger | None = None,
    **kwargs: Any,
) -> Message | None:
    return await _send_with_topic(
        bot.send_document,
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        topic_name=topic_name,
        fallback_to_chat=fallback_to_chat,
        topic_logger=topic_logger,
        **kwargs,
    )


def add_custom_emoji_markup(text: str, entities: Sequence[MessageEntity] | None) -> str:
    if not text or not entities:
        return text

    source = add_surrogates(text)
    chunks: list[bytes] = []
    cursor = 0

    custom_emoji_entities = sorted(
        (
            entity
            for entity in entities
            if entity.type == "custom_emoji" and entity.custom_emoji_id
        ),
        key=lambda entity: entity.offset,
    )
    if not custom_emoji_entities:
        return text

    for entity in custom_emoji_entities:
        start = entity.offset * 2
        end = (entity.offset + entity.length) * 2
        if start < cursor:
            continue

        chunks.append(source[cursor:start])
        emoji_text = remove_surrogates(source[start:end])
        replacement = (
            f'<tg-emoji emoji-id="{entity.custom_emoji_id}">{emoji_text}</tg-emoji>'
        )
        chunks.append(replacement.encode("utf-16-le"))
        cursor = end

    chunks.append(source[cursor:])
    return remove_surrogates(b"".join(chunks))
