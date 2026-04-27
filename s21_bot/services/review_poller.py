from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram import Bot

from ..config import Config
from ..db import UserRepo
from ..strings import (
    REVIEW_REMINDER_HOURS, REVIEW_REMINDER_HOUR, REVIEW_REMINDER_MINUTES,
    REVIEW_PROJECT, REVIEW_TIME, REVIEW_CHECKER,
)
from ..utils.datetime import format_local_dt
from .s21_api import S21Client

logger = logging.getLogger(__name__)


_notified: set[tuple[str, str, int]] = set()

_DATE_FIELDS = (
    "reviewStartDate", "startDate", "verifierStartAt",
    "checkerStartAt", "reviewDate", "start_date",
    "goalEvaluationDate", "evaluationDate",
)

_ID_FIELDS = ("id", "goalId", "projectId", "project_id")

_CHECKER_FIELDS = ("checkerLogin", "verifierLogin", "reviewerLogin", "checker")


def _parse_dt(raw) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def _get(project: dict, *keys: str):
    for k in keys:
        v = project.get(k)
        if v is not None:
            return v
    return None


async def _notify_user(
    tg_id: int,
    login: str,
    bot: Bot,
    s21: S21Client,
    config: Config,
    thresholds_minutes: list[int],
) -> None:
    try:
        projects = await s21.get_projects(login, status="IN_REVIEWS", limit=20)
    except Exception as exc:
        logger.debug("Review fetch failed for %s: %s", login, exc)
        return

    now = datetime.now(timezone.utc)

    for project in projects:
        # Find review datetime
        review_dt = None
        for field in _DATE_FIELDS:
            review_dt = _parse_dt(project.get(field))
            if review_dt:
                break
        if not review_dt:
            continue

        delta_seconds = (review_dt - now).total_seconds()
        if delta_seconds < 0:
            continue

        pid = str(_get(project, *_ID_FIELDS) or project.get("title", "?"))
        title = _get(project, "title", "name", "goalName") or "Проект"
        checker = _get(project, *_CHECKER_FIELDS)

        for minutes in sorted(thresholds_minutes, reverse=True):
            key = (login, pid, minutes)
            if key in _notified:
                continue
            if delta_seconds <= minutes * 60:
                _notified.add(key)

                hours = minutes // 60
                if hours >= 2:
                    header = REVIEW_REMINDER_HOURS.format(hours=hours)
                elif hours == 1:
                    header = REVIEW_REMINDER_HOUR
                else:
                    header = REVIEW_REMINDER_MINUTES.format(minutes=minutes)

                lines = [
                    header,
                    "",
                    REVIEW_PROJECT.format(title=title),
                    REVIEW_TIME.format(time=format_local_dt(review_dt, config)),
                ]
                if checker:
                    lines.append(REVIEW_CHECKER.format(login=checker))

                try:
                    await bot.send_message(
                        chat_id=tg_id,
                        text="\n".join(lines),
                        parse_mode="HTML",
                    )
                    logger.info(
                        "Review reminder: login=%s pid=%s threshold=%dmin",
                        login, pid, minutes,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to send review reminder to %d (%s): %s",
                        tg_id, login, exc,
                    )
                break


async def run_review_poller(bot: Bot, s21: S21Client, config: Config) -> None:
    thresholds = config.review_notify_minutes or [60, 15]
    poll_interval = config.api_poll_interval
    logger.info(
        "Review poller started, thresholds=%s min, interval=%ds",
        thresholds, poll_interval,
    )

    while True:
        await asyncio.sleep(poll_interval)
        try:
            users = await UserRepo.get_approved_users()
            for user in users:
                login = user["school_login"]
                tg_id = user["tg_id"]
                if not login or not tg_id:
                    continue
                await _notify_user(tg_id, login, bot, s21, config, thresholds)
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Review poller error: %s", exc)
