"""Shared fixtures: a fake clock, a factory for edit events and an in-memory meter provider."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

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


@pytest.fixture
def metric_reader() -> InMemoryMetricReader:
    """Collects the metrics in memory, instead of exporting them."""
    return InMemoryMetricReader()


@pytest.fixture
def meter_provider(metric_reader: InMemoryMetricReader) -> Iterator[MeterProvider]:
    """An SDK provider for one test. The global provider is never changed."""
    provider = MeterProvider(metric_readers=[metric_reader])
    yield provider
    provider.shutdown()


@pytest.fixture
def metric_points(metric_reader: InMemoryMetricReader) -> Callable[[str], list[Any]]:
    """Return points(name): the data points of metric `name` at this moment."""

    def points(name: str) -> list[Any]:
        data = metric_reader.get_metrics_data()
        if data is None:
            return []
        return [
            point
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]

    return points
