from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Router
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, ChatPermissions

from ..config import Config


from ..db.moderator_repo import ModeratorRepo
from ..services.antispam import check_message, get_config, set_config, set_enabled
from ..services.community_moderation import (
    display_name,
    parse_reply_or_id,
    resolve_target_label,
    safe_delete_messages,
    scope_ok,
    send_moderation_alert,
)

logger = logging.getLogger(__name__)
router = Router(name="chat_moderation")

class _IsMod(BaseFilter):
    async def __call__(self, message: Message, config: Config) -> bool:
        if not message.from_user:
            return False
        if message.chat.id != config.community_chat_id:
            return False
        uid = message.from_user.id
        if uid in config.admin_ids:
            return True
        return await ModeratorRepo.is_moderator(uid)

class _InCommunity(BaseFilter):
    async def __call__(self, message: Message, config: Config) -> bool:
        return message.chat.id == config.community_chat_id


@router.message(_IsMod(), Command("бан", "ban", ignore_case=True))
async def cmd_ban(message: Message, bot: Bot, config: Config) -> None:
    parts = (message.text or "").split(maxsplit=2)[1:]  # drop command
    target_id, rest = parse_reply_or_id(message, parts)

    if not target_id:
        await message.reply(
            "Использование:\n"
            "• Ответом: <code>/бан [причина]</code>\n"
            "• Прямо: <code>/бан &lt;id&gt; [причина]</code>",
            parse_mode="HTML",
        )
        return

    if target_id in config.admin_ids:
        await message.reply("⚠️ Нельзя забанить модератора.")
        return

    reason = " ".join(rest).strip()
    reason_text = f"\n📝 Причина: {reason}" if reason else ""

    try:
        await bot.ban_chat_member(chat_id=config.community_chat_id, user_id=target_id)
    except Exception as exc:
        await message.reply(f"❌ Не удалось забанить: <code>{exc}</code>", parse_mode="HTML")
        return

    target_label = await resolve_target_label(target_id, message.reply_to_message)
    mod_label = display_name(message.from_user)

    await message.reply(
        f"🚫 <b>Бан</b>\n👤 {target_label}\n👮 {mod_label}{reason_text}",
        parse_mode="HTML",
    )
    await safe_delete_messages(message.reply_to_message, message)
    await send_moderation_alert(
        bot, config,
        logger,
        f"🚫 <b>Бан в чате участников</b>\n\n"
        f"👤 {target_label} (ID: <code>{target_id}</code>)\n"
        f"👮 {mod_label}{reason_text}",
    )
    logger.info("Ban: target=%d mod=%d reason=%r", target_id, message.from_user.id, reason)


@router.message(_IsMod(), Command("анмут", "unmute", ignore_case=True))
async def cmd_unmute(message: Message, bot: Bot, config: Config) -> None:
    parts = (message.text or "").split(maxsplit=1)
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(parts) > 1 and parts[1].strip().isdigit():
        target_id = int(parts[1].strip())
    else:
        target_id, _ = parse_reply_or_id(message, parts[1:])
        if target_id == message.from_user.id and not message.reply_to_message:
            target_id = None

    if not target_id:
        await message.reply("Использование:\n• Ответом: <code>/анмут</code>\n• Прямо: <code>/анмут &lt;id&gt;</code>", parse_mode="HTML")
        return

    from aiogram.types import ChatPermissions
    try:
        await bot.restrict_chat_member(
            chat_id=config.community_chat_id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_change_info=True, can_invite_users=True,
                can_pin_messages=True, can_manage_topics=True,
            ),
        )
    except Exception as exc:
        await message.reply(f"❌ Ошибка: <code>{exc}</code>", parse_mode="HTML")
        return

    target_name = "?"
    try:
        _member = await bot.get_chat_member(config.community_chat_id, target_id)
        target_name = _member.user.full_name
    except Exception:
        target_name = f"ID {target_id}"

    await message.reply(f"🔊 Мут снят с: <a href=\"tg://user?id={target_id}\">{target_name}</a>", parse_mode="HTML")

