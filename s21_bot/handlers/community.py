from __future__ import annotations
import logging
from aiogram import Bot, Router
from aiogram.methods import SetChatMemberTag
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION
from ..config import Config
from ..db import UserRepo
from ..db.guest_invite_repo import GuestInviteRepo
from ..strings import (
    GUEST_WELCOME,
    NEWCOMER_COALITION,
    NEWCOMER_HEADER,
    NEWCOMER_LOGIN,
    NEWCOMER_PROFILE_LINK,
    NEWCOMER_TG_ID,
    NEWCOMER_TG_NAME,
    NEWCOMER_UNVERIFIED_KICK,
    NEWCOMER_WRONG_LINK,
)
from ..utils.branding import build_profile_url
from ..utils.telegram import send_message_with_topic

logger = logging.getLogger(__name__)
router = Router(name="community")


async def _kick(bot: Bot, chat_id: int, user_id: int) -> None:
    """Kick without blacklist (ban + unban)."""
    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
    await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def _alert(bot: Bot, config: Config, text: str) -> None:
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.failed_auth_topic_id or None,
            topic_name="FAILED_AUTH_TOPIC_ID",
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Failed to send alert: %s", exc)


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_member_joined(update: ChatMemberUpdated, bot: Bot, config: Config) -> None:
    if update.chat.id != config.community_chat_id:
        return

    member = update.new_chat_member.user
    if member.is_bot:
        return

    used_link = update.invite_link.invite_link if update.invite_link else None
    tg_name = member.full_name or str(member.id)
    if member.username:
        tg_name += f" (@{member.username})"

    # Ищем пользователя по tg_id
    user = await UserRepo.get_by_tg_id(member.id)

    # Если ссылка использована — ищем кому она принадлежит
    link_owner = None
    if used_link:
        link_owner = await UserRepo.get_by_invite_link(used_link)

    # Сценарий 1: пользователь зашёл по чужой ссылке
    # (ссылка есть в БД, но принадлежит другому tg_id)
    if link_owner and link_owner["tg_id"] != member.id:
        logger.warning(
            "User %d used invite link of user %d (%s)",
            member.id, link_owner["tg_id"], link_owner["school_login"]
        )
        try:
            await _kick(bot, config.community_chat_id, member.id)
        except Exception as exc:
            logger.error("Failed to kick user %d: %s", member.id, exc)

        await _alert(bot, config,
            NEWCOMER_WRONG_LINK.format(
                tg_name=tg_name,
                tg_id=member.id,
                owner_name=link_owner["tg_name"],
                owner_id=link_owner["tg_id"],
                owner_login=link_owner["school_login"] or "—",
            )
        )
        return

    # Сценарий 2: пользователь не верифицирован (нет в БД или статус не approved)
    if not user or user["status"] != "approved":
        logger.warning("Unverified user %d joined community chat (link: %s)", member.id, used_link)
        try:
            await _kick(bot, config.community_chat_id, member.id)
        except Exception as exc:
            logger.error("Failed to kick unverified user %d: %s", member.id, exc)

        await _alert(bot, config,
            NEWCOMER_UNVERIFIED_KICK.format(
                tg_name=tg_name,
                tg_id=member.id,
                invite_link=used_link or "неизвестно (вступил без ссылки)",
            )
        )
        return

    # Сценарий 3: всё ок
    login = user["school_login"]
    coalition = user["coalition"]
    is_guest = user["is_guest"] if "is_guest" in user.keys() else 0

    # Гость из другого кампуса
    if is_guest and login:
        home_campus = user["home_campus"] or "?"
        tg_name_full = member.full_name or str(member.id)
        if member.username:
            tg_name_full += f" (@{member.username})"
        if config.newcomer_topic_id and getattr(config, "enable_newcomer", True):
            try:
                await send_message_with_topic(
                    bot,
                    chat_id=config.community_chat_id,
                    message_thread_id=config.newcomer_topic_id,
                    topic_name="NEWCOMER_TOPIC_ID",
                    topic_logger=logger,
                    text=GUEST_WELCOME.format(
                        login=login,
                        tg_id=member.id,
                        tg_name=tg_name_full,
                        campus=home_campus,
                        coalition=coalition or "—",
                        url=build_profile_url(login, config),
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                logger.error("Guest welcome failed: %s", exc)
        try:
            invite = await GuestInviteRepo.get_pending_for_tg_id(member.id)
            if invite:
                await GuestInviteRepo.mark_used(invite["id"])
        except Exception:
            pass
        return

    if config.newcomer_topic_id and login:
        lines = [NEWCOMER_HEADER]
        lines.append(NEWCOMER_LOGIN.format(login=login))
        lines.append(NEWCOMER_TG_ID.format(tg_id=member.id))
        lines.append(NEWCOMER_TG_NAME.format(tg_name=user["tg_name"]))
        if coalition:
            lines.append(NEWCOMER_COALITION.format(coalition=coalition))
        lines.append(NEWCOMER_PROFILE_LINK.format(url=build_profile_url(login, config)))
        try:
            await send_message_with_topic(
                bot,
                chat_id=config.community_chat_id,
                message_thread_id=config.newcomer_topic_id,
                topic_name="NEWCOMER_TOPIC_ID",
                topic_logger=logger,
                text="\n".join(lines),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.error("Failed to send newcomer notification: %s", exc)

    if login:
        try:
            await bot(SetChatMemberTag(
                chat_id=config.community_chat_id,
                user_id=member.id,
                tag=login,
            ))
            logger.info("Set tag '%s' for user %d", login, member.id)
        except Exception as exc:
            logger.warning("Failed to set tag for user %d: %s", member.id, exc)
