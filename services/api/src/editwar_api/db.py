"""Database tables, engine and migrations.

The column types are generic SQLAlchemy types, so the same models work on
PostgreSQL (production, asyncpg) and on SQLite (tests, aiosqlite):
Uuid is a native uuid on PostgreSQL and CHAR(32) on SQLite, JSON is json on
PostgreSQL and TEXT on SQLite.

Migrations: the api runs `alembic upgrade head` itself when it starts (see
run_migrations), so no separate init step is necessary. The Alembic scripts are
in services/api/alembic. To run them by hand: `cd services/api && alembic upgrade head`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, Boolean, Connection, DateTime, Integer, String, Uuid
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RuleRow(Base):
    """One detection rule. Mirrors editwar_domain.DetectionRule."""

    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    window_seconds: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
    min_users: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AlertRow(Base):
    """One alert. Mirrors editwar_domain.Alert.

    rule_id has no foreign key on purpose: alerts stay in the history after
    their rule is deleted.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    wiki: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    server_url: Mapped[str] = mapped_column(String(255))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def make_engine(database_url: str) -> AsyncEngine:
    """Create the async engine.

    An in-memory SQLite database exists only inside one connection, so the
    tests use a StaticPool that shares one connection.
    """
    if database_url.startswith("sqlite") and ":memory:" in database_url:
        return create_async_engine(
            database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(database_url, pool_pre_ping=True)


def make_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory. expire_on_commit=False keeps rows readable after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


def _upgrade(connection: Connection, script_location: str) -> None:
    """Run `alembic upgrade head` on an open synchronous connection."""
    config = Config()
    config.set_main_option("script_location", script_location)
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def run_migrations(engine: AsyncEngine, script_location: str) -> None:
    """Bring the database schema up to date.

    Alembic is synchronous, so it runs inside run_sync on the async engine.
    alembic/env.py reuses this connection instead of creating its own engine.
    """
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade, script_location)
