from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp
from aiogram import Bot

from ..config import Config
from ..db import UserRepo, ApplicationRepo
from ..db.verifier_repo import VerificationVerifierRepo
from ..utils.helpers import now_iso
from ..utils.telegram import send_message_with_topic

logger = logging.getLogger(__name__)

_CONFIRM_MAJORITY: float = 0.5

async def _fetch_project_members(
    login: str, project_id: int, s21
) -> set[str]:
    """
    GET /v1/participants/{login}/projects/{project_id}
    Returns teammate logins. Empty set on 404 or any error.
    """
    try:
        data = await s21._get(f"/participants/{login}/projects/{project_id}")
    except aiohttp.ClientError as exc:
        logger.warning("S21 API error fetching project %d for %s: %s", project_id, login, exc)
        return set()

    if data is None:  # 404
        return set()

    members = data.get("teamMembers", []) if isinstance(data, dict) else []
    return {m["login"] for m in members if isinstance(m, dict) and m.get("login")}


async def get_candidate_teammates(login: str, s21, project_ids: frozenset) -> set[str]:
    """
    Fetch teammates from both group projects, remove candidate, deduplicate.
    Both 404s → empty set (not an error).
    """
    results = await asyncio.gather(
        *[_fetch_project_members(login, pid, s21) for pid in project_ids],
        return_exceptions=True,
    )
    teammates: set[str] = set()
    for r in results:
        if isinstance(r, set):
            teammates.update(r)
        elif isinstance(r, Exception):
            logger.warning("Teammate fetch exception: %s", r)
    teammates.discard(login)
    return teammates


async def resolve_teammates_to_users(teammate_logins: set[str]) -> list[dict]:
    """
    Resolve S21 logins to local bot users.
    Includes any user with the given school_login regardless of status
    (they might be pending themselves — still can vouch).
    """
    users = []
    for login in teammate_logins:
        row = await UserRepo.get_by_school_login_any_status(login)
        if row is not None:
            users.append(dict(row))
    return users


@dataclass
class AttachStats:
    created: int = 0
    updated_flag: int = 0
    skipped: int = 0


async def attach_teammates_to_request(
    app_id: int, users: list[dict]
) -> AttachStats:
    stats = AttachStats()
    for user in users:
        tg_id: int = user["tg_id"]
        school_login: str = user.get("school_login") or ""

        existing = await VerificationVerifierRepo.get_by_request_and_user(app_id, tg_id)
        if existing is None:
            await VerificationVerifierRepo.create(
                verification_request_id=app_id,
                verifier_user_id=tg_id,
                verifier_school_login=school_login,
                source_teammate_auto=True,
            )
            stats.created += 1
        elif not existing["source_teammate_auto"]:
            await VerificationVerifierRepo.set_teammate_auto_flag(existing["id"])
            stats.updated_flag += 1
        else:
            stats.skipped += 1
    return stats


@dataclass
class NotifyStats:
    sent: int = 0
    failed: int = 0


async def send_verification_requests(
    app_id: int,
    candidate_name: str,
    candidate_login: str,
    bot: Bot,
) -> NotifyStats:
    from ..keyboards.inline import verification_request_kb

    verifiers = await VerificationVerifierRepo.get_pending_notifications(app_id)
    stats = NotifyStats()

    for v in verifiers:
        tg_id: int = v["verifier_user_id"]
        record_id: int = v["id"]
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=(
                    f"👋 Привет!\n\n"
                    f"Участник <b>{candidate_name}</b> (<code>{candidate_login}</code>) "
                    f"подал заявку на вступление в чат Школы 21.\n\n"
                    f"Ты указан как участник совместного группового проекта — "
                    f"мы хотим узнать твоё мнение.\n\n"
                    f"<b>Ты знаешь этого человека как участника Школы 21?</b>"
                ),
                parse_mode="HTML",
                reply_markup=verification_request_kb(app_id, candidate_login),
            )
            await VerificationVerifierRepo.set_notification_sent(record_id, now_iso())
            stats.sent += 1
        except Exception as exc:
            logger.error("Failed to notify verifier tg_id=%d for app #%d: %s", tg_id, app_id, exc)
            stats.failed += 1

    return stats


