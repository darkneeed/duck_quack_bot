from __future__ import annotations
import difflib
import logging
import re
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from ..services import S21Client
from ..services.cache_poller import get_or_refresh
from ..config import Config
from ..db import UserRepo
from ..strings import (
    ONLY_APPROVED, WHERE_USAGE, WHERE_IN_CAMPUS,
    WHERE_NOT_IN_CAMPUS, WHERE_ERROR,
    PROFILE_ERROR,
    PEER_CARD_NOT_FOUND, PEER_CARD_USAGE,
)
from ..utils.branding import build_profile_url
from ..utils.profile import (
    can_send_text_as_photo_caption,
    fit_text_for_photo_caption,
    render_full_peer_card_text,
)

logger = logging.getLogger(__name__)


def _normalize_project_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _iter_project_candidates(project: dict) -> tuple[str, ...]:
    candidates: list[str] = []
    for key in ("title", "name", "code", "slug", "kind", "id"):
        value = project.get(key)
        if value:
            candidates.append(str(value))
    return tuple(dict.fromkeys(candidates))


def _project_match_score(query: str, project: dict) -> float:
    query_norm = _normalize_project_text(query)
    if not query_norm:
        return 0.0

    best = 0.0
    for candidate in _iter_project_candidates(project):
        candidate_lower = candidate.lower()
        candidate_norm = _normalize_project_text(candidate)
        if not candidate_norm:
            continue
        if query_norm == candidate_norm:
            return 1.0
        if query_norm in candidate_norm or candidate_norm in query_norm:
            best = max(best, 0.95)
            continue

        tokens = [token for token in re.split(r"[^a-z0-9]+", candidate_lower) if token]
        if any(query_norm in _normalize_project_text(token) for token in tokens):
            best = max(best, 0.9)
            continue

        best = max(best, difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio())
    return best


def _find_best_project_match(query: str, projects: list[dict]) -> tuple[dict | None, float]:
    best_project: dict | None = None
    best_score = 0.0
    for project in projects:
        score = _project_match_score(query, project)
        if score > best_score:
            best_project = project
            best_score = score
    return best_project, best_score


def _project_display_name(project: dict | None, fallback: str) -> str:
    if not project:
        return fallback
    return str(
        project.get("title")
        or project.get("name")
        or project.get("code")
        or project.get("slug")
        or fallback
    )


def _check_scope(chat_type: str, scope: str) -> bool:
    is_private = chat_type == "private"
    if scope == "PRIVATE":
        return is_private
    if scope == "PUBLIC":
        return not is_private
    if scope == "OFF":
        return False
    return True  # BOTH

router = Router(name="where")


