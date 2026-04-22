from __future__ import annotations
import logging
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from ..config import Config
from ..db import ApplicationRepo, UserRepo
from ..db.workstation_state_repo import WorkstationStateRepo
from ..db.s21_cache_repo import S21CacheRepo
from ..keyboards import decided_kb, cooldown_with_reason_kb, reject_reason_input_kb
from ..utils import now_iso
from ..utils.branding import format_invite_message
from ..utils.telegram import safe_callback_answer, send_message_with_topic
from ..strings import (
    APPROVED_USEFUL_COMMANDS,
    MOD_APP_NOT_FOUND, MOD_APP_ALREADY_DECIDED, MOD_APPROVE_ERROR,
    MOD_APPROVED_ANSWER, MOD_REJECTED_ANSWER, MOD_NOOP, MOD_ERROR_ALERT,
    REJECT_REASON_PROMPT, REJECT_COOLDOWN_PROMPT, REJECT_REASON_PREFIX, REJECT_NO_REASON,
    REJECTED_BASE, REJECTED_REASON, REJECTED_COOLDOWN, REJECTED_CAN_RETRY, REJECTED_SUPPORT,
)

logger = logging.getLogger(__name__)
router = Router(name="moderation")


class ModerationFSM(StatesGroup):
    waiting_reject_reason = State()
    waiting_cooldown = State()


def _moderator_name(user) -> str:
    name = user.full_name or ""
    if user.username:
        name += f" (@{user.username})"
    return name.strip() or str(user.id)


class IsModerator(Filter):
    async def __call__(self, event, config: Config) -> bool:
        uid = event.from_user.id if event.from_user else None
        return uid is not None and uid in config.admin_ids


async def _alert_error(bot: Bot, config: Config, text: str) -> None:
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            topic_logger=logger,
            text=MOD_ERROR_ALERT.format(text=text),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Failed to send error alert: %s", exc)


