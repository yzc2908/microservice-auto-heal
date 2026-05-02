"""
Sentry integration client for fetching error events, stack traces,
and aggregated issue statistics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

SENTRY_API_BASE = "https://sentry.io/api/0"


@dataclass
class SentryErrorEvent:
    event_id: str
    issue_id: str
    title: str
    culprit: str
    level: str
    timestamp: datetime
    stacktrace: str
    raw: dict[str, Any]


class SentryClient:
    """Fetches and parses error data from Sentry's REST API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.sentry_auth_token
        self._org = settings.sentry_org
        self._project = settings.sentry_project
        self._client = httpx.AsyncClient(
            base_url=SENTRY_API_BASE,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def fetch_recent_issues(self, limit: int = 20) -> list[SentryErrorEvent]:
        """Retrieve the most recent unresolved Sentry issues."""
        url = f"/projects/{self._org}/{self._project}/issues/"
        params: dict[str, str | int] = {
            "query": "is:unresolved",
            "limit": limit,
            "sort": "new",
        }

        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        issues = resp.json()

        events: list[SentryErrorEvent] = []
        for issue in issues[:limit]:
            event = await self._fetch_latest_event(issue["id"])
            if event:
                events.append(event)

        return events

    async def fetch_issue_by_id(self, issue_id: str) -> Optional[SentryErrorEvent]:
        """Fetch a specific Sentry issue and its latest event."""
        return await self._fetch_latest_event(issue_id)

    async def _fetch_latest_event(self, issue_id: str) -> Optional[SentryErrorEvent]:
        url = f"/issues/{issue_id}/events/"
        resp = await self._client.get(url, params={"limit": 1})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        events = resp.json()
        if not events:
            return None

        raw = events[0]
        return SentryErrorEvent(
            event_id=raw.get("eventID", raw.get("id", "")),
            issue_id=issue_id,
            title=raw.get("title", ""),
            culprit=raw.get("culprit", ""),
            level=raw.get("level", "error"),
            timestamp=_parse_sentry_ts(raw.get("dateCreated", "")),
            stacktrace=self._extract_stacktrace(raw),
            raw=raw,
        )

    @staticmethod
    def _extract_stacktrace(raw: dict[str, Any]) -> str:
        entries = raw.get("entries", [])
        for entry in entries:
            if entry.get("type") == "stacktrace":
                frames = entry.get("data", {}).get("frames", [])
                return _format_frames(frames)
            if entry.get("type") == "exception":
                exc_values = entry.get("data", {}).get("values", [])
                for exc in exc_values:
                    frames = exc.get("stacktrace", {}).get("frames", [])
                    if frames:
                        return _format_frames(frames)
        return ""

    async def close(self) -> None:
        await self._client.aclose()


def _format_frames(frames: list[dict[str, Any]]) -> str:
    lines = []
    for f in reversed(frames[-25:]):  # Last 25 frames, reversed for top-to-bottom
        filename = f.get("filename", "?")
        function = f.get("function", "?")
        lineno = f.get("lineNo", "?")
        context_line = ""
        if f.get("context"):
            context_line = f["context"][0][1].strip() if f["context"] else ""
        lines.append(f"  {filename}:{lineno} in {function}  {context_line}")
    return "\n".join(lines)


def _parse_sentry_ts(ts_str: str) -> datetime:
    if not ts_str:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=timezone.utc)
