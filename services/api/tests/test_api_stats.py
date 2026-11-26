"""StatsService math with an injected clock."""

from __future__ import annotations

import asyncio
import json

import pytest
from api_fakes import FakeClock, FakeWebSocket, make_alert, make_edit, make_revert

from editwar_api.repositories import AlertRepository
from editwar_api.stats import StatsService
from editwar_api.websocket import WebSocketHub


def test_throughput_counts_last_60_seconds() -> None:
    clock = FakeClock()
    stats = StatsService(clock=clock)
    for _ in range(30):
        stats.record_edit(make_edit())
    assert stats.throughput() == 0.5

    clock.now += 30
    for _ in range(30):
        stats.record_edit(make_edit())
    assert stats.throughput() == 1.0

    clock.now += 30  # the first 30 edits are now exactly 60 s old and leave the window
    assert stats.throughput() == 0.5
    clock.now += 31
    assert stats.throughput() == 0.0
    assert stats.total_edits == 60


def test_top_disputed_ranks_articles_by_reverts() -> None:
    clock = FakeClock()
    stats = StatsService(clock=clock)
    for _ in range(3):
        stats.record_revert(make_revert(title="Bogota"))
    stats.record_revert(make_revert(title="Lima", wiki="eswiki", server_url="https://es.w.org"))
    for _ in range(2):
        stats.record_revert(make_revert(title="Quito"))

    top = stats.top_disputed()
    assert [(item["title"], item["reverts"]) for item in top] == [
        ("Bogota", 3),
        ("Quito", 2),
        ("Lima", 1),
    ]
    assert top[2] == {
        "wiki": "eswiki",
        "title": "Lima",
        "reverts": 1,
        "page_url": "https://es.w.org/wiki/Lima",
    }
    assert len(stats.top_disputed(2)) == 2
    assert stats.total_reverts == 6


def test_top_disputed_forgets_reverts_after_one_hour() -> None:
    clock = FakeClock()
    stats = StatsService(clock=clock)
    stats.record_revert(make_revert(title="Old war"))
    clock.now += 1800
    stats.record_revert(make_revert(title="New war"))
    clock.now += 1801
    assert [item["title"] for item in stats.top_disputed()] == ["New war"]
    assert stats.total_reverts == 2


def test_top_disputed_returns_at_most_ten() -> None:
    stats = StatsService(clock=FakeClock())
    for index in range(15):
        stats.record_revert(make_revert(title=f"Article {index}"))
    assert len(stats.top_disputed()) == 10


async def test_snapshot_without_database() -> None:
    stats = StatsService(clock=FakeClock())
    stats.record_edit(make_edit())
    snapshot = await stats.snapshot()
    assert snapshot["open_alerts"] == 0
    assert snapshot["total_edits"] == 1
    assert snapshot["edits_per_second"] == 0.02
    assert snapshot["top_disputed"] == []
    assert snapshot["started_at"] == stats.started_at.isoformat()


async def test_snapshot_counts_open_alerts(alert_repo: AlertRepository) -> None:
    await alert_repo.create(make_alert())
    stats = StatsService(alert_repo, clock=FakeClock())
    assert (await stats.snapshot())["open_alerts"] == 1


async def test_run_sends_stats_to_connected_clients() -> None:
    hub = WebSocketHub()
    stats = StatsService()
    task = asyncio.create_task(stats.run(hub, 0.01))
    await asyncio.sleep(0.03)  # no clients yet: nothing to send
    client = FakeWebSocket()
    await hub.connect(client)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.sent
    assert json.loads(client.sent[0])["type"] == "stats"


class BrokenAlerts:
    async def count_open(self) -> int:
        raise ConnectionError("database is down")


async def test_run_survives_database_errors(caplog: pytest.LogCaptureFixture) -> None:
    hub = WebSocketHub()
    client = FakeWebSocket()
    await hub.connect(client)
    stats = StatsService(BrokenAlerts())  # type: ignore[arg-type]
    task = asyncio.create_task(stats.run(hub, 0.01))
    await asyncio.sleep(0.05)
    assert not task.done()
    task.cancel()
    assert client.sent == []
    assert "could not send stats" in caplog.text