@router.callback_query(IsModerator(), F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    app_id = int(callback.data.split(":")[1])
    app = await ApplicationRepo.get(app_id)
    if app is None:
        await safe_callback_answer(callback, MOD_APP_NOT_FOUND, show_alert=True)
        return
    if app["status"] != "pending":
        await safe_callback_answer(callback, MOD_APP_ALREADY_DECIDED, show_alert=True)
        return
    now = now_iso()
    moderator_id = callback.from_user.id
    moderator_name = _moderator_name(callback.from_user)

    from ..services import create_one_time_invite
    try:
        invite_link = await create_one_time_invite(
            bot=bot, chat_id=config.community_chat_id,
            expire_seconds=config.invite_link_expire_seconds,
            name=f"s21:{app['school_login']}",
        )
    except Exception as exc:
        await safe_callback_answer(callback, MOD_APPROVE_ERROR, show_alert=True)
        await _alert_error(bot, config,
            f"Ошибка генерации инвайт-ссылки для заявки #{app_id} "
            f"({app['school_login']}):\n<code>{exc}</code>"
        )
        return

    await ApplicationRepo.approve(app_id, moderator_id, moderator_name, now)
    await UserRepo.approve(
        tg_id=app["tg_id"], moderator_id=moderator_id, moderator_name=moderator_name,
        school_login=app["school_login"],
        coalition=app["coalition"] if "coalition" in app.keys() else None,
        invite_link=invite_link, decision_date=now,
    )

    try:
        await bot.send_message(
            chat_id=app["tg_id"],
            text=format_invite_message(invite_link, config),
        )
        await bot.send_message(
            chat_id=app["tg_id"],
            text=APPROVED_USEFUL_COMMANDS,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Failed to notify user %d: %s", app["tg_id"], exc)
        await _alert_error(bot, config,
            f"Не удалось отправить инвайт пользователю <code>{app['tg_id']}</code> "
            f"({app['tg_name']}) для заявки #{app_id}.\n"
            f"Ссылка: {invite_link}\nОшибка: <code>{exc}</code>"
        )

    if app["moderation_msg_id"]:
        try:
            await bot.edit_message_reply_markup(
                chat_id=config.moderation_chat_id,
                message_id=app["moderation_msg_id"],
                reply_markup=decided_kb("approved", moderator_name),
            )
        except TelegramBadRequest as exc:
            logger.warning("Could not edit card: %s", exc)

    await safe_callback_answer(callback, MOD_APPROVED_ANSWER)


@router.callback_query(IsModerator(), F.data.startswith("reject:"))
async def cb_reject_start(callback: CallbackQuery, state: FSMContext) -> None:
    app_id = int(callback.data.split(":")[1])
    app = await ApplicationRepo.get(app_id)
    if app is None:
        await safe_callback_answer(callback, MOD_APP_NOT_FOUND, show_alert=True)
        return
    if app["status"] != "pending":
        await safe_callback_answer(callback, MOD_APP_ALREADY_DECIDED, show_alert=True)
        return
    await state.update_data(reject_app_id=app_id, reject_reason=None)
    await state.set_state(ModerationFSM.waiting_reject_reason)

    await callback.message.answer(
        REJECT_REASON_PROMPT.format(app_id=app_id),
        parse_mode="HTML",
        reply_markup=reject_reason_input_kb(app_id),
    )
    await safe_callback_answer(callback)


@router.message(IsModerator(), ModerationFSM.waiting_reject_reason)
async def process_reject_reason_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    app_id = data.get("reject_app_id")
    if not app_id:
        await state.clear()
        return
    reason = (message.text or "").strip()[:500] or None
    await state.update_data(reject_reason=reason)
    await state.set_state(ModerationFSM.waiting_cooldown)
    label = REJECT_REASON_PREFIX.format(reason=reason) if reason else REJECT_NO_REASON
    await message.answer(
        REJECT_COOLDOWN_PROMPT.format(label=label),
        parse_mode="HTML",
        reply_markup=cooldown_with_reason_kb(app_id),
    )


_PRESET_REASONS = {
    "campus": "Участник не из нашего кампуса",
    "not_student": "Не является участником Школы 21",
    "suspicious": "Подозрительная заявка",
}

@router.callback_query(IsModerator(), F.data.startswith("reject_reason:"))
async def cb_reject_preset(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":", 2)
    app_id = int(parts[1])
    reason_key = parts[2] if len(parts) > 2 else ""
    reason = _PRESET_REASONS.get(reason_key)
    await state.update_data(reject_app_id=app_id, reject_reason=reason)
    await state.set_state(ModerationFSM.waiting_cooldown)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    label = REJECT_REASON_PREFIX.format(reason=reason) if reason else REJECT_NO_REASON
    await callback.message.answer(
        REJECT_COOLDOWN_PROMPT.format(label=label),
        parse_mode="HTML",
        reply_markup=cooldown_with_reason_kb(app_id),
    )
    await safe_callback_answer(callback)

@router.callback_query(IsModerator(), F.data.startswith("reject_skip:"))
async def cb_reject_skip(callback: CallbackQuery, state: FSMContext) -> None:
    app_id = int(callback.data.split(":")[1])
    await state.update_data(reject_app_id=app_id, reject_reason=None)
    await state.set_state(ModerationFSM.waiting_cooldown)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(
        REJECT_COOLDOWN_PROMPT.format(label=REJECT_NO_REASON),
        parse_mode="HTML",
        reply_markup=cooldown_with_reason_kb(app_id),
    )
    await safe_callback_answer(callback)

@router.callback_query(IsModerator(), F.data.startswith("cooldown:"))
async def cb_cooldown(callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config) -> None:
    parts = callback.data.split(":")
    app_id = int(parts[1])
    cooldown_seconds = int(parts[2])

    # reason хранится в FSM state
    data = await state.get_data()
    reason = data.get("reject_reason")
    await state.clear()

    moderator_name = _moderator_name(callback.from_user)
    await _do_reject(
        bot=bot, config=config, app_id=app_id,
        moderator_id=callback.from_user.id, moderator_name=moderator_name,
        reason=reason, cooldown_seconds=cooldown_seconds,
    )
    label = {0: "без кулдауна", 3600: "1 час", 86400: "24 часа", 259200: "72 часа"}.get(cooldown_seconds, f"{cooldown_seconds}с")
    await safe_callback_answer(callback, MOD_REJECTED_ANSWER.format(label=label))
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

async def _do_reject(bot, config, app_id, moderator_id, moderator_name, reason, cooldown_seconds=0):
    now = now_iso()
    app = await ApplicationRepo.get(app_id)
    if app is None:
        return
    await ApplicationRepo.reject(app_id, moderator_id, moderator_name, now, reason)
    await UserRepo.reject(app["tg_id"], moderator_id, moderator_name, now)
    if app.get("school_login"):
        await WorkstationStateRepo.delete(app["school_login"])
        await S21CacheRepo.delete(app["school_login"])
    if cooldown_seconds > 0:
        await UserRepo.set_cooldown(app["tg_id"], cooldown_seconds)

    text = REJECTED_BASE
    if reason:
        text += REJECTED_REASON.format(reason=reason)
    if cooldown_seconds > 0:
        label = {3600: "1 час", 86400: "24 часа", 259200: "72 часа"}.get(cooldown_seconds, f"{cooldown_seconds} секунд")
        text += REJECTED_COOLDOWN.format(label=label)
    else:
        text += REJECTED_CAN_RETRY
    if config.support_contacts:
        text += REJECTED_SUPPORT.format(contacts=", ".join(config.support_contacts))

    try:
        await bot.send_message(chat_id=app["tg_id"], text=text, parse_mode="HTML")
    except Exception as exc:
        logger.error("Failed to notify user %d: %s", app["tg_id"], exc)

    if app["moderation_msg_id"]:
        try:
            await bot.edit_message_reply_markup(
                chat_id=config.moderation_chat_id,
                message_id=app["moderation_msg_id"],
                reply_markup=decided_kb("rejected", moderator_name),
            )
        except TelegramBadRequest as exc:
            logger.warning("Could not update card: %s", exc)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, MOD_NOOP, show_alert=False)
