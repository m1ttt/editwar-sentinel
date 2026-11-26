"""Entry point of the detector: `editwar-detector`."""

from __future__ import annotations

import asyncio
import logging
import signal

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from editwar_detector.engine import DetectionEngine
from editwar_detector.health import HealthServer
from editwar_detector.rule_provider import RuleProvider
from editwar_detector.service import DetectorService
from editwar_detector.sinks import AlertDispatcher, ConsoleAlertSink
from editwar_domain import TOPIC_EDITS
from editwar_domain.settings import (
    API_URL,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_ID,
    RULES_REFRESH_SECONDS,
    env,
    env_int,
)
from editwar_domain.telemetry import configure_telemetry

log = logging.getLogger("editwar.detector")

HEALTH_PORT = "HEALTH_PORT"


def build_service() -> DetectorService:
    """Create the service and its parts from the environment variables."""
    bootstrap = env(KAFKA_BOOTSTRAP_SERVERS, "localhost:9092")
    group_id = env(KAFKA_GROUP_ID, "detector")
    refresh_seconds = env_int(RULES_REFRESH_SECONDS, 30)

    def make_consumer() -> AIOKafkaConsumer:
        return AIOKafkaConsumer(
            TOPIC_EDITS,
            bootstrap_servers=bootstrap,
            group_id=group_id,
            enable_auto_commit=False,  # the service commits after it sends the outputs
            auto_offset_reset="earliest",  # a new group reads the edits kept by Kafka
        )

    def make_producer() -> AIOKafkaProducer:
        return AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all")

    dispatcher = AlertDispatcher()
    dispatcher.subscribe(ConsoleAlertSink())
    return DetectorService(
        engine=DetectionEngine(),
        dispatcher=dispatcher,
        rule_provider=RuleProvider(env(API_URL, "http://localhost:8000"), refresh_seconds),
        consumer_factory=make_consumer,
        producer_factory=make_producer,
        refresh_seconds=refresh_seconds,
    )


async def run_detector() -> None:
    """Start the health server, stop on SIGTERM or SIGINT, and run the service."""
    service = build_service()
    health = HealthServer(service.stats, port=env_int(HEALTH_PORT, 8081))
    await health.start()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, service.stop)
    try:
        await service.run()
    finally:
        await health.stop()
        await service.rule_provider.aclose()


def main() -> None:
    configure_telemetry("detector")
    log.info("starting detector")
    asyncio.run(run_detector())


if __name__ == "__main__":
    main()
