from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

import aiohttp
from aiogram import Bot
from ..config import Config
from ..utils.datetime import format_now_local
from ..utils.telegram import send_message_with_topic
from .s21_api import S21Client

logger = logging.getLogger(__name__)
_CHECK_INTERVAL = 60


async def run_api_monitor(bot: Bot, s21: S21Client, config: Config, threshold_minutes: int = 5) -> None:
    logger.info("API monitor started, threshold=%dmin", threshold_minutes)
    _down_since: float | None = None
    _alerted = False
    _recovered_alerted = False

    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            await s21.get_participant(config.s21_username)
            if _down_since is not None:
                down_minutes = int((time.monotonic() - _down_since) / 60)
                if not _recovered_alerted:
                    await _send(bot, config,
                        f"✅ <b>S21 API восстановлен</b>\n"
                        f"Время недоступности: ~{down_minutes} мин."
                    )
                _down_since = None
                _alerted = False
                _recovered_alerted = False
            logger.debug("API monitor: OK")
        except asyncio.CancelledError:
            raise
        except aiohttp.ClientResponseError as exc:
            if exc.status != 429:
                if _down_since is None:
                    _down_since = time.monotonic()
                    logger.warning("API monitor: S21 API down: %s", exc)

                down_seconds = time.monotonic() - _down_since
                if not _alerted and down_seconds >= threshold_minutes * 60:
                    _alerted = True
                    down_str = format_now_local(config, "%H:%M")
                    await _send(bot, config,
                        f"🚨 <b>S21 API недоступен</b>\n"
                        f"С: {down_str} (>{threshold_minutes} мин)\n"
                        f"Ошибка: <code>{exc}</code>"
                    )
                continue

            if _down_since is not None:
                down_minutes = int((time.monotonic() - _down_since) / 60)
                await _send(
                    bot,
                    config,
                    f"✅ <b>S21 API восстановлен</b>\n"
                    f"Время недоступности: ~{down_minutes} мин.\n"
                    f"ℹ️ Сейчас API отвечает <code>429 Too Many Requests</code>.",
                )
                _down_since = None
                _alerted = False
                _recovered_alerted = False
            logger.warning("API monitor: S21 API rate limited: %s", exc)
        except Exception as exc:
            if _down_since is None:
                _down_since = time.monotonic()
                logger.warning("API monitor: S21 API down: %s", exc)

            down_seconds = time.monotonic() - _down_since
            if not _alerted and down_seconds >= threshold_minutes * 60:
                _alerted = True
                down_str = format_now_local(config, "%H:%M")
                await _send(bot, config,
                    f"🚨 <b>S21 API недоступен</b>\n"
                    f"С: {down_str} (>{threshold_minutes} мин)\n"
                    f"Ошибка: <code>{exc}</code>"
                )


async def _send(bot: Bot, config: Config, text: str) -> None:
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.notify_topic_id or config.moderation_topic_id or None,
            topic_name="NOTIFY_TOPIC_ID/MODERATION_TOPIC_ID",
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("API monitor: failed to send alert: %s", exc)
