from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import Config
from ..db import ApplicationRepo, AuthAttemptRepo, OTPSessionRepo, UserRepo
from ..handlers.invite_code import apply_pending_invite_code
from ..keyboards import cabinet_kb, failed_auth_kb, moderation_card_kb, skip_comment_kb
from ..services import S21Client
from ..services.rocketchat import RocketChatClient, RocketChatError
from ..services.social_trust import get_candidate_teammates, run_social_trust
from ..strings import (
    BANNED,
    LOGIN_ALREADY_TAKEN,
    LOGIN_CHECKING_S21,
    LOGIN_INVALID_FORMAT,
    OTP_CONFIRMED,
    OTP_SENT,
    OTP_WRONG,
    RC_CHECKING,
    RC_ERROR,
    RC_INACTIVE,
    RC_NOT_FOUND,
    RC_UNAVAILABLE,
    SESSION_EXPIRED,
    START_ALREADY_PENDING,
    START_APPROVED_GREETING,
)
from ..utils import ApplicationFSM, build_moderation_card, now_iso, tg_display_name
from ..utils.branding import build_profile_url, format_start_welcome
from ..utils.otp import OTP_MAX_ATTEMPTS, OTP_TTL_SECONDS, generate_otp, verify_otp
from ..utils.telegram import safe_callback_answer, send_message_with_topic

logger = logging.getLogger(__name__)
router = Router(name="auth")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

_OTP_MAX_RESENDS: int = 3
_SUSPICIOUS_LOGIN_COUNT = 3


def _otp_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔁 Не пришёл код", callback_data="otp_resend"))
    return builder.as_markup()


async def _send_failed_auth_alert(
    bot: Bot,
    config: Config,
    tg_id: int,
    tg_name: str,
    login: str,
    reason: str,
    extra: str = "",
) -> None:
    text = (
        f"⚠️ <b>Неуспешная попытка авторизации:</b> {reason}\n\n"
        f"👤 <b>Имя:</b> {tg_name}\n"
        f"🆔 <b>ID:</b> <code>{tg_id}</code>\n"
        f"🔑 <b>Логин:</b> <code>{login}</code>"
    )
    if extra:
        text += f"\n\n{extra}"
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.failed_auth_topic_id or None,
            topic_name="FAILED_AUTH_TOPIC_ID",
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
            reply_markup=failed_auth_kb(tg_id),
        )
    except Exception as exc:
        logger.error("Failed to send auth alert: %s", exc)


async def _check_and_respond(message: Message, state: FSMContext) -> bool:
    assert message.from_user is not None
    user = await UserRepo.get_by_tg_id(message.from_user.id)
    await UserRepo.upsert_basic(message.from_user.id, tg_display_name(message.from_user))

    if user:
        match user["status"]:
            case "approved":
                login = user["school_login"] or ""
                await message.answer(
                    START_APPROVED_GREETING.format(login=login),
                    parse_mode="HTML",
                    reply_markup=cabinet_kb(),
                )
                return True
            case "pending":
                if await ApplicationRepo.get_pending_for_user(message.from_user.id):
                    await message.answer(START_ALREADY_PENDING)
                    return True
            case "banned":
                await message.answer(BANNED)
                return True

    cooldown_msg = await UserRepo.get_cooldown_message(message.from_user.id)
    if cooldown_msg:
        await message.answer(cooldown_msg, parse_mode="HTML")
        return True

    return False


async def _start_flow(message: Message, state: FSMContext, config: Config) -> None:
    await state.set_state(ApplicationFSM.waiting_login)
    await message.answer(
        format_start_welcome(config),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, config: Config) -> None:
    await state.clear()
    if await _check_and_respond(message, state):
        return
    await _start_flow(message, state, config)


