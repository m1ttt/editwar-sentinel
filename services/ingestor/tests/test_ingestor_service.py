"""IngestorService: counters, error isolation and stop."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from editwar_domain import EditEvent
from editwar_ingestor.filters import EventFilter
from editwar_ingestor.normalizer import EventNormalizer
from editwar_ingestor.publisher import InMemoryPublisher
from editwar_ingestor.service import IngestorService
from editwar_ingestor.sources import EventSource

FIXTURE = Path(__file__).parent / "fixtures" / "recentchange-sample.jsonl"


def load_sample() -> list[dict[str, Any]]:
    with FIXTURE.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ListSource(EventSource):
    """Yield a fixed list of raw events, then end."""

    def __init__(self, raws: list[Any]) -> None:
        self.raws = raws
        self.connected = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        for raw in self.raws:
            yield raw

    async def close(self) -> None:
        self.closed = True


class BlockedSource(ListSource):
    """Yield the given events, then wait forever for the next one."""

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        for raw in self.raws:
            yield raw
        await asyncio.Event().wait()
        yield {}  # never reached


class FailingPublisher(InMemoryPublisher):
    """Raise for the edits of one article."""

    def __init__(self, bad_title: str) -> None:
        super().__init__()
        self.bad_title = bad_title

    async def publish(self, event: EditEvent) -> None:
        if event.title == self.bad_title:
            raise RuntimeError("broker rejected the event")
        await super().publish(event)


class ExplodingNormalizer(EventNormalizer):
    def parse(self, raw: Any) -> EditEvent | None:
        if raw.get("explode"):
            raise ValueError("boom")
        return super().parse(raw)


def make_service(source: EventSource, publisher: InMemoryPublisher) -> IngestorService:
    return IngestorService(source, EventNormalizer(), EventFilter(wikis=[]), publisher)


async def test_counts_real_events() -> None:
    raws = load_sample()
    source = ListSource(raws)
    publisher = InMemoryPublisher()
    service = make_service(source, publisher)
    await service.run()

    expected = [raw for raw in raws if raw["type"] in ("edit", "new") and raw["namespace"] == 0]
    stats = service.stats()
    assert stats["received"] == len(raws)
    assert stats["published"] == len(expected) == len(publisher.events)
    assert stats["filtered"] == len(raws) - len(expected)
    assert stats["errors"] == 0
    assert stats["last_event_id"] == expected[-1]["meta"]["id"]
    assert source.connected and source.closed
    assert publisher.flushes == 1


async def test_publish_error_is_counted_and_loop_continues() -> None:
    raws = [raw for raw in load_sample() if raw["type"] == "edit" and raw["namespace"] == 0][:5]
    publisher = FailingPublisher(bad_title=raws[1]["title"])
    service = make_service(ListSource(raws), publisher)
    await service.run()
    bad = sum(1 for raw in raws if raw["title"] == raws[1]["title"])
    assert service.errors == bad
    assert service.published == len(raws) - bad
    assert service.received == service.published + service.filtered + service.errors


async def test_normalizer_error_is_counted() -> None:
    raws: list[Any] = [{"explode": True}, *load_sample()[:3]]
    service = IngestorService(
        ListSource(raws), ExplodingNormalizer(), EventFilter(wikis=[]), InMemoryPublisher()
    )
    await service.run()
    assert service.errors == 1
    assert service.received == 4


async def test_garbage_events_are_filtered_not_errors() -> None:
    service = make_service(ListSource([{}, {"meta": None}, {"type": "edit"}]), InMemoryPublisher())
    await service.run()
    assert service.filtered == 3
    assert service.errors == 0


async def test_stop_ends_a_blocked_source() -> None:
    raws = [raw for raw in load_sample() if raw["type"] == "edit" and raw["namespace"] == 0][:2]
    source = BlockedSource(raws)
    publisher = InMemoryPublisher()
    service = make_service(source, publisher)
    task = asyncio.create_task(service.run())
    for _ in range(100):
        if service.received == 2:
            break
        await asyncio.sleep(0)
    service.stop()
    await asyncio.wait_for(task, timeout=1)
    assert service.published == 2
    assert publisher.flushes == 1
    assert source.closed


async def test_stop_before_run_does_nothing() -> None:
    source = BlockedSource([])
    service = make_service(source, InMemoryPublisher())
    service.stop()
    await asyncio.wait_for(service.run(), timeout=1)
    assert service.received == 0
    assert source.closed


async def test_external_cancel_is_not_swallowed() -> None:
    source = BlockedSource([])
    publisher = InMemoryPublisher()
    task = asyncio.create_task(make_service(source, publisher).run())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert publisher.flushes == 1
    assert source.closed


async def test_stats_keys() -> None:
    stats = make_service(ListSource([]), InMemoryPublisher()).stats()
    assert set(stats) == {
        "received",
        "published",
        "filtered",
        "errors",
        "last_event_id",
        "started_at",
    }
    assert stats["last_event_id"] is None