@router.message(_IsMod(), Command("мут", "mute", ignore_case=True))
async def cmd_mute(message: Message, bot: Bot, config: Config) -> None:
    parts = (message.text or "").split(maxsplit=3)[1:]  # drop command
    target_id, rest = _parse_reply_or_id(message, parts)

    if not target_id or not rest:
        await message.reply(
            "Использование:\n"
            "• Ответом: <code>/мут &lt;минуты&gt; [причина]</code>\n"
            "• Прямо: <code>/мут &lt;id&gt; &lt;минуты&gt; [причина]</code>",
            parse_mode="HTML",
        )
        return

    try:
        minutes = int(rest[0])
    except (ValueError, IndexError):
        await message.reply("❌ Укажите количество минут числом.\nПример: <code>/мут 60 флуд</code>", parse_mode="HTML")
        return

    if target_id in config.admin_ids:
        await message.reply("⚠️ Нельзя замутить модератора.")
        return

    reason = " ".join(rest[1:]).strip()
    reason_text = f"\n📝 Причина: {reason}" if reason else ""
    until_date = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    try:
        await bot.restrict_chat_member(
            chat_id=config.community_chat_id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
    except Exception as exc:
        await message.reply(f"❌ Не удалось замутить: <code>{exc}</code>", parse_mode="HTML")
        return

    if minutes < 60:
        label = f"{minutes} мин."
    elif minutes < 1440:
        label = f"{minutes // 60} ч."
    else:
        label = f"{minutes // 1440} д."

    target_label = await resolve_target_label(target_id, message.reply_to_message)
    mod_label = display_name(message.from_user)

    await message.reply(
        f"🔇 <b>Мут на {label}</b>\n👤 {target_label}\n👮 {mod_label}{reason_text}",
        parse_mode="HTML",
    )
    await safe_delete_messages(message)
    await send_moderation_alert(
        bot, config,
        logger,
        f"🔇 <b>Мут в чате участников</b>\n\n"
        f"👤 {target_label} (ID: <code>{target_id}</code>) на {label}\n"
        f"👮 {mod_label}{reason_text}",
    )
    logger.info("Mute: target=%d min=%d mod=%d reason=%r", target_id, minutes, message.from_user.id, reason)


@router.message(_IsMod(), Command("разбан", "razban", "unban", ignore_case=True))
async def cmd_unban(message: Message, bot: Bot, config: Config) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: <code>/разбан &lt;id&gt;</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1].strip())
    except ValueError:
        await message.reply("❌ ID должен быть числом.")
        return

    try:
        await bot.unban_chat_member(
            chat_id=config.community_chat_id,
            user_id=target_id,
            only_if_banned=True,
        )
    except Exception as exc:
        await message.reply(f"❌ Ошибка: <code>{exc}</code>", parse_mode="HTML")
        return

    await message.reply(f"✅ <code>{target_id}</code> разбанен.", parse_mode="HTML")
    await safe_delete_messages(message)
    logger.info("Unban: target=%d mod=%d", target_id, message.from_user.id)


@router.message(_IsMod(), Command("удалить", "udalit", "delete", ignore_case=True))
async def cmd_delete(message: Message) -> None:
    if not message.reply_to_message:
        await message.reply("Используйте команду ответом на удаляемое сообщение.")
        return
    try:
        await message.reply_to_message.delete()
    except Exception as exc:
        await message.reply(f"❌ Не удалось удалить: <code>{exc}</code>", parse_mode="HTML")
        return
    await safe_delete_messages(message)


@router.message(_InCommunity(), Command("алярм", "alyarm", "alarm", ignore_case=True))
async def cmd_alarm(message: Message, bot: Bot, config: Config) -> None:
    if not message.reply_to_message:
        await message.reply("Используйте команду ответом на нарушающее сообщение.")
        return

    reporter = message.from_user
    offender = message.reply_to_message.from_user

    db_mods = await ModeratorRepo.get_all()
    db_mod_ids = {m["tg_id"] for m in db_mods}
    all_mod_ids = set(config.admin_ids) | db_mod_ids
    pings = " ".join(
        f"<a href='tg://user?id={uid}'>&#8204;</a>"
        for uid in all_mod_ids
    )

    await message.reply(
        f"🚨 Модераторы вызваны!{pings}\n\nЖалоба принята.",
        parse_mode="HTML",
    )

    reported_text = (
        message.reply_to_message.text or
        message.reply_to_message.caption or
        "<i>не текстовое сообщение</i>"
    )
    reported_preview = reported_text[:500] + ("…" if len(reported_text) > 500 else "")

    await send_moderation_alert(
        bot, config,
        logger,
        f"🚨 <b>Алярм из чата участников</b>\n\n"
        f"👤 Жалоба от: {display_name(reporter)}\n"
        f"⚠️ На сообщение от: {display_name(offender)}\n\n"
        f"💬 <b>Текст:</b>\n{reported_preview}",
        forward=message.reply_to_message,
    )

    logger.info("Alarm: reporter=%d on user=%s", reporter.id, offender.id if offender else "?")


