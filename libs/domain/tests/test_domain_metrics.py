"""editwar_domain.metrics: the meter helper and the lag helper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from editwar_domain.metrics import get_meter, seconds_since


def test_get_meter_uses_the_given_provider() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    get_meter("editwar.test", provider).create_counter("editwar.test.things").add(2, {"a": "b"})
    data = reader.get_metrics_data()
    assert data is not None
    (scope,) = data.resource_metrics[0].scope_metrics
    assert scope.scope.name == "editwar.test"
    (metric,) = scope.metrics
    (point,) = metric.data.data_points
    assert (metric.name, point.value, dict(point.attributes)) == (
        "editwar.test.things",
        2,
        {"a": "b"},
    )
    provider.shutdown()


def test_get_meter_without_sdk_is_a_noop() -> None:
    """No provider installed (no Application Insights): every call does nothing, quietly."""
    assert not isinstance(metrics.get_meter_provider(), MeterProvider)
    meter = get_meter("editwar.test")
    meter.create_counter("editwar.test.count").add(1)
    meter.create_histogram("editwar.test.seconds", unit="s").record(0.5)
    meter.create_observable_gauge("editwar.test.gauge", callbacks=[lambda options: []])


def test_seconds_since() -> None:
    now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
    assert seconds_since(now - timedelta(seconds=3.5), now) == 3.5
    assert seconds_since(now + timedelta(seconds=10), now) == 0.0
    assert 0.0 <= seconds_since(datetime.now(UTC)) < 5
