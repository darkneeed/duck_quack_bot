from __future__ import annotations

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
    def __init__(self, base_url: str, user_id: str, auth_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_id = user_id
        self._auth_token = auth_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-User-Id": self._user_id,
            "X-Auth-Token": self._auth_token,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def _get(self, path: str, **params: str) -> dict:
        assert self._session is not None, "RocketChatClient not started"
        async with self._session.get(
            self._url(path), headers=self._headers, params=params
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, payload: dict) -> dict:
        assert self._session is not None, "RocketChatClient not started"
        async with self._session.post(
            self._url(path), headers=self._headers, json=payload
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

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
