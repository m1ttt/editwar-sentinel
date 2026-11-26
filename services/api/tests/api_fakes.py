"""Builders and fake objects shared by the api tests."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from editwar_api.app import create_app
from editwar_api.config import Settings
from editwar_domain import Alert, AlertStatus, EditEvent, RevertEvent, Severity

MEMORY_DB = "sqlite+aiosqlite:///:memory:"


async def start_client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Run the app startup (migrations, seeding) and yield an HTTP client for it.

    httpx.ASGITransport does not run the lifespan, so lifespan_context does it.
    raise_app_exceptions=False turns unhandled errors into 500 responses.
    """
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.app = app  # type: ignore[attr-defined]
            yield client


def make_alert(**overrides: Any) -> Alert:
    values: dict[str, Any] = {
        "rule_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "kind": "revert_war",
        "severity": Severity.HIGH,
        "wiki": "enwiki",
        "title": "Python (programming language)",
        "server_url": "https://en.wikipedia.org",
        "evidence": {"reverts": 4, "users": ["Alice", "Bob"]},
        "status": AlertStatus.OPEN,
    }
    values.update(overrides)
    return Alert(**values)


def make_edit(**overrides: Any) -> EditEvent:
    values: dict[str, Any] = {
        "event_id": "e1",
        "wiki": "enwiki",
        "title": "Python (programming language)",
        "user": "Alice",
        "is_bot": False,
        "timestamp": datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        "comment": "fix typo",
        "old_len": 100,
        "new_len": 120,
        "rev_id": 2,
        "old_rev_id": 1,
        "server_url": "https://en.wikipedia.org",
    }
    values.update(overrides)
    return EditEvent(**values)


def make_revert(**overrides: Any) -> RevertEvent:
    values: dict[str, Any] = {
        "event_id": "r1",
        "wiki": "enwiki",
        "title": "Python (programming language)",
        "user": "Bob",
        "timestamp": datetime(2026, 11, 1, 12, 1, tzinfo=UTC),
        "reason": "comment",
        "server_url": "https://en.wikipedia.org",
    }
    values.update(overrides)
    return RevertEvent(**values)


@dataclass
class FakeMessage:
    """Stands in for an aiokafka ConsumerRecord."""

    topic: str
    value: bytes | None


class FakeWebSocket:
    """Records the messages that the hub sends. fail=True simulates a dead client."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.sent.append(data)


class FakeClock:
    """A clock that the tests move by hand."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeConsumer:
    """Stands in for AIOKafkaConsumer.

    fail_start=True makes start() raise like an unreachable broker.
    block=True keeps the iteration open until the task is cancelled.
    """

    def __init__(
        self,
        messages: list[FakeMessage] | None = None,
        fail_start: bool = False,
        fail_stop: bool = False,
        block: bool = False,
    ) -> None:
        self.messages = messages or []
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.block = block
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        if self.fail_start:
            raise ConnectionError("kafka is down")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True
        if self.fail_stop:
            raise RuntimeError("stop failed")

    def __aiter__(self) -> AsyncIterator[FakeMessage]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[FakeMessage]:
        for message in self.messages:
            yield message
        if self.block:
            await asyncio.Event().wait()