@router.message(ApplicationFSM.waiting_login)
async def process_login(
    message: Message,
    state: FSMContext,
    s21: S21Client,
    rc: RocketChatClient,
    bot: Bot,
    config: Config,
) -> None:
    assert message.from_user is not None
    login = (message.text or "").strip().lower()
    tg_name = tg_display_name(message.from_user)
    tg_id = message.from_user.id
    now = now_iso()

    if not login or len(login) > 64 or not login.replace("-", "").replace("_", "").isalnum():
        await message.answer(LOGIN_INVALID_FORMAT)
        return

    recent = await AuthAttemptRepo.get_recent_logins(tg_id, minutes=30)
    recent_logins = {row["login"] for row in recent}
    if len(recent_logins) >= _SUSPICIOUS_LOGIN_COUNT and login not in recent_logins:
        await _send_failed_auth_alert(
            bot,
            config,
            tg_id,
            tg_name,
            login,
            reason="подозрительный перебор логинов",
            extra=(
                f"⚠️ За последние 30 мин использовано логинов: {len(recent_logins) + 1}\n"
                f"Предыдущие: {', '.join(list(recent_logins)[:5])}"
            ),
        )

    existing = await UserRepo.get_by_school_login(login)
    if existing and existing["tg_id"] != tg_id:
        await AuthAttemptRepo.log(tg_id, tg_name, login, "failed", "login_taken", now)
        await message.answer(LOGIN_ALREADY_TAKEN)
        await _send_failed_auth_alert(bot, config, tg_id, tg_name, login, "логин уже существует")
        return

    wait_msg = await message.answer(LOGIN_CHECKING_S21)
    try:
        is_valid, coalition, failure_reason = await s21.validate_participant(
            login, campus_id=config.s21_campus_id
        )
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.error("S21 API error: %s", exc)
        await wait_msg.delete()
        await message.answer(
            "⚠️ Не удалось проверить логин — сервис Школы 21 временно недоступен. Попробуйте позже."
        )
        return
    await wait_msg.delete()

    if not is_valid:
        reason_map = {
            "expelled": ("участник отчислен", "❌ Этот участник был отчислен из Школы 21."),
            "wrong_campus": ("другой кампус", "❌ Участник зарегистрирован в другом кампусе."),
        }
        reason_text, user_msg = reason_map.get(
            failure_reason,
            ("неверный логин", "❌ Участник с таким логином не найден в Школе 21.\nПроверьте правильность логина."),
        )
        await AuthAttemptRepo.log(tg_id, tg_name, login, "failed", failure_reason, now)

        recent_failed = await AuthAttemptRepo.get_recent_failed(tg_id, minutes=60)
        attempts_used = len(recent_failed)
        max_attempts = 3
        if attempts_used >= max_attempts:
            await UserRepo.set_cooldown(tg_id, 3600)
            await message.answer(
                f"{user_msg}\n\n"
                f"⛔️ Вы исчерпали <b>{max_attempts}/{max_attempts}</b> попыток.\n"
                "Из-за многократных неверных попыток вы временно заблокированы на <b>1 час</b>.",
                parse_mode="HTML",
            )
            await _send_failed_auth_alert(
                bot,
                config,
                tg_id,
                tg_name,
                login,
                reason_text,
                extra=f"⛔️ Исчерпаны все {max_attempts} попытки — автоблокировка на 1 час",
            )
        else:
            remaining = max_attempts - attempts_used
            await message.answer(
                f"{user_msg}\n\n📊 Попыток: <b>{attempts_used}/{max_attempts}</b>. Осталось: {remaining}.",
                parse_mode="HTML",
            )
            await _send_failed_auth_alert(bot, config, tg_id, tg_name, login, reason_text)
        return

    await AuthAttemptRepo.log(tg_id, tg_name, login, "success", None, now)
    await state.update_data(s21_login=login, coalition=coalition, rc_username=login)
    await _send_otp(
        tg_id=tg_id,
        tg_name=tg_name,
        rc_username=login,
        message=message,
        state=state,
        bot=bot,
        config=config,
        rc=rc,
    )


async def _alert_otp_abuse(
    bot: Bot,
    config: Config,
    tg_id: int,
    tg_name: str,
    rc_username: str,
    resend_count: int,
) -> None:
    text = (
        f"🚨 <b>Превышен лимит запросов OTP-кода</b>\n\n"
        f"👤 <b>Имя:</b> {tg_name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        f"🚀 <b>Rocket.Chat:</b> <code>{rc_username}</code>\n"
        f"🔁 <b>Запросов кода:</b> {resend_count + 1} (лимит {_OTP_MAX_RESENDS})\n\n"
        f"Заявка автоматически заморожена на 1 час."
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"fail_ban:{tg_id}"),
        InlineKeyboardButton(text="✅ Пропустить", callback_data=f"fail_skip:{tg_id}"),
    )
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.failed_auth_topic_id or None,
            topic_name="FAILED_AUTH_TOPIC_ID",
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
    except Exception as exc:
        logger.error("Failed to send OTP abuse alert: %s", exc)


