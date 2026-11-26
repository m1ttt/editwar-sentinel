"""Settings of the api service, read from environment variables.

Shared variables (DATABASE_URL, KAFKA_BOOTSTRAP_SERVERS, ...) are documented in
editwar_domain.settings. Variables that only the api uses:

- KAFKA_ENABLED. Default: true. Set false to run without Kafka (tests, local demos).
- ENVIRONMENT. Default: local. Shown by GET /api/version.
- CORS_ORIGINS. Default: "*". Comma list of allowed origins.
- EDIT_SAMPLE_PER_SECOND. Default: 15. Max edit messages per second on /ws/live.
- STATS_INTERVAL_SECONDS. Default: 2. Period of the "stats" message on /ws/live.
- ENABLE_DEBUG_ENDPOINTS. Default: true. Enables /api/debug/error and /api/debug/log.
- ALEMBIC_SCRIPT_LOCATION. Default: services/api/alembic in the source tree.
- PORT. Default: 8000.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from editwar_domain.settings import (
    DATABASE_URL,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_ID,
    SERVICE_VERSION,
    env,
    env_float,
    env_int,
    env_list,
)

DEFAULT_DATABASE_URL = "postgresql+asyncpg://editwar:editwar@localhost/editwar"

# src/editwar_api/config.py -> parents[2] is services/api
DEFAULT_ALEMBIC_DIR = str(Path(__file__).resolve().parents[2] / "alembic")


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean variable. "true", "1" and "yes" mean True."""
    return env(name, str(default)).lower() in {"true", "1", "yes"}


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    kafka_enabled: bool
    kafka_bootstrap_servers: str
    kafka_group_id: str
    service_version: str
    environment: str
    cors_origins: list[str]
    edit_sample_per_second: int
    stats_interval_seconds: float
    enable_debug_endpoints: bool
    alembic_script_location: str
    port: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=env(DATABASE_URL, DEFAULT_DATABASE_URL),
            kafka_enabled=env_bool("KAFKA_ENABLED", True),
            kafka_bootstrap_servers=env(KAFKA_BOOTSTRAP_SERVERS, "localhost:9092"),
            kafka_group_id=env(KAFKA_GROUP_ID, "api"),
            service_version=env(SERVICE_VERSION, "dev"),
            environment=env("ENVIRONMENT", "local"),
            cors_origins=env_list("CORS_ORIGINS") or ["*"],
            edit_sample_per_second=env_int("EDIT_SAMPLE_PER_SECOND", 15),
            stats_interval_seconds=env_float("STATS_INTERVAL_SECONDS", 2.0),
            enable_debug_endpoints=env_bool("ENABLE_DEBUG_ENDPOINTS", True),
            alembic_script_location=env("ALEMBIC_SCRIPT_LOCATION", DEFAULT_ALEMBIC_DIR),
            port=env_int("PORT", 8000),
        )