async def evaluate_votes(
    app_id: int,
    bot: Bot,
    config: Config,
) -> None:
    """
    Called after every vote. Checks if a decision threshold has been reached.

    Thresholds (in priority order):
      1. Any 'suspicious' vote → immediately escalate to moderators
      2. strict majority of confirms → move application to pending (moderation queue)
      3. All votes cast, zero confirms → escalate to moderators for manual review
    """
    summary = await VerificationVerifierRepo.get_vote_summary(app_id)
    confirms = summary["confirm"]
    suspicious = summary["suspicious"]
    pending_votes = summary["pending"]

    app = await ApplicationRepo.get(app_id)
    if app is None or app["status"] != "waiting_votes":
        return
    if suspicious > 0:
        await ApplicationRepo.set_status(app_id, "pending")
        await _alert_moderators_suspicious(app_id, app, summary, bot, config)
        logger.info("App #%d escalated to moderators: suspicious vote", app_id)
        return

    total_voted = confirms + summary["decline"] + suspicious
    if pending_votes == 0 and total_voted > 0:
        majority = confirms / total_voted > _CONFIRM_MAJORITY
        if majority:
            await ApplicationRepo.set_status(app_id, "pending")
            await _notify_moderators_social_confirmed(app_id, app, summary, bot, config)
            logger.info("App #%d confirmed by majority (%d/%d), moved to pending",
                        app_id, confirms, total_voted)
        else:
            await ApplicationRepo.set_status(app_id, "pending")
            await _notify_moderators_no_confirms(app_id, app, summary, bot, config)
            logger.info("App #%d: no majority (%d/%d confirms) — escalated", app_id, confirms, total_voted)


def _vote_summary_text(summary: dict[str, int]) -> str:
    return (
        f"✅ Подтвердили: {summary['confirm']}\n"
        f"❌ Не смогли подтвердить: {summary['decline']}\n"
        f"⚠️ Подозрительно: {summary['suspicious']}\n"
        f"⏳ Ещё не ответили: {summary['pending']}"
    )


async def _send_moderator_alert(
    app_id: int,
    app: dict,
    text: str,
    bot: Bot,
    config: Config,
    result_label: str = "",
) -> None:
    from ..keyboards.inline import moderation_card_kb, decided_kb
    markup = decided_kb(result_label) if result_label else moderation_card_kb(app_id)
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            topic_logger=logger,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception as exc:
        logger.error("Failed to send moderator alert for app #%d: %s", app_id, exc)


async def _alert_moderators_suspicious(
    app_id: int, app: dict, summary: dict[str, int], bot: Bot, config: Config
) -> None:
    text = (
        f"🚨 <b>Тиммейт отметил заявку как подозрительную</b>\n\n"
        f"📋 Заявка: <b>#{app_id}</b>\n"
        f"🔑 Кандидат: <code>{app['school_login']}</code>\n\n"
        f"{_vote_summary_text(summary)}\n\n"
        f"Требуется ручная проверка."
    )
    await _send_moderator_alert(app_id, app, text, bot, config, result_label="suspicious")


async def _notify_moderators_social_confirmed(
    app_id: int, app: dict, summary: dict[str, int], bot: Bot, config: Config
) -> None:
    text = (
        f"✅ <b>Social trust: кандидат подтверждён тиммейтами</b>\n\n"
        f"📋 Заявка: <b>#{app_id}</b>\n"
        f"🔑 Кандидат: <code>{app['school_login']}</code>\n\n"
        f"{_vote_summary_text(summary)}\n\n"
        f"Заявка перешла в очередь модерации."
    )
    await _send_moderator_alert(app_id, app, text, bot, config, result_label="approved")


