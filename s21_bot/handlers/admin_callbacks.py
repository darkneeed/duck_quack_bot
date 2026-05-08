from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..db import AuthAttemptRepo, UserRepo
from ..keyboards import decided_kb, profile_card_reject_reason_kb
from ..strings import (
    PEER_CARD_SUBMISSION_APPROVED_COMMENT,
    PEER_CARD_SUBMISSION_APPROVED_PHOTO,
    PEER_CARD_SUBMISSION_COMMENT_KIND,
    PEER_CARD_SUBMISSION_NOT_PENDING,
    PEER_CARD_SUBMISSION_PHOTO_KIND,
    PEER_CARD_SUBMISSION_REASON_COMMENT_PERSONAL,
    PEER_CARD_SUBMISSION_REASON_COMMENT_RULES,
    PEER_CARD_SUBMISSION_REASON_COMMENT_SWEAR,
    PEER_CARD_SUBMISSION_REASON_PHOTO_FACE,
    PEER_CARD_SUBMISSION_REASON_PHOTO_OTHERS,
    PEER_CARD_SUBMISSION_REJECT_COMMENT_PROMPT,
    PEER_CARD_SUBMISSION_REJECT_PHOTO_PROMPT,
    PEER_CARD_SUBMISSION_REJECTED,
)
from ..utils.telegram import safe_callback_answer
from .admin_common import IsModeratorInModChat, IsModeratorInModChatCB

router = Router(name="admin_callbacks")


class ProfileCardModerationFSM(StatesGroup):
    waiting_reject_reason = State()


_PROFILE_CARD_REJECT_REASONS = {
    ("photo", "no_face"): PEER_CARD_SUBMISSION_REASON_PHOTO_FACE,
    ("photo", "has_others"): PEER_CARD_SUBMISSION_REASON_PHOTO_OTHERS,
    ("comment", "swear"): PEER_CARD_SUBMISSION_REASON_COMMENT_SWEAR,
    ("comment", "rules"): PEER_CARD_SUBMISSION_REASON_COMMENT_RULES,
    ("comment", "personal"): PEER_CARD_SUBMISSION_REASON_COMMENT_PERSONAL,
}


def _profile_card_kind_label(submission_type: str) -> str:
    return (
        PEER_CARD_SUBMISSION_PHOTO_KIND
        if submission_type == "photo"
        else PEER_CARD_SUBMISSION_COMMENT_KIND
    )


def _moderator_name(callback: CallbackQuery | Message) -> str:
    assert callback.from_user is not None
    name = callback.from_user.full_name or ""
    if callback.from_user.username:
        name += f" (@{callback.from_user.username})"
    return name.strip() or str(callback.from_user.id)


def _is_profile_card_pending(user, submission_type: str) -> bool:
    if submission_type == "photo":
        return bool(user["pending_profile_photo_file_id"])
    return bool((user["pending_profile_comment"] or "").strip())


async def _set_profile_card_decision_markup(
    *,
    bot: Bot,
    chat_id: int,
    message_id: int,
    decision: str,
    moderator_name: str,
) -> None:
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=decided_kb(decision, moderator_name),
        )
    except TelegramBadRequest:
        pass


async def _apply_profile_card_rejection(
    *,
    bot: Bot,
    chat_id: int,
    message_id: int,
    tg_id: int,
    submission_type: str,
    reason: str,
    moderator_name: str,
) -> None:
    if submission_type == "photo":
        await UserRepo.reject_pending_profile_photo(tg_id)
    else:
        await UserRepo.reject_pending_profile_comment(tg_id)

    await _set_profile_card_decision_markup(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        decision="rejected",
        moderator_name=moderator_name,
    )

    suffix = "" if submission_type == "comment" else "о"
    try:
        await bot.send_message(
            chat_id=tg_id,
            text=PEER_CARD_SUBMISSION_REJECTED.format(
                kind=_profile_card_kind_label(submission_type).lower(),
                suffix=suffix,
                reason=reason,
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data and c.data.startswith("confirm_deluser:"))
async def cb_confirm_deluser(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":")[1])
    await UserRepo.delete_user(target_id)
    await AuthAttemptRepo.delete_by_tg_id(target_id)
    await callback.message.edit_text(f"🗑 Пользователь <code>{target_id}</code> удалён из БД.", parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data == "cancel_deluser")
async def cb_cancel_deluser(callback: CallbackQuery) -> None:
    await callback.message.edit_text("❌ Удаление отменено.")
    await safe_callback_answer(callback)


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data == "confirm_cleardb")
async def cb_confirm_cleardb(callback: CallbackQuery) -> None:
    await UserRepo.clear_all()
    await callback.message.edit_text("🗑 База данных очищена.")
    await safe_callback_answer(callback)


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data == "cancel_cleardb")
async def cb_cancel_cleardb(callback: CallbackQuery) -> None:
    await callback.message.edit_text("❌ Очистка отменена.")
    await safe_callback_answer(callback)


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data and c.data.startswith("fail_skip:"))
async def cb_fail_skip(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await safe_callback_answer(callback, "Пропущено.")


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data and c.data.startswith("fail_ban:"))
async def cb_fail_ban(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split(":")[1])
    from ..keyboards import ban_duration_kb

    await callback.message.edit_reply_markup(reply_markup=ban_duration_kb(tg_id))
    await safe_callback_answer(callback)


