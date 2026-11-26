"""The ingestion loop: source -> normalizer -> filter -> publisher."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from editwar_ingestor.filters import EventFilter
from editwar_ingestor.normalizer import EventNormalizer
from editwar_ingestor.publisher import EventPublisher
from editwar_ingestor.sources import EventSource

logger = logging.getLogger("editwar.ingestor.service")


class IngestorService:
    """Read raw events, normalize and filter them, and publish the accepted ones.

    A bad event is logged and counted, and the loop goes on. The counters
    always add up: received == published + filtered + errors.
    """

    def __init__(
        self,
        source: EventSource,
        normalizer: EventNormalizer,
        event_filter: EventFilter,
        publisher: EventPublisher,
    ) -> None:
        self.source = source
        self.normalizer = normalizer
        self.filter = event_filter
        self.publisher = publisher
        self.received = 0
        self.published = 0
        self.filtered = 0  # unusable events and events the filter rejected
        self.errors = 0  # events that raised an exception
        self.last_event_id: str | None = None  # meta.id of the last published event
        self.started_at = datetime.now(UTC)
        self._stopped = False
        self._loop_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        """Process events until the source ends or stop() is called. Flushes at the end."""
        await self.source.connect()
        try:
            if self._stopped:
                return  # stop() was called before the loop started
            # The loop runs in its own task, so stop() can cancel it even while the
            # source is waiting for the next event.
            self._loop_task = asyncio.create_task(self._consume())
            await self._loop_task
        except asyncio.CancelledError:
            if not self._stopped:
                raise  # someone else cancelled run(): let the cancellation go on
            logger.info("ingestor stopped")
        finally:
            self._loop_task = None
            await self.publisher.flush()
            await self.source.close()

    def stop(self) -> None:
        """Ask the loop to end. Safe to call from a signal handler."""
        self._stopped = True
        if self._loop_task is not None:
            self._loop_task.cancel()

    def stats(self) -> dict[str, Any]:
        """Counters for the health endpoint and the logs."""
        return {
            "received": self.received,
            "published": self.published,
            "filtered": self.filtered,
            "errors": self.errors,
            "last_event_id": self.last_event_id,
            "started_at": self.started_at.isoformat(),
        }

    async def handle(self, raw: dict[str, Any]) -> None:
        """Process one raw event and update the counters."""
        self.received += 1
        try:
            event = self.normalizer.parse(raw)
            if event is None or not self.filter.accept(event):
                self.filtered += 1
                return
            await self.publisher.publish(event)
        except Exception:
            self.errors += 1
            logger.exception("could not process event %s", _raw_id(raw))
            return
        self.published += 1
        self.last_event_id = event.event_id

    async def _consume(self) -> None:
        async for raw in self.source.events():
            await self.handle(raw)
            if self._stopped:
                break
            # Give other tasks (health server, signal handling) a turn. A fast
            # replay with no delays would otherwise never pause.
            await asyncio.sleep(0)


def _raw_id(raw: Any) -> str:
    """Best-effort id of a raw event, for log messages."""
    try:
        return str(raw["meta"]["id"])
    except (KeyError, TypeError):
        return "<unknown>"
