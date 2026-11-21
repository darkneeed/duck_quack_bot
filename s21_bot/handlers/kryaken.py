from __future__ import annotations

import html
import os
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from s21_bot.services.bridge_client import BridgeClient

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


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("link_")))
async def cmd_start_tg_link(
    message: Message,
    command: CommandObject,
    bridge_client: BridgeClient,
    config: Config | None = None,
) -> None:
    """Handle deep link from Kryaken profile to bind Telegram account."""
    arg = (command.args or "").strip()
    raw_token = arg[len("link_") :]
    from_user = message.from_user
    if not from_user:
        return

    res = await bridge_client.consume_tg_link(
        raw_token=raw_token,
        tg_id=from_user.id,
        tg_username=from_user.username,
        tg_name=from_user.full_name,
    )

    mini_app_url = get_kryaken_mini_app_url(config)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Открыть Крякен",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        ]
    )

    if res and res.get("ok"):
        login = res.get("school_login") or ""
        await message.answer(
            f"✅ Telegram успешно привязан к аккаунту Крякен <b>{html.escape(login)}</b>!",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        err = (
            (res and res.get("error"))
            or "Не удалось привязать Telegram. Ссылка устарела или недействительна."
        )
        await message.answer(f"⚠️ {err}", reply_markup=kb)


@router.callback_query(
    F.data.startswith("tracc:")
    | (F.data == "bot_transfers_info")
    | F.data.startswith("volmod:")
    | F.data.startswith("trmod:")
    | F.data.startswith("penmod:")
)
async def cb_kryaken_callback(
    callback: CallbackQuery,
    bridge_client: BridgeClient,
) -> None:
    """Forward volunteer/ADM actions to Kryaken Bridge API."""
    from_user = callback.from_user
    if not from_user or not callback.data:
        return

    res = await bridge_client.handle_callback(
        callback_data=callback.data,
        tg_id=from_user.id,
        tg_username=from_user.username,
        tg_name=from_user.full_name,
    )

    if res and res.get("ok"):
        answer = res.get("answer_text") or "Действие выполнено!"
        await callback.answer(answer, show_alert=res.get("alert", False))
        if callback.message and isinstance(callback.message, Message) and res.get("message_text"):
            try:
                await callback.message.edit_text(res["message_text"], parse_mode="HTML")
            except Exception:
                pass
    else:
        err = (
            (res and res.get("error"))
            or (res and res.get("answer_text"))
            or "Ошибка обработки запроса."
        )
        await callback.answer(err, show_alert=True)
