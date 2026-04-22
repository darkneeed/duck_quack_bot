from __future__ import annotations

import logging
import secrets
from enum import Enum
from typing import Optional

from ..db.invite_code_repo import InviteCodeRepo
from ..utils.helpers import now_iso

logger = logging.getLogger(__name__)

_CODE_LENGTH = 8

INVITE_CODE_TTL_SECONDS: int = 10 * 60
INVITE_CODE_USAGE_LIMIT: int = 1


class ValidationResult(str, Enum):
    OK         = "ok"
    NOT_FOUND  = "not_found"
    INACTIVE   = "inactive"
    EXPIRED    = "expired"
    EXHAUSTED  = "exhausted"


class AttachResult(str, Enum):
    OK              = "ok"
    ALREADY_ATTACHED = "already_attached"
    INVALID         = "invalid"


def _generate_code() -> str:
    return secrets.token_hex(_CODE_LENGTH // 2).upper()


async def create_invite_code(
    creator_user_id: int,
    campus_id: Optional[str] = None,
    wave_id: Optional[str] = None,
) -> str:
    now = now_iso()

    from datetime import datetime, timezone, timedelta
    expires_dt = datetime.now(timezone.utc) + timedelta(seconds=INVITE_CODE_TTL_SECONDS)
    expires_at: str = expires_dt.strftime("%Y-%m-%d %H:%M:%S")

    for _ in range(5):
        code = _generate_code()
        existing = await InviteCodeRepo.get_by_code(code)
        if existing is None:
            break
    else:
        raise RuntimeError("Could not generate a unique invite code after 5 attempts")

    await InviteCodeRepo.create(
        code=code,
        creator_user_id=creator_user_id,
        created_at=now,
        expires_at=expires_at,
        usage_limit=INVITE_CODE_USAGE_LIMIT,
        campus_id=campus_id,
        wave_id=wave_id,
    )
    logger.info(
        "Invite code created: code=%s creator=%d usage_limit=%d expires_at=%s",
        code, creator_user_id, INVITE_CODE_USAGE_LIMIT, expires_at or "never",
    )
    return code


def build_bot_link(code: str, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start={code}"


async def validate_invite_code(
    code: str,
    candidate_user_id: int,
) -> tuple[ValidationResult, Optional[dict]]:
    row = await InviteCodeRepo.get_by_code(code)
    if row is None:
        return ValidationResult.NOT_FOUND, None

    if not row["is_active"]:
        return ValidationResult.INACTIVE, None

    if row["expires_at"] is not None:
        from datetime import datetime, timezone
        expires_dt = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        if datetime.now(timezone.utc) > expires_dt:
            return ValidationResult.EXPIRED, None

    if row["used_count"] >= row["usage_limit"]:
        return ValidationResult.EXHAUSTED, None

    return ValidationResult.OK, dict(row)


async def attach_invite_code_to_request(
    app_id: int,
    code: str,
    candidate_user_id: int,
) -> AttachResult:
    existing_code_id = await InviteCodeRepo.get_application_code_id(app_id)
    if existing_code_id is not None:
        return AttachResult.ALREADY_ATTACHED

    result, row = await validate_invite_code(code, candidate_user_id)
    if result != ValidationResult.OK or row is None:
        return AttachResult.INVALID

    code_id: int = row["id"]
    now = now_iso()

    await InviteCodeRepo.mark_used(code_id, candidate_user_id, now)
    await InviteCodeRepo.attach_to_application(app_id, code_id)

    new_used_count = row["used_count"] + 1
    if new_used_count >= row["usage_limit"]:
        await InviteCodeRepo.deactivate(code_id)

    logger.info(
        "Invite code attached: code=%s code_id=%d app_id=%d candidate=%d trust_bonus=%d",
        code, code_id, app_id, candidate_user_id, row["trust_bonus"],
    )
    return AttachResult.OK


VALIDATION_MESSAGES: dict[ValidationResult, str] = {
    ValidationResult.NOT_FOUND: "❌ Код не найден. Проверьте правильность ввода.",
    ValidationResult.INACTIVE:  "❌ Этот код деактивирован.",
    ValidationResult.EXPIRED:   "⏰ Срок действия кода истёк.",
    ValidationResult.EXHAUSTED: "❌ Этот код уже был использован максимальное количество раз.",
}
