from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import Config, get_runtime_config_keys, serialize_runtime_config, set_config_value
from ..db import BotSettingsRepo
from ..services.join_cleanup import delete_tracked_join_messages
from ..utils.telegram import safe_callback_answer
from .admin_common import IsAdminInPrivateChat, IsAdminInPrivateChatCB

router = Router(name="admin_panel")

_PAGE_SIZE = 8
_RUNTIME_KEYS = get_runtime_config_keys()


class AdminSettingsFSM(StatesGroup):
    waiting_value = State()


def _format_value(key: str, value: object) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(str(x) for x in value) if value else "—"
    return str(value) if value is not None and str(value) else "—"


def _panel_kb(config: Config) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    auto_delete = "✅" if config.auto_delete_join_messages else "❌"
    builder.row(
        InlineKeyboardButton(
            text=f"Удалять вступления: {auto_delete}",
            callback_data="admin_panel:toggle:auto_delete_join_messages",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🧹 Удалить уже зафиксированные вступления",
            callback_data="admin_panel:cleanup_join_messages",
        )
    )
    builder.row(InlineKeyboardButton(text="⚙️ Редактировать настройки", callback_data="admin_panel:settings:0"))
    return builder.as_markup()


def _settings_kb(config: Config, page: int) -> InlineKeyboardMarkup:
    keys = list(_RUNTIME_KEYS)
    total_pages = max(1, (len(keys) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    chunk = keys[start:start + _PAGE_SIZE]

    builder = InlineKeyboardBuilder()
    for key in chunk:
        value = _format_value(key, getattr(config, key))
        label = f"{key} = {value}"
        if len(label) > 62:
            label = label[:59] + "..."
        builder.row(InlineKeyboardButton(text=label, callback_data=f"admin_panel:key:{key}:{page}"))

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_panel:settings:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="admin_panel:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_panel:settings:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel:back"))
    return builder.as_markup()


@router.message(IsAdminInPrivateChat(), Command("admin"))
async def cmd_admin_panel(message: Message, config: Config, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=_panel_kb(config))


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "cabinet:admin_panel")
async def cb_open_admin_panel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=_panel_kb(config))
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:back")
async def cb_back_to_panel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=_panel_kb(config))
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data.startswith("admin_panel:settings:"))
async def cb_open_settings(callback: CallbackQuery, config: Config) -> None:
    page = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "⚙️ <b>Настройки бота</b>\nВыберите параметр для изменения.",
        parse_mode="HTML",
        reply_markup=_settings_kb(config, page),
    )
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:toggle:auto_delete_join_messages")
async def cb_toggle_auto_delete(callback: CallbackQuery, config: Config) -> None:
    new_value = not config.auto_delete_join_messages
    set_config_value(config, "auto_delete_join_messages", "1" if new_value else "0")
    await BotSettingsRepo.set_value("auto_delete_join_messages", "1" if new_value else "0", callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=_panel_kb(config))
    await safe_callback_answer(callback, "Настройка обновлена")


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:cleanup_join_messages")
async def cb_cleanup_join_messages(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    deleted, failed = await delete_tracked_join_messages(bot, config.community_chat_id)
    await safe_callback_answer(callback)
    await callback.message.answer(
        f"🧹 Очистка сообщений о вступлении завершена.\nУдалено: <b>{deleted}</b>\nНе удалено: <b>{failed}</b>",
        parse_mode="HTML",
    )


@router.callback_query(IsAdminInPrivateChatCB(), F.data.startswith("admin_panel:key:"))
async def cb_pick_setting(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    _, _, _, key, page = callback.data.split(":")
    current = _format_value(key, getattr(config, key))
    await state.set_state(AdminSettingsFSM.waiting_value)
    await state.update_data(setting_key=key, setting_page=int(page))
    await callback.message.answer(
        f"✏️ <b>{key}</b>\nТекущее значение: <code>{current}</code>\n\nОтправьте новое значение одним сообщением.",
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.message(IsAdminInPrivateChat(), AdminSettingsFSM.waiting_value)
async def msg_update_setting(message: Message, state: FSMContext, config: Config) -> None:
    raw = (message.text or "").strip()
    data = await state.get_data()
    key = data.get("setting_key")
    page = int(data.get("setting_page", 0))
    if not key:
        await state.clear()
        await message.answer("Сессия изменения устарела. Откройте настройки заново.")
        return
    try:
        parsed = set_config_value(config, key, raw)
    except Exception as exc:
        await message.answer(f"❌ Не удалось сохранить <code>{key}</code>: <code>{exc}</code>", parse_mode="HTML")
        return

    serialized = serialize_runtime_config(config).get(key, str(parsed))
    await BotSettingsRepo.set_value(key, serialized, message.from_user.id if message.from_user else None)
    await state.clear()
    await message.answer(
        f"✅ <b>{key}</b> обновлён: <code>{_format_value(key, parsed)}</code>",
        parse_mode="HTML",
        reply_markup=_settings_kb(config, page),
    )
