"""Business metrics of the api (meter "editwar.api").

- editwar.api.websocket_clients (observable gauge, {client}): dashboards
  connected to /ws/live on this replica.
- editwar.api.alerts_stored (counter): alerts read from wiki.alerts, with
  `kind` (the RuleKind) and `outcome` = stored or duplicate (the alert id was
  already in the database, for example after a detector retry).
- editwar.api.diff_requests (counter): calls to DiffService.diff (GET
  /api/diff), with `outcome` = cache_hit, fetched, bad_request (not a
  Wikimedia host, bad revision ids or a new page without a previous revision),
  not_found (MediaWiki does not know the revision) or upstream_error (the
  Wikipedia API failed or answered something unexpected).

HTTP request counts and durations come from the FastAPI instrumentation of the
Azure Monitor distro, so they are not repeated here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

from opentelemetry.metrics import CallbackOptions, MeterProvider, Observation

from editwar_domain.metrics import get_meter

METER_NAME = "editwar.api"

AlertOutcome = Literal["stored", "duplicate"]
DiffOutcome = Literal["cache_hit", "fetched", "bad_request", "not_found", "upstream_error"]


class ApiMetrics:
    """The instruments of the api. create_app() makes one and shares it."""

    def __init__(self, meter_provider: MeterProvider | None = None) -> None:
        meter = get_meter(METER_NAME, meter_provider)
        self.websocket_clients: Callable[[], int] | None = None  # set by create_app()
        meter.create_observable_gauge(
            "editwar.api.websocket_clients",
            callbacks=[self._observe_clients],
            unit="{client}",
            description="Dashboards connected to /ws/live on this replica.",
        )
        self._alerts = meter.create_counter(
            "editwar.api.alerts_stored",
            unit="{alert}",
            description="Alerts read from Kafka, stored or ignored as duplicates.",
        )
        self._diffs = meter.create_counter(
            "editwar.api.diff_requests",
            unit="{request}",
            description="Diff requests, by outcome.",
        )

    def alert(self, kind: str, outcome: AlertOutcome) -> None:
        self._alerts.add(1, {"kind": kind, "outcome": outcome})

    def diff(self, outcome: DiffOutcome) -> None:
        self._diffs.add(1, {"outcome": outcome})

    def _observe_clients(self, options: CallbackOptions) -> Iterable[Observation]:
        if self.websocket_clients is None:
            return []
        return [Observation(self.websocket_clients())]
