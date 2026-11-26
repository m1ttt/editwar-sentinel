"""FastAPI application factory.

create_app() builds every object of the api and wires them together.
The lifespan runs at startup and shutdown:

1. `alembic upgrade head` (db.run_migrations) and seeding of default_rules().
2. Background tasks: the "stats" message every STATS_INTERVAL_SECONDS and,
   when KAFKA_ENABLED is true, the AlertConsumer and the LiveConsumer.
3. At shutdown the tasks are cancelled and the database pool is closed.

Telemetry: configure_telemetry("api") runs before the app is created. When
APPLICATIONINSIGHTS_CONNECTION_STRING is set, the azure-monitor-opentelemetry
distro enables the FastAPI instrumentation, but only for FastAPI classes
created after configure_azure_monitor(). FastAPIInstrumentor.instrument_app()
is therefore also called on the app; a second call on an app that is already
instrumented does nothing. Every request then becomes a request in
Application Insights, with its exceptions, and the "editwar.api" logs go to
the traces table with their `extra` values as custom dimensions.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import text

from editwar_api.config import Settings
from editwar_api.consumers import AlertConsumer, LiveConsumer
from editwar_api.controllers import AlertController, RuleController
from editwar_api.db import make_engine, make_sessions, run_migrations
from editwar_api.geo import GeoService
from editwar_api.repositories import AlertRepository, RuleRepository
from editwar_api.stats import StatsService
from editwar_api.websocket import WebSocketHub
from editwar_domain.telemetry import configure_telemetry

logger = logging.getLogger("editwar.api")

DB_START_ATTEMPTS = 10
DB_MAX_RETRY_DELAY_SECONDS = 10.0


async def wait_for_database(
    migrate: Callable[[], Awaitable[None]],
    attempts: int = DB_START_ATTEMPTS,
    first_delay: float = 1.0,
) -> None:
    """Run the migrations, retrying while the database is still starting.

    In Kubernetes the api and PostgreSQL start at the same time. Retrying here
    avoids a crash loop of the api pod.
    """
    delay = first_delay
    for attempt in range(1, attempts + 1):
        try:
            await migrate()
            return
        except Exception as error:
            if attempt == attempts:
                raise
            logger.warning("database not ready (attempt %d of %d): %s", attempt, attempts, error)
            await asyncio.sleep(delay)
            delay = min(delay * 2, DB_MAX_RETRY_DELAY_SECONDS)


class DebugError(RuntimeError):
    """Raised on purpose by GET /api/debug/error to demo error tracking."""


def system_router(settings: Settings) -> APIRouter:
    """Health probes, version and stats."""
    router = APIRouter()

    @router.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        """Liveness probe. Does not touch the database or Kafka."""
        return {"status": "ok"}

    @router.get("/readyz", tags=["system"])
    async def readyz(request: Request) -> JSONResponse:
        """Readiness probe. 503 when the database does not answer."""
        state = request.app.state
        kafka = "disabled"
        if settings.kafka_enabled:
            connected = state.alert_consumer.connected and state.live_consumer.connected
            kafka = "connected" if connected else "disconnected"
        try:
            async with state.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as error:
            logger.warning("readiness check failed: %s", error)
            body = {"status": "unavailable", "database": "error", "kafka": kafka}
            return JSONResponse(body, status_code=503)
        return JSONResponse({"status": "ready", "database": "ok", "kafka": kafka})

    @router.get("/api/version", tags=["system"])
    async def version() -> dict[str, str]:
        return {
            "service": "api",
            "version": settings.service_version,
            "environment": settings.environment,
        }

    @router.get("/api/stats", tags=["stats"])
    async def stats(request: Request) -> dict[str, Any]:
        result: dict[str, Any] = await request.app.state.stats.snapshot()
        return result

    @router.websocket("/ws/live")
    async def live(websocket: WebSocket) -> None:
        """Live feed. The server only sends; messages from the client are ignored."""
        state = websocket.app.state
        hub: WebSocketHub = state.hub
        await hub.connect(websocket)
        try:
            await websocket.send_json({"type": "stats", "data": await state.stats.snapshot()})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(websocket)

    return router


def debug_router(environment: str) -> APIRouter:
    """Endpoints that create an error and a log on purpose, for the APM demo."""
    router = APIRouter(prefix="/api/debug", tags=["debug"])

    @router.get("/error")
    async def error() -> None:
        raise DebugError("debug error requested through /api/debug/error")

    @router.get("/log")
    async def log(message: str = "debug message") -> dict[str, str]:
        logger.warning(
            "debug log: %s",
            message,
            extra={
                "debug_message": message,
                "source": "debug-endpoint",
                "environment": environment,
            },
        )
        return {"logged": message}

    return router


def geo_router() -> APIRouter:
    router = APIRouter(prefix="/api/geo", tags=["geo"])

    @router.get("/recent")
    async def recent_points(
        request: Request, limit: int = Query(default=200, ge=1, le=1000)
    ) -> list[dict[str, Any]]:
        """Last reverts and alerts on articles with coordinates, newest first."""
        geo: GeoService | None = request.app.state.geo
        if geo is None:
            return []
        return [point.to_dict() for point in geo.recent(limit)]

    return router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    telemetry_active = configure_telemetry("api")

    engine = make_engine(settings.database_url)
    sessions = make_sessions(engine)
    rules = RuleRepository(sessions)
    alerts = AlertRepository(sessions)
    hub = WebSocketHub(edits_per_second=settings.edit_sample_per_second)
    stats = StatsService(alerts)
    alert_consumer = AlertConsumer(alerts, hub)
    geo = GeoService(max_points=settings.geo_max_points) if settings.geo_enabled else None
    live_consumer = LiveConsumer(stats, hub, geo)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await wait_for_database(lambda: run_migrations(engine, settings.alembic_script_location))
        seeded = await rules.seed_defaults()
        if seeded:
            logger.info("seeded %d default rules", seeded)
        tasks = [asyncio.create_task(stats.run(hub, settings.stats_interval_seconds))]
        if settings.kafka_enabled:
            servers = settings.kafka_bootstrap_servers
            alert_factory = AlertConsumer.default_factory(servers, settings.kafka_group_id)
            live_factory = LiveConsumer.default_factory(servers)
            tasks.append(asyncio.create_task(alert_consumer.run(alert_factory)))
            tasks.append(asyncio.create_task(live_consumer.run(live_factory)))
        else:
            logger.info("KAFKA_ENABLED=false: Kafka consumers are not started")
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await live_consumer.drain()
        if geo is not None:
            await geo.close()
        await engine.dispose()

    app = FastAPI(title="EditWar Sentinel API", version=settings.service_version, lifespan=lifespan)
    if telemetry_active:
        FastAPIInstrumentor.instrument_app(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.rules = rules
    app.state.alerts = alerts
    app.state.hub = hub
    app.state.stats = stats
    app.state.alert_consumer = alert_consumer
    app.state.live_consumer = live_consumer
    app.state.geo = geo

    app.include_router(system_router(settings))
    app.include_router(geo_router())
    app.include_router(RuleController(rules).router)
    app.include_router(AlertController(alerts).router)
    if settings.enable_debug_endpoints:
        app.include_router(debug_router(settings.environment))
    return app
