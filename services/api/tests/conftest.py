"""Shared fixtures for the api tests.

No network: the database is SQLite in memory (aiosqlite) and Kafka is off.
The test files are named test_api_*.py and the helpers live in api_fakes.py,
so that no module name collides with the tests of the other services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
from api_fakes import MEMORY_DB, start_client
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from editwar_api.config import Settings
from editwar_api.db import make_engine, make_sessions, run_migrations
from editwar_api.repositories import AlertRepository, RuleRepository


@pytest.fixture
def settings() -> Settings:
    return replace(
        Settings.from_env(),
        database_url=MEMORY_DB,
        kafka_enabled=False,
        stats_interval_seconds=0.05,
        enable_debug_endpoints=True,
        service_version="1.2.3",
        environment="test",
    )


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A migrated, empty in-memory database."""
    engine = make_engine(MEMORY_DB)
    await run_migrations(engine, Settings.from_env().alembic_script_location)
    yield make_sessions(engine)
    await engine.dispose()


@pytest.fixture
def rule_repo(sessions: async_sessionmaker[AsyncSession]) -> RuleRepository:
    return RuleRepository(sessions)


@pytest.fixture
def alert_repo(sessions: async_sessionmaker[AsyncSession]) -> AlertRepository:
    return AlertRepository(sessions)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for an app that ran its startup (migrations and seeding)."""
    async for value in start_client(settings):
        yield value


@pytest.fixture
def metric_reader() -> InMemoryMetricReader:
    """Collects the metrics in memory, instead of exporting them."""
    return InMemoryMetricReader()


@pytest.fixture
def meter_provider(metric_reader: InMemoryMetricReader) -> Iterator[MeterProvider]:
    """An SDK provider for one test. The global provider is never changed."""
    provider = MeterProvider(metric_readers=[metric_reader])
    yield provider
    provider.shutdown()


@pytest.fixture
def metric_points(metric_reader: InMemoryMetricReader) -> Callable[[str], list[Any]]:
    """Return points(name): the data points of metric `name` at this moment."""

    def points(name: str) -> list[Any]:
        data = metric_reader.get_metrics_data()
        if data is None:
            return []
        return [
            point
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]

    return points
