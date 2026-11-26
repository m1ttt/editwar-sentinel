# Detector image. Build from the repo root:
#   docker build -f services/detector/Dockerfile -t editwar-detector:local .

# --- builder: install the domain library and the detector into a venv --------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
COPY libs/domain libs/domain
COPY services/detector services/detector

# One command, so pip takes editwar-domain from the local folder, not from PyPI.
RUN pip install "./libs/domain[telemetry]" ./services/detector

# --- runtime: only the venv, run as a non-root user --------------------------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEALTH_PORT=8081

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

COPY --from=builder /opt/venv /opt/venv

USER 10001
EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('HEALTH_PORT', '8081')}/healthz\", timeout=2)"]

# Exec form: the Python process is PID 1 and gets SIGTERM from Kubernetes.
CMD ["editwar-detector"]
