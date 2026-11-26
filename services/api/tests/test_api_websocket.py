"""WebSocketHub with fake connections, and the real /ws/live endpoint."""

from __future__ import annotations

import json
from dataclasses import replace

from api_fakes import FakeClock, FakeWebSocket
from fastapi.testclient import TestClient

from editwar_api.app import create_app
from editwar_api.config import Settings
from editwar_api.websocket import WebSocketHub


async def test_connect_accepts_and_counts() -> None:
    hub = WebSocketHub()
    client = FakeWebSocket()
    await hub.connect(client)
    assert client.accepted
    assert hub.connection_count() == 1
    hub.disconnect(client)
    hub.disconnect(client)  # a second disconnect is harmless
    assert hub.connection_count() == 0


async def test_broadcast_reaches_every_client() -> None:
    hub = WebSocketHub()
    clients = [FakeWebSocket(), FakeWebSocket()]
    for client in clients:
        await hub.connect(client)
    await hub.broadcast({"type": "alert", "data": {"title": "Café"}})
    for client in clients:
        assert json.loads(client.sent[0]) == {"type": "alert", "data": {"title": "Café"}}


async def test_broadcast_without_clients_does_nothing() -> None:
    await WebSocketHub().broadcast({"type": "stats", "data": {}})


async def test_failed_client_is_disconnected() -> None:
    hub = WebSocketHub()
    good, dead = FakeWebSocket(), FakeWebSocket(fail=True)
    await hub.connect(good)
    await hub.connect(dead)
    await hub.broadcast({"type": "revert", "data": {}})
    assert hub.connection_count() == 1
    assert len(good.sent) == 1


async def test_edits_are_sampled_per_second() -> None:
    clock = FakeClock(100.2)
    hub = WebSocketHub(edits_per_second=3, clock=clock)
    client = FakeWebSocket()
    await hub.connect(client)

    results = [await hub.broadcast_edit({"n": n}) for n in range(5)]
    assert results == [True, True, True, False, False]
    assert len(client.sent) == 3

    clock.now = 101.0  # a new second starts a new budget
    assert await hub.broadcast_edit({"n": 5}) is True
    assert json.loads(client.sent[-1]) == {"type": "edit", "data": {"n": 5}}


async def test_reverts_and_alerts_are_not_sampled() -> None:
    hub = WebSocketHub(edits_per_second=1, clock=FakeClock())
    client = FakeWebSocket()
    await hub.connect(client)
    await hub.broadcast_edit({})
    for _ in range(5):
        await hub.broadcast({"type": "revert", "data": {}})
    assert len(client.sent) == 6


async def test_edit_without_clients_is_not_counted() -> None:
    hub = WebSocketHub(edits_per_second=1, clock=FakeClock())
    assert await hub.broadcast_edit({}) is False
    client = FakeWebSocket()
    await hub.connect(client)
    assert await hub.broadcast_edit({}) is True


def test_live_endpoint_sends_stats_and_broadcasts(settings: Settings) -> None:
    app = create_app(replace(settings, stats_interval_seconds=0.05))
    with TestClient(app) as client, client.websocket_connect("/ws/live") as websocket:
        first = websocket.receive_json()
        assert first["type"] == "stats"
        assert first["data"]["total_edits"] == 0
        assert websocket.receive_json()["type"] == "stats"  # from the 2 s loop (0.05 s here)

        message = {"type": "alert", "data": {"id": "x"}}
        client.portal.call(app.state.hub.broadcast, message)  # type: ignore[union-attr]
        received = websocket.receive_json()
        while received["type"] == "stats":
            received = websocket.receive_json()
        assert received == message
    assert app.state.hub.connection_count() == 0
