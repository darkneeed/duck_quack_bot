from __future__ import annotations
import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from ..config import Config
from ..db import UserRepo
from ..strings import PROFILE_ONLY_APPROVED, PROFILE_LOADING, PROFILE_ERROR
from ..services import S21Client
from ..utils.branding import build_profile_url
from ..utils.profile import render_profile_text

logger = logging.getLogger(__name__)
router = Router(name="profile")
router.message.filter(F.chat.type == "private")


@router.message(Command("profile"))
async def cmd_profile(message: Message, s21: S21Client, config: Config) -> None:
    assert message.from_user is not None
    user = await UserRepo.get_by_tg_id(message.from_user.id)
    if not user or user["status"] != "approved" or not user["school_login"]:
        await message.answer(PROFILE_ONLY_APPROVED)
        return

    login = user["school_login"]
    wait = await message.answer(PROFILE_LOADING)

    try:
        profile = await s21.get_full_profile(login)
    except Exception as exc:
        await wait.delete()
        await message.answer(PROFILE_ERROR.format(error=exc))
        return

    await wait.delete()
    await message.answer(
        render_profile_text(login, profile, build_profile_url(login, config)),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
