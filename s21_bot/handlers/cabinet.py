from __future__ import annotations

import io
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..command_catalog import render_cabinet_help
from ..config import Config
from ..db import UserRepo
from ..db.s21_cache_repo import S21CacheRepo
from ..db.invite_code_repo import InviteCodeRepo
from ..keyboards import (
    cabinet_back_kb,
    cabinet_cancel_input_kb,
    cabinet_home_kb,
    cabinet_profile_card_contact_kb,
    cabinet_profile_card_kb,
)
from ..services import S21Client
from ..services.cache_poller import get_or_refresh
from ..services.invite_code_service import build_bot_link, create_invite_code
from ..strings import (
    CABINET_CODES_HEADER,
    CABINET_GENCODE_ERROR,
    CABINET_NO_CODES,
    INVITE_GENCODE_CAPTION,
    ONLY_APPROVED,
    PEER_CARD_COMMENT_REMOVED,
    PEER_CARD_COMMENT_SAVED,
    PEER_CARD_CONTACT_PROMPT,
    PEER_CARD_CONTACT_SAVED,
    PEER_CARD_EDIT_CANCELLED,
    PEER_CARD_EDIT_COMMENT_PROMPT,
    PEER_CARD_EDIT_PHOTO_PROMPT,
    PEER_CARD_MAX_LINK_INVALID,
    PEER_CARD_MAX_LINK_PROMPT,
    PEER_CARD_MAX_LINK_SAVED,
    PEER_CARD_MAX_REQUIRED,
    PEER_CARD_PHOTO_EXPECTED,
    PEER_CARD_PHOTO_REMOVED,
    PEER_CARD_PHOTO_SAVED,
    PROFILE_ERROR,
    WHERE_IN_CAMPUS,
    WHERE_NOT_IN_CAMPUS,
    WHERE_ERROR,
    PEER_CARD_NOT_FOUND,
    tg_mention,
)
from ..utils.branding import build_profile_url
from ..utils.profile import (
    build_profile_card_submission_text,
    can_send_text_as_photo_caption,
    fit_text_for_photo_caption,
    normalize_preferred_contact,
    render_full_peer_card_text,
    render_profile_text,
    render_peer_card_editor_text,
)
from ..utils.states import ProfileCardFSM
from ..utils.telegram import safe_callback_answer, send_message_with_topic, send_photo_with_topic
from .where import _find_best_project_match, _project_display_name

logger = logging.getLogger(__name__)
router = Router(name="cabinet")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

_PROFILE_CARD_COMMENT_LIMIT = 500
_PROFILE_CARD_CONTACTS = {"tg", "max", "rocket"}
_PROFILE_CARD_MAX_LINK_PREFIXES = ("http://", "https://")
_CABINET_COMMAND_INPUT_HINTS: dict[str, str] = {
    "where": "Введите логин участника (например: <code>kylaknap</code>).",
    "peer": "Введите логин участника (например: <code>kylaknap</code>).",
    "peers": "Введите название или код проекта (например: <code>DSB7</code>).",
    "logtime": "Введите логин участника (например: <code>kylaknap</code>).",
}


class CabinetCommandsFSM(StatesGroup):
    waiting_input = State()


def _scope_allows_private(scope: str) -> bool:
    return scope in {"PRIVATE", "BOTH"}


def _commands_section_text(config: Config) -> str:
    commands_without_input = [
        "• <b>Без параметров:</b> профиль, мой логтайм, топ, в кампусе, мероприятия",
    ]
    commands_with_input = [
        "• <b>С вводом:</b> where, пир, пиры, логтайм по логину",
    ]
    lines = [
        "❓ <b>Команды</b>\n",
        "Нажмите кнопку, чтобы выполнить аналог команды прямо из меню.",
        "",
    ]
    lines.extend(commands_without_input)
    lines.extend(commands_with_input)
    lines.append("")
    lines.append("Текущий текстовый справочник:")
    lines.append(render_cabinet_help(config))
    return "\n".join(lines)


