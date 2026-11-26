"""Wiring in main.py: settings, builders, Kafka retry and the serve loop."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from editwar_domain.settings import DEFAULT_STREAM_URL
from editwar_ingestor import main as main_module
from editwar_ingestor.main import (
    IngestorSettings,
    build_filter,
    build_source,
    connect_publisher,
    load_settings,
    serve,
)
from editwar_ingestor.publisher import InMemoryPublisher
from editwar_ingestor.sources import ReplayFileSource, WikimediaSSESource

FIXTURE = Path(__file__).parent / "fixtures" / "recentchange-sample.jsonl"

ENV_NAMES = [
    "EVENT_SOURCE",
    "WIKIMEDIA_STREAM_URL",
    "REPLAY_PATH",
    "REPLAY_SPEED",
    "WIKIS",
    "KAFKA_BOOTSTRAP_SERVERS",
    "HEALTH_PORT",
]


class FlakyPublisher(InMemoryPublisher):
    """Fail to start a given number of times, then work."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.attempts = 0

    async def start(self) -> None:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("broker down")
        await super().start()


def test_load_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert load_settings() == IngestorSettings()


def test_load_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENT_SOURCE", "Replay")
    monkeypatch.setenv("WIKIMEDIA_STREAM_URL", "https://example.org/stream")
    monkeypatch.setenv("REPLAY_PATH", "/tmp/r.jsonl")
    monkeypatch.setenv("REPLAY_SPEED", "5")
    monkeypatch.setenv("WIKIS", "enwiki,eswiki")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    monkeypatch.setenv("HEALTH_PORT", "9000")
    assert load_settings() == IngestorSettings(
        event_source="replay",
        stream_url="https://example.org/stream",
        replay_path="/tmp/r.jsonl",
        replay_speed=5.0,
        wikis=("enwiki", "eswiki"),
        kafka_bootstrap="kafka:9092",
        health_port=9000,
    )


def test_build_source() -> None:
    sse = build_source(IngestorSettings(event_source="sse"))
    assert isinstance(sse, WikimediaSSESource)
    assert sse.url == DEFAULT_STREAM_URL
    replay = build_source(IngestorSettings(event_source="replay", replay_speed=3.0))
    assert isinstance(replay, ReplayFileSource)
    assert replay.speed == 3.0
    assert replay.loop is True
    with pytest.raises(ValueError):
        build_source(IngestorSettings(event_source="kafka"))


def test_build_filter() -> None:
    event_filter = build_filter(IngestorSettings(wikis=("enwiki",)))
    assert event_filter.wikis == {"enwiki"}
    assert event_filter.namespaces == {0}
    assert event_filter.types == {"edit", "new"}


async def test_connect_publisher_retries_until_kafka_is_up() -> None:
    publisher = FlakyPublisher(failures=2)
    connected = await connect_publisher(publisher, asyncio.Event(), initial_delay=0.001)
    assert connected
    assert publisher.attempts == 3
    assert publisher.started


async def test_connect_publisher_gives_up_on_stop() -> None:
    publisher = FlakyPublisher(failures=1000)
    stop_event = asyncio.Event()
    task = asyncio.create_task(connect_publisher(publisher, stop_event, initial_delay=60))
    await asyncio.sleep(0.01)
    stop_event.set()
    assert await asyncio.wait_for(task, timeout=1) is False
    assert publisher.attempts == 1


async def wait_until(condition: Callable[[], bool]) -> None:
    """Let other tasks run until the condition is true. Fail after 2 seconds instead of hanging."""
    async with asyncio.timeout(2):
        while not condition():
            await asyncio.sleep(0)


def replay_settings() -> IngestorSettings:
    return IngestorSettings(event_source="replay", replay_path=str(FIXTURE), health_port=0)


async def test_serve_runs_until_the_source_ends() -> None:
    source = ReplayFileSource(FIXTURE, speed=0, loop=False)
    publisher = InMemoryPublisher()
    service = await serve(replay_settings(), source, publisher, asyncio.Event())
    with FIXTURE.open(encoding="utf-8") as handle:
        raws = [json.loads(line) for line in handle]
    assert service.received == len(raws)
    assert service.published == len(publisher.events) > 0
    assert publisher.flushes == 1
    assert publisher.closed


async def test_serve_stops_on_stop_event() -> None:
    source = ReplayFileSource(FIXTURE, speed=0, loop=True)
    publisher = InMemoryPublisher()
    stop_event = asyncio.Event()
    task = asyncio.create_task(serve(replay_settings(), source, publisher, stop_event))
    await wait_until(lambda: len(publisher.events) >= 100)
    stop_event.set()
    service = await asyncio.wait_for(task, timeout=2)
    assert source.passes >= 1
    assert service.received == service.published + service.filtered + service.errors
    assert publisher.flushes == 1
    assert publisher.closed


async def test_serve_returns_when_stopped_before_kafka_connects() -> None:
    publisher = FlakyPublisher(failures=1000)
    stop_event = asyncio.Event()
    stop_event.set()
    source = ReplayFileSource(FIXTURE, speed=0)
    service = await serve(replay_settings(), source, publisher, stop_event)
    assert service.received == 0
    assert publisher.closed


async def test_run_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real entry point with the Kafka publisher replaced by memory."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EVENT_SOURCE", "replay")
    monkeypatch.setenv("REPLAY_PATH", str(FIXTURE))
    monkeypatch.setenv("REPLAY_SPEED", "0")
    monkeypatch.setenv("HEALTH_PORT", "0")
    publishers: list[InMemoryPublisher] = []

    def fake_kafka(bootstrap: str) -> InMemoryPublisher:
        publisher = InMemoryPublisher()
        publishers.append(publisher)
        return publisher

    monkeypatch.setattr(main_module, "KafkaEventPublisher", fake_kafka)
    task = asyncio.create_task(main_module.run_from_environment())
    await wait_until(lambda: bool(publishers) and len(publishers[0].events) >= 10)
    # The signal handlers are installed before the publisher is built, so SIGTERM is safe here.
    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(task, timeout=2)
    assert publishers[0].flushes == 1
    assert publishers[0].closed


async def test_serve_flushes_when_cancelled() -> None:
    source = ReplayFileSource(FIXTURE, speed=0, loop=True)
    publisher = InMemoryPublisher()
    task = asyncio.create_task(serve(replay_settings(), source, publisher, asyncio.Event()))
    await wait_until(lambda: len(publisher.events) >= 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert publisher.flushes == 1
    assert publisher.closed


def test_main_configures_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(main_module, "configure_telemetry", lambda name: calls.append(name))

    async def fake_run() -> None:
        calls.append("run")

    monkeypatch.setattr(main_module, "run_from_environment", fake_run)
    main_module.main()
    assert calls == ["ingestor", "run"]
