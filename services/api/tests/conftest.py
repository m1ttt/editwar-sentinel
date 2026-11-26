"""Shared fixtures for the api tests.

No network: the database is SQLite in memory (aiosqlite) and Kafka is off.
The test files are named test_api_*.py and the helpers live in api_fakes.py,
so that no module name collides with the tests of the other services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
from api_fakes import MEMORY_DB, start_client
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
