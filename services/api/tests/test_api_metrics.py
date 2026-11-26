"""ApiMetrics: what each instrument records, and when."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest
from api_fakes import FakeMessage, make_alert
from fastapi.testclient import TestClient
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider

from editwar_api.app import create_app
from editwar_api.config import Settings
from editwar_api.consumers import AlertConsumer
from editwar_api.diffs import DiffError, DiffService
from editwar_api.metrics import ApiMetrics
from editwar_api.repositories import AlertRepository
from editwar_api.websocket import WebSocketHub
from editwar_domain import TOPIC_ALERTS

CLIENTS = "editwar.api.websocket_clients"
ALERTS = "editwar.api.alerts_stored"
DIFFS = "editwar.api.diff_requests"

SERVER = "https://en.wikipedia.org"
COMPARE = {"compare": {"body": "<tr></tr>", "fromuser": "A", "touser": "B"}}

MetricPoints = Callable[[str], list[Any]]  # the metric_points fixture of conftest.py


def values(points: list[Any]) -> dict[tuple[tuple[str, Any], ...], float]:
    """Point value by its sorted attributes."""
    return {tuple(sorted(point.attributes.items())): point.value for point in points}


def wikipedia(request: httpx.Request) -> httpx.Response:
    """Fake action=compare: revision 404 is unknown, revision 503 fails."""
    torev = request.url.params["torev"]
    if torev == "404":
        return httpx.Response(200, json={"error": {"code": "nosuchrevid"}})
    if torev == "503":
        return httpx.Response(503)
    return httpx.Response(200, json=COMPARE)


async def test_alerts_stored_and_duplicates(
    alert_repo: AlertRepository, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    consumer = AlertConsumer(alert_repo, WebSocketHub(), ApiMetrics(meter_provider))
    alert = make_alert()
    message = FakeMessage(TOPIC_ALERTS, alert.to_json().encode())
    await consumer.handle(message)
    await consumer.handle(message)
    await consumer.handle(FakeMessage(TOPIC_ALERTS, make_alert(kind="burst").to_json().encode()))
    await consumer.handle(FakeMessage(TOPIC_ALERTS, None))  # not an alert: not counted

    assert values(metric_points(ALERTS)) == {
        (("kind", "revert_war"), ("outcome", "stored")): 1,
        (("kind", "revert_war"), ("outcome", "duplicate")): 1,
        (("kind", "burst"), ("outcome", "stored")): 1,
    }


async def test_every_diff_outcome(
    meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(wikipedia))
    diffs = DiffService(client=client, metrics=ApiMetrics(meter_provider))
    await diffs.diff(SERVER, 11, 10)  # fetched
    await diffs.diff(SERVER, 11, 10)  # cache_hit
    await diffs.diff(SERVER, 11, 10)  # cache_hit
    for args in [
        ("https://evil.example.org", 11, 10),  # bad_request: not Wikimedia
        (SERVER, 11, 0),  # bad_request: new page
        (SERVER, 404, 10),  # not_found
        (SERVER, 503, 10),  # upstream_error
    ]:
        with pytest.raises(DiffError):
            await diffs.diff(*args)
    await diffs.close()

    assert values(metric_points(DIFFS)) == {
        (("outcome", "fetched"),): 1,
        (("outcome", "cache_hit"),): 2,
        (("outcome", "bad_request"),): 2,
        (("outcome", "not_found"),): 1,
        (("outcome", "upstream_error"),): 1,
    }


def test_app_wires_the_websocket_gauge_and_the_diff_counter(
    settings: Settings, meter_provider: MeterProvider, metric_points: MetricPoints
) -> None:
    app = create_app(replace(settings, stats_interval_seconds=60), ApiMetrics(meter_provider))
    with TestClient(app) as client:
        (clients,) = metric_points(CLIENTS)
        assert clients.value == 0
        with client.websocket_connect("/ws/live") as websocket:
            websocket.receive_json()  # the first "stats" message: the client is registered
            (clients,) = metric_points(CLIENTS)
            assert clients.value == 1
        params = {"server_url": "https://evil.example.org", "rev_id": 2, "old_rev_id": 1}
        assert client.get("/api/diff", params=params).status_code == 400
    (clients,) = metric_points(CLIENTS)
    assert clients.value == 0
    assert values(metric_points(DIFFS)) == {(("outcome", "bad_request"),): 1}


async def test_metrics_are_a_noop_without_an_sdk(alert_repo: AlertRepository) -> None:
    """Without Application Insights the global provider is the API proxy: nothing fails."""
    assert not isinstance(metrics.get_meter_provider(), MeterProvider)
    for provider in (None, metrics.NoOpMeterProvider()):
        recorder = ApiMetrics(provider)
        recorder.websocket_clients = lambda: 3
        recorder.alert("burst", "stored")
        recorder.diff("cache_hit")
    consumer = AlertConsumer(alert_repo, WebSocketHub())
    assert await consumer.handle(FakeMessage(TOPIC_ALERTS, make_alert().to_json().encode()))
