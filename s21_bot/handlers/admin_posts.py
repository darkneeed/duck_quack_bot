from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import Config
from ..utils.telegram import (
    add_custom_emoji_markup,
    safe_callback_answer,
    send_document_with_topic,
    send_message_with_topic,
    send_photo_with_topic,
)
from .admin_common import IsAdminInPrivateChat, IsAdminInPrivateChatCB

logger = logging.getLogger(__name__)
router = Router(name="admin_posts")

_SKIP_IMAGE_CALLBACK = "admin_post:skip_image"
_CANCEL_CALLBACK = "admin_post:cancel"
_POST_TOPIC_NAME = "DIGEST_TOPIC_ID"
_CAPTION_TOO_LONG_MARKER = "caption is too long"

_POST_TEXT_PROMPT = (
    "📝 Отправьте текст поста одним сообщением.\n\n"
    "Поддерживается HTML-разметка: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, "
    "<code>&lt;u&gt;</code>, <code>&lt;s&gt;</code>, <code>&lt;code&gt;</code>, "
    "<code>&lt;pre&gt;</code>, <code>&lt;a href=\"...\"&gt;</code>, "
    "<code>&lt;tg-spoiler&gt;</code>.\n\n"
    "Форматирование нужно писать тегами прямо в тексте, а не через меню Telegram.\n"
    "Премиальные эмодзи можно вставлять как обычно, бот сохранит их автоматически."
)
_POST_IMAGE_PROMPT = (
    "🖼 Текст сохранён. Предпросмотр выше.\n\n"
    "Теперь пришлите картинку одним сообщением или нажмите кнопку ниже."
)
_POST_TEXT_REQUIRED = "❌ Нужен текст поста. Отправьте его одним сообщением."
_POST_MARKUP_ERROR = (
    "❌ Не удалось разобрать текст поста.\n"
    "<code>{error}</code>\n\n"
    "Исправьте разметку и отправьте текст ещё раз."
)
_POST_IMAGE_REQUIRED = (
    "❌ Жду фото или изображение-документ. "
    "Либо нажмите «Без картинки»."
)
_POST_SESSION_EXPIRED = "⚠️ Сессия публикации истекла. Запустите /пост заново."
_POST_CANCELLED = "❌ Публикация отменена."
_POST_PUBLISHED = "✅ Пост опубликован в общий тред."
_POST_PUBLISH_ERROR = (
    "❌ Не удалось опубликовать пост.\n"
    "<code>{error}</code>"
)


class AdminPostFSM(StatesGroup):
    waiting_text = State()
    waiting_image = State()


def _cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=_CANCEL_CALLBACK))
    return builder.as_markup()


def _image_step_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭ Без картинки", callback_data=_SKIP_IMAGE_CALLBACK))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=_CANCEL_CALLBACK))
    return builder.as_markup()


async def _publish_post(
    bot: Bot,
    config: Config,
    html_text: str,
    *,
    photo_id: str | None = None,
    document_id: str | None = None,
) -> None:
    topic_id = config.digest_topic_id or None

    if photo_id:
        await _publish_media_with_optional_caption(
            sender=send_photo_with_topic,
            bot=bot,
            chat_id=config.community_chat_id,
            message_thread_id=topic_id,
            photo=photo_id,
            html_text=html_text,
        )
        return

    if document_id:
        await _publish_media_with_optional_caption(
            sender=send_document_with_topic,
            bot=bot,
            chat_id=config.community_chat_id,
            message_thread_id=topic_id,
            document=document_id,
            html_text=html_text,
        )
        return

    await send_message_with_topic(
        bot,
        chat_id=config.community_chat_id,
        message_thread_id=topic_id,
        topic_name=_POST_TOPIC_NAME,
        fallback_to_chat=True,
        topic_logger=logger,
        text=html_text,
        parse_mode="HTML",
    )


async def _publish_media_with_optional_caption(
    *,
    sender,
    bot: Bot,
    chat_id: int,
    message_thread_id: int | None,
    html_text: str,
    **media_kwargs,
) -> None:
    try:
        await sender(
            bot,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            topic_name=_POST_TOPIC_NAME,
            fallback_to_chat=True,
            topic_logger=logger,
            caption=html_text,
            parse_mode="HTML",
            **media_kwargs,
        )
        return
    except TelegramBadRequest as exc:
        if _CAPTION_TOO_LONG_MARKER not in str(exc).lower():
            raise

    await sender(
        bot,
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        topic_name=_POST_TOPIC_NAME,
        fallback_to_chat=True,
        topic_logger=logger,
        **media_kwargs,
    )
    await send_message_with_topic(
        bot,
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        topic_name=_POST_TOPIC_NAME,
        fallback_to_chat=True,
        topic_logger=logger,
        text=html_text,
        parse_mode="HTML",
    )


