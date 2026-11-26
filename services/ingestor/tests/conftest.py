"""Shared fixtures: an OpenTelemetry SDK provider that keeps the metrics in memory."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


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
    """Return points(name): the data points of metric `name` collected so far."""

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
