"""REST tests for /api/alerts: filters, pagination, PATCH, DELETE, 404 and 422."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from api_fakes import make_alert

from editwar_api.repositories import AlertRepository
from editwar_domain import Alert, AlertStatus

UNKNOWN_ID = "11111111-1111-1111-1111-111111111111"


def repo(client: httpx.AsyncClient) -> AlertRepository:
    return client.app.state.alerts  # type: ignore[attr-defined, no-any-return]


async def store_samples(client: httpx.AsyncClient) -> list[Alert]:
    """Five alerts, one minute apart. The last one is the newest."""
    start = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    alerts = [
        make_alert(created_at=start, wiki="enwiki", kind="revert_war"),
        make_alert(created_at=start + timedelta(minutes=1), wiki="eswiki", kind="burst"),
        make_alert(created_at=start + timedelta(minutes=2), wiki="enwiki", kind="bot_spike"),
        make_alert(
            created_at=start + timedelta(minutes=3), wiki="enwiki", status=AlertStatus.DISMISSED
        ),
        make_alert(created_at=start + timedelta(minutes=4), wiki="dewiki", kind="burst"),
    ]
    for alert in alerts:
        await repo(client).create(alert)
    return alerts


async def test_list_alerts_newest_first(client: httpx.AsyncClient) -> None:
    alerts = await store_samples(client)
    response = await client.get("/api/alerts")
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(a.id) for a in reversed(alerts)]
    assert body[0] == alerts[-1].to_dict()
    assert body[0]["page_url"] == "https://en.wikipedia.org/wiki/Python_(programming_language)"


async def test_list_alerts_empty(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/alerts")).json() == []


async def test_filter_alerts(client: httpx.AsyncClient) -> None:
    await store_samples(client)
    by_wiki = (await client.get("/api/alerts", params={"wiki": "enwiki"})).json()
    assert len(by_wiki) == 3
    by_kind = (await client.get("/api/alerts", params={"kind": "burst"})).json()
    assert {a["wiki"] for a in by_kind} == {"eswiki", "dewiki"}
    by_status = (await client.get("/api/alerts", params={"status": "dismissed"})).json()
    assert len(by_status) == 1
    combined = await client.get(
        "/api/alerts", params={"wiki": "enwiki", "status": "open", "kind": "revert_war"}
    )
    assert len(combined.json()) == 1


async def test_paginate_alerts(client: httpx.AsyncClient) -> None:
    alerts = await store_samples(client)
    newest_first = [str(a.id) for a in reversed(alerts)]
    page1 = (await client.get("/api/alerts", params={"limit": 2})).json()
    page2 = (await client.get("/api/alerts", params={"limit": 2, "offset": 2})).json()
    page3 = (await client.get("/api/alerts", params={"limit": 2, "offset": 4})).json()
    assert [a["id"] for a in page1 + page2 + page3] == newest_first
    assert len(page3) == 1


async def test_invalid_alert_queries_are_422(client: httpx.AsyncClient) -> None:
    for params in (
        {"limit": 501},
        {"limit": 0},
        {"offset": -1},
        {"status": "closed"},
        {"kind": "riot"},
    ):
        assert (await client.get("/api/alerts", params=params)).status_code == 422


async def test_get_alert(client: httpx.AsyncClient) -> None:
    alert = make_alert()
    await repo(client).create(alert)
    response = await client.get(f"/api/alerts/{alert.id}")
    assert response.status_code == 200
    assert response.json() == alert.to_dict()
    assert (await client.get(f"/api/alerts/{UNKNOWN_ID}")).status_code == 404


async def test_acknowledge_alert(client: httpx.AsyncClient) -> None:
    alert = make_alert()
    await repo(client).create(alert)
    body = {"status": "acknowledged", "user": "Maria"}
    response = await client.patch(f"/api/alerts/{alert.id}", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert response.json()["acknowledged_by"] == "Maria"
    stored = (await client.get(f"/api/alerts/{alert.id}")).json()
    assert stored["acknowledged_by"] == "Maria"


async def test_acknowledge_without_user(client: httpx.AsyncClient) -> None:
    alert = make_alert()
    await repo(client).create(alert)
    response = await client.patch(f"/api/alerts/{alert.id}", json={"status": "acknowledged"})
    assert response.json()["acknowledged_by"] == "anonymous"


async def test_dismiss_alert(client: httpx.AsyncClient) -> None:
    alert = make_alert()
    await repo(client).create(alert)
    response = await client.patch(f"/api/alerts/{alert.id}", json={"status": "dismissed"})
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert response.json()["acknowledged_by"] is None


async def test_patch_errors(client: httpx.AsyncClient) -> None:
    alert = make_alert()
    await repo(client).create(alert)
    response = await client.patch(f"/api/alerts/{alert.id}", json={"status": "open"})
    assert response.status_code == 422
    response = await client.patch(f"/api/alerts/{UNKNOWN_ID}", json={"status": "dismissed"})
    assert response.status_code == 404
    assert response.json() == {"detail": "alert not found"}


async def test_delete_alert(client: httpx.AsyncClient) -> None:
    alert = make_alert()
    await repo(client).create(alert)
    assert (await client.delete(f"/api/alerts/{alert.id}")).status_code == 204
    assert (await client.get(f"/api/alerts/{alert.id}")).status_code == 404
    assert (await client.delete(f"/api/alerts/{alert.id}")).status_code == 404
