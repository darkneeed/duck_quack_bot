from __future__ import annotations

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
)

_STATUS_ICONS = {
    "IN_PROGRESS": "🔄",
    "IN_REVIEWS": "👀",
    "REGISTERED": "📝",
    "ASSIGNED": "📋",
    "ACCEPTED": "✅",
    "FAILED": "❌",
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
