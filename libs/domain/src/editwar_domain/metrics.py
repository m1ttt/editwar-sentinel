"""Business metrics shared by all services (OpenTelemetry metrics API).

Each service keeps its instruments in one small class (IngestorMetrics,
DetectorMetrics, ApiMetrics) that gets its Meter from get_meter(). The class
receives an optional MeterProvider:

- In production it is None, so the global provider is used.
  configure_telemetry() lets the Azure Monitor distro install an SDK provider
  that exports every 60 s (OTEL_METRIC_EXPORT_INTERVAL) to the customMetrics
  table of Application Insights.
- Without APPLICATIONINSIGHTS_CONNECTION_STRING no SDK provider is installed.
  The global provider of the API is then a proxy that does nothing, so the
  instruments cost almost nothing and never fail (docker compose, tests).
  Instruments created before configure_telemetry() still work: the proxy
  forwards them to the real provider once it is installed.
- Tests pass their own MeterProvider with an InMemoryMetricReader, so no test
  changes the global provider.

Attributes must have few values (an outcome, a reason, a rule kind). Article
titles, user names, wikis and ids would create one time series per value and
make Application Insights slow and expensive, so they never become attributes.

One instance per process: an SDK meter keeps the callbacks of the first
observable gauge with a given name and ignores the ones of later instances.
"""

from __future__ import annotations

from datetime import UTC, datetime

from opentelemetry import metrics
from opentelemetry.metrics import Meter, MeterProvider

# Histogram buckets in seconds. Azure Monitor only keeps count, sum, min and
# max, but an OTLP or Prometheus exporter would use these boundaries.
LATENCY_BUCKETS_SECONDS = (
    0.0005,
    0.001,
    0.0025,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
)
LAG_BUCKETS_SECONDS = (0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)


def get_meter(name: str, meter_provider: MeterProvider | None = None) -> Meter:
    """The Meter `name` of `meter_provider`, or of the global provider when it is None."""
    return metrics.get_meter(name, meter_provider=meter_provider)


def seconds_since(timestamp: datetime, now: datetime | None = None) -> float:
    """Seconds from `timestamp` to `now` (default: the current UTC time). Never negative.

    A clock that runs a little ahead on the producer side would give a negative
    lag; it counts as 0 so the histogram stays meaningful.
    """
    current = now if now is not None else datetime.now(UTC)
    return max(0.0, (current - timestamp).total_seconds())
