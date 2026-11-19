from __future__ import annotations

import os
from typing import TYPE_CHECKING

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

if TYPE_CHECKING:
    from s21_bot.config import Config
    from s21_bot.services.bridge_state import BridgeState

router = Router(name="kryaken")


def get_kryaken_mini_app_url(config: Config | None = None) -> str:
    """Resolve the Kryaken Mini App URL from configuration or environment."""
    if config and getattr(config, "kryaken_mini_app_url", None):
        return config.kryaken_mini_app_url
    return os.environ.get("KRYAKEN_MINI_APP_URL", "https://quack-21.mwnd.tech")


async def setup_kryaken_menu(bot: Bot, url: str | None = None) -> None:
    """Configure the Telegram chat menu button to launch the Kryaken Mini App."""
    target_url = url or os.environ.get("KRYAKEN_MINI_APP_URL", "https://quack-21.mwnd.tech")
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Крякен",
            web_app=WebAppInfo(url=target_url),
        )
    )


@router.message(Command("kryaken"))
async def cmd_kryaken(
    message: Message,
    config: Config | None = None,
    bridge_state: BridgeState | None = None,
) -> None:
    """Send an informational card about Kryaken with an inline Mini App button."""
    # Scope check
    if bridge_state is not None:
        scope = bridge_state.get_command_scope("kryaken").upper()
        chat_type = getattr(message.chat, "type", "private") if message.chat else "private"
        is_private = chat_type == "private"

        if scope == "OFF":
            return

        if scope == "PRIVATE" and not is_private:
            await message.answer("Эта команда доступна только в личных сообщениях с ботом.")
            return

        if scope == "PUBLIC" and is_private:
            await message.answer("Эта команда доступна только в групповых чатах.")
            return

    mini_app_url = get_kryaken_mini_app_url(config)

    card_text = (
        "<b>Платформа «Крякен» — Школа 21</b>\n\n"
        "Единая экосистема волонтёрского движения и студенческих активностей.\n\n"
        "• Управление волонтёрскими сменами и расписанием\n"
        "• Начисление и премодерация трайб-баллов\n"
        "• P2P-замены смен и верификация через Rocket.Chat\n"
        "• Каталог мероприятий и кампусный мониторинг\n\n"
        "Для входа нажмите кнопку ниже:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть Крякен",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        ]
    )

    await message.answer(
        text=card_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
