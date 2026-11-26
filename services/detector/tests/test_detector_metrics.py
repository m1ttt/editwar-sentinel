"""DetectorMetrics: what each instrument records, and when."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

from aiokafka.errors import IllegalStateError
from aiokafka.structs import TopicPartition
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from test_detector_service import TP, make_service, record, rules

from editwar_detector.metrics import DetectorMetrics
from editwar_domain import TOPIC_EDITS

PROCESSED = "editwar.detector.edits_processed"
REVERTS = "editwar.detector.reverts"
ALERTS = "editwar.detector.alerts"
PROCESSING = "editwar.detector.processing_seconds"
LAG = "editwar.detector.consumer_lag"
WINDOWS = "editwar.detector.open_windows"

MetricPoints = Callable[[str], list[Any]]  # the metric_points fixture of conftest.py


def values(points: list[Any]) -> dict[tuple[tuple[str, Any], ...], float]:
    """Point value by its sorted attributes."""
    return {tuple(sorted(point.attributes.items())): point.value for point in points}


def ticking_clock(step: float) -> Callable[[], float]:
    """perf_counter stand-in that advances `step` seconds on every call."""
    ticks = itertools.count()
    return lambda: next(ticks) * step


async def test_edits_reverts_alerts_and_time(
    make_event, clock, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    service, producer, _ = make_service(
        [], metrics=DetectorMetrics(meter_provider), clock=ticking_clock(0.25)
    )
    service.engine.reload_rules(rules())
    service.producer = producer

    await service.handle(make_event(user="A", comment="rv"))
    clock.advance(1)
    await service.handle(make_event(user="B", comment="Reverted edits by A"))
    clock.advance(1)
    await service.handle(make_event(user="C", title="Other", old_len=100, new_len=600))
    clock.advance(1)
    await service.handle(make_event(user="D", title="Other", old_len=600, new_len=100, comment=""))

    (processed,) = metric_points(PROCESSED)
    assert processed.value == 4 == service.stats()["processed"]
    assert values(metric_points(REVERTS)) == {
        (("reason", "comment"),): 2,
        (("reason", "size_restore"),): 1,
    }
    assert values(metric_points(ALERTS)) == {
        (("kind", "revert_war"), ("severity", "medium")): 1,
    }
    (processing,) = metric_points(PROCESSING)
    assert processing.count == 4
    assert processing.sum == 4 * 0.25
    assert dict(processing.attributes) == {}


async def test_open_windows_gauge_reads_the_engine(
    make_event, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    service, producer, _ = make_service([], metrics=DetectorMetrics(meter_provider))
    service.producer = producer
    await service.handle(make_event(title="One"))
    await service.handle(make_event(title="Two"))
    (windows,) = metric_points(WINDOWS)
    assert windows.value == 2 == service.engine.window_count()


async def test_consumer_lag_after_each_batch(
    make_event, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    tp1 = TopicPartition(TOPIC_EDITS, 1)
    tp2 = TopicPartition(TOPIC_EDITS, 2)
    detector_metrics = DetectorMetrics(meter_provider)
    service, _, consumer = make_service(
        [], batches=[{TP: [record(9, make_event())]}], metrics=detector_metrics
    )
    # Partition 2 was not fetched yet: no high-water mark, so it does not count.
    consumer.highwaters = {TP: 100, tp1: 50, tp2: None}
    consumer.positions = {TP: 10, tp1: 50}
    exported: list[list[int]] = []
    process_batch = service.process_batch

    async def spy(batch: Any) -> None:
        # What an export would send right now, before this batch is processed.
        exported.append([point.value for point in metric_points(LAG)])
        await process_batch(batch)

    service.process_batch = spy  # type: ignore[method-assign]
    await service.run()

    # Batch 1 (one record), then batch 2 (empty, stops the service). Nothing is
    # reported before the first batch; after it the lag is (100-10) + (50-50).
    assert exported == [[], [90]]
    assert detector_metrics.consumer_lag is None  # reset when the service stops
    assert metric_points(LAG) == []


async def test_consumer_lag_keeps_the_last_value_during_a_rebalance() -> None:
    service, _, consumer = make_service([])
    service.metrics.consumer_lag = 7
    consumer.highwaters = {TP: 100}
    consumer.positions = {TP: IllegalStateError("partition not assigned")}
    await service._update_lag(consumer)
    assert service.metrics.consumer_lag == 7

    consumer.positions = {TP: 100}
    await service._update_lag(consumer)
    assert service.metrics.consumer_lag == 0


def test_gauges_report_nothing_before_the_service_sets_them(
    meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    DetectorMetrics(meter_provider)
    assert metric_points(LAG) == []
    assert metric_points(WINDOWS) == []


async def test_metrics_are_a_noop_without_an_sdk(make_event) -> None:
    """Without Application Insights the global provider is the API proxy: nothing fails."""
    assert not isinstance(metrics.get_meter_provider(), MeterProvider)
    for provider in (None, metrics.NoOpMeterProvider()):
        recorder = DetectorMetrics(provider)
        recorder.edit_processed()
        recorder.processing_time(0.1)
        recorder.revert("comment")
        recorder.alert("burst", "low")
    service, producer, _ = make_service([])
    service.producer = producer
    await service.handle(make_event(comment="rv"))
    assert service.stats()["reverts"] == 1
