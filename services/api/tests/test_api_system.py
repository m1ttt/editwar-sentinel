"""Health probes, version, stats, debug endpoints, CORS, startup and main()."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from api_fakes import FakeConsumer, make_alert, make_edit, start_client

import editwar_api.app as app_module
import editwar_api.main as main_module
from editwar_api.app import create_app
from editwar_api.config import Settings, env_bool
from editwar_api.consumers import AlertConsumer, LiveConsumer


async def test_healthz(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_with_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "kafka": "disabled"}


class BrokenEngine:
    def connect(self) -> Any:
        raise ConnectionError("database is down")


async def test_readyz_without_database(client: httpx.AsyncClient) -> None:
    client.app.state.engine = BrokenEngine()  # type: ignore[attr-defined]
    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["database"] == "error"
    assert (await client.get("/healthz")).status_code == 200


async def test_readyz_reports_kafka_state(settings: Settings) -> None:
    app = create_app(replace(settings, kafka_enabled=True))  # lifespan not started
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/readyz")).json()["kafka"] == "disconnected"
        app.state.alert_consumer.connected = True
        app.state.live_consumer.connected = True
        assert (await client.get("/readyz")).json()["kafka"] == "connected"


async def test_version(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/version")
    assert response.json() == {"service": "api", "version": "1.2.3", "environment": "test"}


async def test_stats_endpoint(client: httpx.AsyncClient) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    await state.alerts.create(make_alert())
    state.stats.record_edit(make_edit())
    body = (await client.get("/api/stats")).json()
    assert set(body) == {
        "edits_per_second",
        "total_edits",
        "total_reverts",
        "open_alerts",
        "top_disputed",
        "started_at",
    }
    assert body["total_edits"] == 1
    assert body["open_alerts"] == 1


async def test_debug_error_returns_500(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/debug/error")
    assert response.status_code == 500


async def test_debug_log_has_custom_dimensions(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="editwar.api"):
        response = await client.get("/api/debug/log", params={"message": "hola"})
    assert response.json() == {"logged": "hola"}
    record = next(r for r in caplog.records if r.name == "editwar.api")
    assert record.levelno == logging.WARNING
    assert record.debug_message == "hola"  # type: ignore[attr-defined]
    assert record.environment == "test"  # type: ignore[attr-defined]


async def test_debug_endpoints_can_be_disabled(settings: Settings) -> None:
    async for client in start_client(replace(settings, enable_debug_endpoints=False)):
        assert (await client.get("/api/debug/error")).status_code == 404
        assert (await client.get("/api/debug/log")).status_code == 404


async def test_rule_changes_are_logged(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    body = {"name": "Log me", "kind": "burst", "window_seconds": 60, "threshold": 5}
    with caplog.at_level(logging.INFO, logger="editwar.api"):
        await client.post("/api/rules", json=body)
    record = next(r for r in caplog.records if getattr(r, "action", None) == "created")
    assert record.rule_name == "Log me"  # type: ignore[attr-defined]


async def test_cors_header(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"Origin": "http://dashboard.local"})
    assert response.headers["access-control-allow-origin"] == "*"


async def test_seeding_happens_once(settings: Settings, tmp_path: Path) -> None:
    file_db = replace(settings, database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    async for client in start_client(file_db):
        rule_id = "00000000-0000-0000-0000-000000000001"
        assert (await client.delete(f"/api/rules/{rule_id}")).status_code == 204
    async for client in start_client(file_db):  # second start: table not empty, no new seed
        assert len((await client.get("/api/rules")).json()) == 2


async def test_startup_with_kafka_starts_consumers(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeConsumer] = []

    def fake_factory(*args: object) -> Any:
        def create() -> FakeConsumer:
            consumer = FakeConsumer(block=True)
            created.append(consumer)
            return consumer

        return create

    monkeypatch.setattr(AlertConsumer, "default_factory", staticmethod(fake_factory))
    monkeypatch.setattr(LiveConsumer, "default_factory", staticmethod(fake_factory))
    async for client in start_client(replace(settings, kafka_enabled=True)):
        await asyncio.sleep(0.01)  # let the consumer tasks call start()
        assert (await client.get("/readyz")).json()["kafka"] == "connected"
    assert len(created) == 2
    assert all(consumer.stopped for consumer in created)


def test_telemetry_instruments_the_app(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "configure_telemetry", lambda name: True)
    app = create_app(settings)
    assert app._is_instrumented_by_opentelemetry  # type: ignore[attr-defined]


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_ENABLED", "false")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("EDIT_SAMPLE_PER_SECOND", "5")
    monkeypatch.setenv("PORT", "9000")
    settings = Settings.from_env()
    assert settings.kafka_enabled is False
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.edit_sample_per_second == 5
    assert settings.port == 9000
    assert Path(settings.alembic_script_location, "env.py").exists()
    assert env_bool("UNSET_VARIABLE_FOR_TEST", True) is True


def test_main_runs_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    def fake_run(app: object, host: str, port: int) -> None:
        calls.update(app=app, host=host, port=port)

    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(main_module.uvicorn, "run", fake_run)
    main_module.main()
    assert (calls["host"], calls["port"]) == ("0.0.0.0", 8123)
