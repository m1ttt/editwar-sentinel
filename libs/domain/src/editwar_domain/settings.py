"""Environment variables shared by all services.

Every service reads its configuration from the environment, so the same image
runs in docker compose, k3d, dev and prod. Kubernetes fills these values from
ConfigMaps and Secrets.

- KAFKA_BOOTSTRAP_SERVERS (ingestor, detector, api). Default: localhost:9092.
- KAFKA_GROUP_ID (detector, api). Default: service name.
- DATABASE_URL (api). Default: postgresql+asyncpg://editwar:editwar@localhost/editwar.
- API_URL (detector). Default: http://localhost:8000.
- RULES_REFRESH_SECONDS (detector). Default: 30.
- EVENT_SOURCE (ingestor). Default: sse  (sse or replay).
- WIKIMEDIA_STREAM_URL (ingestor). Default: https://stream.wikimedia.org/v2/stream/recentchange.
- REPLAY_PATH (ingestor). Default: /data/replay.jsonl.
- REPLAY_SPEED (ingestor). Default: 1.0.
- WIKIS (ingestor). Default: empty = all wikis, else comma list (enwiki,eswiki).
- APPLICATIONINSIGHTS_CONNECTION_STRING (all). Default: empty = telemetry off.
- LOG_LEVEL (all). Default: INFO.
- SERVICE_VERSION (all). Default: dev.
- HEALTH_PORT (ingestor, detector). Default: 8081.
"""

from __future__ import annotations

import os


def env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def env_int(name: str, default: int) -> int:
    return int(env(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env(name, str(default)))


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


KAFKA_BOOTSTRAP_SERVERS = "KAFKA_BOOTSTRAP_SERVERS"
KAFKA_GROUP_ID = "KAFKA_GROUP_ID"
DATABASE_URL = "DATABASE_URL"
API_URL = "API_URL"
RULES_REFRESH_SECONDS = "RULES_REFRESH_SECONDS"
EVENT_SOURCE = "EVENT_SOURCE"
WIKIMEDIA_STREAM_URL = "WIKIMEDIA_STREAM_URL"
REPLAY_PATH = "REPLAY_PATH"
REPLAY_SPEED = "REPLAY_SPEED"
WIKIS = "WIKIS"
APPLICATIONINSIGHTS_CONNECTION_STRING = "APPLICATIONINSIGHTS_CONNECTION_STRING"
LOG_LEVEL = "LOG_LEVEL"
SERVICE_VERSION = "SERVICE_VERSION"
HEALTH_PORT = "HEALTH_PORT"

DEFAULT_STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
