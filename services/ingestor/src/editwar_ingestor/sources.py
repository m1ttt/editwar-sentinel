"""Event sources: the live Wikimedia stream and a recorded replay file.

Both classes follow the EventSource interface (Adapter pattern), so the
service does not know where its events come from.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from httpx_sse import SSEError, aconnect_sse

from editwar_domain.settings import DEFAULT_STREAM_URL

logger = logging.getLogger("editwar.ingestor.sources")

# Wikimedia asks every client to send a descriptive User-Agent.
USER_AGENT = "EditWarSentinel/0.1 (student project; https://github.com/m1ttt/editwar-sentinel)"

SleepFunction = Callable[[float], Awaitable[None]]


class EventSource(ABC):
    """A source of raw recentchange events (plain dicts)."""

    @abstractmethod
    async def connect(self) -> None:
        """Prepare the source. Call it once before events()."""

    @abstractmethod
    def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield raw events, one dict per event."""

    @abstractmethod
    async def close(self) -> None:
        """Release network connections or files."""


class WikimediaSSESource(EventSource):
    """Read the live recentchange stream over Server-Sent Events.

    When the connection fails or ends, the source waits with exponential
    backoff and connects again. It sends the Last-Event-ID header so the
    stream continues from the last event it received.
    """

    def __init__(
        self,
        url: str = DEFAULT_STREAM_URL,
        last_event_id: str | None = None,
        *,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFunction = asyncio.sleep,
    ) -> None:
        self.url = url
        self.last_event_id = last_event_id  # the SSE "id" field, sent back on reconnect
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff = initial_backoff
        self.reconnects = 0
        self._transport = transport  # tests inject httpx.MockTransport here
        self._sleep = sleep  # tests inject a fake sleep here
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Create the HTTP client. The stream itself opens in events()."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                # The stream is long-lived. Reconnect if no data arrives for 60 seconds.
                timeout=httpx.Timeout(10.0, read=60.0),
                transport=self._transport,
            )

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield events forever, reconnecting after every failure or end of stream."""
        await self.connect()
        while True:
            try:
                async for event in self._read_stream():
                    yield event
                logger.warning("stream ended, reconnecting")
            except (httpx.HTTPError, SSEError) as exc:
                logger.warning("stream failed: %r", exc)
            await self.reconnect()

    async def reconnect(self) -> None:
        """Wait for the current backoff before the next attempt, then double it (with a cap)."""
        self.reconnects += 1
        logger.info("reconnecting in %.1f s (Last-Event-ID=%s)", self.backoff, self.last_event_id)
        await self._sleep(self.backoff)
        self.backoff = min(self.backoff * 2, self.max_backoff)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _read_stream(self) -> AsyncIterator[dict[str, Any]]:
        """Open one SSE connection and yield its events until it ends."""
        assert self._client is not None, "connect() was not called"
        headers = {"Accept": "text/event-stream"}
        if self.last_event_id:
            headers["Last-Event-ID"] = self.last_event_id
        async with aconnect_sse(self._client, "GET", self.url, headers=headers) as source:
            source.response.raise_for_status()
            logger.info("connected to %s", self.url)
            async for sse in source.aiter_sse():
                if sse.id:
                    self.last_event_id = sse.id
                if sse.event != "message" or not sse.data:
                    continue
                try:
                    event = json.loads(sse.data)
                except json.JSONDecodeError:
                    logger.warning("skipping SSE message that is not JSON")
                    continue
                # The connection works again, so the next failure starts with a short wait.
                self.backoff = self.initial_backoff
                yield event


class ReplayFileSource(EventSource):
    """Replay raw events from a JSONL file, one event per line.

    The delay between two events is the original delay divided by `speed`.
    A speed of 0 or less means no delay. With loop=True the file starts again
    at the end, so a demo never runs out of events.
    """

    def __init__(
        self,
        path: str | Path,
        speed: float = 1.0,
        *,
        loop: bool = True,
        sleep: SleepFunction = asyncio.sleep,
    ) -> None:
        self.path = Path(path)
        self.speed = speed
        self.loop = loop
        self.passes = 0  # how many times the whole file was replayed
        self._sleep = sleep

    async def connect(self) -> None:
        """Check that the file exists."""
        if not self.path.is_file():
            raise FileNotFoundError(f"replay file not found: {self.path}")

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield the events of the file, once or forever."""
        while True:
            count = 0
            previous_time: float | None = None  # reset on every pass: no delay at the wrap
            for event in self._read_file():
                current_time = _event_time(event)
                delay = self._delay(previous_time, current_time)
                if delay > 0:
                    await self._sleep(delay)
                # The stream is not strictly ordered. Keep the latest time seen, so an
                # older event does not make the next one wait again.
                if current_time is not None:
                    previous_time = max(previous_time or current_time, current_time)
                count += 1
                yield self._as_live(event)
            self.passes += 1
            if count == 0:
                logger.warning("replay file %s has no events", self.path)
                return
            if not self.loop:
                return
            logger.info("replay file finished pass %d, starting again", self.passes)

    async def close(self) -> None:
        """Nothing to close: the file is opened and closed on each pass."""

    def _as_live(self, event: dict[str, Any]) -> dict[str, Any]:
        """Make a recorded event look live.

        The detector keeps time windows, so the event gets the current time.
        After the first pass the id gets a suffix, so a looped event is not a duplicate.
        """
        meta = dict(event.get("meta") or {})
        meta["dt"] = datetime.now(UTC).isoformat()
        if self.passes > 0 and "id" in meta:
            meta["id"] = f"{meta['id']}-r{self.passes}"
        return {**event, "meta": meta}

    def _read_file(self) -> list[dict[str, Any]]:
        """Read every valid JSON line of the file."""
        events = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("skipping a line of %s that is not JSON", self.path)
        return events

    def _delay(self, previous_time: float | None, current_time: float | None) -> float:
        """Seconds to wait before the current event. Never negative."""
        if self.speed <= 0 or previous_time is None or current_time is None:
            return 0.0
        return max(0.0, (current_time - previous_time) / self.speed)


def _event_time(event: dict[str, Any]) -> float | None:
    """The Unix time of a raw event (the recentchange "timestamp" field), if present."""
    value = event.get("timestamp")
    if isinstance(value, int | float):
        return float(value)
    return None
