"""REST tests for /api/rules: every verb, 404 and 422."""

from __future__ import annotations

import uuid

import httpx

VALID_RULE = {
    "name": "Small war",
    "kind": "revert_war",
    "window_seconds": 600,
    "threshold": 2,
    "min_users": 2,
    "enabled": True,
}
UNKNOWN_ID = "11111111-1111-1111-1111-111111111111"


async def test_list_rules_returns_seeded_defaults(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/rules")
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) == 3
    assert {rule["kind"] for rule in rules} == {"revert_war", "burst", "bot_spike"}
    assert rules[0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert set(rules[0]) == {
        "id",
        "name",
        "kind",
        "window_seconds",
        "threshold",
        "min_users",
        "enabled",
    }


async def test_create_and_get_rule(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/rules", json=VALID_RULE)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Small war"
    uuid.UUID(body["id"])

    fetched = await client.get(f"/api/rules/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    assert len((await client.get("/api/rules")).json()) == 4


async def test_create_rule_uses_defaults(client: httpx.AsyncClient) -> None:
    body = {"name": "Bursty", "kind": "burst", "window_seconds": 60, "threshold": 5}
    created = (await client.post("/api/rules", json=body)).json()
    assert created["min_users"] == 1
    assert created["enabled"] is True


async def test_create_rule_with_invalid_values_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/rules", json=VALID_RULE | {"window_seconds": 5})
    assert response.status_code == 422
    assert response.json() == {"detail": "window_seconds must be between 10 and 86400"}

    response = await client.post("/api/rules", json=VALID_RULE | {"name": "  "})
    assert response.status_code == 422
    assert response.json()["detail"] == "name must not be empty"


async def test_create_rule_with_bad_body_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/rules", json=VALID_RULE | {"kind": "unknown"})
    assert response.status_code == 422
    response = await client.post("/api/rules", json={"name": "missing fields"})
    assert response.status_code == 422


async def test_get_unknown_rule_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/rules/{UNKNOWN_ID}")
    assert response.status_code == 404
    assert response.json() == {"detail": "rule not found"}


async def test_get_rule_with_bad_id_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/rules/not-a-uuid")).status_code == 422


async def test_update_rule(client: httpx.AsyncClient) -> None:
    rule_id = "00000000-0000-0000-0000-000000000002"
    change = VALID_RULE | {"name": "Bigger burst", "kind": "burst", "enabled": False}
    response = await client.put(f"/api/rules/{rule_id}", json=change)
    assert response.status_code == 200
    assert response.json() == change | {"id": rule_id}
    assert (await client.get(f"/api/rules/{rule_id}")).json()["enabled"] is False


async def test_update_rule_with_invalid_values_is_422(client: httpx.AsyncClient) -> None:
    rule_id = "00000000-0000-0000-0000-000000000001"
    response = await client.put(f"/api/rules/{rule_id}", json=VALID_RULE | {"threshold": 0})
    assert response.status_code == 422
    assert response.json() == {"detail": "threshold must be at least 1"}
    unchanged = (await client.get(f"/api/rules/{rule_id}")).json()
    assert unchanged["threshold"] == 3


async def test_update_unknown_rule_is_404(client: httpx.AsyncClient) -> None:
    response = await client.put(f"/api/rules/{UNKNOWN_ID}", json=VALID_RULE)
    assert response.status_code == 404


async def test_delete_rule(client: httpx.AsyncClient) -> None:
    rule_id = "00000000-0000-0000-0000-000000000003"
    response = await client.delete(f"/api/rules/{rule_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(f"/api/rules/{rule_id}")).status_code == 404
    assert (await client.delete(f"/api/rules/{rule_id}")).status_code == 404