@router.message(Command("where"))
async def cmd_where(message: Message, s21: S21Client, config: Config) -> None:
    assert message.from_user is not None

    if not _check_scope(message.chat.type, config.cmd_where_scope):
        return
    caller = await UserRepo.get_by_tg_id(message.from_user.id)
    if not caller or caller["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(WHERE_USAGE, parse_mode="HTML")
        return

    login = parts[1].strip().lower()

    try:
        data = await s21.get_workstation(login)
    except Exception as exc:
        logger.warning("Workstation fetch failed for %s: %s", login, exc)
        await message.answer(WHERE_ERROR)
        return

    if not data:
        await message.answer(WHERE_NOT_IN_CAMPUS.format(login=login), parse_mode="HTML")
        return

    cluster = (
        data.get("clusterName") or data.get("cluster") or
        data.get("cluster_name") or data.get("hostName") or ""
    )
    row = data.get("row") or data.get("workstationRow") or ""
    number = data.get("number") or data.get("workstationNumber") or data.get("num") or ""

    if not cluster and not row and not number:
        logger.info("Unknown workstation response for %s: %s", login, dict(data))
        await message.answer(WHERE_NOT_IN_CAMPUS.format(login=login), parse_mode="HTML")
        return

    seat = f"{cluster} {row}{number}".strip()
    await message.answer(WHERE_IN_CAMPUS.format(login=login, seat=seat), parse_mode="HTML")


@router.message(Command("peer", "пир", ignore_case=True))
async def cmd_peer_card(message: Message, s21: S21Client, config: Config) -> None:
    assert message.from_user is not None

    if not _check_scope(message.chat.type, config.cmd_peer_scope):
        return

    caller = await UserRepo.get_by_tg_id(message.from_user.id)
    if not caller or caller["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(PEER_CARD_USAGE, parse_mode="HTML")
        return

    login = parts[1].strip().lower()
    user = await UserRepo.get_approved_by_school_login(login)
    if not user:
        await message.answer(PEER_CARD_NOT_FOUND.format(login=login), parse_mode="HTML")
        return

    try:
        profile = await get_or_refresh(login, s21)
        if not profile:
            raise ValueError("empty response")
    except Exception as exc:
        await message.answer(PROFILE_ERROR.format(error=exc), parse_mode="HTML")
        return

    card_text = render_full_peer_card_text(
        login,
        profile,
        build_profile_url(login, config),
        user,
        show_coins=caller["tg_id"] == user["tg_id"],
    )
    if user["profile_photo_file_id"]:
        if can_send_text_as_photo_caption(card_text):
            await message.answer_photo(
                photo=user["profile_photo_file_id"],
                caption=fit_text_for_photo_caption(card_text),
                parse_mode="HTML",
            )
        else:
            await message.answer_photo(
                photo=user["profile_photo_file_id"],
            )
            await message.answer(
                card_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return

    await message.answer(
        card_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("peers", "пиры", ignore_case=True))
async def cmd_peers(message: Message, s21: S21Client, config: Config) -> None:
    assert message.from_user is not None

    if not _check_scope(message.chat.type, config.cmd_peers_scope):
        return

    caller = await UserRepo.get_by_tg_id(message.from_user.id)
    if not caller or caller["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Использование: <code>/peers &lt;проект или код&gt;</code>\n"
            "Например: <code>/peers DSB7</code> или <code>/peers Pandas</code>",
            parse_mode="HTML",
        )
        return

    query = parts[1].strip().lower()
    wait = await message.answer("🔄 Ищу…")

    from ..db import UserRepo as _UR
    approved = await _UR.get_approved_users()
    matches: list[tuple[str, int, dict, float]] = []  # (login, tg_id, project, score)

    for user in approved:
        login = user["school_login"]
        tg_id_u = user["tg_id"]
        if not login:
            continue
        try:
            all_projects: list[dict] = []
            for status in ("IN_PROGRESS", "IN_REVIEWS", "REGISTERED"):
                projects = await s21.get_projects(login, status=status, limit=20)
                all_projects.extend(projects)
            best_project, best_score = _find_best_project_match(query, all_projects)
            if best_project and best_score >= 0.65:
                matches.append((login, tg_id_u, best_project, best_score))
        except Exception:
            continue

    await wait.delete()

    if not matches:
        await message.answer(f"📭 Никто из участников не работает над <code>{query}</code>.", parse_mode="HTML")
        return

    mentions = []
    best_match_name = _project_display_name(max(matches, key=lambda item: item[3])[2], query)
    for login, tg_id_m, _, _ in sorted(matches, key=lambda item: item[0]):
        mentions.append(f"<a href='tg://user?id={tg_id_m}'>{login}</a>")
    logins_str = ", ".join(mentions)
    await message.answer(
        f"👥 <b>Работают над «{best_match_name}»</b> — {len(matches)}\n\n{logins_str}",
        parse_mode="HTML",
    )


@router.message(Command("logtime", "логтайм", ignore_case=True))
async def cmd_logtime(message: Message, s21: S21Client, config: Config) -> None:
    if not _check_scope(message.chat.type, config.cmd_logtime_scope):
        return
    assert message.from_user is not None

    caller = await UserRepo.get_by_tg_id(message.from_user.id)
    if not caller or caller["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        login = parts[1].strip().lower()
    else:
        login = caller["school_login"]
        if not login:
            await message.answer("❌ Ваш логин не найден.")
            return

    try:
        hours = await s21.get_logtime(login)
    except Exception as exc:
        await message.answer(f"⚠️ Не удалось получить данные: <code>{exc}</code>", parse_mode="HTML")
        return

    if hours is None:
        await message.answer(f"📭 Данные о логтайме для <code>{login}</code> недоступны.", parse_mode="HTML")
        return

    h = int(hours)
    m = int((hours - h) * 60)
    time_str = f"{h} ч. {m} мин." if m else f"{h} ч."

    await message.answer(
        f"🕐 <b>Среднее время в кампусе</b>\n\n"
        f"👤 <code>{login}</code>\n"
        f"📊 За неделю: <b>{time_str}</b>",
        parse_mode="HTML",
    )