async def _notify_moderators_no_confirms(
    app_id: int, app: dict, summary: dict[str, int], bot: Bot, config: Config
) -> None:
    text = (
        f"⚠️ <b>Social trust: никто не подтвердил кандидата</b>\n\n"
        f"📋 Заявка: <b>#{app_id}</b>\n"
        f"🔑 Кандидат: <code>{app['school_login']}</code>\n\n"
        f"{_vote_summary_text(summary)}\n\n"
        f"Все тиммейты проголосовали, подтверждений нет. Требуется ручная проверка."
    )
    await _send_moderator_alert(app_id, app, text, bot, config, result_label="rejected")


async def _alert_moderators_no_teammates(
    app_id: int,
    candidate_login: str,
    candidate_name: str,
    bot: Bot,
    config: Config,
) -> None:
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            topic_logger=logger,
            text=(
                f"ℹ️ <b>Social trust: тиммейты не найдены</b>\n\n"
                f"📋 Заявка: <b>#{app_id}</b>\n"
                f"🔑 Кандидат: <code>{candidate_login}</code> ({candidate_name})\n\n"
                f"Зарегистрированных тиммейтов нет — автоматическая верификация невозможна.\n"
                f"Заявка ожидает ручного решения."
            ),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Failed to send no-teammates alert for app #%d: %s", app_id, exc)



async def _notify_moderators_waiting_votes(
    app_id: int,
    candidate_login: str,
    candidate_name: str,
    verifiers_count: int,
    verifier_logins: list[str],
    bot: Bot,
    config: Config,
) -> None:
    logins_text = ""
    if verifier_logins:
        logins_text = "\n👥 <b>Тиммейты:</b> " + ", ".join(
            f"<code>{tm}</code>" for tm in verifier_logins
        )
    try:
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            topic_logger=logger,
            text=(
                f"🔍 <b>Social trust запущен</b>\n\n"
                f"📋 Заявка: <b>#{app_id}</b>\n"
                f"🔑 Кандидат: <code>{candidate_login}</code> ({candidate_name})"
                f"{logins_text}\n\n"
                f"Отправлено запросов: <b>{verifiers_count}</b>. Ожидаем голосования."
            ),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Failed to send waiting_votes notification for app #%d: %s", app_id, exc)


async def run_social_trust(
    app_id: int,
    candidate_login: str,
    candidate_tg_name: str,
    bot: Bot,
    config: Config,
    s21,
) -> None:
    logger.info("[social_trust] Starting for app #%d login=%s", app_id, candidate_login)
    try:
        await ApplicationRepo.set_status(app_id, "waiting_votes")

        teammate_logins = await get_candidate_teammates(candidate_login, s21, config.social_trust_project_ids)
        logger.info("[social_trust] Teammates found for %s: %s", candidate_login, teammate_logins)

        users = await resolve_teammates_to_users(teammate_logins)
        logger.info("[social_trust] Registered users resolved: %d", len(users))

        if not users:
            # No registered teammates — alert moderators, leave in waiting_votes
            logger.info("[social_trust] No registered teammates for app #%d, alerting moderators", app_id)
            await _alert_moderators_no_teammates(
                app_id, candidate_login, candidate_tg_name, bot, config
            )
            return

        attach_stats = await attach_teammates_to_request(app_id, users)
        logger.info("[social_trust] Attach stats for app #%d: %s", app_id, attach_stats)

        notify_stats = await send_verification_requests(
            app_id=app_id,
            candidate_name=candidate_tg_name,
            candidate_login=candidate_login,
            bot=bot,
        )
        logger.info("[social_trust] Notify stats for app #%d: %s", app_id, notify_stats)

        notified_logins = [
            u["verifier_school_login"] or str(u["verifier_user_id"])
            for u in await VerificationVerifierRepo.get_all_for_request(app_id)
            if u["notification_sent_at"] is not None
        ]

        await _notify_moderators_waiting_votes(
            app_id=app_id,
            candidate_login=candidate_login,
            candidate_name=candidate_tg_name,
            verifiers_count=notify_stats.sent,
            verifier_logins=notified_logins,
            bot=bot,
            config=config,
        )

    except Exception as exc:
        logger.error(
            "[social_trust] Pipeline failed for app #%d: %s", app_id, exc, exc_info=True
        )
