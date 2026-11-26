"""Coordinates of edited articles, for the incident map of the dashboard.

The Wikimedia stream has no location of the editor. Many articles, however,
have coordinates (a city, a stadium, a battle). GeoService asks the public
Wikipedia API for them:

    GET {server_url}/w/api.php?action=query&prop=coordinates&titles=<title>

Only reverts and alerts are looked up, not every edit, so the api sends a few
requests per minute. Answers (also "no coordinates") stay in an LRU cache, and
the last points stay in memory for GET /api/geo/recent.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass
from typing import Any

import httpx

logger = logging.getLogger("editwar.api")

USER_AGENT = "EditWarSentinel/1.0 (student project; https://github.com/m1ttt/editwar-sentinel)"


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """One revert or alert on an article that has coordinates."""

    kind: str  # "revert" or "alert"
    wiki: str
    title: str
    lat: float
    lon: float
    page_url: str
    timestamp: str  # ISO 8601
    severity: str | None = None  # alerts only
    alert_kind: str | None = None  # alerts only

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_coordinates(payload: dict[str, Any]) -> tuple[float, float] | None:
    """Read the primary Earth coordinates from an API answer (formatversion=2)."""
    pages = payload.get("query", {}).get("pages", [])
    for page in pages:
        for coordinate in page.get("coordinates", []):
            if coordinate.get("globe", "earth") == "earth":
                return float(coordinate["lat"]), float(coordinate["lon"])
    return None


class GeoService:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        max_points: int = 200,
        cache_size: int = 5000,
        concurrency: int = 2,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=5.0, headers={"User-Agent": USER_AGENT})
        self._cache: OrderedDict[tuple[str, str], tuple[float, float] | None] = OrderedDict()
        self._cache_size = cache_size
        self._limit = asyncio.Semaphore(concurrency)  # polite to the Wikipedia API
        self._points: deque[GeoPoint] = deque(maxlen=max_points)

    async def coordinates(self, server_url: str, title: str) -> tuple[float, float] | None:
        """Coordinates of an article, or None. Network errors are not cached."""
        if title == "*":  # wiki-wide alerts have no article
            return None
        key = (server_url, title)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        params = {
            "action": "query",
            "prop": "coordinates",
            "coprimary": "primary",
            "titles": title,
            "format": "json",
            "formatversion": "2",
        }
        async with self._limit:
            try:
                response = await self._client.get(f"{server_url}/w/api.php", params=params)
                response.raise_for_status()
                result = parse_coordinates(response.json())
            except (httpx.HTTPError, ValueError, KeyError) as error:
                logger.debug("no coordinates for %s %s: %s", server_url, title, error)
                return None
        self._cache[key] = result
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    def add(self, point: GeoPoint) -> None:
        self._points.append(point)

    def recent(self, limit: int) -> list[GeoPoint]:
        """The last points, newest first."""
        return list(self._points)[::-1][:limit]

    async def close(self) -> None:
        await self._client.aclose()
