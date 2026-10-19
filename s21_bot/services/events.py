from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from ..config import Config
from ..utils.datetime import format_local_dt
from ..utils.collections import BoundedSet
from ..utils.telegram import send_message_with_topic
from .s21_api import S21Client

logger = logging.getLogger(__name__)
_seen_event_ids: BoundedSet[str] = BoundedSet(maxsize=10_000)


def _fmt_date(raw: str, config: Config) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return format_local_dt(dt, config)
    except Exception:
        return raw


def _format_event(event: dict, config: Config) -> str:
    name = event.get("name") or "Мероприятие"
    description = event.get("description") or ""
    location = event.get("location") or ""
    start_raw = event.get("startDateTime") or ""
    end_raw = event.get("endDateTime") or ""
    organizers = event.get("organizers") or []
    capacity = event.get("capacity")
    registered = event.get("registerCount")
    event_type = event.get("type") or ""

    lines = [f"📅 <b>{name}</b>"]
    if event_type:
        lines.append(f"🏷 <i>{event_type}</i>")
    if start_raw:
        time_line = f"🕐 <b>Начало:</b> {_fmt_date(start_raw, config)}"
        if end_raw:
            time_line += f" — {_fmt_date(end_raw, config)}"
        lines.append(time_line)
    if location:
        lines.append(f"📍 <b>Место:</b> {location}")
    if organizers:
        lines.append(f"👤 <b>Организатор:</b> {', '.join(organizers)}")
    if capacity:
        reg_str = f"{registered}/{capacity}" if registered is not None else str(capacity)
        lines.append(f"👥 <b>Мест:</b> {reg_str}")
    if description:
        short = description[:400] + ("…" if len(description) > 400 else "")
        lines.append(f"\n{short}")
    return "\n".join(lines)


def _time_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    to = now + timedelta(days=30)
    return (
        now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        to.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


async def run_events_poller(bot: Bot, s21: S21Client, config: Config) -> None:
    poll_interval = config.api_poll_interval
    logger.info("Events poller initialized, poll interval=%ds", poll_interval)
    seeded = False

    while True:
        try:
            if not getattr(config, "enable_events", True):
                logger.debug("Events poller is disabled (enable_events=False)")
                await asyncio.sleep(poll_interval)
                continue

            events_thread_id = config.events_topic_id
            if not events_thread_id:
                logger.debug("Events poller is disabled (events_topic_id=0)")
                await asyncio.sleep(poll_interval)
                continue

            target_chat_id = getattr(config, "events_chat_id", 0) or config.community_chat_id

            if not seeded:
                try:
                    from_dt, to_dt = _time_window()
                    events = await s21.get_events(from_dt, to_dt)
                    for e in events:
                        _seen_event_ids.add(str(e.get("id", "")))
                    logger.info("Events poller: seeded %d events", len(_seen_event_ids))
                    seeded = True
                except Exception as exc:
                    logger.warning("Events poller seed failed: %s", exc)

            from_dt, to_dt = _time_window()
            events = await s21.get_events(from_dt, to_dt)
            for event in events:
                eid = str(event.get("id", ""))
                if not eid or eid in _seen_event_ids:
                    continue

                if getattr(config, "events_exclude_tribes", False):
                    event_type = (event.get("type") or "").strip().lower()
                    if event_type == "трайб":
                        _seen_event_ids.add(eid)
                        logger.info("Skipping tribe event id=%s name=%s", eid, event.get("name"))
                        continue

                text = _format_event(event, config)
                sent = await send_message_with_topic(
                    bot,
                    chat_id=target_chat_id,
                    message_thread_id=events_thread_id or None,
                    topic_name="EVENTS_TOPIC_ID",
                    topic_logger=logger,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                if sent is None and events_thread_id:
                    logger.warning(
                        "Disabling EVENTS_TOPIC_ID for fallback run: chat_id=%s thread_id=%s",
                        target_chat_id,
                        events_thread_id,
                    )
                    sent = await send_message_with_topic(
                        bot,
                        chat_id=target_chat_id,
                        message_thread_id=None,
                        topic_name="EVENTS_TOPIC_ID",
                        topic_logger=logger,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                if sent is not None:
                    _seen_event_ids.add(eid)
                    logger.info("Posted new event id=%s name=%s to chat %s thread %s", eid, event.get("name"), target_chat_id, events_thread_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Events poller error: %s", exc)

        await asyncio.sleep(poll_interval)
