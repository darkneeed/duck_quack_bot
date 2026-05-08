from __future__ import annotations

import html

from ..strings import (
    PROFILE_HEADER,
    PROFILE_LINK,
    PROFILE_LEVEL,
    PROFILE_XP,
    PROFILE_PARALLEL,
    PROFILE_COALITION,
    PROFILE_COALITION_RANK,
    PROFILE_PEER_PTS,
    PROFILE_CODE_PTS,
    PROFILE_COINS,
    PROFILE_PROJECTS_HEADER,
    PROFILE_SKILLS_HEADER,
    PEER_CARD_COMMENT,
    PEER_CARD_CONTACT_MAX,
    PEER_CARD_CONTACT_NONE,
    PEER_CARD_CONTACT_ROCKET,
    PEER_CARD_CONTACT_TELEGRAM,
    PEER_CARD_PHOTO_NO,
    PEER_CARD_PHOTO_YES,
    PEER_CARD_PENDING_COMMENT,
    PEER_CARD_PENDING_PHOTO,
    PEER_CARD_PREVIEW_HEADER,
    PEER_CARD_SUBMISSION_COMMENT,
    PEER_CARD_SUBMISSION_COMMENT_TITLE,
    PEER_CARD_SUBMISSION_LOGIN,
    PEER_CARD_SUBMISSION_PHOTO_TITLE,
    PEER_CARD_SUBMISSION_RULES,
    PEER_CARD_SUBMISSION_TG,
)

_STATUS_ICONS = {
    "IN_PROGRESS": "🔄",
    "IN_REVIEWS": "👀",
    "REGISTERED": "📝",
    "ASSIGNED": "📋",
    "ACCEPTED": "✅",
    "FAILED": "❌",
}

_CONTACT_LABELS = {
    "tg": "Telegram",
    "max": "MAX",
    "rocket": "Rocket.Chat",
}


def render_profile_text(login: str, profile: dict, profile_url: str) -> str:
    info = profile.get("info") or {}
    coalition = profile.get("coalition") or {}
    points = profile.get("points") or {}
    projects = profile.get("active_projects") or []
    skills = sorted(profile.get("skills") or [], key=lambda s: s.get("points", 0), reverse=True)

    level = info.get("level", 0)
    exp = info.get("expValue", 0)
    exp_next = info.get("expToNextLevel", 0)
    parallel = info.get("parallelName") or info.get("className") or "—"
    coalition_name = coalition.get("name") or "—"
    coalition_rank = coalition.get("rank")
    peer_pts = points.get("peerReviewPoints", 0)
    code_pts = points.get("codeReviewPoints", 0)
    coins = points.get("coins", 0)

    lines = [
        PROFILE_HEADER.format(login=login),
        PROFILE_LINK.format(url=profile_url),
        "",
        PROFILE_LEVEL.format(level=level),
        PROFILE_XP.format(
            exp=f"{exp:,}".replace(",", " "),
            exp_next=f"{exp_next:,}".replace(",", " "),
        ),
        PROFILE_PARALLEL.format(parallel=parallel),
        (
            PROFILE_COALITION_RANK.format(name=coalition_name, rank=coalition_rank)
            if coalition_rank else PROFILE_COALITION.format(name=coalition_name)
        ),
        "",
        PROFILE_PEER_PTS.format(pts=peer_pts),
        PROFILE_CODE_PTS.format(pts=code_pts),
        PROFILE_COINS.format(coins=coins),
    ]

    if projects:
        lines.append("")
        lines.append(PROFILE_PROJECTS_HEADER)
        for project in projects[:5]:
            icon = _STATUS_ICONS.get(project.get("status", ""), "▪️")
            pct = project.get("finalPercentage")
            pct_str = f" — {pct}%" if pct else ""
            lines.append(f"{icon} {project.get('title', '—')}{pct_str}")

    if skills:
        top_skills = skills[:5]
        skills_str = ", ".join(f"{skill['name']} ({skill['points']})" for skill in top_skills)
        lines.append("")
        lines.append(PROFILE_SKILLS_HEADER.format(skills=skills_str))

    return "\n".join(lines)


def normalize_preferred_contact(value: str | None) -> str:
    if value in _CONTACT_LABELS:
        return value
    return "tg"


def render_peer_card_text(user) -> str:
    login = html.escape(user["school_login"] or "—")
    tg_id = user["tg_id"]
    preferred_contact = normalize_preferred_contact(user["preferred_contact"])
    comment = (user["profile_comment"] or "").strip()

    lines = [
        f"👤 <b>{login}</b>",
        f"💬 <b>Telegram:</b> <a href='tg://user?id={tg_id}'>{login}</a>",
    ]

    if comment:
        lines.append(PEER_CARD_COMMENT.format(comment=html.escape(comment)))

    if preferred_contact == "tg":
        lines.append(PEER_CARD_CONTACT_TELEGRAM.format(tg_id=tg_id))
    elif preferred_contact == "rocket":
        rocket_username = (user["rocket_username"] or "").strip()
        if rocket_username:
            lines.append(
                PEER_CARD_CONTACT_ROCKET.format(
                    rocket=html.escape(rocket_username),
                )
            )
        else:
            lines.append(PEER_CARD_CONTACT_NONE.format(contact=_CONTACT_LABELS[preferred_contact]))
    else:
        lines.append(PEER_CARD_CONTACT_MAX)

    return "\n".join(lines)


def render_peer_card_editor_text(user) -> str:
    has_photo = bool(user["profile_photo_file_id"])
    preferred_contact = normalize_preferred_contact(user["preferred_contact"])
    preview = render_peer_card_text(user)
    lines = [
        PEER_CARD_PREVIEW_HEADER,
        "",
        preview,
        "",
        PEER_CARD_PHOTO_YES if has_photo else PEER_CARD_PHOTO_NO,
        f"📡 <b>Выбранный канал:</b> {_CONTACT_LABELS[preferred_contact]}",
    ]
    if user["pending_profile_photo_file_id"]:
        lines.append(PEER_CARD_PENDING_PHOTO)
    if (user["pending_profile_comment"] or "").strip():
        lines.append(PEER_CARD_PENDING_COMMENT)
    return "\n".join(lines)


def build_profile_card_submission_text(user, submission_type: str) -> str:
    login = html.escape(user["school_login"] or "—")
    tg_name = html.escape(user["tg_name"] or user["school_login"] or str(user["tg_id"]))
    lines = [
        PEER_CARD_SUBMISSION_PHOTO_TITLE if submission_type == "photo" else PEER_CARD_SUBMISSION_COMMENT_TITLE,
        "",
        PEER_CARD_SUBMISSION_LOGIN.format(login=login),
        PEER_CARD_SUBMISSION_TG.format(tg_id=user["tg_id"], name=tg_name),
    ]
    if submission_type == "photo":
        lines.append(PEER_CARD_SUBMISSION_RULES)
    else:
        comment = html.escape((user["pending_profile_comment"] or "").strip())
        lines.append(PEER_CARD_SUBMISSION_COMMENT.format(comment=comment))
    return "\n".join(lines)