async def _send_otp(
    *,
    tg_id: int,
    tg_name: str,
    rc_username: str,
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    rc: RocketChatClient,
) -> None:
    fsm_data = await state.get_data()
    resend_count: int = fsm_data.get("otp_resend_count", 0)

    if resend_count >= _OTP_MAX_RESENDS:
        await state.clear()
        await UserRepo.set_cooldown(tg_id, 3600)
        await message.answer(
            "🚫 Вы превысили лимит запросов кода подтверждения.\n\n"
            "Ваша заявка заморожена на <b>1 час</b>. Модераторы уже уведомлены и разберутся с ситуацией.",
            parse_mode="HTML",
        )
        await _alert_otp_abuse(bot, config, tg_id, tg_name, rc_username, resend_count)
        return

    await state.update_data(otp_resend_count=resend_count + 1)
    wait_msg = await message.answer(RC_CHECKING)

    try:
        rc_user = await rc.get_user_info(rc_username)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.error("RC API network error for username=%s: %s", rc_username, exc)
        await wait_msg.delete()
        await message.answer(RC_UNAVAILABLE)
        return
    except RocketChatError as exc:
        logger.error("RC API unexpected response for username=%s: %s", rc_username, exc)
        await wait_msg.delete()
        await message.answer(RC_ERROR)
        return

    await wait_msg.delete()

    if rc_user is None:
        await message.answer(RC_NOT_FOUND.format(rc_login=rc_username), parse_mode="HTML")
        await state.clear()
        return

    if not rc_user.active:
        await message.answer(RC_INACTIVE.format(rc_login=rc_username), parse_mode="HTML")
        await _send_failed_auth_alert(bot, config, tg_id, tg_name, rc_username, reason="RC аккаунт неактивен")
        await state.clear()
        return

    code, secret, digest = generate_otp()
    await OTPSessionRepo.create(
        tg_id=tg_id,
        rc_username=rc_username,
        code_hash=digest,
        secret=secret,
        created_at=now_iso(),
        ttl_seconds=OTP_TTL_SECONDS,
    )

    try:
        await rc.send_direct_message(
            rc_username,
            f"🔐 Ваш код подтверждения для входа в Telegram-бот Школы 21: *{code}*\n\n"
            f"Код действителен 10 минут. Не передавайте его никому.",
        )
    except (aiohttp.ClientError, asyncio.TimeoutError, RocketChatError) as exc:
        logger.error("Failed to send OTP DM to @%s: %s", rc_username, exc)
        await OTPSessionRepo.invalidate_all(tg_id)
        await message.answer(
            "⚠️ Не удалось отправить код в Rocket.Chat. Попробуйте позже или обратитесь к модераторам."
        )
        return

    await state.set_state(ApplicationFSM.waiting_otp)
    await message.answer(
        OTP_SENT.format(rc_login=rc_username),
        parse_mode="HTML",
        reply_markup=_otp_keyboard(),
    )


