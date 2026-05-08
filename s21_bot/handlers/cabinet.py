from __future__ import annotations

import io
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..command_catalog import render_cabinet_help
from ..config import Config
from ..db import UserRepo
from ..db.invite_code_repo import InviteCodeRepo
from ..keyboards import (
    cabinet_back_kb,
    cabinet_cancel_input_kb,
    cabinet_home_kb,
    cabinet_profile_card_contact_kb,
    cabinet_profile_card_kb,
)
from ..services import S21Client
from ..services.cache_poller import get_or_refresh
from ..services.invite_code_service import build_bot_link, create_invite_code
from ..strings import (
    CABINET_CODES_HEADER,
    CABINET_GENCODE_ERROR,
    CABINET_NO_CODES,
    INVITE_GENCODE_CAPTION,
    ONLY_APPROVED,
    PEER_CARD_COMMENT_REMOVED,
    PEER_CARD_COMMENT_SAVED,
    PEER_CARD_CONTACT_PROMPT,
    PEER_CARD_CONTACT_SAVED,
    PEER_CARD_EDIT_CANCELLED,
    PEER_CARD_EDIT_COMMENT_PROMPT,
    PEER_CARD_EDIT_PHOTO_PROMPT,
    PEER_CARD_MAX_LINK_INVALID,
    PEER_CARD_MAX_LINK_PROMPT,
    PEER_CARD_MAX_LINK_SAVED,
    PEER_CARD_MAX_REQUIRED,
    PEER_CARD_PHOTO_EXPECTED,
    PEER_CARD_PHOTO_REMOVED,
    PEER_CARD_PHOTO_SAVED,
    PROFILE_ERROR,
    PROFILE_LOADING,
)
from ..utils.branding import build_profile_url
from ..utils.profile import (
    build_profile_card_submission_text,
    can_send_text_as_photo_caption,
    fit_text_for_photo_caption,
    normalize_preferred_contact,
    render_peer_card_editor_text,
)
from ..utils.states import ProfileCardFSM
from ..utils.telegram import safe_callback_answer, send_message_with_topic, send_photo_with_topic

logger = logging.getLogger(__name__)
router = Router(name="cabinet")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

_PROFILE_CARD_COMMENT_LIMIT = 500
_PROFILE_CARD_CONTACTS = {"tg", "max", "rocket"}
_PROFILE_CARD_MAX_LINK_PREFIXES = ("http://", "https://")


def _is_admin(tg_id: int, config: Config) -> bool:
    return tg_id in config.admin_ids


def _cabinet_home_text(login: str) -> str:
    return (
        f"👋 Добро пожаловать, <b>{login}</b>!\n\n"
        "Здесь собраны основные действия:\n"
        "• профиль и карточка сообщества\n"
        "• создание инвайта\n"
        "• просмотр своих инвайтов\n"
        "• краткая справка по командам"
    )


async def _edit_cabinet_card(
    callback: CallbackQuery,
    text: str,
    config: Config,
    *,
    disable_web_page_preview: bool = True,
) -> None:
    assert callback.from_user is not None
    await callback.message.answer(
        text,
        parse_mode="HTML",
        disable_web_page_preview=disable_web_page_preview,
        reply_markup=cabinet_back_kb(is_admin=_is_admin(callback.from_user.id, config)),
    )
    await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


def _profile_card_keyboard(user) -> object:
    return cabinet_profile_card_kb(
        has_photo=bool(user["profile_photo_file_id"]),
        has_comment=bool((user["profile_comment"] or "").strip()),
    )


async def _build_cabinet_profile_text(user, s21: S21Client, config: Config) -> str:
    login = user["school_login"]
    try:
        profile = await get_or_refresh(login, s21)
        if not profile:
            raise ValueError("empty response")
    except Exception as exc:
        return PROFILE_ERROR.format(error=exc)
    return render_peer_card_editor_text(
        login,
        profile,
        build_profile_url(login, config),
        user,
    )


