from __future__ import annotations
import asyncio
import logging

from aiogram import Bot
from ..config import Config
from ..db import UserRepo
from ..utils.telegram import send_message_with_topic
from .s21_api import S21Client

logger = logging.getLogger(__name__)

_last_state: dict[str, str | None] = {}


async def run_workstation_poller(bot: Bot, s21: S21Client, config: Config) -> None:
    if not getattr(config, "enable_workstation", True):
        logger.info("Workstation poller disabled (ENABLE_WORKSTATION=0)")
        return
    if not config.workstation_topic_id:
        logger.info("Workstation poller disabled (WORKSTATION_TOPIC_ID=0)")
        return

    poll_interval = config.workstation_poll_interval or config.api_poll_interval
    logger.info("Workstation poller started, interval=%ds", poll_interval)

    try:
        await _poll_once(bot, s21, config, announce=False)
    except Exception as exc:
        logger.warning("Workstation seed failed: %s", exc)

    while True:
        await asyncio.sleep(poll_interval)
        try:
            await _poll_once(bot, s21, config, announce=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Workstation poller error: %s", exc)


async def _poll_once(bot: Bot, s21: S21Client, config: Config, announce: bool) -> None:
    clusters = await s21.get_campus_clusters(config.s21_campus_id)
    logger.debug("Workstation: fetched %d clusters for campus %s", len(clusters), config.s21_campus_id)
    current: dict[str, str] = {}

    for cluster in clusters:
        cluster_id = cluster.get("id")
        cluster_name = cluster.get("name") or str(cluster_id)
        if not cluster_id:
            continue
        try:
            seats = await s21.get_cluster_map(cluster_id)
        except Exception as exc:
            logger.debug("Cluster map fetch failed for %s: %s", cluster_id, exc)
            continue

        for seat in seats:
            login = seat.get("login")
            row = seat.get("row", "")
            number = seat.get("number", "")
            if login:
                current[login] = f"{cluster_name} {row}{number}"

    if not announce:
        for login, seat in current.items():
            _last_state[login] = seat
        return

    approved_users = await UserRepo.get_approved_users()
    approved_logins = {u["school_login"] for u in approved_users if u["school_login"]}

    for login in approved_logins:
        seat = current.get(login)
        prev = _last_state.get(login)

        if seat and seat != prev:
            sent = await send_message_with_topic(
                bot,
                chat_id=config.community_chat_id,
                message_thread_id=config.workstation_topic_id or None,
                topic_name="WORKSTATION_TOPIC_ID",
                topic_logger=logger,
                text=f"🖥 <b>{login}</b> в кампусе — <code>{seat}</code>",
                parse_mode="HTML",
            )
            if sent is not None:
                logger.info("User %s now at seat %s", login, seat)

        elif prev and not seat:
            logger.info("User %s left campus", login)

        _last_state[login] = seat
