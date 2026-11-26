"""Business metrics of the ingestor (meter "editwar.ingestor").

- editwar.ingestor.events (counter): one per raw event read from the source,
  with `outcome` = published, filtered (the filter rejected a valid edit or the
  event is not an edit: log, categorize, canary), invalid (the event could not
  be parsed) or error (an exception, for example Kafka refused the event).
- editwar.ingestor.stream_reconnects (counter): `source` = sse (the stream
  failed or ended) or replay (the replay file starts a new pass).
- editwar.ingestor.event_lag_seconds (histogram, s): now (UTC) minus the time
  of the edit, for published events only. It shows how far behind Wikipedia
  the pipeline is.

See editwar_domain.metrics for the provider and the no-op behaviour.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from opentelemetry.metrics import MeterProvider

from editwar_domain.metrics import LAG_BUCKETS_SECONDS, get_meter, seconds_since

METER_NAME = "editwar.ingestor"

Outcome = Literal["published", "filtered", "invalid", "error"]
Source = Literal["sse", "replay"]


class IngestorMetrics:
    """The instruments of the ingestor. Create one per process and share it."""

    def __init__(self, meter_provider: MeterProvider | None = None) -> None:
        meter = get_meter(METER_NAME, meter_provider)
        self._events = meter.create_counter(
            "editwar.ingestor.events",
            unit="{event}",
            description="Raw events read from the source, by outcome.",
        )
        self._reconnects = meter.create_counter(
            "editwar.ingestor.stream_reconnects",
            unit="{reconnect}",
            description="Reconnections of the SSE stream and new passes of the replay file.",
        )
        self._lag = meter.create_histogram(
            "editwar.ingestor.event_lag_seconds",
            unit="s",
            description="Time between the edit on Wikipedia and its publication to Kafka.",
            explicit_bucket_boundaries_advisory=LAG_BUCKETS_SECONDS,
        )

    def event(self, outcome: Outcome) -> None:
        """Count one raw event."""
        self._events.add(1, {"outcome": outcome})

    def reconnect(self, source: Source) -> None:
        """Count one reconnection of `source`."""
        self._reconnects.add(1, {"source": source})

    def published(self, timestamp: datetime, now: datetime | None = None) -> None:
        """Count a published event and record its lag."""
        self.event("published")
        self._lag.record(seconds_since(timestamp, now))
