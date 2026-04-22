from __future__ import annotations
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from s21_bot.config import load_config
from s21_bot.db import init_db
from s21_bot.handlers import setup_routers
from s21_bot.middlewares import BanCheckMiddleware
from s21_bot.services import (
    S21Client, run_events_poller, run_workstation_poller,
    run_digest, run_api_monitor, run_pending_alert,
    run_review_poller, run_cache_poller,
    RocketChatClient,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    await init_db()

    s21_client = S21Client(
        config.s21_username,
        config.s21_password,
        request_interval_ms=config.s21_request_interval_ms,
        backoff_seconds=config.s21_429_backoff_seconds,
    )
    await s21_client.start()

    rc_client = RocketChatClient(
        base_url=config.rc_base_url,
        user_id=config.rc_user_id,
        auth_token=config.rc_auth_token,
    )
    await rc_client.start()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(BanCheckMiddleware())
    dp["config"] = config
    dp["s21"] = s21_client
    dp["rc"] = rc_client

    dp.include_router(setup_routers())

    loop = asyncio.get_event_loop()
    tasks = [
        loop.create_task(run_events_poller(bot, s21_client, config)),
        loop.create_task(run_workstation_poller(bot, s21_client, config)),
        loop.create_task(run_digest(bot, s21_client, config)),
        loop.create_task(run_api_monitor(bot, s21_client, config, config.api_down_alert_minutes)),
        loop.create_task(run_pending_alert(bot, config)),
        loop.create_task(run_review_poller(bot, s21_client, config)),
        loop.create_task(run_cache_poller(bot, s21_client, config)),
    ]

    logger.info("Bot starting…")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await s21_client.close()
        await rc_client.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
