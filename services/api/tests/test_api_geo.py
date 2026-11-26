"""GeoService, the "geo" messages of LiveConsumer and GET /api/geo/recent."""

from __future__ import annotations

import json
from typing import Any

import httpx
from api_fakes import FakeClock, FakeMessage, FakeWebSocket, make_alert, make_revert

from editwar_api.consumers import LiveConsumer
from editwar_api.geo import GeoPoint, GeoService, parse_coordinates
from editwar_api.stats import StatsService
from editwar_api.websocket import WebSocketHub
from editwar_domain import TOPIC_ALERTS, TOPIC_REVERTS

GUADALAJARA = {
    "query": {
        "pages": [
            {
                "title": "Guadalajara",
                "coordinates": [{"lat": 20.67, "lon": -103.35, "globe": "earth"}],
            }
        ]
    }
}
NO_COORDINATES = {"query": {"pages": [{"title": "Python"}]}}


def geo_with(answers: dict[str, Any], calls: list[httpx.Request]) -> GeoService:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        title = request.url.params["titles"]
        if title == "boom":
            return httpx.Response(503)
        return httpx.Response(200, json=answers.get(title, NO_COORDINATES))

    return GeoService(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_parse_coordinates() -> None:
    assert parse_coordinates(GUADALAJARA) == (20.67, -103.35)
    assert parse_coordinates(NO_COORDINATES) is None
    moon = {"query": {"pages": [{"coordinates": [{"lat": 1, "lon": 2, "globe": "moon"}]}]}}
    assert parse_coordinates(moon) is None
    assert parse_coordinates({}) is None


async def test_coordinates_are_cached() -> None:
    calls: list[httpx.Request] = []
    geo = geo_with({"Guadalajara": GUADALAJARA}, calls)
    server = "https://es.wikipedia.org"
    assert await geo.coordinates(server, "Guadalajara") == (20.67, -103.35)
    assert await geo.coordinates(server, "Guadalajara") == (20.67, -103.35)
    assert await geo.coordinates(server, "Python") is None
    assert await geo.coordinates(server, "Python") is None
    assert len(calls) == 2
    assert calls[0].url.path == "/w/api.php"
    assert calls[0].url.params["prop"] == "coordinates"
    await geo.close()


async def test_wiki_wide_title_and_errors() -> None:
    calls: list[httpx.Request] = []
    geo = geo_with({}, calls)
    assert await geo.coordinates("https://en.wikipedia.org", "*") is None
    assert calls == []
    assert await geo.coordinates("https://en.wikipedia.org", "boom") is None
    assert await geo.coordinates("https://en.wikipedia.org", "boom") is None
    assert len(calls) == 2  # errors are not cached
    await geo.close()


async def test_cache_size_is_limited() -> None:
    calls: list[httpx.Request] = []
    geo = geo_with({}, calls)
    geo._cache_size = 2
    for title in ["a", "b", "c"]:
        await geo.coordinates("https://en.wikipedia.org", title)
    assert len(geo._cache) == 2
    await geo.close()


def test_recent_points_newest_first() -> None:
    geo = GeoService(max_points=2)
    for n in range(3):
        geo.add(GeoPoint("revert", "enwiki", f"T{n}", 1.0, 2.0, "u", f"2026-01-0{n + 1}"))
    assert [p.title for p in geo.recent(10)] == ["T2", "T1"]
    assert [p.title for p in geo.recent(1)] == ["T2"]


async def connected_hub() -> tuple[WebSocketHub, FakeWebSocket]:
    hub = WebSocketHub(edits_per_second=100, clock=FakeClock())
    client = FakeWebSocket()
    await hub.connect(client)
    return hub, client


async def test_live_consumer_sends_geo_for_revert_and_alert() -> None:
    calls: list[httpx.Request] = []
    geo = geo_with({"Guadalajara": GUADALAJARA}, calls)
    hub, client = await connected_hub()
    consumer = LiveConsumer(StatsService(clock=FakeClock()), hub, geo)
    revert = make_revert(title="Guadalajara", server_url="https://es.wikipedia.org", wiki="eswiki")
    alert = make_alert(title="Guadalajara", server_url="https://es.wikipedia.org", wiki="eswiki")

    await consumer.handle(FakeMessage(TOPIC_REVERTS, revert.to_json().encode()))
    await consumer.handle(FakeMessage(TOPIC_ALERTS, alert.to_json().encode()))
    await consumer.drain()

    messages = [json.loads(raw) for raw in client.sent]
    geo_messages = [m["data"] for m in messages if m["type"] == "geo"]
    assert [m["kind"] for m in geo_messages] == ["revert", "alert"]
    assert geo_messages[0]["lat"] == 20.67 and geo_messages[0]["severity"] is None
    assert geo_messages[1]["severity"] == alert.severity.value
    assert geo_messages[1]["alert_kind"] == alert.kind
    assert geo_messages[1]["page_url"] == "https://es.wikipedia.org/wiki/Guadalajara"
    assert len(geo.recent(10)) == 2
    await geo.close()


async def test_live_consumer_without_coordinates_sends_no_geo() -> None:
    calls: list[httpx.Request] = []
    geo = geo_with({}, calls)
    hub, client = await connected_hub()
    consumer = LiveConsumer(StatsService(clock=FakeClock()), hub, geo)
    await consumer.handle(FakeMessage(TOPIC_REVERTS, make_revert().to_json().encode()))
    await consumer.drain()
    assert [json.loads(raw)["type"] for raw in client.sent] == ["revert"]
    await geo.close()


async def test_locate_without_geo_service_does_nothing() -> None:
    hub, client = await connected_hub()
    consumer = LiveConsumer(StatsService(clock=FakeClock()), hub)
    await consumer.locate("revert", "https://en.wikipedia.org", "enwiki", "X", "t")
    assert client.sent == []


async def test_geo_recent_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/geo/recent")
    assert response.status_code == 200
    assert response.json() == []
    assert (await client.get("/api/geo/recent?limit=0")).status_code == 422
