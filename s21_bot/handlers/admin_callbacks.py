from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from ..db import AuthAttemptRepo, UserRepo
from ..utils.telegram import safe_callback_answer
from .admin_common import IsModeratorInModChatCB

router = Router(name="admin_callbacks")


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