@router.callback_query(IsModeratorInModChatCB(), lambda c: c.data and c.data.startswith("fail_ban_do:"))
async def cb_fail_ban_do(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    tg_id = int(parts[1])
    duration = int(parts[2])
    await UserRepo.upsert_basic(tg_id, f"id:{tg_id}")
    await UserRepo.set_banned(tg_id, True)
    if duration > 0:
        await UserRepo.set_cooldown(tg_id, duration)
    label = {3600: "1 час", 86400: "24 часа", 259200: "72 часа", 0: "навсегда"}.get(duration, str(duration))
    await callback.message.edit_text(
        callback.message.text + f"\n\n🔨 <b>Заблокирован на {label}</b> модератором {callback.from_user.full_name}",
        parse_mode="HTML",
    )
    await safe_callback_answer(callback, f"Заблокирован на {label}.")


@router.callback_query(IsModeratorInModChatCB(), F.data.startswith("profile_card:approve:"))
async def cb_profile_card_approve(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.from_user is not None
    parts = callback.data.split(":")
    submission_type = parts[2]
    tg_id = int(parts[3])
    user = await UserRepo.get_by_tg_id(tg_id)
    if not user or not _is_profile_card_pending(user, submission_type):
        await callback.message.edit_reply_markup(reply_markup=None)
        await safe_callback_answer(callback, PEER_CARD_SUBMISSION_NOT_PENDING, show_alert=True)
        return

    if submission_type == "photo":
        await UserRepo.approve_pending_profile_photo(tg_id)
        user_text = PEER_CARD_SUBMISSION_APPROVED_PHOTO
    else:
        await UserRepo.approve_pending_profile_comment(tg_id)
        user_text = PEER_CARD_SUBMISSION_APPROVED_COMMENT

    moderator_name = _moderator_name(callback)
    await _set_profile_card_decision_markup(
        bot=bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        decision="approved",
        moderator_name=moderator_name,
    )
    await safe_callback_answer(callback, "Одобрено.")

    try:
        await bot.send_message(chat_id=tg_id, text=user_text, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(IsModeratorInModChatCB(), F.data.startswith("profile_card:reject:"))
async def cb_profile_card_reject(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    submission_type = parts[2]
    tg_id = int(parts[3])
    user = await UserRepo.get_by_tg_id(tg_id)
    if not user or not _is_profile_card_pending(user, submission_type):
        await callback.message.edit_reply_markup(reply_markup=None)
        await safe_callback_answer(callback, PEER_CARD_SUBMISSION_NOT_PENDING, show_alert=True)
        return

    await state.set_state(ProfileCardModerationFSM.waiting_reject_reason)
    await state.update_data(
        profile_card_tg_id=tg_id,
        profile_card_submission_type=submission_type,
        profile_card_message_id=callback.message.message_id,
        profile_card_prompt_message_id=None,
    )
    prompt = await callback.message.answer(
        PEER_CARD_SUBMISSION_REJECT_PHOTO_PROMPT
        if submission_type == "photo"
        else PEER_CARD_SUBMISSION_REJECT_COMMENT_PROMPT,
        reply_markup=profile_card_reject_reason_kb(submission_type=submission_type, tg_id=tg_id),
    )
    await state.update_data(profile_card_prompt_message_id=prompt.message_id)
    await safe_callback_answer(callback)


@router.callback_query(IsModeratorInModChatCB(), F.data.startswith("profile_card:reject_reason:"))
async def cb_profile_card_reject_reason(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    submission_type = parts[2]
    tg_id = int(parts[3])
    reason_key = parts[4]
    reason = _PROFILE_CARD_REJECT_REASONS.get((submission_type, reason_key))
    data = await state.get_data()
    source_message_id = data.get("profile_card_message_id")
    user = await UserRepo.get_by_tg_id(tg_id)
    if not user or not reason or not _is_profile_card_pending(user, submission_type) or not source_message_id:
        await callback.message.edit_reply_markup(reply_markup=None)
        await safe_callback_answer(callback, PEER_CARD_SUBMISSION_NOT_PENDING, show_alert=True)
        await state.clear()
        return

    moderator_name = _moderator_name(callback)
    await _apply_profile_card_rejection(
        bot=bot,
        chat_id=callback.message.chat.id,
        message_id=source_message_id,
        tg_id=tg_id,
        submission_type=submission_type,
        reason=reason,
        moderator_name=moderator_name,
    )
    await safe_callback_answer(callback, "Отклонено.")

    prompt_message_id = data.get("profile_card_prompt_message_id")
    if prompt_message_id:
        try:
            await bot.delete_message(callback.message.chat.id, prompt_message_id)
        except Exception:
            pass
    await state.clear()


@router.message(IsModeratorInModChat(), ProfileCardModerationFSM.waiting_reject_reason)
async def msg_profile_card_reject_reason(message: Message, state: FSMContext, bot: Bot) -> None:
    assert message.from_user is not None
    data = await state.get_data()
    tg_id = data.get("profile_card_tg_id")
    submission_type = data.get("profile_card_submission_type")
    source_message_id = data.get("profile_card_message_id")
    prompt_message_id = data.get("profile_card_prompt_message_id")
    if not tg_id or not submission_type or not source_message_id:
        await state.clear()
        return

    reason = (message.text or "").strip()[:500]
    if not reason:
        return

    user = await UserRepo.get_by_tg_id(tg_id)
    if not user or not _is_profile_card_pending(user, submission_type):
        await message.answer(PEER_CARD_SUBMISSION_NOT_PENDING)
        await state.clear()
        return

    moderator_name = _moderator_name(message)
    await _apply_profile_card_rejection(
        bot=bot,
        chat_id=message.chat.id,
        message_id=source_message_id,
        tg_id=tg_id,
        submission_type=submission_type,
        reason=reason,
        moderator_name=moderator_name,
    )

    if prompt_message_id:
        try:
            await bot.delete_message(message.chat.id, prompt_message_id)
        except Exception:
            pass
    await state.clear()
    await message.answer("Отклонено.")
