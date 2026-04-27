from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Filter as AiogramFilter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..config import Config
from ..db import ApplicationRepo
from ..db.invite_code_repo import InviteCodeRepo
import io

from ..strings import (
    INVITE_ACCEPTED_START, INVITE_INVALID, INVITE_NO_APP_STORED,
    INVITE_ATTACHED_OK, INVITE_ALREADY_ATTACHED, INVITE_ATTACH_FAILED,
    INVITE_GENCODE_CAPTION, INVITE_GENCODE_ERROR,
    INVITE_NO_CODES, INVITE_CODES_HEADER,
)
from ..services.invite_code_service import (
    AttachResult,
    ValidationResult,
    VALIDATION_MESSAGES,
    attach_invite_code_to_request,
    build_bot_link,
    create_invite_code,
    validate_invite_code,
)

logger = logging.getLogger(__name__)
router = Router(name="invite_code")

_PENDING_CODE_KEY = "pending_invite_code"


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_code(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    payload = (message.text or "").split(maxsplit=1)
    code = payload[1].strip().upper() if len(payload) > 1 else ""

    if not code:
        return

    result, _ = await validate_invite_code(code, message.from_user.id)
    if result == ValidationResult.OK:
        await state.update_data(**{_PENDING_CODE_KEY: code})
        await message.answer(INVITE_ACCEPTED_START.format(code=code, creator="администратора"), parse_mode="HTML")
        logger.info(
            "Invite code stored in FSM: code=%s tg_id=%d",
            code, message.from_user.id,
        )
    else:
        await message.answer(
            VALIDATION_MESSAGES.get(result, INVITE_INVALID) +
            "\n\nВы можете продолжить оформление заявки без кода.",
            parse_mode="HTML",
        )


@router.message(F.chat.type == "private", Command("invite"))
async def cmd_invite(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Использование: <code>/invite КОД</code>\n"
            "Например: <code>/invite A3F7C21B</code>",
            parse_mode="HTML",
        )
        return

    code = parts[1].strip().upper()
    tg_id = message.from_user.id

    app = await ApplicationRepo.get_pending_for_user(tg_id)
    if app is not None:
        result = await attach_invite_code_to_request(app["id"], code, tg_id)
        await _reply_attach_result(message, result, code, app["id"])
        return

    result, _ = await validate_invite_code(code, tg_id)
    if result == ValidationResult.OK:
        await state.update_data(**{_PENDING_CODE_KEY: code})
        await message.answer(
            INVITE_NO_APP_STORED.format(code=code),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            VALIDATION_MESSAGES.get(result, "❌ Недействительный код."),
            parse_mode="HTML",
        )


async def apply_pending_invite_code(
    app_id: int,
    tg_id: int,
    state: FSMContext,
    answer_func,
) -> None:
    data = await state.get_data()
    code: str | None = data.get(_PENDING_CODE_KEY)
    if not code:
        return

    await state.update_data(**{_PENDING_CODE_KEY: None})

    result = await attach_invite_code_to_request(app_id, code, tg_id)
    await _reply_attach_result_func(answer_func, result, code, app_id)


async def _reply_attach_result(
    message: Message,
    result: AttachResult,
    code: str,
    app_id: int,
) -> None:
    await _reply_attach_result_func(message.answer, result, code, app_id)


async def _reply_attach_result_func(
    answer_func,
    result: AttachResult,
    code: str,
    app_id: int,
) -> None:
    if result == AttachResult.OK:
        await answer_func(
            INVITE_ATTACHED_OK.format(code=code, app_id=app_id),
            parse_mode="HTML",
        )
    elif result == AttachResult.ALREADY_ATTACHED:
        await answer_func(
            INVITE_ALREADY_ATTACHED.format(app_id=app_id),
            parse_mode="HTML",
        )
    else:
        await answer_func(
            INVITE_ATTACH_FAILED,
            parse_mode="HTML",
        )


def _build_qr_image(data: str) -> io.BytesIO:
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("qrcode library not installed: pip install qrcode[pil]") from exc

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="#00e640")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class _IsAdminInModChat(AiogramFilter):
    async def __call__(self, message: Message, config: Config) -> bool:
        if not message.from_user:
            return False
        return (
            message.from_user.id in config.admin_ids
            and message.chat.id == config.moderation_chat_id
        )


@router.message(_IsAdminInModChat(), Command("gencode"))
async def cmd_gencode(message: Message, config: Config, bot: Bot) -> None:
    assert message.from_user is not None
    creator_id = message.from_user.id

    try:
        code = await create_invite_code(creator_user_id=creator_id)
    except Exception as exc:
        await message.reply(INVITE_GENCODE_ERROR.format(error=exc), parse_mode="HTML")
        return

    bot_info = await bot.get_me()
    link = build_bot_link(code, bot_info.username or "")

    caption = INVITE_GENCODE_CAPTION.format(link=link)

    try:
        qr_buf = _build_qr_image(link)
        from aiogram.types import BufferedInputFile
        await message.reply_photo(
            photo=BufferedInputFile(qr_buf.read(), filename=f"invite_{code}.png"),
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("QR generation failed, sending text only: %s", exc)
        await message.reply(caption, parse_mode="HTML", disable_web_page_preview=True)

    logger.info("Admin %d generated invite code %s", creator_id, code)

@router.message(_IsAdminInModChat(), Command("mycodes"))
async def cmd_mycodes(message: Message, bot: Bot) -> None:
    """List invite codes created by the calling admin."""
    assert message.from_user is not None
    codes = await InviteCodeRepo.get_by_creator(message.from_user.id)
    if not codes:
        await message.reply(INVITE_NO_CODES)
        return

    lines = [INVITE_CODES_HEADER]
    for row in codes[:20]:
        is_used = row["used_count"] >= row["usage_limit"]
        status = "✅" if row["is_active"] and not is_used else "❌"
        expires = (row["expires_at"] or "∞")
        if row["used_by_user_id"]:
            used_user = await UserRepo.get_by_tg_id(row["used_by_user_id"])
            used_label = used_user["school_login"] if used_user and used_user["school_login"] else str(row["used_by_user_id"])
        else:
            used_label = "не использован"
        lines.append(
            f"{status} <code>{row['code']}</code> | {used_label} | до {expires}"
        )

    await message.reply("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
