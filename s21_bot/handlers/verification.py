from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from ..config import Config
from ..db import ApplicationRepo
from ..db.verifier_repo import VerificationVerifierRepo
from ..services.social_trust import evaluate_votes
from ..utils.helpers import now_iso
from ..utils.telegram import safe_callback_answer
from ..strings import (
    VERIFY_BAD_REQUEST, VERIFY_UNKNOWN_VOTE, VERIFY_BAD_ID,
    VERIFY_NOT_VERIFIER, VERIFY_ALREADY_VOTED, VERIFY_VOTING_CLOSED,
    VERIFY_VOTE_CONFIRM, VERIFY_VOTE_DECLINE, VERIFY_VOTE_SUSPICIOUS,
    VERIFY_VOTE_LABEL_SUFFIX,
)

logger = logging.getLogger(__name__)
router = Router(name="verification")

_VOTE_LABELS = {
    "confirm":    "✅ Подтвердить",
    "decline":    "❌ Не могу подтвердить",
    "suspicious": "⚠️ Выглядит странно",
}


@router.callback_query(F.data.startswith("verify:"))
async def cb_verify(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await safe_callback_answer(callback, VERIFY_BAD_REQUEST, show_alert=True)
        return

    _, app_id_str, vote = parts
    if vote not in _VOTE_LABELS:
        await safe_callback_answer(callback, VERIFY_UNKNOWN_VOTE, show_alert=True)
        return

    try:
        app_id = int(app_id_str)
    except ValueError:
        await safe_callback_answer(callback, VERIFY_BAD_ID, show_alert=True)
        return

    tg_id = callback.from_user.id

    record = await VerificationVerifierRepo.get_by_verifier_and_request(tg_id, app_id)
    if record is None:
        await safe_callback_answer(callback, VERIFY_NOT_VERIFIER, show_alert=True)
        return

    if record["vote"] is not None:
        already = _VOTE_LABELS.get(record["vote"], record["vote"])
        await safe_callback_answer(
            callback,
            VERIFY_ALREADY_VOTED.format(label=already),
            show_alert=True,
        )
        return

    app = await ApplicationRepo.get(app_id)
    if app is None or app["status"] != "waiting_votes":
        await safe_callback_answer(callback, VERIFY_VOTING_CLOSED, show_alert=True)
        return

    await VerificationVerifierRepo.record_vote(record["id"], vote, now_iso())

    reply_text = {
        "confirm":    VERIFY_VOTE_CONFIRM,
        "decline":    VERIFY_VOTE_DECLINE,
        "suspicious": VERIFY_VOTE_SUSPICIOUS,
    }[vote]

    try:
        await callback.message.edit_text(
            callback.message.html_text + VERIFY_VOTE_LABEL_SUFFIX.format(label=reply_text),
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        pass

    await safe_callback_answer(callback, reply_text)

    logger.info(
        "Vote recorded: app_id=%d verifier_tg_id=%d vote=%s",
        app_id, tg_id, vote,
    )

    await evaluate_votes(app_id=app_id, bot=bot, config=config)