def _cabinet_commands_kb(config: Config) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 /profile", callback_data="cabinet:cmd:profile")
    builder.button(text="🕐 /логтайм (мой)", callback_data="cabinet:cmd:logtime_me")
    if _scope_allows_private(config.cmd_where_scope):
        builder.button(text="🖥 /where", callback_data="cabinet:cmd_input:where")
    if _scope_allows_private(config.cmd_peer_scope):
        builder.button(text="🪪 /пир", callback_data="cabinet:cmd_input:peer")
    if _scope_allows_private(config.cmd_peers_scope):
        builder.button(text="👥 /пиры", callback_data="cabinet:cmd_input:peers")
    if _scope_allows_private(config.cmd_logtime_scope):
        builder.button(text="🕐 /логтайм (логин)", callback_data="cabinet:cmd_input:logtime")
    if _scope_allows_private(config.cmd_top_scope):
        builder.button(text="🏆 /топ", callback_data="cabinet:cmd:top")
    if _scope_allows_private(config.cmd_incampus_scope):
        builder.button(text="🏙 /вкампусе", callback_data="cabinet:cmd:incampus")
    if _scope_allows_private(config.cmd_events_scope):
        builder.button(text="📅 /мероприятия", callback_data="cabinet:cmd:events")
    builder.button(text="⬅️ Назад", callback_data="cabinet:home")
    builder.adjust(1)
    return builder.as_markup()


def _cabinet_cmd_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ К командам", callback_data="cabinet:help"))
    return builder.as_markup()


def _cabinet_cmd_home_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 На главную", callback_data="cabinet:home"))
    return builder.as_markup()


def _cabinet_cmd_input_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cabinet:cmd_input_cancel"))
    return builder.as_markup()


async def _edit_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
    disable_web_page_preview: bool = True,
) -> None:
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            return
        await callback.message.answer(
            text,
            parse_mode="HTML",
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=reply_markup,
        )
        await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


async def _run_profile_text(user, s21: S21Client, config: Config) -> str:
    login = user["school_login"]
    profile = await s21.get_full_profile(login)
    return render_profile_text(login, profile, build_profile_url(login, config))


async def _run_logtime_text(login: str, s21: S21Client) -> str:
    hours = await s21.get_logtime(login)
    if hours is None:
        return f"📭 Данные о логтайме для <code>{login}</code> недоступны."
    h = int(hours)
    m = int((hours - h) * 60)
    time_str = f"{h} ч. {m} мин." if m else f"{h} ч."
    return (
        "🕐 <b>Среднее время в кампусе</b>\n\n"
        f"👤 <code>{login}</code>\n"
        f"📊 За неделю: <b>{time_str}</b>"
    )


async def _run_where_text(login: str, s21: S21Client) -> str:
    data = await s21.get_workstation(login)
    if not data:
        return WHERE_NOT_IN_CAMPUS.format(login=login)
    cluster = data.get("clusterName") or data.get("cluster") or data.get("cluster_name") or data.get("hostName") or ""
    row = data.get("row") or data.get("workstationRow") or ""
    number = data.get("number") or data.get("workstationNumber") or data.get("num") or ""
    if not cluster and not row and not number:
        return WHERE_NOT_IN_CAMPUS.format(login=login)
    seat = f"{cluster} {row}{number}".strip()
    return WHERE_IN_CAMPUS.format(login=login, seat=seat)


async def _run_peers_text(query: str, s21: S21Client) -> str:
    approved = await UserRepo.get_approved_users()
    matches: list[tuple[str, int, str | None, str | None, dict, float]] = []
    for user in approved:
        login = user["school_login"]
        if not login:
            continue
        profile = await S21CacheRepo.get(login)
        all_projects = list((profile or {}).get("active_projects") or [])
        if not all_projects:
            all_projects = await s21.get_active_projects(login)
        best_project, best_score = _find_best_project_match(query, all_projects)
        if best_project and best_score >= 0.65:
            matches.append((login, user["tg_id"], user["tg_username"], user["tg_name"], best_project, best_score))
    if not matches:
        return f"📭 Никто из участников не работает над <code>{query}</code>."
    best_match_name = _project_display_name(max(matches, key=lambda item: item[5])[4], query)
    mentions = [
        tg_mention(tg_id_m, login, tg_username=tg_username_m, tg_name=tg_name_m)
        for login, tg_id_m, tg_username_m, tg_name_m, _, _ in sorted(matches, key=lambda item: item[0])
    ]
    return (
        f"👥 <b>Работают над «{best_match_name}»</b> — {len(matches)}\n\n"
        + ", ".join(mentions)
    )


