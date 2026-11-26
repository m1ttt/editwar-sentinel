"""Alembic environment.

Two ways to run it:

- From the api at startup (editwar_api.db.run_migrations). The api passes an
  open connection in config.attributes["connection"] and env.py uses it.
- From the command line: `cd services/api && alembic upgrade head`. env.py then
  creates its own async engine from DATABASE_URL.

fileConfig() is not called on purpose: it would disable the "editwar" loggers
that send logs to Application Insights.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection

from editwar_api.config import Settings
from editwar_api.db import Base, make_engine

target_metadata = Base.metadata


def run_on_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_from_command_line() -> None:
    engine = make_engine(Settings.from_env().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(run_on_connection)
    await engine.dispose()


existing_connection = context.config.attributes.get("connection")
if existing_connection is None:
    asyncio.run(run_from_command_line())
else:
    run_on_connection(existing_connection)