async def _get_post_html(state: FSMContext) -> str | None:
    data = await state.get_data()
    post_html = data.get("post_html")
    return post_html if isinstance(post_html, str) and post_html else None


@router.message(IsAdminInPrivateChat(), Command("post", "пост", ignore_case=True))
async def cmd_post(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminPostFSM.waiting_text)
    await message.answer(
        _POST_TEXT_PROMPT,
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )


@router.message(IsAdminInPrivateChat(), AdminPostFSM.waiting_text)
async def process_post_text(message: Message, state: FSMContext) -> None:
    raw_text = message.text or ""
    if not raw_text.strip():
        await message.answer(
            _POST_TEXT_REQUIRED,
            reply_markup=_cancel_kb(),
        )
        return

    html_text = add_custom_emoji_markup(raw_text, message.entities)
    try:
        await message.answer(
            html_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        await message.answer(
            _POST_MARKUP_ERROR.format(error=html.escape(str(exc))),
            parse_mode="HTML",
            reply_markup=_cancel_kb(),
        )
        return

    await state.update_data(post_html=html_text)
    await state.set_state(AdminPostFSM.waiting_image)
    await message.answer(
        _POST_IMAGE_PROMPT,
        reply_markup=_image_step_kb(),
    )


@router.message(IsAdminInPrivateChat(), AdminPostFSM.waiting_image)
async def process_post_image(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
) -> None:
    post_html = await _get_post_html(state)
    if not post_html:
        await state.clear()
        await message.answer(_POST_SESSION_EXPIRED)
        return

    photo_id = message.photo[-1].file_id if message.photo else None
    document_id = None
    if message.document and (message.document.mime_type or "").startswith("image/"):
        document_id = message.document.file_id

    if not photo_id and not document_id:
        await message.answer(
            _POST_IMAGE_REQUIRED,
            reply_markup=_image_step_kb(),
        )
        return

    try:
        await _publish_post(
            bot,
            config,
            post_html,
            photo_id=photo_id,
            document_id=document_id,
        )
    except TelegramBadRequest as exc:
        logger.warning("Failed to publish admin post: %s", exc)
        await message.answer(
            _POST_PUBLISH_ERROR.format(error=html.escape(str(exc))),
            parse_mode="HTML",
            reply_markup=_image_step_kb(),
        )
        return
    except Exception as exc:
        logger.exception("Unexpected error while publishing admin post")
        await message.answer(
            _POST_PUBLISH_ERROR.format(error=html.escape(str(exc))),
            parse_mode="HTML",
            reply_markup=_image_step_kb(),
        )
        return

    await state.clear()
    await message.answer(_POST_PUBLISHED)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == _SKIP_IMAGE_CALLBACK, AdminPostFSM.waiting_image)
async def cb_publish_without_image(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    config: Config,
) -> None:
    post_html = await _get_post_html(state)
    if not post_html:
        await state.clear()
        await safe_callback_answer(callback, _POST_SESSION_EXPIRED, show_alert=True)
        return

    await safe_callback_answer(callback, "Публикую…")
    try:
        await _publish_post(bot, config, post_html)
    except TelegramBadRequest as exc:
        logger.warning("Failed to publish admin post without image: %s", exc)
        await callback.message.answer(
            _POST_PUBLISH_ERROR.format(error=html.escape(str(exc))),
            parse_mode="HTML",
            reply_markup=_image_step_kb(),
        )
        return
    except Exception as exc:
        logger.exception("Unexpected error while publishing admin post without image")
        await callback.message.answer(
            _POST_PUBLISH_ERROR.format(error=html.escape(str(exc))),
            parse_mode="HTML",
            reply_markup=_image_step_kb(),
        )
        return

    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.message.answer(_POST_PUBLISHED)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == _CANCEL_CALLBACK)
async def cb_cancel_post(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await safe_callback_answer(callback)
    await callback.message.answer(_POST_CANCELLED)
