from __future__ import annotations
import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from ..services import S21Client
from ..config import Config
from ..db import UserRepo
from ..strings import (
    ONLY_APPROVED, WHERE_USAGE, WHERE_IN_CAMPUS,
    WHERE_NOT_IN_CAMPUS, WHERE_ERROR,
)

logger = logging.getLogger(__name__)


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
router.message.filter(F.chat.type == "private")


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


@router.message(Command("peers", "пиры", ignore_case=True))
async def cmd_peers(message: Message, s21: S21Client) -> None:
    assert message.from_user is not None

    caller = await UserRepo.get_by_tg_id(message.from_user.id)
    if not caller or caller["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Использование: <code>/peers &lt;название проекта&gt;</code>\n"
            "Например: <code>/peers C2_SimpleBashUtils</code>",
            parse_mode="HTML",
        )
        return

    query = parts[1].strip().lower()
    wait = await message.answer("🔄 Ищу…")

    from ..db import UserRepo as _UR
    approved = await _UR.get_approved_users()
    matches: list[tuple[str, int]] = []  # (login, tg_id)

    for user in approved:
        login = user["school_login"]
        tg_id_u = user["tg_id"]
        if not login:
            continue
        try:
            found = False
            for status in ("IN_PROGRESS", "IN_REVIEWS", "REGISTERED"):
                if found:
                    break
                projects = await s21.get_projects(login, status=status, limit=20)
                for p in projects:
                    title = p.get("title") or ""
                    if query in title.lower() or query in str(p.get("id", "")):
                        matches.append((login, tg_id_u))
                        found = True
                        break
        except Exception:
            continue

    await wait.delete()

    if not matches:
        await message.answer(f"📭 Никто из участников не работает над <code>{query}</code>.", parse_mode="HTML")
        return

    mentions = []
    for login, tg_id_m in sorted(matches, key=lambda x: x[0]):
        mentions.append(f"<a href='tg://user?id={tg_id_m}'>{login}</a>")
    logins_str = ", ".join(mentions)
    await message.answer(
        f"👥 <b>Работают над «{query}»</b> — {len(matches)}\n\n{logins_str}",
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
