from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any, FrozenSet


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


RUNTIME_CONFIG_ENV_MAP: dict[str, str] = {
    "moderation_topic_id": "MODERATION_TOPIC_ID",
    "invite_link_expire_seconds": "INVITE_LINK_EXPIRE_SECONDS",
    "events_topic_id": "EVENTS_TOPIC_ID",
    "workstation_topic_id": "WORKSTATION_TOPIC_ID",
    "newcomer_topic_id": "NEWCOMER_TOPIC_ID",
    "digest_topic_id": "DIGEST_TOPIC_ID",
    "pending_alert_hours": "PENDING_ALERT_HOURS",
    "failed_auth_topic_id": "FAILED_AUTH_TOPIC_ID",
    "notify_topic_id": "NOTIFY_TOPIC_ID",
    "api_poll_interval": "API_POLL_INTERVAL",
    "workstation_poll_interval": "WORKSTATION_POLL_INTERVAL",
    "api_down_alert_minutes": "API_DOWN_ALERT_MINUTES",
    "review_notify_minutes": "REVIEW_NOTIFY_MINUTES",
    "s21_request_interval_ms": "S21_REQUEST_INTERVAL_MS",
    "s21_429_backoff_seconds": "S21_429_BACKOFF_SECONDS",
    "rules_url": "RULES_URL",
    "platform_base_url": "PLATFORM_BASE_URL",
    "community_name": "COMMUNITY_NAME",
    "community_city": "COMMUNITY_CITY",
    "display_timezone": "DISPLAY_TIMEZONE",
    "enable_digest": "ENABLE_DIGEST",
    "enable_workstation": "ENABLE_WORKSTATION",
    "enable_newcomer": "ENABLE_NEWCOMER",
    "auto_delete_join_messages": "AUTO_DELETE_JOIN_MESSAGES",
    "cmd_where_scope": "CMD_WHERE_SCOPE",
    "cmd_peers_scope": "CMD_PEERS_SCOPE",
    "cmd_logtime_scope": "CMD_LOGTIME_SCOPE",
    "cmd_top_scope": "CMD_TOP_SCOPE",
    "cmd_incampus_scope": "CMD_INCAMPUS_SCOPE",
    "cmd_events_scope": "CMD_EVENTS_SCOPE",
    "cmd_profile_scope": "CMD_PROFILE_SCOPE",
    "support_contacts": "SUPPORT_CONTACTS",
    "social_trust_project_ids": "SOCIAL_TRUST_PROJECT_IDS",
}

RUNTIME_CONFIG_KEYS: tuple[str, ...] = tuple(RUNTIME_CONFIG_ENV_MAP.keys())
RUNTIME_CONFIG_KEY_SET: frozenset[str] = frozenset(RUNTIME_CONFIG_KEYS)


@dataclass
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
    auto_delete_join_messages: bool = field(default=False)

    cmd_where_scope: str = field(default="BOTH")
    cmd_peers_scope: str = field(default="BOTH")
    cmd_logtime_scope: str = field(default="BOTH")
    cmd_top_scope: str = field(default="PUBLIC")
    cmd_incampus_scope: str = field(default="PUBLIC")
    cmd_events_scope: str = field(default="BOTH")
    cmd_profile_scope: str = field(default="PRIVATE")

    support_contacts: list = field(default_factory=list)
    social_trust_project_ids: frozenset = field(default_factory=frozenset)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() not in ("0", "false", "off", "no", "")


def _serialize_field(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (set, frozenset, list, tuple)):
        return ",".join(str(x) for x in value)
    return str(value)


def serialize_config(config: Config) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in config.__dataclass_fields__:
        out[name] = _serialize_field(getattr(config, name))
    return out


def serialize_runtime_config(config: Config) -> dict[str, str]:
    serialized = serialize_config(config)
    return {key: serialized[key] for key in RUNTIME_CONFIG_KEYS}


def _coerce_field(name: str, raw_value: str, current: Config) -> Any:
    base = getattr(current, name)
    int_list_fields = {"review_notify_minutes"}
    int_set_fields = {"social_trust_project_ids", "admin_ids"}
    scope_fields = {
        "cmd_where_scope",
        "cmd_peers_scope",
        "cmd_logtime_scope",
        "cmd_top_scope",
        "cmd_incampus_scope",
        "cmd_events_scope",
        "cmd_profile_scope",
    }
    if isinstance(base, bool):
        return _parse_bool(raw_value)
    if name in scope_fields:
        return raw_value.strip().upper()
    if name in int_list_fields:
        return [int(x.strip()) for x in raw_value.split(",") if x.strip()]
    if name in int_set_fields:
        return frozenset(int(x.strip()) for x in raw_value.split(",") if x.strip())
    if isinstance(base, int) and not isinstance(base, bool):
        return int(raw_value.strip())
    if base is None:
        return int(raw_value.strip()) if raw_value.strip() else None
    if isinstance(base, list):
        if base and isinstance(base[0], int):
            return [int(x.strip()) for x in raw_value.split(",") if x.strip()]
        return [x.strip() for x in raw_value.split(",") if x.strip()]
    if isinstance(base, (set, frozenset)):
        if base and all(isinstance(x, int) for x in base):
            return frozenset(int(x.strip()) for x in raw_value.split(",") if x.strip())
        return frozenset(x.strip() for x in raw_value.split(",") if x.strip())
    return raw_value


def apply_config_overrides(config: Config, overrides: dict[str, str]) -> None:
    for key, raw_value in overrides.items():
        if key not in RUNTIME_CONFIG_KEY_SET or not hasattr(config, key):
            continue
        try:
            setattr(config, key, _coerce_field(key, raw_value, config))
        except Exception:
            continue


def set_config_value(config: Config, key: str, raw_value: str) -> Any:
    if key not in RUNTIME_CONFIG_KEY_SET or not hasattr(config, key):
        raise KeyError(key)
    parsed = _coerce_field(key, raw_value, config)
    setattr(config, key, parsed)
    return parsed


def get_runtime_config_keys() -> tuple[str, ...]:
    return RUNTIME_CONFIG_KEYS


def get_legacy_runtime_overrides(existing_keys: set[str] | frozenset[str] | None = None) -> dict[str, str]:
    existing = set(existing_keys or ())
    overrides: dict[str, str] = {}

    for key, env_name in RUNTIME_CONFIG_ENV_MAP.items():
        if key in existing:
            continue

        if key == "notify_topic_id":
            if env_name in os.environ:
                overrides[key] = os.environ[env_name]
            elif "FAILED_AUTH_TOPIC_ID" in os.environ:
                overrides[key] = os.environ["FAILED_AUTH_TOPIC_ID"]
            continue

        if env_name not in os.environ:
            continue
        overrides[key] = os.environ[env_name]

    return overrides


def load_config() -> Config:
    return Config(
        bot_token=_require("BOT_TOKEN"),
        admin_ids=_int_list("ADMIN_IDS"),
        moderation_chat_id=_require_int("MODERATION_CHAT_ID"),
        moderation_topic_id=0,
        s21_username=_require("S21_API_USERNAME"),
        s21_password=_require("S21_API_PASSWORD"),
        s21_campus_id=_require("S21_CAMPUS_ID"),
        community_chat_id=_require_int("COMMUNITY_CHAT_ID"),
        rc_base_url=_require("RC_BASE_URL"),
        rc_user_id=_require("RC_USER_ID"),
        rc_auth_token=_require("RC_AUTH_TOKEN"),
        db_path=os.environ.get("DB_PATH", "data/bot.db"),
    )