async def _run_top_text(caller_tg_id: int) -> str:
    approved = await UserRepo.get_approved_users()
    scores: list[tuple[str, int, int, str]] = []
    for user in approved:
        login = user["school_login"]
        if not login:
            continue
        data = await S21CacheRepo.get(login)
        if not data:
            continue
        info = data.get("info") or {}
        coalition = (data.get("coalition") or {}).get("name") or ""
        xp = info.get("expValue", 0) or 0
        level = info.get("level", 0) or 0
        scores.append((login, xp, level, coalition))
    if not scores:
        return "📭 Нет данных. Кэш ещё не заполнен — попробуйте позже."
    scores.sort(key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"] + ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    login_to_user = {u["school_login"]: u for u in approved if u["school_login"]}

    def fmt_row(i: int, login: str, xp: int, level: int, coalition: str) -> str:
        medal = medals[i] if i < len(medals) else f"{i + 1}."
        xp_str = f"{xp:,}".replace(",", " ")
        tribe = f" · {coalition}" if coalition else ""
        user = login_to_user.get(login)
        name = tg_mention(
            user["tg_id"] if user else None,
            login,
            tg_username=user["tg_username"] if user else None,
            tg_name=user["tg_name"] if user else None,
        )
        return f"{medal} {name}{tribe} — {xp_str} XP (ур. {level})"

    lines = [f"🏆 <b>Топ-10 из {len(scores)}</b>\n"]
    for i, (login, xp, level, coalition) in enumerate(scores[:10]):
        lines.append(fmt_row(i, login, xp, level, coalition))
    caller = await UserRepo.get_by_tg_id(caller_tg_id)
    caller_login = caller["school_login"] if caller else None
    if caller_login:
        caller_pos = next((i for i, (lg, *_) in enumerate(scores) if lg == caller_login), None)
        if caller_pos is not None and caller_pos >= 10:
            login, xp, level, coalition = scores[caller_pos]
            lines.append("")
            lines.append("— — —")
            lines.append(fmt_row(caller_pos, login, xp, level, coalition))
    return "\n".join(lines)


async def _run_incampus_text(config: Config, s21: S21Client) -> str:
    approved = await UserRepo.get_approved_users()
    approved_logins = {u["school_login"] for u in approved if u["school_login"]}
    clusters = await s21.get_campus_clusters(config.s21_campus_id)
    current: dict[str, str] = {}
    for cluster in clusters:
        cluster_id = cluster.get("id")
        cluster_name = cluster.get("name") or str(cluster_id)
        seats = await s21.get_cluster_map(cluster_id)
        for seat in seats:
            login = seat.get("login")
            if login and login in approved_logins:
                row = seat.get("row", "")
                number = seat.get("number", "")
                current[login] = f"{cluster_name} {row}{number}".strip()
    if not current:
        return "🏙 Сейчас никого нет в кампусе."
    lines = [f"🖥 <b>В кампусе сейчас — {len(current)}</b>\n"]
    by_cluster: dict[str, list[str]] = {}
    for login, seat in sorted(current.items(), key=lambda x: x[1]):
        cluster = seat.split()[0] if seat else "?"
        by_cluster.setdefault(cluster, []).append(f"  <code>{login}</code> — {seat}")
    for cluster_name, entries in by_cluster.items():
        lines.append(f"<b>{cluster_name}:</b>")
        lines.extend(entries)
    return "\n".join(lines)


async def _run_events_text(config: Config, s21: S21Client) -> str:
    from datetime import datetime, timedelta, timezone
    from ..services.events import _format_event

    now = datetime.now(timezone.utc)
    to = now + timedelta(days=30)
    events = await s21.get_events(now.strftime("%Y-%m-%dT%H:%M:%SZ"), to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if not events:
        return "📭 Ближайших мероприятий не найдено."
    blocks = [_format_event(event, config) for event in events[:5]]
    return "\n\n——————\n\n".join(blocks)


def _is_admin(tg_id: int, config: Config) -> bool:
    return tg_id in config.admin_ids


def _cabinet_home_text(login: str) -> str:
    return (
        f"👋 Добро пожаловать, <b>{login}</b>!\n\n"
        "Здесь собраны основные действия:\n"
        "• профиль и карточка сообщества\n"
        "• создание инвайта\n"
        "• просмотр своих инвайтов\n"
        "• краткая справка по командам"
    )


async def _edit_cabinet_card(
    callback: CallbackQuery,
    text: str,
    config: Config,
    *,
    disable_web_page_preview: bool = True,
) -> None:
    assert callback.from_user is not None
    keyboard = cabinet_back_kb(is_admin=_is_admin(callback.from_user.id, config))
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            return
        # For media/system messages where edit_text is not allowed, keep legacy fallback.
        await callback.message.answer(
            text,
            parse_mode="HTML",
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=keyboard,
        )
        await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


def _profile_card_keyboard(user) -> object:
    return cabinet_profile_card_kb(
        has_photo=bool(user["profile_photo_file_id"]),
        has_comment=bool((user["profile_comment"] or "").strip()),
    )


async def _build_cabinet_profile_text(user, s21: S21Client, config: Config) -> str:
    login = user["school_login"]
    try:
        profile = await get_or_refresh(login, s21)
        if not profile:
            raise ValueError("empty response")
    except Exception as exc:
        return PROFILE_ERROR.format(error=exc)
    return render_peer_card_editor_text(
        login,
        profile,
        build_profile_url(login, config),
        user,
    )


async def _replace_with_profile_card(
    message: Message,
    user,
    s21: S21Client,
    config: Config,
) -> Message:
    text = await _build_cabinet_profile_text(user, s21, config)
    reply_markup = _profile_card_keyboard(user)
    if user["profile_photo_file_id"]:
        if can_send_text_as_photo_caption(text):
            sent = await message.answer_photo(
                photo=user["profile_photo_file_id"],
                caption=fit_text_for_photo_caption(text),
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            await message.answer_photo(
                photo=user["profile_photo_file_id"],
            )
            sent = await message.answer(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
    else:
        sent = await message.answer(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    await _delete_message_safe(message.bot, message.chat.id, message.message_id)
    return sent


async def _refresh_profile_message(
    message: Message,
    user,
    s21: S21Client,
    config: Config,
) -> Message:
    return await _replace_with_profile_card(message, user, s21, config)


async def _show_profile_card_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    prompt_text: str,
) -> None:
    prompt = await callback.message.answer(
        prompt_text,
        parse_mode="HTML",
        reply_markup=cabinet_cancel_input_kb(),
    )
    await state.update_data(
        profile_card_message_id=callback.message.message_id,
        profile_card_prompt_message_id=prompt.message_id,
    )


async def _delete_message_safe(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _drop_pending_moderation_message(
    *,
    bot: Bot,
    config: Config,
    message_id: int | None,
) -> None:
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=config.moderation_chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    except Exception:
        pass


async def _restore_profile_card_after_input(
    *,
    bot: Bot,
    source_message: Message,
    state: FSMContext,
    user_id: int,
    s21: S21Client,
    config: Config,
    notice_text: str | None = None,
) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("profile_card_prompt_message_id")
    card_message_id = data.get("profile_card_message_id")

    await _delete_message_safe(bot, source_message.chat.id, prompt_message_id)
    await _delete_message_safe(bot, source_message.chat.id, card_message_id)

    if notice_text:
        await source_message.answer(notice_text)

    user = await UserRepo.get_by_tg_id(user_id)
    if user and user["status"] == "approved":
        await _replace_with_profile_card(source_message, user, s21, config)

    await state.clear()


async def _require_approved_user(tg_id: int):
    user = await UserRepo.get_by_tg_id(tg_id)
    if not user or user["status"] != "approved" or not user["school_login"]:
        return None
    return user


async def _render_contact_picker(callback: CallbackQuery, user) -> None:
    selected = normalize_preferred_contact(user["preferred_contact"])
    try:
        await callback.message.edit_text(
            PEER_CARD_CONTACT_PROMPT,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=cabinet_profile_card_contact_kb(selected=selected),
        )
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            return
        await callback.message.answer(
            PEER_CARD_CONTACT_PROMPT,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=cabinet_profile_card_contact_kb(selected=selected),
        )
        await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


def _is_valid_max_profile_url(raw_url: str) -> bool:
    return raw_url.startswith(_PROFILE_CARD_MAX_LINK_PREFIXES)


async def _send_profile_card_submission_for_moderation(
    *,
    bot: Bot,
    config: Config,
    user,
    submission_type: str,
) -> int | None:
    from ..keyboards import profile_card_submission_kb

    text = build_profile_card_submission_text(user, submission_type)
    reply_markup = profile_card_submission_kb(submission_type=submission_type, tg_id=user["tg_id"])

    if submission_type == "photo":
        sent = await send_photo_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            fallback_to_chat=True,
            topic_logger=logger,
            photo=user["pending_profile_photo_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    else:
        sent = await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            fallback_to_chat=True,
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    return sent.message_id if sent else None


@router.message(Command("changetg"))
async def cmd_changetg(message: Message) -> None:
    assert message.from_user is not None
    user = await UserRepo.get_by_tg_id(message.from_user.id)
    if not user or user["status"] != "approved":
        await message.answer(ONLY_APPROVED)
        return
    await message.answer(
        f"ℹ️ Ваш текущий логин: <code>{user['school_login']}</code>\n\n"
        "Если вы хотите привязать другой Telegram-аккаунт, обратитесь к модераторам.",
        parse_mode="HTML",
    )


@router.message(Command("cancel", ignore_case=True), ProfileCardFSM.waiting_photo)
@router.message(Command("cancel", ignore_case=True), ProfileCardFSM.waiting_comment)
@router.message(Command("cancel", ignore_case=True), ProfileCardFSM.waiting_max_link)
async def cmd_cancel_profile_card_edit(
    message: Message,
    state: FSMContext,
    bot: Bot,
    s21: S21Client,
    config: Config,
) -> None:
    assert message.from_user is not None
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_EDIT_CANCELLED,
    )


@router.callback_query(F.data == "cabinet:profile")
async def cb_cabinet_profile(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await _replace_with_profile_card(callback.message, user, s21, config)


@router.callback_query(F.data == "cabinet:card_open")
async def cb_cabinet_card_open(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    await cb_cabinet_profile(callback, s21, config)


@router.callback_query(F.data == "cabinet:card_refresh")
async def cb_cabinet_card_refresh(callback: CallbackQuery, s21: S21Client, config: Config) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await _refresh_profile_message(callback.message, user, s21, config)


@router.callback_query(F.data == "cabinet:card_edit_photo")
async def cb_cabinet_card_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await state.set_state(ProfileCardFSM.waiting_photo)
    await _show_profile_card_prompt(callback, state, PEER_CARD_EDIT_PHOTO_PROMPT)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:card_edit_comment")
async def cb_cabinet_card_edit_comment(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await state.set_state(ProfileCardFSM.waiting_comment)
    await _show_profile_card_prompt(callback, state, PEER_CARD_EDIT_COMMENT_PROMPT)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:card_edit_max_link")
async def cb_cabinet_card_edit_max_link(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await state.set_state(ProfileCardFSM.waiting_max_link)
    await _show_profile_card_prompt(callback, state, PEER_CARD_MAX_LINK_PROMPT)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:card_cancel_input")
async def cb_cabinet_card_cancel_input(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    s21: S21Client,
    config: Config,
) -> None:
    assert callback.from_user is not None
    await safe_callback_answer(callback)
    await callback.message.delete()
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=callback.message,
        state=state,
        user_id=callback.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_EDIT_CANCELLED,
    )


@router.callback_query(F.data == "cabinet:card_contact")
async def cb_cabinet_card_contact(callback: CallbackQuery) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    await _render_contact_picker(callback, user)


@router.callback_query(F.data.startswith("cabinet:card_contact_set:"))
async def cb_cabinet_card_contact_set(
    callback: CallbackQuery,
    s21: S21Client,
    config: Config,
) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return

    contact = callback.data.rsplit(":", maxsplit=1)[-1]
    if contact not in _PROFILE_CARD_CONTACTS:
        await safe_callback_answer(callback, "Некорректный способ связи.", show_alert=True)
        return
    if contact == "max" and not (user["max_profile_url"] or "").strip():
        await safe_callback_answer(callback, PEER_CARD_MAX_REQUIRED, show_alert=True)
        return

    await UserRepo.set_preferred_contact(callback.from_user.id, contact)
    updated_user = await UserRepo.get_by_tg_id(callback.from_user.id)
    await safe_callback_answer(callback, PEER_CARD_CONTACT_SAVED)
    if updated_user:
        await _refresh_profile_message(callback.message, updated_user, s21, config)


@router.callback_query(F.data == "cabinet:card_delete_photo")
async def cb_cabinet_card_delete_photo(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_photo_message_id"],
    )
    await UserRepo.clear_profile_photo_file_id(callback.from_user.id)
    updated_user = await UserRepo.get_by_tg_id(callback.from_user.id)
    await safe_callback_answer(callback, PEER_CARD_PHOTO_REMOVED)
    if updated_user:
        await _refresh_profile_message(callback.message, updated_user, s21, config)


@router.callback_query(F.data == "cabinet:card_delete_comment")
async def cb_cabinet_card_delete_comment(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_comment_message_id"],
    )
    await UserRepo.clear_profile_comment(callback.from_user.id)
    updated_user = await UserRepo.get_by_tg_id(callback.from_user.id)
    await safe_callback_answer(callback, PEER_CARD_COMMENT_REMOVED)
    if updated_user:
        await _refresh_profile_message(callback.message, updated_user, s21, config)


def _build_qr_image(data: str):
    try:
        import qrcode  # type: ignore[import]
    except ImportError:
        return None
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="#00e640")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@router.callback_query(F.data == "cabinet:home")
async def cb_cabinet_home(callback: CallbackQuery, config: Config) -> None:
    assert callback.from_user is not None
    user = await UserRepo.get_by_tg_id(callback.from_user.id)
    if not user or user["status"] != "approved" or not user["school_login"]:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)
    try:
        await callback.message.edit_text(
            _cabinet_home_text(user["school_login"]),
            parse_mode="HTML",
            reply_markup=cabinet_home_kb(is_admin=_is_admin(callback.from_user.id, config)),
        )
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            return
        await callback.message.answer(
            _cabinet_home_text(user["school_login"]),
            parse_mode="HTML",
            reply_markup=cabinet_home_kb(is_admin=_is_admin(callback.from_user.id, config)),
        )
        await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)


@router.callback_query(F.data == "cabinet:gencode")
async def cb_cabinet_gencode(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    assert callback.from_user is not None
    user = await UserRepo.get_by_tg_id(callback.from_user.id)
    if not user or user["status"] != "approved":
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return
    await safe_callback_answer(callback)

    try:
        code = await create_invite_code(creator_user_id=callback.from_user.id)
        bot_info = await bot.get_me()
        link = build_bot_link(code, bot_info.username or "")
        text = INVITE_GENCODE_CAPTION.format(link=f"<code>{link}</code>")
        await _edit_cabinet_card(callback, text, config, disable_web_page_preview=True)
        qr_buf = _build_qr_image(link)
        if qr_buf:
            await callback.message.answer_photo(
                photo=BufferedInputFile(qr_buf.read(), filename=f"invite_{code}.png"),
                caption="QR-код для быстрого открытия инвайта",
            )
    except Exception as exc:
        await _edit_cabinet_card(callback, CABINET_GENCODE_ERROR.format(error=exc), config, disable_web_page_preview=False)


@router.callback_query(F.data == "cabinet:mycodes")
async def cb_cabinet_mycodes(callback: CallbackQuery, config: Config) -> None:
    assert callback.from_user is not None
    await safe_callback_answer(callback)
    codes = await InviteCodeRepo.get_by_creator(callback.from_user.id)
    if not codes:
        await _edit_cabinet_card(callback, CABINET_NO_CODES, config, disable_web_page_preview=False)
        return

    lines = [CABINET_CODES_HEADER]
    for row in codes[:20]:
        is_used = row["used_count"] >= row["usage_limit"]
        status = "✅" if row["is_active"] and not is_used else "❌"
        if row["used_by_user_id"]:
            used_user = await UserRepo.get_by_tg_id(row["used_by_user_id"])
            used_label = (
                used_user["school_login"]
                if used_user and used_user["school_login"]
                else str(row["used_by_user_id"])
            )
        else:
            used_label = "не использован"
        expires = row["expires_at"] or "∞"
        lines.append(f"{status} <code>{row['code']}</code> | {used_label} | до {expires}")

    await _edit_cabinet_card(callback, "\n".join(lines), config, disable_web_page_preview=True)


@router.callback_query(F.data == "cabinet:help")
async def cb_cabinet_help(callback: CallbackQuery, config: Config) -> None:
    await safe_callback_answer(callback)
    await _edit_callback_message(
        callback,
        text=_commands_section_text(config),
        reply_markup=_cabinet_commands_kb(config),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("cabinet:cmd_input:"))
async def cb_cabinet_command_input(callback: CallbackQuery, state: FSMContext) -> None:
    command_key = callback.data.rsplit(":", 1)[-1]
    hint = _CABINET_COMMAND_INPUT_HINTS.get(command_key)
    if not hint:
        await safe_callback_answer(callback, "Неизвестная команда.", show_alert=True)
        return
    await state.set_state(CabinetCommandsFSM.waiting_input)
    prompt = await callback.message.answer(
        f"✏️ <b>Введите данные для команды</b>\n\n{hint}",
        parse_mode="HTML",
        reply_markup=_cabinet_cmd_input_kb(),
    )
    await state.update_data(command_key=command_key, prompt_message_id=prompt.message_id)
    await safe_callback_answer(callback)


@router.callback_query(F.data == "cabinet:cmd_input_cancel")
async def cb_cabinet_command_input_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _delete_message_safe(callback.message.bot, callback.message.chat.id, callback.message.message_id)
    await safe_callback_answer(callback, "Ввод отменён")


@router.callback_query(F.data.startswith("cabinet:cmd:"))
async def cb_cabinet_quick_commands(callback: CallbackQuery, config: Config, s21: S21Client) -> None:
    assert callback.from_user is not None
    user = await _require_approved_user(callback.from_user.id)
    if not user:
        await safe_callback_answer(callback, ONLY_APPROVED, show_alert=True)
        return

    command = callback.data.rsplit(":", 1)[-1]
    try:
        if command == "profile":
            if not _scope_allows_private(config.cmd_profile_scope):
                await safe_callback_answer(callback, "Команда отключена в личке.", show_alert=True)
                return
            text = await _run_profile_text(user, s21, config)
        elif command == "logtime_me":
            if not _scope_allows_private(config.cmd_logtime_scope):
                await safe_callback_answer(callback, "Команда отключена в личке.", show_alert=True)
                return
            if not user["school_login"]:
                await safe_callback_answer(callback, "Логин не найден.", show_alert=True)
                return
            text = await _run_logtime_text(user["school_login"], s21)
        elif command == "top":
            if not _scope_allows_private(config.cmd_top_scope):
                await safe_callback_answer(callback, "Команда отключена в личке.", show_alert=True)
                return
            text = await _run_top_text(callback.from_user.id)
        elif command == "incampus":
            if not _scope_allows_private(config.cmd_incampus_scope):
                await safe_callback_answer(callback, "Команда отключена в личке.", show_alert=True)
                return
            text = await _run_incampus_text(config, s21)
        elif command == "events":
            if not _scope_allows_private(config.cmd_events_scope):
                await safe_callback_answer(callback, "Команда отключена в личке.", show_alert=True)
                return
            text = await _run_events_text(config, s21)
        else:
            await safe_callback_answer(callback, "Неизвестная команда.", show_alert=True)
            return
    except Exception as exc:
        await safe_callback_answer(callback)
        await _edit_callback_message(
            callback,
            text=f"⚠️ Ошибка выполнения команды: <code>{exc}</code>",
            reply_markup=_cabinet_cmd_back_kb(),
            disable_web_page_preview=True,
        )
        return

    await safe_callback_answer(callback)
    await _edit_callback_message(
        callback,
        text=text,
        reply_markup=_cabinet_cmd_back_kb(),
        disable_web_page_preview=True,
    )


@router.message(CabinetCommandsFSM.waiting_input)
async def msg_cabinet_command_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    data = await state.get_data()
    command_key = data.get("command_key")
    prompt_message_id = data.get("prompt_message_id")
    raw_value = (message.text or "").strip()
    prompt_hint = _CABINET_COMMAND_INPUT_HINTS.get(command_key, "Введите значение.")
    normalized_login = raw_value.lower()

    if not command_key or not raw_value:
        if prompt_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_message_id,
                    text=f"❌ Некорректный ввод.\n\n{prompt_hint}",
                    parse_mode="HTML",
                    reply_markup=_cabinet_cmd_input_kb(),
                )
            except Exception:
                pass
        await _delete_message_safe(bot, message.chat.id, message.message_id)
        return

    try:
        if command_key == "where":
            if not _scope_allows_private(config.cmd_where_scope):
                raise ValueError("Команда отключена в личке.")
            if not normalized_login.replace("-", "").replace("_", "").isalnum():
                raise ValueError("Логин должен содержать только буквы, цифры, '-' и '_'.")
            result_text = await _run_where_text(normalized_login, s21)
            await message.answer(result_text, parse_mode="HTML", reply_markup=_cabinet_cmd_home_kb())
        elif command_key == "peer":
            if not _scope_allows_private(config.cmd_peer_scope):
                raise ValueError("Команда отключена в личке.")
            if not normalized_login.replace("-", "").replace("_", "").isalnum():
                raise ValueError("Логин должен содержать только буквы, цифры, '-' и '_'.")
            login = normalized_login
            target_user = await UserRepo.get_approved_by_school_login(login)
            if not target_user:
                await message.answer(PEER_CARD_NOT_FOUND.format(login=login), parse_mode="HTML", reply_markup=_cabinet_cmd_home_kb())
            else:
                profile = await get_or_refresh(login, s21)
                if not profile:
                    raise ValueError("Профиль не найден.")
                card_text = render_full_peer_card_text(
                    login,
                    profile,
                    build_profile_url(login, config),
                    target_user,
                    show_coins=user["tg_id"] == target_user["tg_id"],
                )
                if target_user["profile_photo_file_id"] and can_send_text_as_photo_caption(card_text):
                    await message.answer_photo(
                        photo=target_user["profile_photo_file_id"],
                        caption=fit_text_for_photo_caption(card_text),
                        parse_mode="HTML",
                        reply_markup=_cabinet_cmd_home_kb(),
                    )
                elif target_user["profile_photo_file_id"]:
                    await message.answer_photo(photo=target_user["profile_photo_file_id"])
                    await message.answer(
                        card_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=_cabinet_cmd_home_kb(),
                    )
                else:
                    await message.answer(
                        card_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=_cabinet_cmd_home_kb(),
                    )
        elif command_key == "peers":
            if not _scope_allows_private(config.cmd_peers_scope):
                raise ValueError("Команда отключена в личке.")
            if len(raw_value) < 2:
                raise ValueError("Укажите не менее 2 символов названия проекта.")
            text = await _run_peers_text(raw_value.lower(), s21)
            await message.answer(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=_cabinet_cmd_home_kb(),
            )
        elif command_key == "logtime":
            if not _scope_allows_private(config.cmd_logtime_scope):
                raise ValueError("Команда отключена в личке.")
            if not normalized_login.replace("-", "").replace("_", "").isalnum():
                raise ValueError("Логин должен содержать только буквы, цифры, '-' и '_'.")
            text = await _run_logtime_text(normalized_login, s21)
            await message.answer(text, parse_mode="HTML", reply_markup=_cabinet_cmd_home_kb())
        else:
            raise ValueError("Неизвестная команда.")
    except ValueError as exc:
        if prompt_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_message_id,
                    text=f"❌ {exc}\n\n{prompt_hint}",
                    parse_mode="HTML",
                    reply_markup=_cabinet_cmd_input_kb(),
                )
            except Exception:
                pass
        await _delete_message_safe(bot, message.chat.id, message.message_id)
        return
    except Exception as exc:
        error_text = WHERE_ERROR if command_key == "where" else f"⚠️ Ошибка выполнения команды: <code>{exc}</code>"
        if prompt_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_message_id,
                    text=f"{error_text}\n\n{prompt_hint}",
                    parse_mode="HTML",
                    reply_markup=_cabinet_cmd_input_kb(),
                )
            except Exception:
                pass
        await _delete_message_safe(bot, message.chat.id, message.message_id)
        return

    await _delete_message_safe(bot, message.chat.id, message.message_id)
    await _delete_message_safe(bot, message.chat.id, prompt_message_id)
    await state.clear()


@router.message(ProfileCardFSM.waiting_photo, F.photo)
async def process_profile_card_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_photo_message_id"],
    )

    photo = message.photo[-1]
    await UserRepo.set_pending_profile_photo(message.from_user.id, photo.file_id, None)
    refreshed_user = await UserRepo.get_by_tg_id(message.from_user.id)
    if refreshed_user:
        moderation_message_id = await _send_profile_card_submission_for_moderation(
            bot=bot,
            config=config,
            user=refreshed_user,
            submission_type="photo",
        )
        await UserRepo.set_pending_profile_photo(message.from_user.id, photo.file_id, moderation_message_id)
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_PHOTO_SAVED,
    )


@router.message(ProfileCardFSM.waiting_photo)
async def process_profile_card_photo_invalid(message: Message) -> None:
    await message.answer(PEER_CARD_PHOTO_EXPECTED)


@router.message(ProfileCardFSM.waiting_comment)
async def process_profile_card_comment(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    raw_comment = (message.text or "").strip()
    if not raw_comment:
        await message.answer(PEER_CARD_EDIT_COMMENT_PROMPT, parse_mode="HTML")
        return

    comment = raw_comment[:_PROFILE_CARD_COMMENT_LIMIT] if raw_comment else None
    await _drop_pending_moderation_message(
        bot=bot,
        config=config,
        message_id=user["pending_profile_comment_message_id"],
    )
    await UserRepo.set_pending_profile_comment(message.from_user.id, comment, None)
    refreshed_user = await UserRepo.get_by_tg_id(message.from_user.id)
    if refreshed_user:
        moderation_message_id = await _send_profile_card_submission_for_moderation(
            bot=bot,
            config=config,
            user=refreshed_user,
            submission_type="comment",
        )
        await UserRepo.set_pending_profile_comment(message.from_user.id, comment, moderation_message_id)
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_COMMENT_SAVED,
    )


@router.message(ProfileCardFSM.waiting_max_link)
async def process_profile_card_max_link(
    message: Message,
    state: FSMContext,
    bot: Bot,
    s21: S21Client,
    config: Config,
) -> None:
    assert message.from_user is not None
    user = await _require_approved_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(ONLY_APPROVED)
        return

    raw_url = (message.text or "").strip()
    if not _is_valid_max_profile_url(raw_url):
        await message.answer(PEER_CARD_MAX_LINK_INVALID)
        return

    await UserRepo.set_max_profile_url(message.from_user.id, raw_url)
    await _restore_profile_card_after_input(
        bot=bot,
        source_message=message,
        state=state,
        user_id=message.from_user.id,
        s21=s21,
        config=config,
        notice_text=PEER_CARD_MAX_LINK_SAVED,
    )
