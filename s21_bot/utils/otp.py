from __future__ import annotations

import hashlib
import hmac
import logging
import secrets

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS: int = 600
OTP_MAX_ATTEMPTS: int = 3
OTP_LENGTH: int = 6


def _generate_secret() -> str:
    return secrets.token_hex(32)


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def _hmac_code(secret: str, code: str) -> str:
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def _compare_hmac(secret: str, code: str, stored_digest: str) -> bool:
    digest = _hmac_code(secret, code)
    return hmac.compare_digest(digest, stored_digest)


def generate_otp() -> tuple[str, str, str]:
    secret = _generate_secret()
    code = _generate_code()
    digest = _hmac_code(secret, code)
    return code, secret, digest


def verify_otp(candidate: str, secret: str, stored_digest: str) -> bool:
    return _compare_hmac(secret, candidate.strip(), stored_digest)