@router.message(ApplicationFSM.waiting_otp)
async def process_otp(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    candidate = (message.text or "").strip()
    tg_id = message.from_user.id

    session = await OTPSessionRepo.get_live(tg_id)
    if session is None:
        await message.answer(
            "⏱ Срок действия кода истёк или код уже использован.\nНачните заново командой /start."
        )
        await state.clear()
        return

    session_id: int = session["id"]
    attempts = await OTPSessionRepo.increment_attempts(session_id)

    if not verify_otp(candidate, session["secret"], session["code_hash"]):
        remaining = OTP_MAX_ATTEMPTS - attempts
        if remaining <= 0:
            await OTPSessionRepo.mark_used(session_id)
            await state.clear()
            await UserRepo.set_cooldown(tg_id, 3600)
            await message.answer(
                "❌ Неверный код. Вы исчерпали все попытки.\n\n🕐 Повторная попытка будет доступна через <b>1 час</b>.",
                parse_mode="HTML",
            )
            return
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔁 Не пришёл код", callback_data="otp_resend"))
        await message.answer(
            OTP_WRONG.format(remaining=remaining),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        return

    await OTPSessionRepo.mark_used(session_id)
    rc_username: str = session["rc_username"]

    await state.update_data(rc_verified=True, otp_resend_count=0)
    await state.set_state(ApplicationFSM.waiting_comment)

    await message.answer(
        OTP_CONFIRMED.format(rc_login=rc_username) + "Хотите добавить комментарий к заявке? (необязательно)",
        parse_mode="HTML",
        reply_markup=skip_comment_kb(),
    )


@router.callback_query(F.data == "otp_resend", ApplicationFSM.waiting_otp)
async def cb_otp_resend(
    callback: CallbackQuery,
    state: FSMContext,
    rc: RocketChatClient,
    bot: Bot,
    config: Config,
) -> None:
    tg_id = callback.from_user.id
    tg_name = tg_display_name(callback.from_user)

    fsm_data = await state.get_data()
    rc_username = fsm_data.get("rc_username")
    if not rc_username:
        await safe_callback_answer(callback, SESSION_EXPIRED, show_alert=True)
        await state.clear()
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await safe_callback_answer(callback)
    await OTPSessionRepo.invalidate_all(tg_id)

    await _send_otp(
        tg_id=tg_id,
        tg_name=tg_name,
        rc_username=rc_username,
        message=callback.message,
        state=state,
        bot=bot,
        config=config,
        rc=rc,
    )


@router.callback_query(F.data == "skip_comment", ApplicationFSM.waiting_comment)
async def skip_comment(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _submit_application(
        tg_id=callback.from_user.id,
        tg_name=tg_display_name(callback.from_user),
        user_comment=None,
        state=state,
        bot=bot,
        config=config,
        s21=s21,
        answer_func=callback.message.answer,
    )
    await safe_callback_answer(callback)


@router.message(ApplicationFSM.waiting_comment)
async def process_comment(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
) -> None:
    assert message.from_user is not None
    raw = (message.text or "").strip()
    await _submit_application(
        tg_id=message.from_user.id,
        tg_name=tg_display_name(message.from_user),
        user_comment=raw[:500] if raw else None,
        state=state,
        bot=bot,
        config=config,
        s21=s21,
        answer_func=message.answer,
    )


async def _submit_application(
    tg_id: int,
    tg_name: str,
    user_comment: str | None,
    state: FSMContext,
    bot: Bot,
    config: Config,
    s21: S21Client,
    answer_func,
) -> None:
    data = await state.get_data()
    login = data["s21_login"]
    coalition = data.get("coalition")
    rc_username = data.get("rc_username")

    now = now_iso()
    await UserRepo.upsert_basic(tg_id, tg_name)
    await UserRepo.set_application_date(tg_id, now)

    if rc_username:
        await UserRepo.set_rocket_username(tg_id, rc_username)

    has_welcome_badge = False
    try:
        has_welcome_badge = await s21.has_badge(login, "welcome on board")
    except Exception as exc:
        logger.warning("Badge check failed for %s: %s", login, exc)

    xp: int | None = None
    try:
        info = await s21.get_participant(login)
        if info:
            xp = info.get("expValue")
    except Exception as exc:
        logger.warning("XP fetch failed for %s: %s", login, exc)

    app_id = await ApplicationRepo.create(
        tg_id=tg_id,
        tg_name=tg_name,
        school_login=login,
        user_comment=user_comment,
        submitted_at=now,
        coalition=coalition,
    )

    await apply_pending_invite_code(app_id, tg_id, state, answer_func)
    await state.clear()

    teammate_logins: list[str] = []
    try:
        if config.social_trust_project_ids:
            tm_set = await get_candidate_teammates(login, s21, config.social_trust_project_ids)
            teammate_logins = sorted(tm_set)
    except Exception as exc:
        logger.warning("Teammate fetch for card failed for %s: %s", login, exc)

    invite_code_str = None
    try:
        from ..db.invite_code_repo import InviteCodeRepo

        code_id = await InviteCodeRepo.get_application_code_id(app_id)
        if code_id:
            code_row = await InviteCodeRepo.get_by_id(code_id)
            if code_row:
                invite_code_str = code_row["code"]
    except Exception:
        pass

    card_text = build_moderation_card(
        tg_name=tg_name,
        tg_id=tg_id,
        school_login=login,
        profile_url=build_profile_url(login, config),
        user_comment=user_comment,
        app_id=app_id,
        has_welcome_badge=has_welcome_badge,
        coalition=coalition,
        xp=xp,
        rc_username=rc_username,
        teammates=teammate_logins if teammate_logins else None,
        invite_code=invite_code_str,
    )

    try:
        sent = await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            topic_logger=logger,
            fallback_to_chat=True,
            text=card_text,
            reply_markup=moderation_card_kb(app_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        if sent is not None:
            await ApplicationRepo.set_moderation_msg_id(app_id, sent.message_id)
    except Exception as exc:
        logger.error("Failed to send moderation card for app #%d: %s", app_id, exc)
        try:
            await send_message_with_topic(
                bot,
                chat_id=config.moderation_chat_id,
                message_thread_id=config.moderation_topic_id or None,
                topic_name="MODERATION_TOPIC_ID",
                topic_logger=logger,
                text=(
                    f"🚨 <b>Ошибка отправки карточки заявки #{app_id}!</b>\n"
                    f"Пользователь: {tg_name} (<code>{tg_id}</code>)\n"
                    f"Ошибка: <code>{exc}</code>"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    await answer_func("📨 Ваша заявка отправлена на рассмотрение!\nМы уведомим вас о решении в ближайшее время.")

    asyncio.create_task(
        run_social_trust(
            app_id=app_id,
            candidate_login=login,
            candidate_tg_name=tg_name,
            bot=bot,
            config=config,
            s21=s21,
        )
    )
    logger.info(
        "New application #%d from tg_id=%d login=%s rc=%s coalition=%s badge=%s",
        app_id,
        tg_id,
        login,
        rc_username,
        coalition,
        has_welcome_badge,
    )


@router.message()
async def fallback(message: Message, state: FSMContext, config: Config) -> None:
    if await state.get_state() is not None:
        return
    if await _check_and_respond(message, state):
        return
    await _start_flow(message, state, config)