async def _replace_with_profile_card(
    message: Message,
    user,
    s21: S21Client,
    config: Config,
) -> Message:
    text = await _build_cabinet_profile_text(user, s21, config)
    reply_markup = _profile_card_keyboard(user)
    if user["profile_photo_file_id"]:
        if can_send_text_as_photo_caption(text):
            sent = await message.answer_photo(
                photo=user["profile_photo_file_id"],
                caption=fit_text_for_photo_caption(text),
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            await message.answer_photo(
                photo=user["profile_photo_file_id"],
            )
            sent = await message.answer(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
    else:
        sent = await message.answer(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    await _delete_message_safe(message.bot, message.chat.id, message.message_id)
    return sent


async def _refresh_profile_message(
    message: Message,
    user,
    s21: S21Client,
    config: Config,
) -> Message:
    return await _replace_with_profile_card(message, user, s21, config)


async def _show_profile_card_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    prompt_text: str,
) -> None:
    prompt = await callback.message.answer(
        prompt_text,
        parse_mode="HTML",
        reply_markup=cabinet_cancel_input_kb(),
    )
    await state.update_data(
        profile_card_message_id=callback.message.message_id,
        profile_card_prompt_message_id=prompt.message_id,
    )


async def _delete_message_safe(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _drop_pending_moderation_message(
    *,
    bot: Bot,
    config: Config,
    message_id: int | None,
) -> None:
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=config.moderation_chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    except Exception:
        pass


async def _restore_profile_card_after_input(
    *,
    bot: Bot,
    source_message: Message,
    state: FSMContext,
    user_id: int,
    s21: S21Client,
    config: Config,
    notice_text: str | None = None,
) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("profile_card_prompt_message_id")
    card_message_id = data.get("profile_card_message_id")

    await _delete_message_safe(bot, source_message.chat.id, prompt_message_id)
    await _delete_message_safe(bot, source_message.chat.id, card_message_id)

    if notice_text:
        await source_message.answer(notice_text)

    user = await UserRepo.get_by_tg_id(user_id)
    if user and user["status"] == "approved":
        await _replace_with_profile_card(source_message, user, s21, config)

    await state.clear()


async def _require_approved_user(tg_id: int):
    user = await UserRepo.get_by_tg_id(tg_id)
    if not user or user["status"] != "approved" or not user["school_login"]:
        return None
    return user


async def _render_contact_picker(callback: CallbackQuery, user) -> None:
    selected = normalize_preferred_contact(user["preferred_contact"])
    await callback.message.answer(
        PEER_CARD_CONTACT_PROMPT,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=cabinet_profile_card_contact_kb(selected=selected),
    )
    await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


def _is_valid_max_profile_url(raw_url: str) -> bool:
    return raw_url.startswith(_PROFILE_CARD_MAX_LINK_PREFIXES)


async def _send_profile_card_submission_for_moderation(
    *,
    bot: Bot,
    config: Config,
    user,
    submission_type: str,
) -> int | None:
    from ..keyboards import profile_card_submission_kb

    text = build_profile_card_submission_text(user, submission_type)
    reply_markup = profile_card_submission_kb(submission_type=submission_type, tg_id=user["tg_id"])

    if submission_type == "photo":
        sent = await send_photo_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            fallback_to_chat=True,
            topic_logger=logger,
            photo=user["pending_profile_photo_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    else:
        sent = await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            fallback_to_chat=True,
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    return sent.message_id if sent else None


@router.message(Command("changetg"))
async def cmd_changetg(message: Message) -> None:
    assert message.from_user is not None
    user = await UserRepo.get_by_tg_id(message.from_user.id)
    if not user or user["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return
    await message.answer(
        f"ℹ️ Ваш текущий логин: <code>{user['school_login']}</code>\n\n"
        "Если вы хотите привязать другой Telegram-аккаунт, обратитесь к модераторам.",
        parse_mode="HTML",
    )


@router.message(Command("cancel", ignore_case=True), ProfileCardFSM.waiting_photo)
@router.message(Command("cancel", ignore_case=True), ProfileCardFSM.waiting_comment)
@router.message(Command("cancel", ignore_case=True), ProfileCardFSM.waiting_max_link)
async def cmd_cancel_profile_card_edit(
    message: Message,
    state: FSMContext,
    bot: Bot,
    s21: S21Client,
    config: Config,
) -> None:
    assert message.from_user is not None
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_EDIT_CANCELLED,
    )


@router.callback_query(F.data == "cabinet:profile")
async def cb_cabinet_profile(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await _replace_with_profile_card(callback.message, user, s21, config)


@router.callback_query(F.data == "cabinet:card_open")
async def cb_cabinet_card_open(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    await cb_cabinet_profile(callback, s21, config)


@router.callback_query(F.data == "cabinet:card_refresh")
async def cb_cabinet_card_refresh(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await _refresh_profile_message(callback.message, user, s21, config)


@router.callback_query(F.data == "cabinet:card_edit_photo")
async def cb_cabinet_card_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await state.set_state(ProfileCardFSM.waiting_photo)
    await _show_profile_card_prompt(callback, state, PEER_CARD_EDIT_PHOTO_PROMPT)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:card_edit_comment")
async def cb_cabinet_card_edit_comment(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await state.set_state(ProfileCardFSM.waiting_comment)
    await _show_profile_card_prompt(callback, state, PEER_CARD_EDIT_COMMENT_PROMPT)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:card_edit_max_link")
async def cb_cabinet_card_edit_max_link(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await state.set_state(ProfileCardFSM.waiting_max_link)
    await _show_profile_card_prompt(callback, state, PEER_CARD_MAX_LINK_PROMPT)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:card_cancel_input")
async def cb_cabinet_card_cancel_input(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    s21: S21Client,
    config: Config,
) -> None:
    assert callback.from_user is not None
    await safe_callback_answer(callback)
    await callback.message.delete()
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=callback.message,
        state=state,
        user_id=callback.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_EDIT_CANCELLED,
    )


@router.callback_query(F.data == "cabinet:card_contact")
async def cb_cabinet_card_contact(callback: CallbackQuery) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await _render_contact_picker(callback, user)


@router.callback_query(F.data.startswith("cabinet:card_contact_set:"))
async def cb_cabinet_card_contact_set(
    callback: CallbackQuery,
    s21: S21Client,
    config: Config,
) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return

    contact = callback.data.rsplit(":", maxsplit=1)[-1]
    if contact not in _PROFILE_CARD_CONTACTS:
        await safe_callback_answer(callback, "Некорректный способ связи.", show_alert=True)
        return
    if contact == "max" and not (user["max_profile_url"] or "").strip():
        await safe_callback_answer(callback, PEER_CARD_MAX_REQUIRED, show_alert=True)
        return

    await UserRepo.set_preferred_contact(callback.from_user.id, contact)
    updated_user = await UserRepo.get_by_tg_id(callback.from_user.id)
    await safe_callback_answer(callback, PEER_CARD_CONTACT_SAVED)
    if updated_user:
        await _refresh_profile_message(callback.message, updated_user, s21, config)


@router.callback_query(F.data == "cabinet:card_delete_photo")
async def cb_cabinet_card_delete_photo(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_photo_message_id"],
    )
    await UserRepo.clear_profile_photo_file_id(callback.from_user.id)
    updated_user = await UserRepo.get_by_tg_id(callback.from_user.id)
    await safe_callback_answer(callback, PEER_CARD_PHOTO_REMOVED)
    if updated_user:
        await _refresh_profile_message(callback.message, updated_user, s21, config)


@router.callback_query(F.data == "cabinet:card_delete_comment")
async def cb_cabinet_card_delete_comment(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_comment_message_id"],
    )
    await UserRepo.clear_profile_comment(callback.from_user.id)
    updated_user = await UserRepo.get_by_tg_id(callback.from_user.id)
    await safe_callback_answer(callback, PEER_CARD_COMMENT_REMOVED)
    if updated_user:
        await _refresh_profile_message(callback.message, updated_user, s21, config)


def _build_qr_image(data: str):
    try:
        import qrcode  # type: ignore[import]
    except ImportError:
        return None
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="#00e640")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@router.callback_query(F.data == "cabinet:home")
async def cb_cabinet_home(callback: CallbackQuery, config: Config) -> None:
    assert callback.from_user is not None
    user = await UserRepo.get_by_tg_id(callback.from_user.id)
    if not user or user["status"] != "approved" or not user["school_login"]:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await callback.message.answer(
        _cabinet_home_text(user["school_login"]),
        parse_mode="HTML",
        reply_markup=cabinet_home_kb(is_admin=_is_admin(callback.from_user.id, config)),
    )
    await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


@router.callback_query(F.data == "cabinet:gencode")
async def cb_cabinet_gencode(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    assert callback.from_user is not None
    user = await UserRepo.get_by_tg_id(callback.from_user.id)
    if not user or user["status"] != "approved":
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)

    try:
        code = await create_invite_code(creator_user_id=callback.from_user.id)
        bot_info = await bot.get_me()
        link = build_bot_link(code, bot_info.username or "")
        text = INVITE_GENCODE_CAPTION.format(link=f"<code>{link}</code>")
        await _edit_cabinet_card(callback, text, config, disable_web_page_preview=True)
        qr_buf = _build_qr_image(link)
        if qr_buf:
            await callback.message.answer_photo(
                photo=BufferedInputFile(qr_buf.read(), filename=f"invite_{code}.png"),
                caption="QR-код для быстрого открытия инвайта",
            )
    except Exception as exc:
        await _edit_cabinet_card(callback, CABINET_GENCODE_ERROR.format(error=exc), config, disable_web_page_preview=False)


@router.callback_query(F.data == "cabinet:mycodes")
async def cb_cabinet_mycodes(callback: CallbackQuery, config: Config) -> None:
    assert callback.from_user is not None
    await safe_callback_answer(callback)
    codes = await InviteCodeRepo.get_by_creator(callback.from_user.id)
    if not codes:
        await _edit_cabinet_card(callback, CABINET_NO_CODES, config, disable_web_page_preview=False)
        return

    lines = [CABINET_CODES_HEADER]
    for row in codes[:20]:
        is_used = row["used_count"] >= row["usage_limit"]
        status = "✅" if row["is_active"] and not is_used else "❌"
        if row["used_by_user_id"]:
            used_user = await UserRepo.get_by_tg_id(row["used_by_user_id"])
            used_label = (
                used_user["school_login"]
                if used_user and used_user["school_login"]
                else str(row["used_by_user_id"])
            )
        else:
            used_label = "не использован"
        expires = row["expires_at"] or "∞"
        lines.append(f"{status} <code>{row['code']}</code> | {used_label} | до {expires}")

    await _edit_cabinet_card(callback, "\n".join(lines), config, disable_web_page_preview=True)


@router.callback_query(F.data == "cabinet:help")
async def cb_cabinet_help(callback: CallbackQuery, config: Config) -> None:
    await safe_callback_answer(callback)
    await _edit_cabinet_card(callback, render_cabinet_help(config), config, disable_web_page_preview=True)


@router.message(ProfileCardFSM.waiting_photo, F.photo)
async def process_profile_card_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_photo_message_id"],
    )

    photo = message.photo[-1]
    await UserRepo.set_pending_profile_photo(message.from_user.id, photo.file_id, None)
    refreshed_user = await UserRepo.get_by_tg_id(message.from_user.id)
    if refreshed_user:
        moderation_message_id = await _send_profile_card_submission_for_moderation(
            bot=bot,
            config=config,
            user=refreshed_user,
            submission_type="photo",
        )
        await UserRepo.set_pending_profile_photo(message.from_user.id, photo.file_id, moderation_message_id)
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_PHOTO_SAVED,
    )


@router.message(ProfileCardFSM.waiting_photo)
async def process_profile_card_photo_invalid(message: Message) -> None:
    await message.answer(PEER_CARD_PHOTO_EXPECTED)


@router.message(ProfileCardFSM.waiting_comment)
async def process_profile_card_comment(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    raw_comment = (message.text or "").strip()
    if not raw_comment:
        await message.answer(PEER_CARD_EDIT_COMMENT_PROMPT, parse_mode="HTML")
        return

    comment = raw_comment[:_PROFILE_CARD_COMMENT_LIMIT] if raw_comment else None
    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_comment_message_id"],
    )
    await UserRepo.set_pending_profile_comment(message.from_user.id, comment, None)
    refreshed_user = await UserRepo.get_by_tg_id(message.from_user.id)
    if refreshed_user:
        moderation_message_id = await _send_profile_card_submission_for_moderation(
            bot=bot,
            config=config,
            user=refreshed_user,
            submission_type="comment",
        )
        await UserRepo.set_pending_profile_comment(message.from_user.id, comment, moderation_message_id)
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_COMMENT_SAVED,
    )


@router.message(ProfileCardFSM.waiting_max_link)
async def process_profile_card_max_link(
    message: Message,
    state: FSMContext,
    bot: Bot,
    s21: S21Client,
    config: Config,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    raw_url = (message.text or "").strip()
    if not _is_valid_max_profile_url(raw_url):
        await message.answer(PEER_CARD_MAX_LINK_INVALID)
        return

    await UserRepo.set_max_profile_url(message.from_user.id, raw_url)
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_MAX_LINK_SAVED,
    )
