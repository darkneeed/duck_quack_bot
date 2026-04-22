from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from ..config import Config
from ..db.models import get_db
from ..utils.telegram import send_message_with_topic

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 900
_alerted_app_ids: set[int] = set()


async def run_pending_alert(bot: Bot, config: Config) -> None:
    if not config.pending_alert_hours:
        logger.info("Pending alert disabled (PENDING_ALERT_HOURS=0)")
        return

    logger.info(
        "Pending alert poller started, threshold=%dh, interval=%ds",
        config.pending_alert_hours, _CHECK_INTERVAL,
    )

    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            await _check_once(bot, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Pending alert poller error: %s", exc)


async def _check_once(bot: Bot, config: Config) -> None:
    threshold_hours = config.pending_alert_hours
    async with get_db() as db:
        async with db.execute(
            """
            SELECT id, tg_id, tg_name, school_login, status, submitted_at, moderation_msg_id
            FROM applications
            WHERE status IN ('pending', 'waiting_votes')
              AND submitted_at <= datetime('now', ? || ' hours')
            ORDER BY submitted_at ASC
            """,
            (f"-{threshold_hours}",),
        ) as cur:
            rows = await cur.fetchall()

    for app in rows:
        app_id: int = app["id"]
        if app_id in _alerted_app_ids:
            continue

        _alerted_app_ids.add(app_id)

        status = app["status"]
        login = app["school_login"] or "?"
        tg_name = app["tg_name"] or "?"
        submitted_at = app["submitted_at"] or ""

        wait_str = ""
        try:
            dt = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            delta = datetime.now(timezone.utc) - dt
            hours = int(delta.total_seconds() // 3600)
            wait_str = f"{hours}ч"
        except Exception:
            wait_str = f">{threshold_hours}ч"

        status_label = {
            "pending": "ожидает модератора",
            "waiting_votes": "ожидает голосов тиммейтов",
        }.get(status, status)

        admin_mentions = " ".join(f"<a href='tg://user?id={uid}'>&#8204;</a>" for uid in config.admin_ids)

        text = (
            f"⏰ <b>Заявка зависла</b> {admin_mentions}\n\n"
            f"📋 Заявка: <b>#{app_id}</b>\n"
            f"🔑 Кандидат: <code>{login}</code> ({tg_name})\n"
            f"📊 Статус: {status_label}\n"
            f"🕐 Ожидает: <b>{wait_str}</b>"
        )

        try:
            sent = await send_message_with_topic(
                bot,
                chat_id=config.moderation_chat_id,
                message_thread_id=config.notify_topic_id or config.moderation_topic_id or None,
                topic_name="NOTIFY_TOPIC_ID/MODERATION_TOPIC_ID",
                topic_logger=logger,
                text=text,
                parse_mode="HTML",
            )
            if sent is not None:
                logger.info(
                    "Pending alert sent for app #%d (status=%s, wait=%s)",
                    app_id, status, wait_str,
                )
        except Exception as exc:
            logger.error("Failed to send pending alert for app #%d: %s", app_id, exc)
            _alerted_app_ids.discard(app_id)  # retry next cycle
