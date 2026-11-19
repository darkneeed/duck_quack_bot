from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class BridgeState:
    """Thread-safe dynamic state cache synchronized from Kryaken Bridge API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runtime_config: dict[str, Any] = {}
        self._approved_chats: dict[int, dict[str, Any]] = {}
        self._last_sync_timestamp: float | None = None

    @property
    def runtime_config(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._runtime_config)

    @property
    def approved_chats(self) -> dict[int, dict[str, Any]]:
        with self._lock:
            return dict(self._approved_chats)

    @property
    def last_sync(self) -> float | None:
        return self._last_sync_timestamp

    @property
    def last_sync_timestamp(self) -> float | None:
        return self._last_sync_timestamp

    def update(
        self,
        runtime_config: dict[str, Any] | None = None,
        approved_chats: list[dict[str, Any]] | None = None,
    ) -> None:
        """Atomically update cached runtime config and approved chats."""
        with self._lock:
            if runtime_config is not None:
                self._runtime_config = dict(runtime_config)

            if approved_chats is not None:
                new_approved: dict[int, dict[str, Any]] = {}
                for chat in approved_chats:
                    if not isinstance(chat, dict):
                        continue
                    raw_id = chat.get("tg_chat_id")
                    if raw_id is not None:
                        try:
                            chat_id = int(raw_id)
                            new_approved[chat_id] = chat
                        except (ValueError, TypeError):
                            logger.warning("Skipping chat with invalid tg_chat_id: %r", raw_id)
                self._approved_chats = new_approved

            self._last_sync_timestamp = time.time()

    def is_chat_approved(self, chat_id: int) -> bool:
        """Check whether a group chat ID is currently in approved chats."""
        try:
            cid = int(chat_id)
        except (ValueError, TypeError):
            return False

        with self._lock:
            return cid in self._approved_chats

    def get_chat_config(self, chat_id: int) -> dict[str, Any]:
        """Return the configuration dictionary for an approved chat.

        Returns defensive copy of config_json if defined, config_overrides if defined,
        or empty dict if chat is unknown.
        """
        try:
            cid = int(chat_id)
        except (ValueError, TypeError):
            return {}

        with self._lock:
            chat = self._approved_chats.get(cid)
            if not chat:
                return {}

            cfg = chat.get("config_json")
            if isinstance(cfg, dict):
                return dict(cfg)

            cfg_overrides = chat.get("config_overrides")
            if isinstance(cfg_overrides, dict):
                return dict(cfg_overrides)

            return dict(chat)

    def get_approved_chat_ids(self) -> set[int]:
        """Return a set of all currently approved Telegram chat IDs."""
        with self._lock:
            return set(self._approved_chats.keys())

    def is_cache_fresh(self, max_age: float = 60.0) -> bool:
        """Check if cached state has been synchronized within max_age seconds."""
        ts = self._last_sync_timestamp
        if ts is None:
            return False
        return (time.time() - ts) <= max_age

    def get_command_scope(self, command: str) -> str:
        """Get the visibility scope for a given command.

        Returns configured scope (e.g. 'ALL', 'BOTH', 'PRIVATE', 'PUBLIC', 'OFF')
        or defaults to 'all'.
        """
        if not isinstance(command, str) or not command.strip():
            return "all"

        raw = command.strip().lstrip("/")
        if "@" in raw:
            raw = raw.split("@", 1)[0]
        clean_cmd = raw.lower()

        with self._lock:
            scopes = self._runtime_config.get("command_scopes")
            if not isinstance(scopes, dict):
                return "all"

            # Direct match on normalized command
            if clean_cmd in scopes:
                return str(scopes[clean_cmd])

            # Check original command as-is
            if command in scopes:
                return str(scopes[command])

            # Check stripped raw command
            if raw in scopes:
                return str(scopes[raw])

            # Check case-insensitive match
            for k, v in scopes.items():
                if isinstance(k, str) and k.lower() == clean_cmd:
                    return str(v)

            # Check cmd_<name>_scope format
            scoped_key = f"cmd_{clean_cmd}_scope"
            if scoped_key in scopes:
                return str(scopes[scoped_key])

            for k, v in scopes.items():
                if isinstance(k, str) and k.lower() == scoped_key:
                    return str(v)

            return "all"
