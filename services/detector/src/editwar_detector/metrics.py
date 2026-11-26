"""Business metrics of the detector (meter "editwar.detector").

- editwar.detector.edits_processed (counter): edits run through the engine.
- editwar.detector.reverts (counter): reverts sent to wiki.reverts, with
  `reason` = comment or size_restore.
- editwar.detector.alerts (counter): alerts sent, with `kind` (the RuleKind)
  and `severity` (low, medium, high).
- editwar.detector.processing_seconds (histogram, s): time to process one
  edit, including the send of its revert and alerts.
- editwar.detector.consumer_lag (observable gauge, {message}): messages of
  wiki.edits that this pod still has to read, summed over its partitions
  (high-water mark minus position). After a batch is committed the position is
  the committed offset, so the sum over all pods is the lag of the group
  "detector" that the KEDA ScaledObject scales on.
- editwar.detector.open_windows (observable gauge, {window}): sliding windows
  in memory (articles and wikis).

The gauges are read by the exporter thread every export interval. Their
callbacks only return values that the service already keeps: the lag is
computed in the consume loop after each batch and cached here, and the window
count is a len() of two dicts.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, MeterProvider, Observation

from editwar_domain.metrics import LATENCY_BUCKETS_SECONDS, get_meter

METER_NAME = "editwar.detector"


class DetectorMetrics:
    """The instruments of the detector. Create one per process and share it."""

    def __init__(self, meter_provider: MeterProvider | None = None) -> None:
        meter = get_meter(METER_NAME, meter_provider)
        self.consumer_lag: int | None = None  # None until the first batch: nothing to report
        self.window_count: Callable[[], int] | None = None  # set by the service
        self._edits = meter.create_counter(
            "editwar.detector.edits_processed",
            unit="{edit}",
            description="Edits processed by the detection engine.",
        )
        self._reverts = meter.create_counter(
            "editwar.detector.reverts",
            unit="{revert}",
            description="Reverts detected and published, by reason.",
        )
        self._alerts = meter.create_counter(
            "editwar.detector.alerts",
            unit="{alert}",
            description="Alerts published, by rule kind and severity.",
        )
        self._processing = meter.create_histogram(
            "editwar.detector.processing_seconds",
            unit="s",
            description="Time to process one edit and send its outputs.",
            explicit_bucket_boundaries_advisory=LATENCY_BUCKETS_SECONDS,
        )
        meter.create_observable_gauge(
            "editwar.detector.consumer_lag",
            callbacks=[self._observe_lag],
            unit="{message}",
            description="Messages of wiki.edits behind the high-water mark on this pod.",
        )
        meter.create_observable_gauge(
            "editwar.detector.open_windows",
            callbacks=[self._observe_windows],
            unit="{window}",
            description="Sliding windows kept in memory.",
        )

    def edit_processed(self) -> None:
        self._edits.add(1)

    def processing_time(self, seconds: float) -> None:
        """Record how long one edit took, once its revert and alerts were sent."""
        self._processing.record(seconds)

    def revert(self, reason: str) -> None:
        self._reverts.add(1, {"reason": reason})

    def alert(self, kind: str, severity: str) -> None:
        self._alerts.add(1, {"kind": kind, "severity": severity})

    def _observe_lag(self, options: CallbackOptions) -> Iterable[Observation]:
        if self.consumer_lag is None:
            return []
        return [Observation(self.consumer_lag)]

    def _observe_windows(self, options: CallbackOptions) -> Iterable[Observation]:
        if self.window_count is None:
            return []
        return [Observation(self.window_count())]
