"""Shared fixtures: a fake clock and a factory for edit events."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from editwar_domain import EditEvent

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class FakeClock:
    """Event time under test control."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def advance(self, seconds: float) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_event(clock: FakeClock) -> Callable[..., EditEvent]:
    """Return a factory: make_event(user="Bob", comment="rv") -> EditEvent at clock.now."""
    ids = itertools.count(1)

    def factory(**overrides: Any) -> EditEvent:
        number = next(ids)
        values: dict[str, Any] = {
            "event_id": f"e{number}",
            "wiki": "enwiki",
            "title": "Python (programming language)",
            "user": "Alice",
            "is_bot": False,
            "timestamp": clock.now,
            "comment": "fix typo",
            "old_len": 1000,
            "new_len": 1010,
            "rev_id": 100 + number,
            "old_rev_id": 99 + number,
            "server_url": "https://en.wikipedia.org",
        }
        values.update(overrides)
        return EditEvent(**values)

    return factory
