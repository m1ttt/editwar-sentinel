"""Live metrics calculated in memory from the edits and reverts topics.

The windows use the time when the api receives each event (an injected clock),
not event.timestamp: in replay mode the events carry old timestamps.
Every api replica reads every edit, so every replica has the same numbers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter, deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from editwar_domain import EditEvent, RevertEvent

if TYPE_CHECKING:
    from editwar_api.repositories import AlertRepository
    from editwar_api.websocket import WebSocketHub

logger = logging.getLogger("editwar.api")

THROUGHPUT_WINDOW_SECONDS = 60
DISPUTED_WINDOW_SECONDS = 3600


def page_url(server_url: str, title: str) -> str:
    return f"{server_url}/wiki/{title.replace(' ', '_')}"


class StatsService:
    """Counts edits and reverts and keeps the "most disputed articles" ranking."""

    def __init__(
        self,
        alerts: AlertRepository | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._alerts = alerts  # used only to count the open alerts
        self._clock = clock
        self._edit_times: deque[float] = deque()
        self._reverts: deque[tuple[float, str, str, str]] = deque()  # time, wiki, title, url
        self.total_edits = 0
        self.total_reverts = 0
        self.started_at = datetime.now(UTC)

    def _drop_old(self, now: float) -> None:
        """Forget the events that are outside their windows."""
        while self._edit_times and self._edit_times[0] <= now - THROUGHPUT_WINDOW_SECONDS:
            self._edit_times.popleft()
        while self._reverts and self._reverts[0][0] <= now - DISPUTED_WINDOW_SECONDS:
            self._reverts.popleft()

    def record_edit(self, event: EditEvent) -> None:
        now = self._clock()
        self._edit_times.append(now)
        self.total_edits += 1
        self._drop_old(now)

    def record_revert(self, event: RevertEvent) -> None:
        now = self._clock()
        self._reverts.append((now, event.wiki, event.title, event.server_url))
        self.total_reverts += 1
        self._drop_old(now)

    def throughput(self) -> float:
        """Average edits per second in the last 60 seconds."""
        self._drop_old(self._clock())
        return len(self._edit_times) / THROUGHPUT_WINDOW_SECONDS

    def top_disputed(self, n: int = 10) -> list[dict[str, Any]]:
        """Articles with the most reverts in the last hour."""
        self._drop_old(self._clock())
        counts = Counter((wiki, title) for _, wiki, title, _ in self._reverts)
        urls = {(wiki, title): url for _, wiki, title, url in self._reverts}
        return [
            {
                "wiki": wiki,
                "title": title,
                "reverts": reverts,
                "page_url": page_url(urls[(wiki, title)], title),
            }
            for (wiki, title), reverts in counts.most_common(n)
        ]

    async def snapshot(self) -> dict[str, Any]:
        """All the metrics in the shape of GET /api/stats.

        open_alerts comes from the database, the other values from memory.
        """
        open_alerts = await self._alerts.count_open() if self._alerts else 0
        return {
            "edits_per_second": round(self.throughput(), 2),
            "total_edits": self.total_edits,
            "total_reverts": self.total_reverts,
            "open_alerts": open_alerts,
            "top_disputed": self.top_disputed(10),
            "started_at": self.started_at.isoformat(),
        }

    async def run(self, hub: WebSocketHub, interval_seconds: float) -> None:
        """Send a "stats" message to the dashboards every interval_seconds."""
        while True:
            await asyncio.sleep(interval_seconds)
            if hub.connection_count() == 0:
                continue
            try:
                await hub.broadcast({"type": "stats", "data": await self.snapshot()})
            except Exception:  # for example the database is down; try again next time
                logger.exception("could not send stats")
