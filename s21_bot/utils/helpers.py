from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from aiogram.types import User
from ..strings import (
    CARD_BADGE_FAIL,
    CARD_BADGE_OK,
    CARD_COALITION,
    CARD_COMMENT,
    CARD_HEADER,
    CARD_ID,
    CARD_LOGIN,
    CARD_PROFILE_LINK,
    CARD_RC,
    CARD_TEAMMATES,
    CARD_NAME,
    CARD_XP,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def tg_display_name(user: User) -> str:
    parts = [user.first_name or ""]
    if user.last_name:
        parts.append(user.last_name)
    name = " ".join(parts).strip()
    if user.username:
        name += f" (@{user.username})"
    return name or f"id:{user.id}"


def build_moderation_card(
    tg_name: str,
    tg_id: int,
    school_login: str,
    profile_url: str,
    user_comment: Optional[str],
    app_id: int,
    has_welcome_badge: bool = False,
    coalition: Optional[str] = None,
    xp: Optional[int] = None,
    rc_username: Optional[str] = None,
    teammates: Optional[list[str]] = None,
    invite_code: Optional[str] = None,
) -> str:
    lines = [
        CARD_HEADER.format(app_id=app_id),
        "",
        CARD_NAME.format(tg_name=tg_name),
        CARD_ID.format(tg_id=tg_id),
        CARD_LOGIN.format(login=school_login),
        CARD_PROFILE_LINK.format(url=profile_url),
    ]
    if coalition:
        lines.append(CARD_COALITION.format(coalition=coalition))
    if xp is not None:
        lines.append(CARD_XP.format(xp=f"{xp:,}".replace(",", " ")))
    if has_welcome_badge:
        lines.append(CARD_BADGE_OK)
    else:
        lines.append(CARD_BADGE_FAIL)
    if rc_username:
        lines.append(CARD_RC.format(rc=rc_username))
    if teammates:
        logins_str = ", ".join(f"<code>{l}</code>" for l in teammates)
        lines.append(CARD_TEAMMATES.format(logins=logins_str))
    if invite_code:
        lines.append(f"🎟 <b>Инвайт-код:</b> <code>{invite_code}</code>")
    if user_comment:
        lines.append(CARD_COMMENT.format(comment=user_comment))
    return "\n".join(lines)
