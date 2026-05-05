from __future__ import annotations

import io
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..keyboards import cabinet_back_kb, cabinet_home_kb
from ..config import Config
from ..command_catalog import render_cabinet_help
from ..db import UserRepo
from ..db.invite_code_repo import InviteCodeRepo
from ..services import S21Client
from ..services.cache_poller import get_or_refresh
from ..services.invite_code_service import build_bot_link, create_invite_code
from ..strings import (
    CABINET_CODES_HEADER,
    CABINET_GENCODE_ERROR,
    CABINET_NO_CODES,
    INVITE_GENCODE_CAPTION,
    ONLY_APPROVED,
    PROFILE_ERROR,
    PROFILE_LOADING,
)
from ..utils.branding import build_profile_url
from ..utils.profile import render_profile_text
from ..utils.telegram import safe_callback_answer

logger = logging.getLogger(__name__)
router = Router(name="cabinet")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def _is_admin(tg_id: int, config: Config) -> bool:
    return tg_id in config.admin_ids


def _cabinet_home_text(login: str) -> str:
    return (
        f"👋 Добро пожаловать, <b>{login}</b>!\n\n"
        "Здесь собраны основные действия:\n"
        "• профиль на платформе\n"
        "• создание инвайта\n"
        "• просмотр своих инвайтов\n"
        "• краткая справка по командам"
    )


async def _show_home(message: Message, login: str, config: Config, tg_id: int) -> None:
    await message.answer(
        _cabinet_home_text(login),
        parse_mode="HTML",
        reply_markup=cabinet_home_kb(is_admin=_is_admin(tg_id, config)),
    )


async def _edit_cabinet_card(
    callback: CallbackQuery,
    text: str,
    config: Config,
    *,
    disable_web_page_preview: bool = True,
) -> None:
    assert callback.from_user is not None
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=disable_web_page_preview,
        reply_markup=cabinet_back_kb(is_admin=_is_admin(callback.from_user.id, config)),
    )


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


@router.callback_query(F.data == "cabinet:profile")
async def cb_cabinet_profile(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    assert callback.from_user is not None
    user = await UserRepo.get_by_tg_id(callback.from_user.id)
    if not user or user["status"] != "approved" or not user["school_login"]:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)

    login = user["school_login"]
    await _edit_cabinet_card(callback, PROFILE_LOADING, config, disable_web_page_preview=False)
    try:
        profile = await get_or_refresh(login, s21)
        if not profile:
            raise ValueError("empty response")
    except Exception as exc:
        await _edit_cabinet_card(callback, PROFILE_ERROR.format(error=exc), config, disable_web_page_preview=False)
        return

    await _edit_cabinet_card(
        callback,
        render_profile_text(login, profile, build_profile_url(login, config)),
        disable_web_page_preview=True,
        config=config,
    )


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
    await callback.message.edit_text(
        _cabinet_home_text(user["school_login"]),
        parse_mode="HTML",
        reply_markup=cabinet_home_kb(is_admin=_is_admin(callback.from_user.id, config)),
    )


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
