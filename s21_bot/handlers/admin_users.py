from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import Config
from ..db import ApplicationRepo, AuthAttemptRepo, UserRepo
from ..services import S21Client
from ..utils.branding import format_invite_message
from ..utils.helpers import now_iso
from .admin_common import IsModeratorInModChat

logger = logging.getLogger(__name__)
router = Router(name="admin_users")


@router.message(IsModeratorInModChat(), Command("ban"))
async def cmd_ban(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)[1:]
    if not parts:
        await message.reply("❌ Формат: <code>/ban 123456789 [причина]</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[0])
    except ValueError:
        await message.reply("❌ TG ID должен быть числом.", parse_mode="HTML")
        return
    reason = parts[1].strip() if len(parts) > 1 else None
    user = await UserRepo.get_by_tg_id(target_id)
    if user is None:
        await message.reply(f"❌ Пользователь <code>{target_id}</code> не найден в базе.", parse_mode="HTML")
        return
    if user["is_banned"]:
        await message.reply(f"ℹ️ Пользователь <code>{target_id}</code> уже заблокирован.", parse_mode="HTML")
        return
    await UserRepo.set_banned(target_id, banned=True)
    reason_text = f"\n<b>Причина:</b> {reason}" if reason else ""
    await message.reply(f"🚫 <code>{target_id}</code> (<b>{user['tg_name']}</b>) заблокирован.{reason_text}", parse_mode="HTML")
    logger.info("User %d banned by %d, reason: %s", target_id, message.from_user.id, reason or "—")


@router.message(IsModeratorInModChat(), Command("unban"))
async def cmd_unban(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)[1:]
    if not parts:
        await message.reply("❌ Формат: <code>/unban 123456789</code>", parse_mode="HTML")
        return
    user = await UserRepo.find_by_identifier(parts[0].strip())
    if user is None:
        await message.reply(f"❌ Пользователь <code>{parts[0]}</code> не найден в базе.", parse_mode="HTML")
        return
    target_id = user["tg_id"]
    if not user["is_banned"]:
        await message.reply(f"ℹ️ Пользователь <code>{target_id}</code> не заблокирован.", parse_mode="HTML")
        return
    await UserRepo.set_banned(target_id, banned=False)
    await message.reply(f"✅ <code>{target_id}</code> (<b>{user['tg_name']}</b>) разблокирован.", parse_mode="HTML")


@router.message(IsModeratorInModChat(), Command("deluser"))
async def cmd_deluser(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)[1:]
    if not parts:
        await message.reply("❌ Формат: <code>/deluser 123456789</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[0].strip())
    except ValueError:
        await message.reply("❌ TG ID должен быть числом.", parse_mode="HTML")
        return
    user = await UserRepo.get_by_tg_id(target_id)
    if user is None:
        await message.reply(f"❌ Пользователь <code>{target_id}</code> не найден в базе.", parse_mode="HTML")
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_deluser:{target_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deluser"),
    )
    await message.reply(
        f"⚠️ Удалить пользователя <code>{target_id}</code> (<b>{user['tg_name']}</b>) и все его заявки из БД?",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.message(IsModeratorInModChat(), Command("cleardb"))
async def cmd_cleardb(message: Message) -> None:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💣 Да, очистить ВСЁ", callback_data="confirm_cleardb"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_cleardb"),
    )
    await message.reply(
        "⚠️ <b>Вы уверены?</b> Это удалит <b>всех пользователей и все заявки</b> из базы данных безвозвратно.",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.message(IsModeratorInModChat(), Command("userinfo"))
async def cmd_userinfo(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)[1:]
    if not parts:
        await message.reply("❌ Формат: <code>/userinfo 123456789</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[0].strip())
    except ValueError:
        await message.reply("❌ TG ID должен быть числом.", parse_mode="HTML")
        return
    user = await UserRepo.get_by_tg_id(target_id)
    if user is None:
        await message.reply(f"❌ Пользователь <code>{target_id}</code> не найден в базе.", parse_mode="HTML")
        return
    status_emoji = {"approved": "✅", "pending": "⏳", "rejected": "❌", "banned": "🚫"}.get(user["status"], "❓")
    lines = [
        f"👤 <b>{user['tg_name']}</b>",
        f"🆔 <code>{user['tg_id']}</code>",
        f"🔑 Логин: <code>{user['school_login'] or '—'}</code>",
        f"⚡️ Статус: {status_emoji} {user['status']}",
        f"📅 Заявка: {user['application_date'] or '—'}",
        f"📋 Решение: {user['decision_date'] or '—'}",
        f"🏰 Коалиция: {user['coalition'] or '—'}",
        f"🚫 Бан: {'да' if user['is_banned'] else 'нет'}",
    ]
    if user.get("invite_link") or (hasattr(user, "__getitem__") and "invite_link" in user.keys() and user["invite_link"]):
        lines.append(f"🔗 Инвайт: {user['invite_link']}")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(IsModeratorInModChat(), Command("events"))
async def cmd_events(message: Message, s21: S21Client, config: Config) -> None:
    from datetime import datetime, timedelta, timezone
    from ..services.events import _format_event

    now = datetime.now(timezone.utc)
    to = now + timedelta(days=30)
    try:
        events = await s21.get_events(now.strftime("%Y-%m-%dT%H:%M:%SZ"), to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    except Exception as exc:
        await message.reply(f"❌ Ошибка: {exc}")
        return
    if not events:
        await message.reply("📭 Ближайших мероприятий не найдено.")
        return
    for event in events[:10]:
        await message.reply(_format_event(event, config), parse_mode="HTML", disable_web_page_preview=True)


@router.message(IsModeratorInModChat(), Command("history"))
async def cmd_history(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)[1:]
    if not parts:
        await message.reply("❌ Формат: <code>/history 123456789</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[0].strip())
    except ValueError:
        await message.reply("❌ TG ID должен быть числом.", parse_mode="HTML")
        return

    attempts = await AuthAttemptRepo.get_history(target_id, limit=20)
    if not attempts:
        await message.reply(f"📭 История попыток для <code>{target_id}</code> пуста.", parse_mode="HTML")
        return

    lines = [f"📋 <b>История авторизаций для {target_id}</b>\n"]
    for attempt in attempts:
        icon = "✅" if attempt["result"] == "success" else "❌"
        reason = f" ({attempt['reason']})" if attempt["reason"] else ""
        lines.append(f"{icon} <code>{attempt['login']}</code>{reason} — {attempt['attempted_at']}")

    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(IsModeratorInModChat(), Command("approve"))
async def cmd_approve(message: Message, bot: Bot, config: Config) -> None:
    assert message.from_user is not None
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("Использование: <code>/approve &lt;app_id&gt;</code>", parse_mode="HTML")
        return

    app_id = int(parts[1])
    app = await ApplicationRepo.get(app_id)
    if app is None:
        await message.reply(f"❌ Заявка #{app_id} не найдена.")
        return

    terminal = {"approved", "rejected", "banned"}
    if app["status"] in terminal:
        await message.reply(
            f"⚠️ Заявка #{app_id} уже в статусе <b>{app['status']}</b>.",
            parse_mode="HTML",
        )
        return

    now = now_iso()
    moderator_id = message.from_user.id
    moderator_name = message.from_user.full_name or str(moderator_id)
    if message.from_user.username:
        moderator_name += f" (@{message.from_user.username})"

    from ..services import create_one_time_invite

    try:
        invite_link = await create_one_time_invite(
            bot=bot,
            chat_id=config.community_chat_id,
            expire_seconds=config.invite_link_expire_seconds,
            name=f"s21:{app['school_login']}",
        )
    except Exception as exc:
        await message.reply(f"🚨 Ошибка создания ссылки: <code>{exc}</code>", parse_mode="HTML")
        return

    await ApplicationRepo.approve(app_id, moderator_id, moderator_name, now)
    await UserRepo.approve(
        tg_id=app["tg_id"],
        moderator_id=moderator_id,
        moderator_name=moderator_name,
        school_login=app["school_login"],
        coalition=app["coalition"] if "coalition" in app.keys() else None,
        invite_link=invite_link,
        decision_date=now,
    )

    try:
        await bot.send_message(chat_id=app["tg_id"], text=format_invite_message(invite_link, config))
    except Exception as exc:
        logger.error("Failed to notify user %d: %s", app["tg_id"], exc)
        await message.reply("Одобрено, но не удалось отправить ссылку. Ссылка: " + invite_link, parse_mode="HTML")

    if app["moderation_msg_id"]:
        from ..keyboards import decided_kb

        try:
            await bot.edit_message_reply_markup(
                chat_id=config.moderation_chat_id,
                message_id=app["moderation_msg_id"],
                reply_markup=decided_kb("approved", moderator_name),
            )
        except Exception:
            pass

    await message.reply(
        f"✅ Заявка <b>#{app_id}</b> одобрена.\n"
        f"👤 <b>{app['tg_name']}</b> (<code>{app['school_login']}</code>) уведомлён.",
        parse_mode="HTML",
    )
    logger.info("Manual approve: app_id=%d by moderator=%d", app_id, moderator_id)


@router.message(IsModeratorInModChat(), Command("guestinvite", "гостьинвайт", ignore_case=True))
async def cmd_guest_invite(message: Message, bot: Bot, config: Config, s21: S21Client) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.reply(
            "Использование: <code>/guestinvite &lt;tg_id&gt; &lt;логин&gt;</code>\n"
            "Например: <code>/guestinvite 123456789 vasya-pupkin</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_tg_id = int(parts[1].strip())
    except ValueError:
        await message.reply("❌ TG ID должен быть числом.")
        return

    school_login = parts[2].strip().lower()
    wait = await message.reply(f"🔄 Проверяю логин <code>{school_login}</code>…", parse_mode="HTML")

    try:
        info = await s21.get_participant(school_login)
    except Exception as exc:
        await wait.edit_text(f"❌ Ошибка API: <code>{exc}</code>", parse_mode="HTML")
        return

    if not info:
        await wait.edit_text(f"❌ Логин <code>{school_login}</code> не найден в S21.", parse_mode="HTML")
        return

    campus = (info.get("campus") or {}).get("shortName") or "Неизвестен"
    coalition_data = await s21.get_coalition(school_login)
    coalition = coalition_data.get("name") if coalition_data else "—"

    from ..db.guest_invite_repo import GuestInviteRepo
    from ..services import create_one_time_invite
    from ..strings import GUEST_INVITE_CREATED, GUEST_INVITE_DM

    try:
        invite_link = await create_one_time_invite(
            bot=bot,
            chat_id=config.community_chat_id,
            expire_seconds=config.invite_link_expire_seconds,
            name=f"guest:{school_login}",
        )
    except Exception as exc:
        await wait.edit_text(f"❌ Ошибка создания ссылки: <code>{exc}</code>", parse_mode="HTML")
        return

    now = now_iso()
    await UserRepo.upsert_basic(target_tg_id, f"Guest:{school_login}")
    from ..db.models import get_db

    async with get_db() as db:
        await db.execute(
            "UPDATE users SET status='approved', school_login=?, coalition=?, "
            "invite_link=?, is_guest=1, home_campus=?, decision_date=?, "
            "moderator_id=?, moderator_name=? WHERE tg_id=?",
            (school_login, coalition, invite_link, campus, now, message.from_user.id, message.from_user.full_name, target_tg_id),
        )
        await db.commit()

    await GuestInviteRepo.create(
        tg_id=target_tg_id,
        school_login=school_login,
        home_campus=campus,
        invite_link=invite_link,
        created_by=message.from_user.id,
        created_at=now,
    )

    try:
        await bot.send_message(chat_id=target_tg_id, text=GUEST_INVITE_DM.format(invite_link=invite_link), parse_mode="HTML")
        dm_sent = True
    except Exception:
        dm_sent = False

    try:
        tg_user = await bot.get_chat(target_tg_id)
        tg_name = tg_user.full_name or str(target_tg_id)
        if hasattr(tg_user, "username") and tg_user.username:
            tg_name += f" (@{tg_user.username})"
    except Exception:
        tg_name = str(target_tg_id)

    result = GUEST_INVITE_CREATED.format(
        tg_id=target_tg_id,
        tg_name=tg_name,
        login=school_login,
        campus=campus,
    )
    if not dm_sent:
        result += f"\n\n⚠️ Не удалось отправить DM — гость должен сначала написать боту.\n🔗 Ссылка: {invite_link}"

    await wait.edit_text(result, parse_mode="HTML")
    logger.info("Guest invite: login=%s tg_id=%d by=%d", school_login, target_tg_id, message.from_user.id)


@router.message(IsModeratorInModChat(), Command("dm", "написать", ignore_case=True))
async def cmd_dm(message: Message, bot: Bot) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.reply(
            "Использование: <code>/dm &lt;tg_id или логин&gt; &lt;текст&gt;</code>\n"
            "Например: <code>/dm kylaknap Привет!</code>",
            parse_mode="HTML",
        )
        return

    identifier = parts[1].strip()
    text = parts[2].strip()

    user = await UserRepo.find_by_identifier(identifier)
    if user is None:
        await message.reply(f"❌ Пользователь <code>{identifier}</code> не найден в базе.", parse_mode="HTML")
        return

    tg_id = user["tg_id"]
    login = user["school_login"] or str(tg_id)

    try:
        await bot.send_message(chat_id=tg_id, text=f"📨 <b>Сообщение от модератора:</b>\n\n{text}", parse_mode="HTML")
        await message.reply(
            f"✅ Сообщение отправлено → <a href='tg://user?id={tg_id}'>{login}</a>",
            parse_mode="HTML",
        )
        logger.info("DM sent to %d (%s) by mod %d", tg_id, login, message.from_user.id)
    except Exception as exc:
        await message.reply(f"❌ Не удалось отправить: <code>{exc}</code>", parse_mode="HTML")
