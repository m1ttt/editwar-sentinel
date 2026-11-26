"""IngestorMetrics: what each instrument records, and when."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from test_ingestor_replay import take, write_events
from test_ingestor_service import ExplodingNormalizer, FailingPublisher, ListSource, load_sample

from editwar_ingestor.filters import EventFilter
from editwar_ingestor.metrics import IngestorMetrics
from editwar_ingestor.normalizer import EventNormalizer
from editwar_ingestor.publisher import InMemoryPublisher
from editwar_ingestor.service import IngestorService
from editwar_ingestor.sources import ReplayFileSource, WikimediaSSESource

EVENTS = "editwar.ingestor.events"
RECONNECTS = "editwar.ingestor.stream_reconnects"
LAG = "editwar.ingestor.event_lag_seconds"

MetricPoints = Callable[[str], list[Any]]  # the metric_points fixture of conftest.py


def by_attribute(points: list[Any], key: str) -> dict[str, float]:
    return {point.attributes[key]: point.value for point in points}


class NoSleep:
    async def __call__(self, seconds: float) -> None:
        return None


async def test_every_raw_event_gets_one_outcome(
    meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    raws: list[Any] = [*load_sample(), {}, {"type": "edit", "meta": {"id": "x"}}]
    service = IngestorService(
        ListSource(raws),
        EventNormalizer(),
        EventFilter(wikis=[]),
        InMemoryPublisher(),
        IngestorMetrics(meter_provider),
    )
    await service.run()

    outcomes = by_attribute(metric_points(EVENTS), "outcome")
    assert outcomes["published"] == service.published > 0
    assert outcomes["invalid"] == 2
    assert outcomes["filtered"] == service.filtered - 2
    assert "error" not in outcomes
    assert sum(outcomes.values()) == service.received == len(raws)
    # One lag measurement per published event, with no attribute at all.
    (lag,) = metric_points(LAG)
    assert lag.count == service.published
    assert dict(lag.attributes) == {}


async def test_errors_are_counted(
    meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    raws = [raw for raw in load_sample() if raw["type"] == "edit" and raw["namespace"] == 0][:3]
    publisher = FailingPublisher(bad_title=raws[0]["title"])
    service = IngestorService(
        ListSource([{"explode": True}, *raws]),
        ExplodingNormalizer(),
        EventFilter(wikis=[]),
        publisher,
        IngestorMetrics(meter_provider),
    )
    await service.run()
    outcomes = by_attribute(metric_points(EVENTS), "outcome")
    assert outcomes["error"] == service.errors >= 2  # the normalizer and the publisher
    assert outcomes.get("published", 0) == service.published


def test_lag_is_now_minus_event_time(
    meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    recorder = IngestorMetrics(meter_provider)
    now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
    recorder.published(now - timedelta(seconds=4), now)
    recorder.published(now + timedelta(seconds=2), now)  # clock skew counts as 0
    (lag,) = metric_points(LAG)
    assert lag.count == 2
    assert lag.sum == 4.0
    assert lag.min == 0.0
    assert by_attribute(metric_points(EVENTS), "outcome") == {"published": 2}


async def test_sse_reconnect_is_counted(
    meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    source = WikimediaSSESource(sleep=NoSleep(), metrics=IngestorMetrics(meter_provider))
    await source.reconnect()
    await source.reconnect()
    assert by_attribute(metric_points(RECONNECTS), "source") == {"sse": 2}


async def test_replay_new_pass_is_counted(
    tmp_path: Path, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    path = write_events(tmp_path / "r.jsonl", [1, 2])
    source = ReplayFileSource(path, 0, loop=True, metrics=IngestorMetrics(meter_provider))
    await take(source, 5)  # pass 1, pass 2, then one event of pass 3
    assert by_attribute(metric_points(RECONNECTS), "source") == {"replay": 2}


async def test_replay_without_loop_counts_nothing(
    tmp_path: Path, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    path = write_events(tmp_path / "r.jsonl", [1, 2])
    source = ReplayFileSource(path, 0, loop=False, metrics=IngestorMetrics(meter_provider))
    await take(source, 5)
    assert metric_points(RECONNECTS) == []


async def test_metrics_are_a_noop_without_an_sdk() -> None:
    """Without Application Insights the global provider is the API proxy: nothing fails."""
    assert not isinstance(metrics.get_meter_provider(), MeterProvider)
    for provider in (None, metrics.NoOpMeterProvider()):
        recorder = IngestorMetrics(provider)
        recorder.event("filtered")
        recorder.reconnect("sse")
        recorder.published(datetime.now(UTC))
    service = IngestorService(
        ListSource(load_sample()[:5]), EventNormalizer(), EventFilter(wikis=[]), InMemoryPublisher()
    )
    await service.run()
    assert service.received == 5
