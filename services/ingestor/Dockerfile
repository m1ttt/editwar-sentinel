# Ingestor image. Build from the repo root:
#   docker build -f services/ingestor/Dockerfile -t editwar-ingestor:local .

# ---- Stage 1: install the packages into a virtual environment ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
COPY libs/domain/pyproject.toml libs/domain/pyproject.toml
COPY libs/domain/src libs/domain/src
COPY services/ingestor/pyproject.toml services/ingestor/pyproject.toml
COPY services/ingestor/src services/ingestor/src

# Install both packages in one command, so pip takes editwar-domain from the
# local folder instead of looking for it on PyPI.
RUN pip install "./libs/domain[telemetry]" ./services/ingestor

# ---- Stage 2: runtime image with only the virtual environment ----
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    REPLAY_PATH=/data/replay.jsonl \
    HEALTH_PORT=8081

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
# Recorded events, so EVENT_SOURCE=replay works without network access.
COPY data/replay.jsonl /data/replay.jsonl

USER 10001
EXPOSE 8081
CMD ["editwar-ingestor"]