@router.message(Command("вкампусе", "incampus", ignore_case=True))
async def cmd_incampus(message: Message, config: Config, s21) -> None:
    if not scope_ok(message.chat.type, config.cmd_incampus_scope):
        return
    """Показывает всех approved участников которые сейчас в кампусе"""
    from ..db import UserRepo

    approved = await UserRepo.get_approved_users()
    approved_logins = {u["school_login"] for u in approved if u["school_login"]}

    try:
        clusters = await s21.get_campus_clusters(config.s21_campus_id)
    except Exception as exc:
        await message.reply(f"⚠️ Не удалось получить данные: <code>{exc}</code>", parse_mode="HTML")
        return

    current: dict[str, str] = {}
    for cluster in clusters:
        cluster_id = cluster.get("id")
        cluster_name = cluster.get("name") or str(cluster_id)
        try:
            seats = await s21.get_cluster_map(cluster_id)
        except Exception:
            continue
        for seat in seats:
            login = seat.get("login")
            if login and login in approved_logins:
                row = seat.get("row", "")
                number = seat.get("number", "")
                current[login] = f"{cluster_name} {row}{number}".strip()

    if not current:
        await message.reply("🏙 Сейчас никого нет в кампусе.")
        return

    lines = [f"🖥 <b>В кампусе сейчас — {len(current)}</b>\n"]
    # Group by cluster
    by_cluster: dict[str, list[str]] = {}
    for login, seat in sorted(current.items(), key=lambda x: x[1]):
        cluster = seat.split()[0] if seat else "?"
        by_cluster.setdefault(cluster, []).append(f"  <code>{login}</code> — {seat}")

    for cluster_name, entries in by_cluster.items():
        lines.append(f"<b>{cluster_name}:</b>")
        lines.extend(entries)

    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("events", "мероприятия", ignore_case=True))
