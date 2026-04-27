from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from ..config import Config
from ..db import UserRepo
from ..db.s21_cache_repo import S21CacheRepo
from ..utils.helpers import now_iso
from .s21_api import S21Client

logger = logging.getLogger(__name__)

_REFRESH_INTERVAL = 86_400
_STARTUP_DELAY    = 30


async def refresh_user_cache(login: str, s21: S21Client) -> dict:
    profile = await s21.get_full_profile(login)
    await S21CacheRepo.set(login, profile, now_iso())
    logger.debug("Cache refreshed for %s", login)
    return profile


async def get_or_refresh(login: str, s21: S21Client, ttl_hours: int = 24) -> dict | None:
    if await S21CacheRepo.is_fresh(login, ttl_hours):
        data, _ = await S21CacheRepo.get_with_age(login)
        if data:
            return data

    try:
        return await refresh_user_cache(login, s21)
    except Exception as exc:
        logger.warning("Cache refresh failed for %s: %s", login, exc)
        data, _ = await S21CacheRepo.get_with_age(login)
        return data


async def run_cache_poller(bot: Bot, s21: S21Client, config: Config) -> None:
    logger.info("Cache poller started, refresh interval=%ds", _REFRESH_INTERVAL)

    await asyncio.sleep(_STARTUP_DELAY)

    while True:
        try:
            await _refresh_all(s21)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Cache poller error: %s", exc)

        await asyncio.sleep(_REFRESH_INTERVAL)


async def _refresh_all(s21: S21Client) -> None:
    users = await UserRepo.get_approved_users()
    logger.info("Cache poller: refreshing %d users", len(users))
    ok = 0
    fail = 0
    for user in users:
        login = user["school_login"]
        if not login:
            continue
        try:
            await refresh_user_cache(login, s21)
            ok += 1
        except Exception as exc:
            logger.debug("Cache refresh failed for %s: %s", login, exc)
            fail += 1
        await asyncio.sleep(1.0)
    logger.info("Cache poller: done — ok=%d fail=%d", ok, fail)
