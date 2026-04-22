from __future__ import annotations
import asyncio
import logging
import time
from email.utils import parsedate_to_datetime
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://auth.21-school.ru/auth/realms/EduPowerKeycloak/protocol/openid-connect/token"
_BASE_URL = "https://platform.21-school.ru/services/21-school/api/v1"
_MAX_429_RETRIES = 2


class S21Client:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        request_interval_ms: int = 750,
        backoff_seconds: int = 15,
    ) -> None:
        self._username = username
        self._password = password
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_down_since: Optional[float] = None
        self._api_down_alerted: bool = False
        self._request_interval_seconds = max(request_interval_ms, 0) / 1000
        self._rate_limit_backoff_seconds = max(backoff_seconds, 1)
        self._request_gate = asyncio.Lock()
        self._next_request_at: float = 0.0
        self._rate_limited_until: float = 0.0

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        await self._authenticate()

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def _authenticate(self) -> None:
        assert self._session is not None
        payload = {"client_id": "s21-open-api", "username": self._username, "password": self._password, "grant_type": "password"}
        async with self._session.post(_TOKEN_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}) as resp:
            resp.raise_for_status()
            data = await resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._token_expires_at = time.monotonic() + data.get("expires_in", 300) - 60

    async def _refresh_or_reauth(self) -> None:
        assert self._session is not None
        if not self._refresh_token:
            await self._authenticate()
            return
        try:
            async with self._session.post(_TOKEN_URL, data={"client_id": "s21-open-api", "refresh_token": self._refresh_token, "grant_type": "refresh_token"}, headers={"Content-Type": "application/x-www-form-urlencoded"}) as resp:
                if resp.status != 200:
                    await self._authenticate()
                    return
                data = await resp.json()
        except aiohttp.ClientError:
            await self._authenticate()
            return
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._token_expires_at = time.monotonic() + data.get("expires_in", 300) - 60

    async def _headers(self) -> dict[str, str]:
        if time.monotonic() >= self._token_expires_at:
            await self._refresh_or_reauth()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _wait_for_request_slot(self) -> None:
        while True:
            async with self._request_gate:
                now = time.monotonic()
                wait_for = max(
                    self._next_request_at - now,
                    self._rate_limited_until - now,
                    0.0,
                )
                if wait_for <= 0:
                    self._next_request_at = now + self._request_interval_seconds
                    return
            await asyncio.sleep(wait_for)

    def _retry_after_seconds(self, retry_after_header: str | None) -> float:
        if retry_after_header:
            retry_after_header = retry_after_header.strip()
            try:
                return max(float(retry_after_header), 0.0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after_header).timestamp()
                    return max(retry_at - time.time(), 0.0)
                except (TypeError, ValueError, IndexError, OverflowError):
                    pass
        return float(self._rate_limit_backoff_seconds)

    def _set_rate_limit_backoff(self, retry_after_seconds: float) -> None:
        self._rate_limited_until = max(
            self._rate_limited_until,
            time.monotonic() + max(retry_after_seconds, 0.0),
        )

    async def _request(self, path: str, *, response_format: str = "json") -> Optional[dict | list | str]:
        assert self._session is not None
        url = f"{_BASE_URL}{path}"
        for attempt in range(_MAX_429_RETRIES + 1):
            await self._wait_for_request_slot()
            async with self._session.get(url, headers=await self._headers()) as resp:
                if resp.status == 404:
                    self._api_down_since = None
                    self._api_down_alerted = False
                    return None

                if resp.status == 429:
                    retry_after_seconds = self._retry_after_seconds(
                        resp.headers.get("Retry-After")
                    )
                    self._set_rate_limit_backoff(retry_after_seconds)
                    logger.warning(
                        "S21 API rate limited for %s; backoff=%.2fs attempt=%d/%d",
                        path,
                        retry_after_seconds,
                        attempt + 1,
                        _MAX_429_RETRIES + 1,
                    )
                    if attempt >= _MAX_429_RETRIES:
                        resp.raise_for_status()
                    continue

                resp.raise_for_status()
                self._api_down_since = None
                self._api_down_alerted = False
                if response_format == "text":
                    return await resp.text()
                return await resp.json()

        raise RuntimeError("S21 request retry loop exited unexpectedly")

    async def _get(self, path: str) -> Optional[dict | list]:
        data = await self._request(path)
        if data is None:
            return None
        return data

    async def _get_text(self, path: str) -> Optional[str]:
        data = await self._request(path, response_format="text")
        if data is None:
            return None
        return str(data)

    def mark_api_down(self) -> float:
        if self._api_down_since is None:
            self._api_down_since = time.monotonic()
        return time.monotonic() - self._api_down_since

    def mark_api_up(self) -> bool:
        was_down = self._api_down_since is not None
        self._api_down_since = None
        self._api_down_alerted = False
        return was_down

    def should_alert_down(self, threshold_minutes: int = 5) -> bool:
        if self._api_down_since is None or self._api_down_alerted:
            return False
        down_seconds = time.monotonic() - self._api_down_since
        if down_seconds >= threshold_minutes * 60:
            self._api_down_alerted = True
            return True
        return False

    async def get_participant(self, login: str) -> Optional[dict]:
        return await self._get(f"/participants/{login}")

    async def get_coalition(self, login: str) -> Optional[dict]:
        return await self._get(f"/participants/{login}/coalition")

    async def get_badges(self, login: str) -> list[dict]:
        data = await self._get(f"/participants/{login}/badges")
        if not data:
            return []
        return data.get("badges", []) if isinstance(data, dict) else data

    async def get_points(self, login: str) -> Optional[dict]:
        return await self._get(f"/participants/{login}/points")

    async def get_projects(self, login: str, status: str | None = None, limit: int = 10) -> list[dict]:
        path = f"/participants/{login}/projects?limit={limit}"
        if status:
            path += f"&status={status}"
        data = await self._get(path)
        if not data:
            return []
        return data.get("projects", []) if isinstance(data, dict) else data

    async def get_active_projects(self, login: str) -> list[dict]:
        result = []
        for status in ("IN_PROGRESS", "IN_REVIEWS", "REGISTERED"):
            projects = await self.get_projects(login, status=status, limit=5)
            result.extend(projects)
        return result

    async def get_skills(self, login: str) -> list[dict]:
        data = await self._get(f"/participants/{login}/skills")
        if not data:
            return []
        return data.get("skills", []) if isinstance(data, dict) else data

    async def get_logtime(self, login: str) -> Optional[float]:
        data = await self._get(f"/participants/{login}/logtime")
        if data is None:
            return None
        return float(data) if isinstance(data, (int, float)) else None

    async def get_workstation(self, login: str) -> Optional[dict]:
        text = await self._get_text(f"/participants/{login}/workstation")
        if not text or not text.strip() or text.strip() == "null":
            return None  # не в кампусе - пустой ответ норма
        import json as _json
        try:
            return _json.loads(text)
        except Exception:
            return None

    async def get_campus_participants(self, campus_id: str, limit: int = 1000) -> list[str]:
        data = await self._get(f"/campuses/{campus_id}/participants?limit={limit}")
        if not data:
            return []
        participants = data.get("participants", []) if isinstance(data, dict) else data
        return [p if isinstance(p, str) else p.get("login", "") for p in participants]

    async def get_campus_clusters(self, campus_id: str) -> list[dict]:
        data = await self._get(f"/campuses/{campus_id}/clusters")
        if not data:
            return []
        return data.get("clusters", []) if isinstance(data, dict) else data

    async def get_cluster_map(self, cluster_id: int) -> list[dict]:
        data = await self._get(f"/clusters/{cluster_id}/map?limit=1000&occupied=true")
        if not data:
            return []
        seats = data.get("clusterMap", []) if isinstance(data, dict) else data
        return [s for s in seats if s.get("login")]

    async def get_events(self, from_dt: str, to_dt: str, limit: int = 100) -> list[dict]:
        data = await self._get(f"/events?from={from_dt}&to={to_dt}&limit={limit}")
        if not data:
            return []
        return data.get("events", []) if isinstance(data, dict) else data

    async def validate_participant(self, login: str, campus_id: str | None = None) -> tuple[bool, Optional[str], Optional[str]]:
        try:
            info = await self.get_participant(login)
        except aiohttp.ClientResponseError as exc:
            logger.error("S21 API error validating '%s': %s", login, exc)
            raise
        if info is None:
            return False, None, "not_found"
        if info.get("expelledDate") or info.get("status", "").lower() == "expelled":
            return False, None, "expelled"
        if campus_id:
            participant_campus = (info.get("campus") or {}).get("id")
            if participant_campus and participant_campus != campus_id:
                return False, None, "wrong_campus"
        coalition_data = await self.get_coalition(login)
        coalition_name = coalition_data.get("name") if coalition_data else None
        return True, coalition_name, None

    async def has_badge(self, login: str, badge_name: str) -> bool:
        badges = await self.get_badges(login)
        name_lower = badge_name.lower()
        return any(name_lower in (b.get("name") or "").lower() for b in badges)

    async def get_full_profile(self, login: str) -> dict:
        import asyncio
        info, coalition, points, active_projects, skills = await asyncio.gather(
            self.get_participant(login),
            self.get_coalition(login),
            self.get_points(login),
            self.get_active_projects(login),
            self.get_skills(login),
            return_exceptions=True,
        )
        return {
            "info": info if not isinstance(info, Exception) else None,
            "coalition": coalition if not isinstance(coalition, Exception) else None,
            "points": points if not isinstance(points, Exception) else None,
            "active_projects": active_projects if not isinstance(active_projects, Exception) else [],
            "skills": skills if not isinstance(skills, Exception) else [],
        }
