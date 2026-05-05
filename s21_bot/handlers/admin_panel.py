from __future__ import annotations
from dataclasses import dataclass

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

_PAGE_SIZE = 6
_RUNTIME_KEYS = get_runtime_config_keys()


class AdminSettingsFSM(StatesGroup):
    waiting_value = State()


@dataclass(frozen=True)
class SectionMeta:
    title: str
    description: str


@dataclass(frozen=True)
class SettingMeta:
    label: str
    description: str
    section: str
    example: str = ""
    is_toggle: bool = False


_SECTION_META: dict[str, SectionMeta] = {
    "topics": SectionMeta("📣 Топики и уведомления", "Куда бот отправляет сервисные сообщения."),
    "features": SectionMeta("🧩 Фичи и поведение", "Что включено и как бот ведёт себя в чате."),
    "commands": SectionMeta("⌨️ Команды", "Где доступны команды участников."),
    "api": SectionMeta("🛰 API и тайминги", "Интервалы опросов, лимиты и служебные пороги."),
    "branding": SectionMeta("🎨 Брендинг и тексты", "Ссылки, названия и пользовательские подписи."),
}

_SETTING_META: dict[str, SettingMeta] = {
    "moderation_topic_id": SettingMeta("Топик модерации", "Топик, куда приходят карточки заявок.", "topics", "Например: 4"),
    "notify_topic_id": SettingMeta("Универсальный notify-топик", "Куда слать общие сервисные уведомления.", "topics", "0 или ID топика"),
    "failed_auth_topic_id": SettingMeta("Топик ошибок авторизации", "Алерты по неудачным логинам и подозрительным попыткам.", "topics", "Например: 7"),
    "events_topic_id": SettingMeta("Топик мероприятий", "Куда публиковать анонсы событий.", "topics", "0 или ID топика"),
    "workstation_topic_id": SettingMeta("Топик кампуса", "Уведомления о местах и активности в кампусе.", "topics", "0 или ID топика"),
    "newcomer_topic_id": SettingMeta("Топик новичков", "Карточки новых участников и welcome-сообщения.", "topics", "0 или ID топика"),
    "digest_topic_id": SettingMeta("Топик дайджеста", "Куда отправлять еженедельный дайджест и админ-посты.", "topics", "0 или ID топика"),
    "invite_link_expire_seconds": SettingMeta("TTL инвайт-ссылки", "Сколько секунд живёт Telegram invite link после одобрения.", "features", "86400 = 24 часа"),
    "pending_alert_hours": SettingMeta("Порог зависших заявок", "Через сколько часов пинговать модераторов о pending-заявках.", "features", "0 чтобы отключить"),
    "enable_digest": SettingMeta("Еженедельный дайджест", "Фоновая отправка дайджеста по кампусу.", "features", is_toggle=True),
    "enable_workstation": SettingMeta("Мониторинг кампуса", "Фоновый поллер мест/кластеров.", "features", is_toggle=True),
    "enable_newcomer": SettingMeta("Уведомления о новичках", "Отправка newcomer-карточек в чат сообщества.", "features", is_toggle=True),
    "auto_delete_join_messages": SettingMeta("Удалять сервисные сообщения о входе", "Автоматически удалять Telegram service messages о вступлении.", "features", is_toggle=True),
    "cmd_where_scope": SettingMeta("/where", "Где доступна команда поиска участника.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "cmd_peers_scope": SettingMeta("/пиры", "Где доступна команда поиска участников по проекту.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "cmd_logtime_scope": SettingMeta("/логтайм", "Где доступна команда логтайма.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "cmd_top_scope": SettingMeta("/топ", "Где доступна команда топа по XP.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "cmd_incampus_scope": SettingMeta("/вкампусе", "Где доступна команда списка тех, кто в кампусе.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "cmd_events_scope": SettingMeta("/мероприятия", "Где доступна команда ближайших событий.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "cmd_profile_scope": SettingMeta("/profile", "Где доступна команда профиля.", "commands", "PRIVATE | PUBLIC | BOTH | OFF"),
    "api_poll_interval": SettingMeta("Базовый интервал poller'ов", "Общий интервал опроса S21 API в секундах.", "api", "Например: 120"),
    "workstation_poll_interval": SettingMeta("Интервал мониторинга кампуса", "Отдельный интервал для workstation poller.", "api", "Пусто = взять базовый"),
    "api_down_alert_minutes": SettingMeta("Порог алерта недоступности API", "Через сколько минут слать алерт, что S21 API лежит.", "api", "Например: 5"),
    "review_notify_minutes": SettingMeta("Напоминания о ревью", "Список минут через запятую, например 60,15.", "api", "Например: 60,15"),
    "s21_request_interval_ms": SettingMeta("Пауза между S21 запросами", "Минимальная задержка между стартами запросов к API.", "api", "Например: 750"),
    "s21_429_backoff_seconds": SettingMeta("Backoff после 429", "Резервная пауза, если API вернул Too Many Requests.", "api", "Например: 15"),
    "social_trust_project_ids": SettingMeta("Проекты social trust", "ID групповых проектов через запятую.", "api", "Например: 73190,73196"),
    "rules_url": SettingMeta("Ссылка на правила", "URL правил, который бот показывает пользователю.", "branding", "Полный https:// URL"),
    "platform_base_url": SettingMeta("Базовый URL платформы", "Используется для ссылок на профиль.", "branding", "Например: https://platform.21-school.ru"),
    "community_name": SettingMeta("Название сообщества", "Название чата/комьюнити в пользовательских сообщениях.", "branding", "Например: Школа 21"),
    "community_city": SettingMeta("Город сообщества", "Город в welcome и invite-сообщениях.", "branding", "Например: Волгоград"),
    "display_timezone": SettingMeta("Таймзона отображения", "Локальная таймзона для сообщений и уведомлений.", "branding", "Например: Europe/Moscow"),
    "support_contacts": SettingMeta("Контакты поддержки", "Список контактов через запятую для отказов и помощи.", "branding", "Например: @mod1,@mod2"),
}


def _format_value(key: str, value: object) -> str:
    if isinstance(value, bool):
        return "ВКЛ" if value else "ВЫКЛ"
    if value is None:
        return "—"
    if isinstance(value, int) and value == 0 and key.endswith("_topic_id"):
        return "не задан"
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(str(x) for x in value) if value else "—"
    return str(value) if value is not None and str(value) else "—"


def _short_value(key: str, value: object) -> str:
    rendered = _format_value(key, value)
    return rendered if len(rendered) <= 28 else rendered[:25] + "..."


def _section_keys(section: str) -> list[str]:
    return [key for key in _RUNTIME_KEYS if _SETTING_META[key].section == section]


def _panel_text(config: Config) -> str:
    enabled = sum(1 for key in ("enable_digest", "enable_workstation", "enable_newcomer") if getattr(config, key))
    return (
        "🛠 <b>Админ-панель</b>\n\n"
        "Управление runtime-настройками бота без правки `.env`.\n\n"
        f"• Фоновые фичи включены: <b>{enabled}/3</b>\n"
        f"• Notify-топик: <code>{_format_value('notify_topic_id', config.notify_topic_id)}</code>\n"
        f"• Порог алерта API: <b>{config.api_down_alert_minutes} мин.</b>\n"
        "• Команды и уведомления разбиты по разделам ниже"
    )


def _panel_kb(config: Config) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section in _SECTION_META:
        meta = _SECTION_META[section]
        builder.row(
            InlineKeyboardButton(
                text=meta.title,
                callback_data=f"admin_panel:section:{section}:0",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=f"Удалять сообщения о входе: {_format_value('auto_delete_join_messages', config.auto_delete_join_messages)}",
            callback_data="admin_panel:toggle:auto_delete_join_messages:features:0",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🧹 Очистить уже зафиксированные сообщения о входе",
            callback_data="admin_panel:cleanup_join_messages",
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ К кабинету", callback_data="cabinet:home"))
    return builder.as_markup()


def _section_text(config: Config, section: str, page: int) -> str:
    meta = _SECTION_META[section]
    keys = _section_keys(section)
    total_pages = max(1, (len(keys) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    chunk = keys[start:start + _PAGE_SIZE]
    lines = [f"{meta.title}\n", meta.description, ""]
    for key in chunk:
        setting = _SETTING_META[key]
        lines.append(f"• <b>{setting.label}</b>: <code>{_format_value(key, getattr(config, key))}</code>")
    lines.append("")
    lines.append(f"Страница <b>{page + 1}/{total_pages}</b>. Выберите параметр для просмотра или изменения.")
    return "\n".join(lines)


def _section_kb(config: Config, section: str, page: int) -> InlineKeyboardMarkup:
    keys = _section_keys(section)
    total_pages = max(1, (len(keys) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    chunk = keys[start:start + _PAGE_SIZE]
    builder = InlineKeyboardBuilder()
    for key in chunk:
        setting = _SETTING_META[key]
        label = f"{setting.label}: {_short_value(key, getattr(config, key))}"
        if len(label) > 62:
            label = label[:59] + "..."
        builder.row(InlineKeyboardButton(text=label, callback_data=f"admin_panel:detail:{key}:{section}:{page}"))

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_panel:section:{section}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="admin_panel:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_panel:section:{section}:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ К панели", callback_data="admin_panel:back"))
    return builder.as_markup()


def _detail_text(config: Config, key: str) -> str:
    meta = _SETTING_META[key]
    parts = [
        f"⚙️ <b>{meta.label}</b>",
        "",
        meta.description,
        "",
        f"Ключ: <code>{key}</code>",
        f"Текущее значение: <code>{_format_value(key, getattr(config, key))}</code>",
    ]
    if meta.example:
        parts.append(f"Пример: <code>{meta.example}</code>")
    return "\n".join(parts)


def _detail_kb(config: Config, key: str, section: str, page: int) -> InlineKeyboardMarkup:
    meta = _SETTING_META[key]
    builder = InlineKeyboardBuilder()
    if meta.is_toggle:
        new_state = "0" if getattr(config, key) else "1"
        action = "Выключить" if getattr(config, key) else "Включить"
        builder.row(
            InlineKeyboardButton(
                text=f"{action}",
                callback_data=f"admin_panel:toggle:{key}:{section}:{page}:{new_state}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Ввести новое значение",
            callback_data=f"admin_panel:edit:{key}:{section}:{page}",
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ К разделу", callback_data=f"admin_panel:section:{section}:{page}"))
    return builder.as_markup()


async def _save_setting(config: Config, key: str, raw_value: str, updated_by: int | None) -> object:
    parsed = set_config_value(config, key, raw_value)
    serialized = serialize_runtime_config(config).get(key, str(parsed))
    await BotSettingsRepo.set_value(key, serialized, updated_by)
    return parsed


@router.message(IsAdminInPrivateChat(), Command("admin"))
async def cmd_admin_panel(message: Message, config: Config, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_panel_text(config), parse_mode="HTML", reply_markup=_panel_kb(config))


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "cabinet:admin_panel")
async def cb_open_admin_panel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(_panel_text(config), parse_mode="HTML", reply_markup=_panel_kb(config))
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:back")
async def cb_back_to_panel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(_panel_text(config), parse_mode="HTML", reply_markup=_panel_kb(config))
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data.startswith("admin_panel:section:"))
async def cb_open_section(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await state.clear()
    _, _, section, page_raw = callback.data.split(":", 3)
    page = int(page_raw)
    await callback.message.edit_text(
        _section_text(config, section, page),
        parse_mode="HTML",
        reply_markup=_section_kb(config, section, page),
    )
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data.startswith("admin_panel:detail:"))
async def cb_setting_detail(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await state.clear()
    _, _, _, key, section, page_raw = callback.data.split(":")
    page = int(page_raw)
    await callback.message.edit_text(
        _detail_text(config, key),
        parse_mode="HTML",
        reply_markup=_detail_kb(config, key, section, page),
    )
    await safe_callback_answer(callback)


@router.callback_query(IsAdminInPrivateChatCB(), F.data.startswith("admin_panel:toggle:"))
async def cb_toggle_auto_delete(callback: CallbackQuery, config: Config) -> None:
    parts = callback.data.split(":")
    key = parts[2]
    section = parts[3]
    page = int(parts[4])
    raw_value = parts[5] if len(parts) > 5 else ("0" if getattr(config, key) else "1")
    await _save_setting(config, key, raw_value, callback.from_user.id)
    if section in _SECTION_META:
        await callback.message.edit_text(
            _detail_text(config, key),
            parse_mode="HTML",
            reply_markup=_detail_kb(config, key, section, page),
        )
    else:
        await callback.message.edit_text(_panel_text(config), parse_mode="HTML", reply_markup=_panel_kb(config))
    await safe_callback_answer(callback, "Настройка обновлена")


@router.callback_query(IsAdminInPrivateChatCB(), F.data == "admin_panel:cleanup_join_messages")
async def cb_cleanup_join_messages(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    deleted, failed = await delete_tracked_join_messages(bot, config.community_chat_id)
    await safe_callback_answer(callback)
    await callback.message.answer(
        f"🧹 Очистка сообщений о вступлении завершена.\nУдалено: <b>{deleted}</b>\nНе удалено: <b>{failed}</b>",
        parse_mode="HTML",
    )


@router.callback_query(IsAdminInPrivateChatCB(), F.data.startswith("admin_panel:edit:"))
async def cb_pick_setting(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    _, _, _, key, section, page = callback.data.split(":")
    meta = _SETTING_META[key]
    current = _format_value(key, getattr(config, key))
    await state.set_state(AdminSettingsFSM.waiting_value)
    await state.update_data(setting_key=key, setting_page=int(page), setting_section=section)
    prompt = (
        f"✏️ <b>{meta.label}</b>\n"
        f"Текущее значение: <code>{current}</code>\n"
        f"{meta.description}\n"
    )
    if meta.example:
        prompt += f"\nПример: <code>{meta.example}</code>\n"
    prompt += "\nОтправьте новое значение одним сообщением."
    await callback.message.answer(
        prompt,
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.message(IsAdminInPrivateChat(), AdminSettingsFSM.waiting_value)
async def msg_update_setting(message: Message, state: FSMContext, config: Config) -> None:
    raw = (message.text or "").strip()
    data = await state.get_data()
    key = data.get("setting_key")
    page = int(data.get("setting_page", 0))
    section = data.get("setting_section")
    if not key:
        await state.clear()
        await message.answer("Сессия изменения устарела. Откройте настройки заново.")
        return
    try:
        parsed = await _save_setting(config, key, raw, message.from_user.id if message.from_user else None)
    except Exception as exc:
        await message.answer(f"❌ Не удалось сохранить <code>{key}</code>: <code>{exc}</code>", parse_mode="HTML")
        return

    await state.clear()
    await message.answer(
        f"✅ <b>{_SETTING_META[key].label}</b> обновлён: <code>{_format_value(key, parsed)}</code>",
        parse_mode="HTML",
        reply_markup=_detail_kb(config, key, section, page) if section in _SECTION_META else _panel_kb(config),
    )
