from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from ..config import Config
from ..utils.datetime import format_now_local
from ..utils.telegram import send_message_with_topic
from .s21_api import S21Client

logger = logging.getLogger(__name__)


def _next_monday_midnight(now: datetime) -> datetime:
    days_ahead = 7 - now.weekday()
    if days_ahead == 7:
        days_ahead = 7
    next_monday = now + timedelta(days=days_ahead)
    return next_monday.replace(hour=6, minute=0, second=0, microsecond=0)


async def run_digest(bot: Bot, s21: S21Client, config: Config) -> None:
    if not getattr(config, "enable_digest", True):
        logger.info("Digest disabled (ENABLE_DIGEST=0)")
        return
    if not config.events_topic_id:
        logger.info("Digest disabled (EVENTS_TOPIC_ID=0)")
        return

    logger.info("Digest scheduler started")

    while True:
        now = datetime.now(timezone.utc)
        next_run = _next_monday_midnight(now)
        wait_seconds = (next_run - now).total_seconds()
        logger.info("Digest next run in %.0f seconds (%s UTC)", wait_seconds, next_run.strftime("%Y-%m-%d %H:%M"))
        await asyncio.sleep(wait_seconds)

        try:
            await _send_digest(bot, s21, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Digest error: %s", exc)


async def _send_digest(bot: Bot, s21: S21Client, config: Config) -> None:
    logger.info("Sending weekly digest…")

    logins = await s21.get_campus_participants(config.s21_campus_id, limit=1000)
    if not logins:
        logger.warning("Digest: no participants found")
        return

    xp_data: list[tuple[str, int]] = []
    active_count = 0
    main_count = 0

    for login in logins:
        try:
            info = await s21.get_participant(login)
            if info:
                parallel = info.get("parallelName") or ""
                if parallel != "Core program":
                    await asyncio.sleep(0.05)
                    continue
                main_count += 1
                if (info.get("status") or "").upper() == "ACTIVE":
                    active_count += 1
                xp = info.get("expValue", 0) or 0
                xp_data.append((login, xp))
            await asyncio.sleep(0.05)  # avoid rate limit
        except Exception:
            pass

    xp_data.sort(key=lambda x: x[1], reverse=True)
    top21 = xp_data[:9] + (xp_data[20:21] if len(xp_data) >= 21 else [])

    online_logins: set[str] = set()
    try:
        clusters = await s21.get_campus_clusters(config.s21_campus_id)
        for cluster in clusters:
            seats = await s21.get_cluster_map(cluster["id"])
            for seat in seats:
                if seat.get("login"):
                    online_logins.add(seat["login"])
    except Exception as exc:
        logger.warning("Digest: cluster fetch failed: %s", exc)

    now_str = format_now_local(config, "%d.%m.%Y")
    lines = [
        f"📊 <b>Еженедельный дайджест кампуса</b> — {now_str}",
        "",
        f"👥 <b>Участников основы:</b> {main_count}",
        f"✅ <b>Активных:</b> {active_count}",
        f"🖥 <b>Сейчас в кампусе:</b> {len(online_logins)}",
        "",
        "🏆 <b>Топ по XP (основа):</b>",
    ]
    for idx, (login, xp) in enumerate(top21):
        place = idx + 1 if idx < 9 else 21
        if idx == 9:
            lines.append("…")
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
        lines.append(f"{medal} <code>{login}</code> — {xp:,} XP")

    sent = await send_message_with_topic(
        bot,
        chat_id=config.community_chat_id,
        message_thread_id=config.digest_topic_id or None,
        topic_name="DIGEST_TOPIC_ID",
        topic_logger=logger,
        text="\n".join(lines),
        parse_mode="HTML",
    )
    if sent is not None:
        logger.info("Digest sent: %d participants, top10 computed", len(logins))
