from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from s21_bot.services.bridge_state import BridgeState

logger = logging.getLogger(__name__)

ALLOWED_CHAT_ACTIONS = frozenset({"added", "removed", "rights_changed"})


class BridgeClient:
    """HTTP client communicating with the Kryaken Platform Bridge API (/api/v1/bridge/*)."""

    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        bridge_state: BridgeState | None = None,
        *,
        bridge_url: str | None = None,
        bridge_secret: str | None = None,
        state: BridgeState | None = None,
        sync_interval: int = 60,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        raw_url = base_url or bridge_url or "https://quack-21.mwnd.tech"
        clean_url = raw_url.rstrip("/")
        if clean_url.endswith("/api/v1/bridge"):
            clean_url = clean_url[:-len("/api/v1/bridge")].rstrip("/")
        elif clean_url.endswith("/api/v1"):
            clean_url = clean_url[:-len("/api/v1")].rstrip("/")
        self.base_url: str = clean_url
        self.secret: str = secret or bridge_secret or ""
        self.state: BridgeState | None = bridge_state if bridge_state is not None else state
        self.sync_interval: int = sync_interval
        self._session: aiohttp.ClientSession | None = session
        self._sync_task: asyncio.Task | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or getattr(self._session, "closed", False) is True:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch_config(self) -> dict[str, Any] | None:
        """Fetch runtime configuration and approved chats from Bridge API.

        Updates the associated BridgeState when available.
        Returns the parsed dictionary, or None on failure.
        """
        url = f"{self.base_url}/api/v1/bridge/config"
        headers = {"X-Bridge-Secret": self.secret}

        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning("Bridge config fetch failed with status HTTP %d", resp.status)
                    return None
                data = await resp.json()
                if not isinstance(data, dict):
                    logger.warning("Bridge config response is not a dict: %r", type(data))
                    return None

                if self.state is not None:
                    self.state.update(
                        runtime_config=data.get("runtime_config"),
                        approved_chats=data.get("approved_chats"),
                    )
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Bridge config fetch network error: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Bridge config fetch unexpected error: %s", exc)
            return None

    async def report_chat_event(
        self,
        tg_chat_id: int,
        title: str,
        chat_type: str,
        action: str,
    ) -> dict[str, Any] | None:
        """Report a chat membership or permission update to the Bridge API.

        Valid actions: 'added', 'removed', 'rights_changed'.
        Raises ValueError if action is unsupported before making network call.
        """
        if action not in ALLOWED_CHAT_ACTIONS:
            raise ValueError(
                f"Invalid chat action '{action}'. Supported actions: {sorted(ALLOWED_CHAT_ACTIONS)}"
            )

        url = f"{self.base_url}/api/v1/bridge/chats/event"
        headers = {
            "X-Bridge-Secret": self.secret,
            "Content-Type": "application/json",
        }
        payload = {
            "tg_chat_id": int(tg_chat_id),
            "title": title,
            "chat_type": chat_type,
            "action": action,
        }

        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning("Bridge chat event failed with status HTTP %d", resp.status)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Bridge chat event network error: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Bridge chat event unexpected error: %s", exc)
            return None

    # Alias for dispatch compatibility
    post_chat_event = report_chat_event

    async def lookup_peer(self, login: str) -> dict[str, Any] | None:
        """Proxy peer lookup via School 21 API pool on the Bridge."""
        url = f"{self.base_url}/api/v1/bridge/s21/peer/{login}"
        headers = {"X-Bridge-Secret": self.secret}

        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 404:
                    return None
                if resp.status >= 400:
                    logger.warning("Bridge peer lookup failed for %s with status HTTP %d", login, resp.status)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Bridge peer lookup network error for %s: %s", login, exc)
            return None
        except Exception as exc:
            logger.warning("Bridge peer lookup unexpected error for %s: %s", login, exc)
            return None

    def start_sync_task(self, interval_seconds: int | None = None) -> asyncio.Task:
        """Start periodic background synchronization of runtime configuration."""
        interval = interval_seconds if interval_seconds is not None else self.sync_interval

        async def _sync_loop() -> None:
            while True:
                try:
                    await self.fetch_config()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("Unexpected error during bridge config sync: %s", exc)

                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break

        self._sync_task = asyncio.create_task(_sync_loop())
        return self._sync_task

    async def close(self) -> None:
        """Cancel background tasks and close client session."""
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def consume_tg_link(
        self,
        raw_token: str,
        tg_id: int,
        tg_username: str | None = None,
        tg_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Consume a Kryaken one-time Telegram link token."""
        url = f"{self.base_url}/api/v1/bridge/tg-link/consume"
        headers = {
            "X-Bridge-Secret": self.secret,
            "Content-Type": "application/json",
        }
        payload = {
            "raw_token": raw_token,
            "tg_id": int(tg_id),
            "tg_username": tg_username,
            "tg_name": tg_name,
        }
        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as resp:
                data = None
                try:
                    data = await resp.json()
                except Exception:
                    pass
                if resp.status >= 400:
                    logger.warning("Bridge tg-link consume failed with status HTTP %d", resp.status)
                    if isinstance(data, dict):
                        return data
                    return None
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Bridge tg-link consume network error: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Bridge tg-link consume unexpected error: %s", exc)
            return None

    async def handle_callback(
        self,
        callback_data: str,
        tg_id: int,
        tg_username: str | None = None,
        tg_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Forward an inline button callback to Kryaken Bridge API."""
        url = f"{self.base_url}/api/v1/bridge/callback"
        headers = {
            "X-Bridge-Secret": self.secret,
            "Content-Type": "application/json",
        }
        payload = {
            "callback_data": callback_data,
            "tg_id": int(tg_id),
            "tg_username": tg_username,
            "tg_name": tg_name,
        }
        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as resp:
                data = None
                try:
                    data = await resp.json()
                except Exception:
                    pass
                if resp.status >= 400:
                    logger.warning("Bridge callback failed with status HTTP %d", resp.status)
                    if isinstance(data, dict):
                        return data
                    return None
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Bridge callback network error: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Bridge callback unexpected error: %s", exc)
            return None
