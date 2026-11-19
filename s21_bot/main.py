from __future__ import annotations
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from s21_bot.config import apply_config_overrides, get_legacy_runtime_overrides, load_config
from s21_bot.db import BotSettingsRepo, init_db
from s21_bot.db.models import set_db_path
from s21_bot.handlers import setup_routers
from s21_bot.handlers.bridge_chats import router as bridge_chats_router
from s21_bot.handlers.kryaken import router as kryaken_router, setup_kryaken_menu
from s21_bot.middlewares import BanCheckMiddleware
from s21_bot.middlewares.chat_approval import ChatApprovalMiddleware
from s21_bot.services import (
    S21Client, run_events_poller, run_workstation_poller,
    run_digest, run_api_monitor, run_pending_alert,
    run_review_poller, run_cache_poller,
    RocketChatClient,
)
from s21_bot.services.bridge_client import BridgeClient
from s21_bot.services.bridge_state import BridgeState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    set_db_path(config.db_path)
    await init_db()
    stored_settings = await BotSettingsRepo.get_all()
    backfilled = get_legacy_runtime_overrides(set(stored_settings))
    for key, value in backfilled.items():
        await BotSettingsRepo.set_value(key, value)
    stored_settings.update(backfilled)
    apply_config_overrides(config, stored_settings)

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
        username=config.rc_username or config.s21_username,
        password=config.rc_password or config.s21_password,
    )
    await rc_client.start()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    try:
        from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
        await bot.set_my_commands(
            [
                BotCommand(command="menu", description="Личный кабинет"),
                BotCommand(command="profile", description="Мой профиль"),
                BotCommand(command="where", description="Где сидит пир"),
                BotCommand(command="events", description="Мероприятия"),
                BotCommand(command="start", description="Главное меню / перезапуск"),
            ],
            scope=BotCommandScopeAllPrivateChats(),
        )
    except Exception as exc:
        logger.warning("Failed to set bot commands: %s", exc)

    try:
        await setup_kryaken_menu(bot, config.kryaken_mini_app_url)
    except Exception as exc:
        logger.warning("Failed to configure Kryaken menu button: %s", exc)

    bridge_state = BridgeState()
    bridge_client = BridgeClient(
        base_url=config.bridge_api_url,
        secret=config.bridge_secret,
        bridge_state=bridge_state,
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(ChatApprovalMiddleware(bridge_state=bridge_state))
    dp.callback_query.middleware(ChatApprovalMiddleware(bridge_state=bridge_state))
    dp.my_chat_member.middleware(ChatApprovalMiddleware(bridge_state=bridge_state))
    dp["config"] = config
    dp["s21"] = s21_client
    dp["rc"] = rc_client
    dp["bridge_state"] = bridge_state
    dp["bridge_client"] = bridge_client

    dp.include_router(kryaken_router)
    dp.include_router(bridge_chats_router)
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
        bridge_client.start_sync_task(),
    ]

    logger.info("Bot starting…")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
        )
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bridge_client.close()
        await s21_client.close()
        await rc_client.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
