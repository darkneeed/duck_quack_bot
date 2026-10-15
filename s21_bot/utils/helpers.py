from __future__ import annotations
import html
import re
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
    full_name = getattr(user, "full_name", None)
    if isinstance(full_name, str) and full_name.strip():
        name = full_name.strip()
    else:
        parts: list[str] = []
        first_name = getattr(user, "first_name", None)
        if isinstance(first_name, str) and first_name:
            parts.append(first_name)
        last_name = getattr(user, "last_name", None)
        if isinstance(last_name, str) and last_name:
            parts.append(last_name)
        name = " ".join(parts).strip()
    username = getattr(user, "username", None)
    if isinstance(username, str) and username:
        name += f" (@{username})"
    user_id = getattr(user, "id", None)
    return name or f"id:{user_id}"


def format_tg_user_link(tg_id: int, full_name: str, username: str | None = None) -> str:
    clean_name = (full_name or "").split(" (@")[0].strip() or f"id:{tg_id}"
    safe_name = html.escape(clean_name)
    clean_username = (username or "").strip().lstrip("@")
    if not clean_username and " (@" in (full_name or ""):
        m = re.search(r"\(@([A-Za-z0-9_]{5,})\)", full_name)
        if m:
            clean_username = m.group(1)
    if clean_username:
        safe_user = html.escape(clean_username)
        return f"<a href='tg://user?id={tg_id}'>{safe_name}</a> (@{safe_user})"
    return f"<a href='tg://user?id={tg_id}'>{safe_name}</a>"


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
    invite_author: Optional[str] = None,
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
        lines.append(f"🎟 <b>Инвайт:</b> <code>{invite_code}</code>")
    if invite_author:
        lines.append(f"🙋 <b>Автор инвайта:</b> {invite_author}")
    if user_comment:
        lines.append(CARD_COMMENT.format(comment=user_comment))
    return "\n".join(lines)
