"""Entry point: read the settings, wire the classes together and run until SIGTERM."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from dataclasses import dataclass

from editwar_domain.settings import (
    DEFAULT_STREAM_URL,
    EVENT_SOURCE,
    KAFKA_BOOTSTRAP_SERVERS,
    REPLAY_PATH,
    REPLAY_SPEED,
    WIKIMEDIA_STREAM_URL,
    WIKIS,
    env,
    env_float,
    env_int,
    env_list,
)
from editwar_domain.telemetry import configure_telemetry
from editwar_ingestor.filters import EventFilter
from editwar_ingestor.health import HealthServer
from editwar_ingestor.metrics import IngestorMetrics
from editwar_ingestor.normalizer import EventNormalizer
from editwar_ingestor.publisher import EventPublisher, KafkaEventPublisher
from editwar_ingestor.service import IngestorService
from editwar_ingestor.sources import EventSource, ReplayFileSource, WikimediaSSESource

logger = logging.getLogger("editwar.ingestor.main")

# Only the ingestor uses this variable, so it is not in editwar_domain.settings.
HEALTH_PORT = "HEALTH_PORT"


@dataclass(frozen=True)
class IngestorSettings:
    """Configuration of the ingestor, read from environment variables."""

    event_source: str = "sse"
    stream_url: str = DEFAULT_STREAM_URL
    replay_path: str = "/data/replay.jsonl"
    replay_speed: float = 1.0
    wikis: tuple[str, ...] = ()
    kafka_bootstrap: str = "localhost:9092"
    health_port: int = 8081


def load_settings() -> IngestorSettings:
    """Read the settings from the environment."""
    return IngestorSettings(
        event_source=env(EVENT_SOURCE, "sse").lower(),
        stream_url=env(WIKIMEDIA_STREAM_URL, DEFAULT_STREAM_URL),
        replay_path=env(REPLAY_PATH, "/data/replay.jsonl"),
        replay_speed=env_float(REPLAY_SPEED, 1.0),
        wikis=tuple(env_list(WIKIS)),
        kafka_bootstrap=env(KAFKA_BOOTSTRAP_SERVERS, "localhost:9092"),
        health_port=env_int(HEALTH_PORT, 8081),
    )


def build_source(settings: IngestorSettings, metrics: IngestorMetrics | None = None) -> EventSource:
    """Create the live stream source or the replay source."""
    if settings.event_source == "sse":
        return WikimediaSSESource(settings.stream_url, metrics=metrics)
    if settings.event_source == "replay":
        return ReplayFileSource(settings.replay_path, settings.replay_speed, metrics=metrics)
    raise ValueError(f"EVENT_SOURCE must be 'sse' or 'replay', not {settings.event_source!r}")


def build_filter(settings: IngestorSettings) -> EventFilter:
    """Create the filter: articles only, edits and new pages, the configured wikis."""
    return EventFilter(wikis=settings.wikis)


async def connect_publisher(
    publisher: EventPublisher,
    stop_event: asyncio.Event,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
) -> bool:
    """Start the publisher, retrying with backoff while the broker is down.

    Returns False if stop_event is set before the publisher connects.
    """
    delay = initial_delay
    while not stop_event.is_set():
        try:
            await publisher.start()
            return True
        except Exception as exc:
            logger.warning("Kafka is not ready (%r), retrying in %.0f s", exc, delay)
        # Wait for the delay, but wake up at once if a stop is requested.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        delay = min(delay * 2, max_delay)
    return False


async def serve(
    settings: IngestorSettings,
    source: EventSource,
    publisher: EventPublisher,
    stop_event: asyncio.Event,
    metrics: IngestorMetrics | None = None,
) -> IngestorService:
    """Run the health server and the ingestor until the source ends or stop_event is set."""
    service = IngestorService(source, EventNormalizer(), build_filter(settings), publisher, metrics)
    # Start the health server first, so the probes pass while Kafka is still starting.
    health = HealthServer(service.stats, port=settings.health_port)
    await health.start()
    try:
        if not await connect_publisher(publisher, stop_event):
            return service
        run_task = asyncio.create_task(service.run())
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            # Wait until the source ends or a stop is requested.
            await asyncio.wait({run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            service.stop()
            stop_task.cancel()
            await run_task  # run() flushes the publisher before it returns
        logger.info("final stats: %s", service.stats())
        return service
    finally:
        await publisher.close()
        await health.stop()


async def run_from_environment() -> None:
    """Build everything from the environment and run until SIGTERM or SIGINT."""
    settings = load_settings()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)
    logger.info("starting ingestor with source=%s", settings.event_source)
    metrics = IngestorMetrics()  # one per process, shared by the source and the service
    source = build_source(settings, metrics)
    publisher = KafkaEventPublisher(settings.kafka_bootstrap)
    await serve(settings, source, publisher, stop_event, metrics)


def main() -> None:
    """Console script entry point (editwar-ingestor)."""
    configure_telemetry("ingestor")
    asyncio.run(run_from_environment())


if __name__ == "__main__":
    main()
