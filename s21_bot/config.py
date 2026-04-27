from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import FrozenSet


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return value


def _require_int(key: str) -> int:
    return int(_require(key))


def _int_list(key: str) -> FrozenSet[int]:
    raw = os.environ.get(key, "")
    if not raw.strip():
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return frozenset(int(x.strip()) for x in raw.split(",") if x.strip())


def _opt_list(key: str) -> list[str]:
    raw = os.environ.get(key, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _opt_int(key: str) -> int | None:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return None
    return int(raw)


def _opt_int_list(key: str) -> list[int]:
    return [int(x) for x in _opt_list(key)]


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: FrozenSet[int]
    moderation_chat_id: int
    moderation_topic_id: int
    s21_username: str
    s21_password: str
    s21_campus_id: str
    community_chat_id: int

    rc_base_url: str
    rc_user_id: str
    rc_auth_token: str

    db_path: str = field(default="data/bot.db")
    invite_link_expire_seconds: int = field(default=86_400)
    events_topic_id: int = field(default=0)
    workstation_topic_id: int = field(default=0)
    newcomer_topic_id: int = field(default=0)
    digest_topic_id: int = field(default=0)
    pending_alert_hours: int = field(default=0)
    failed_auth_topic_id: int = field(default=0)
    notify_topic_id: int = field(default=0)
    api_poll_interval: int = field(default=120)
    workstation_poll_interval: int | None = field(default=None)
    api_down_alert_minutes: int = field(default=5)
    review_notify_minutes: list[int] = field(default_factory=list)
    s21_request_interval_ms: int = field(default=750)
    s21_429_backoff_seconds: int = field(default=15)
    rules_url: str = field(default="https://docs.google.com/document/d/1eDYD1tKE7tW7P_8I3k7Bt4F1aknvwed2qweXCcCrFZc/edit?tab=t.0")
    platform_base_url: str = field(default="https://platform.21-school.ru")
    community_name: str = field(default="Школы 21")
    community_city: str = field(default="Волгоград")
    display_timezone: str = field(default="Europe/Moscow")
    enable_digest: bool = field(default=True)
    enable_workstation: bool = field(default=True)
    enable_newcomer: bool = field(default=True)

    cmd_where_scope: str = field(default="BOTH")
    cmd_peers_scope: str = field(default="BOTH")
    cmd_logtime_scope: str = field(default="BOTH")
    cmd_top_scope: str = field(default="PUBLIC")
    cmd_incampus_scope: str = field(default="PUBLIC")
    cmd_events_scope: str = field(default="BOTH")
    cmd_profile_scope: str = field(default="PRIVATE")

    support_contacts: list = field(default_factory=list)
    social_trust_project_ids: frozenset = field(default_factory=frozenset)


def load_config() -> Config:
    return Config(
        bot_token=_require("BOT_TOKEN"),
        admin_ids=_int_list("ADMIN_IDS"),
        moderation_chat_id=_require_int("MODERATION_CHAT_ID"),
        moderation_topic_id=int(os.environ.get("MODERATION_TOPIC_ID", "0")),
        s21_username=_require("S21_API_USERNAME"),
        s21_password=_require("S21_API_PASSWORD"),
        s21_campus_id=_require("S21_CAMPUS_ID"),
        community_chat_id=_require_int("COMMUNITY_CHAT_ID"),
        rc_base_url=_require("RC_BASE_URL"),
        rc_user_id=_require("RC_USER_ID"),
        rc_auth_token=_require("RC_AUTH_TOKEN"),
        db_path=os.environ.get("DB_PATH", "data/bot.db"),
        invite_link_expire_seconds=int(os.environ.get("INVITE_LINK_EXPIRE_SECONDS", "86400")),
        events_topic_id=int(os.environ.get("EVENTS_TOPIC_ID", "0")),
        workstation_topic_id=int(os.environ.get("WORKSTATION_TOPIC_ID", "0")),
        newcomer_topic_id=int(os.environ.get("NEWCOMER_TOPIC_ID", "0")),
        digest_topic_id=int(os.environ.get("DIGEST_TOPIC_ID", "0")),
        pending_alert_hours=int(os.environ.get("PENDING_ALERT_HOURS", "0")),
        failed_auth_topic_id=int(os.environ.get("FAILED_AUTH_TOPIC_ID", "0")),
        notify_topic_id=int(
            os.environ.get("NOTIFY_TOPIC_ID") or
            os.environ.get("FAILED_AUTH_TOPIC_ID", "0")
        ),
        api_poll_interval=int(os.environ.get("API_POLL_INTERVAL", "120")),
        workstation_poll_interval=_opt_int("WORKSTATION_POLL_INTERVAL"),
        api_down_alert_minutes=int(os.environ.get("API_DOWN_ALERT_MINUTES", "5")),
        review_notify_minutes=_opt_int_list("REVIEW_NOTIFY_MINUTES"),
        s21_request_interval_ms=int(os.environ.get("S21_REQUEST_INTERVAL_MS", "750")),
        s21_429_backoff_seconds=int(os.environ.get("S21_429_BACKOFF_SECONDS", "15")),
        rules_url=os.environ.get("RULES_URL", "https://docs.google.com/document/d/1eDYD1tKE7tW7P_8I3k7Bt4F1aknvwed2qweXCcCrFZc/edit?tab=t.0"),
        platform_base_url=os.environ.get("PLATFORM_BASE_URL", "https://platform.21-school.ru"),
        community_name=os.environ.get("COMMUNITY_NAME", "Школы 21"),
        community_city=os.environ.get("COMMUNITY_CITY", "Волгоград"),
        display_timezone=os.environ.get("DISPLAY_TIMEZONE", "Europe/Moscow"),
        enable_digest=os.environ.get("ENABLE_DIGEST", "1") not in ("0", "false", "off"),
        enable_workstation=os.environ.get("ENABLE_WORKSTATION", "1") not in ("0", "false", "off"),
        enable_newcomer=os.environ.get("ENABLE_NEWCOMER", "1") not in ("0", "false", "off"),
        cmd_where_scope=os.environ.get("CMD_WHERE_SCOPE", "BOTH").upper(),
        cmd_peers_scope=os.environ.get("CMD_PEERS_SCOPE", "BOTH").upper(),
        cmd_logtime_scope=os.environ.get("CMD_LOGTIME_SCOPE", "BOTH").upper(),
        cmd_top_scope=os.environ.get("CMD_TOP_SCOPE", "PUBLIC").upper(),
        cmd_incampus_scope=os.environ.get("CMD_INCAMPUS_SCOPE", "PUBLIC").upper(),
        cmd_events_scope=os.environ.get("CMD_EVENTS_SCOPE", "BOTH").upper(),
        cmd_profile_scope=os.environ.get("CMD_PROFILE_SCOPE", "PRIVATE").upper(),

        support_contacts=_opt_list("SUPPORT_CONTACTS"),
        social_trust_project_ids=frozenset(
            int(x) for x in _opt_list("SOCIAL_TRUST_PROJECT_IDS")
        ),
    )
