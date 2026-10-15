from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RCUserInfo:
    user_id: str
    username: str
    active: bool


class RocketChatError(Exception):
    pass


class RocketChatClient:
    def __init__(
        self,
        base_url: str,
        user_id: str = "",
        auth_token: str = "",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_id = user_id
        self._auth_token = auth_token
        self._username = username
        self._password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._auth_lock = asyncio.Lock()

    async def login(self) -> None:
        if not self._username or not self._password:
            raise RocketChatError("Cannot login to Rocket.Chat: username or password not configured")
        assert self._session is not None, "RocketChatClient not started"
        async with self._auth_lock:
            payload = {"user": self._username, "password": self._password}
            async with self._session.post(
                self._url("/api/v1/login"), json=payload
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RocketChatError(f"Rocket.Chat login failed ({resp.status}): {text}")
                data = await resp.json()

            if not data.get("success") or data.get("status") != "success":
                raise RocketChatError(f"Rocket.Chat login returned failure: {data}")

            auth_data = data.get("data", {})
            self._user_id = auth_data.get("userId", "")
            self._auth_token = auth_data.get("authToken", "")
            logger.info("Rocket.Chat login successful for user=%s (userId=%s)", self._username, self._user_id)

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=15.0, connect=5.0)
        self._session = aiohttp.ClientSession(timeout=timeout)
        if (not self._user_id or not self._auth_token) and self._username and self._password:
            await self.login()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self._user_id:
            headers["X-User-Id"] = self._user_id
        if self._auth_token:
            headers["X-Auth-Token"] = self._auth_token
        return headers

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def _get(self, path: str, **params: str) -> dict:
        assert self._session is not None, "RocketChatClient not started"
        for attempt in range(2):
            async with self._session.get(
                self._url(path), headers=self._headers, params=params
            ) as resp:
                if resp.status == 401 and attempt == 0 and self._username and self._password:
                    logger.warning("Rocket.Chat returned 401 Unauthorized, re-authenticating...")
                    try:
                        await self.login()
                        continue
                    except Exception as exc:
                        logger.error("Failed to re-authenticate with Rocket.Chat: %s", exc)
                resp.raise_for_status()
                return await resp.json()
        raise RocketChatError(f"Rocket.Chat GET {path} failed")

    async def _post(self, path: str, payload: dict) -> dict:
        assert self._session is not None, "RocketChatClient not started"
        for attempt in range(2):
            async with self._session.post(
                self._url(path), headers=self._headers, json=payload
            ) as resp:
                if resp.status == 401 and attempt == 0 and self._username and self._password:
                    logger.warning("Rocket.Chat returned 401 Unauthorized, re-authenticating...")
                    try:
                        await self.login()
                        continue
                    except Exception as exc:
                        logger.error("Failed to re-authenticate with Rocket.Chat: %s", exc)
                resp.raise_for_status()
                return await resp.json()
        raise RocketChatError(f"Rocket.Chat POST {path} failed")

    async def get_user_info(self, username: str) -> Optional[RCUserInfo]:
        """
        GET /api/v1/users.info?username=<username>

        Returns None if the user does not exist (API returns success=false).
        Raises RocketChatError on unexpected payloads.
        Raises aiohttp.ClientError on network / HTTP errors.
        """
        data = await self._get("/api/v1/users.info", username=username)

        if not data.get("success"):
            logger.info("users.info success=false for username=%s", username)
            return None

        user = data.get("user")
        if not isinstance(user, dict):
            raise RocketChatError(f"Unexpected users.info payload: {data}")

        return RCUserInfo(
            user_id=user["_id"],
            username=user["username"],
            active=bool(user.get("active", False)),
        )

    async def send_direct_message(self, username: str, text: str) -> str:
        """
        POST /api/v1/chat.postMessage  {channel: "@username", text: "…"}

        Returns the message _id on success.
        Raises RocketChatError if success != true.
        Raises aiohttp.ClientError on network / HTTP errors.
        """
        data = await self._post(
            "/api/v1/chat.postMessage",
            {"channel": f"@{username}", "text": text},
        )

        if not data.get("success"):
            raise RocketChatError(f"chat.postMessage failed: {data}")

        msg = data.get("message", {})
        msg_id = msg.get("_id", "")
        logger.info(
            "RC DM sent to @%s | channel=%s msg_id=%s rid=%s",
            username, data.get("channel"), msg_id, msg.get("rid"),
        )
        return msg_id