async def cmd_events_community(message: Message, s21, config: Config) -> None:
    if not scope_ok(message.chat.type, config.cmd_events_scope):
        return
    """Ближайшие мероприятия."""
    from datetime import datetime, timezone, timedelta
    from ..services.events import _format_event

    now = datetime.now(timezone.utc)
    to = now + timedelta(days=30)
    try:
        events = await s21.get_events(
            now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except Exception as exc:
        await message.reply(f"❌ Ошибка: <code>{exc}</code>", parse_mode="HTML")
        return
    if not events:
        await message.reply("📭 Ближайших мероприятий не найдено.")
        return
    for event in events[:10]:
        await message.reply(_format_event(event, config), parse_mode="HTML", disable_web_page_preview=True)


@router.message(_InCommunity())
async def antispam_check(message: Message, bot: Bot, config: Config) -> None:
    await check_message(message, bot, config)


@router.message(_IsMod(), Command("антиспам", "antispam", ignore_case=True))
async def cmd_antispam(message: Message, config: Config) -> None:
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else "статус"

    if arg in ("выкл", "off", "disable"):
        await set_enabled(False)
        await message.reply("✅ Антиспам <b>отключён</b>.", parse_mode="HTML")
        return

    if arg in ("статус", "status"):
        cfg = await get_config()
        status = "✅ включён" if cfg["enabled"] else "❌ отключён"
        await message.reply(
            f"📊 <b>Антиспам:</b> {status}\n\n"
            f"Порог: <b>{cfg['msg_count']}</b> сообщений за <b>{cfg['window_secs']}с</b>\n"
            f"Мут: <b>{cfg['mute_minutes']} мин.</b>\n\n"
            f"Изменить: <code>/антиспам вкл &lt;сообщений&gt; &lt;секунд&gt; &lt;мут_минут&gt;</code>",
            parse_mode="HTML",
        )
        return

    tokens = arg.split()
    if tokens[0] not in ("вкл", "on", "enable") or len(tokens) < 4:
        await message.reply(
            "Использование:\n"
            "<code>/антиспам вкл &lt;сообщений&gt; &lt;секунд&gt; &lt;мут_минут&gt;</code>\n"
            "<code>/антиспам выкл</code>\n"
            "<code>/антиспам статус</code>\n\n"
            "Пример: <code>/антиспам вкл 5 10 30</code>",
            parse_mode="HTML",
        )
        return

    try:
        msg_count    = int(tokens[1])
        window_secs  = int(tokens[2])
        mute_minutes = int(tokens[3])
    except ValueError:
        await message.reply("❌ Все параметры должны быть числами.")
        return

    if msg_count < 2 or window_secs < 1 or mute_minutes < 1:
        await message.reply("❌ Минимальные значения: сообщений ≥ 2, секунд ≥ 1, мут ≥ 1.")
        return

    await set_config(1, msg_count, window_secs, mute_minutes)
    await message.reply(
        f"✅ Антиспам <b>включён</b>\n\n"
        f"Порог: <b>{msg_count}</b> сообщений за <b>{window_secs}с</b>\n"
        f"Мут: <b>{mute_minutes} мин.</b>",
        parse_mode="HTML",
    )


@router.message(Command("топ", "top", ignore_case=True))
async def cmd_top(message: Message, config: Config) -> None:
    if not scope_ok(message.chat.type, config.cmd_top_scope):
        return
    """Топ-10 + место вызвавшего участника по XP из кэша."""
    from ..db import UserRepo
    from ..db.s21_cache_repo import S21CacheRepo

    approved = await UserRepo.get_approved_users()
    scores: list[tuple[str, int, int, str]] = []

    for user in approved:
        login = user["school_login"]
        if not login:
            continue
        data = await S21CacheRepo.get(login)
        if not data:
            continue
        info      = data.get("info") or {}
        coalition = (data.get("coalition") or {}).get("name") or ""
        xp        = info.get("expValue", 0) or 0
        level     = info.get("level", 0) or 0
        scores.append((login, xp, level, coalition))

    if not scores:
        await message.reply("📭 Нет данных. Кэш ещё не заполнен — попробуйте позже.")
        return

    scores.sort(key=lambda x: x[1], reverse=True)

    medals = ["🥇", "🥈", "🥉"] + ["4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    login_to_tgid = {u["school_login"]: u["tg_id"] for u in approved if u["school_login"]}

    def fmt_row(i: int, login: str, xp: int, level: int, coalition: str) -> str:
        medal  = medals[i] if i < len(medals) else f"{i+1}."
        xp_str = f"{xp:,}".replace(",", " ")
        tribe  = f" · {coalition}" if coalition else ""
        tg_id  = login_to_tgid.get(login)
        name   = f"<a href='tg://user?id={tg_id}'>{login}</a>" if tg_id else f"<code>{login}</code>"
        return f"{medal} {name}{tribe} — {xp_str} XP (ур. {level})"

    lines = [f"🏆 <b>Топ-10 из {len(scores)}</b>\n"]
    for i, (login, xp, level, coalition) in enumerate(scores[:10]):
        lines.append(fmt_row(i, login, xp, level, coalition))

    caller_login = None
    if message.from_user:
        caller = await UserRepo.get_by_tg_id(message.from_user.id)
        if caller:
            caller_login = caller["school_login"] if caller else None

    if len(scores) >= 21:
        login, xp, level, coalition = scores[20]
        lines.append("")
        lines.append("— — —")
        lines.append(fmt_row(20, login, xp, level, coalition))

    if caller_login:
        caller_pos = next(
            (i for i, (lg, *_) in enumerate(scores) if lg == caller_login), None
        )
        if caller_pos is not None and caller_pos >= 10 and caller_pos != 20:
            login, xp, level, coalition = scores[caller_pos]
            lines.append("")
            lines.append("— — —")
            lines.append(fmt_row(caller_pos, login, xp, level, coalition))

    await message.reply("\n".join(lines), parse_mode="HTML")
