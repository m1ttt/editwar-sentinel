# EditWar Sentinel api image.
# Build from the repository root:
#   docker build -f services/api/Dockerfile -t editwar-api:local .

# ---- builder: install the locked dependencies into a virtual environment ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# uv needs the root project, the lock file and every workspace member's
# pyproject.toml to read the workspace. Only the api and the domain are installed.
COPY pyproject.toml uv.lock .python-version ./
COPY libs/domain/pyproject.toml libs/domain/
COPY services/ingestor/pyproject.toml services/ingestor/
COPY services/detector/pyproject.toml services/detector/
COPY services/api/pyproject.toml services/api/

# Third-party dependencies first: this layer is cached until uv.lock changes.
RUN uv sync --frozen --no-dev --package editwar-api --no-install-workspace

# Then our own code, installed as normal (not editable) packages.
COPY libs/domain/src libs/domain/src
COPY services/api/src services/api/src
RUN uv sync --frozen --no-dev --package editwar-api --no-editable

# ---- runtime: only the virtual environment and the Alembic scripts ----
FROM python:3.12-slim

RUN useradd --create-home --uid 10001 editwar

COPY --from=builder /opt/venv /opt/venv
COPY services/api/alembic /app/alembic

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    ALEMBIC_SCRIPT_LOCATION=/app/alembic \
    PORT=8000

WORKDIR /app
USER 10001
EXPOSE 8000

CMD ["editwar-api"]
