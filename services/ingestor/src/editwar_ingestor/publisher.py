"""Publishers: send EditEvent objects to Kafka, or keep them in memory for tests."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any

from aiokafka import AIOKafkaProducer

from editwar_domain import TOPIC_EDITS, EditEvent

logger = logging.getLogger("editwar.ingestor.publisher")

# Tracing is optional: without OpenTelemetry the publisher works the same.
try:
    from opentelemetry import trace

    _tracer: Any = trace.get_tracer("editwar.ingestor")
except ImportError:  # pragma: no cover
    _tracer = None


class EventPublisher(ABC):
    """Destination for normalized edits."""

    async def start(self) -> None:  # noqa: B027  (optional hook, empty by default)
        """Open connections. The default does nothing."""

    @abstractmethod
    async def publish(self, event: EditEvent) -> None:
        """Send one event."""

    @abstractmethod
    async def flush(self) -> None:
        """Wait until every sent event is delivered."""

    async def close(self) -> None:  # noqa: B027  (optional hook, empty by default)
        """Close connections. The default does nothing."""


class KafkaEventPublisher(EventPublisher):
    """Publish edits to a Kafka topic with aiokafka.

    The key is "wiki:title", so all edits of one article go to the same
    partition and keep their order. acks="all" plus idempotence means the
    broker does not lose or duplicate an event when the producer retries.
    """

    def __init__(
        self,
        bootstrap: str,
        topic: str = TOPIC_EDITS,
        *,
        linger_ms: int = 20,
        producer_factory: Callable[..., Any] = AIOKafkaProducer,
    ) -> None:
        self.bootstrap = bootstrap
        self.topic = topic
        self.linger_ms = linger_ms
        self.delivery_errors = 0
        self._producer_factory = producer_factory  # tests inject a fake producer here
        self._producer: Any = None

    async def start(self) -> None:
        """Create a producer and connect it. Raises if the broker is not reachable."""
        producer = self._producer_factory(
            bootstrap_servers=self.bootstrap,
            client_id="editwar-ingestor",
            acks="all",
            enable_idempotence=True,
            linger_ms=self.linger_ms,
        )
        try:
            await producer.start()
        except Exception:
            # A producer that failed to start cannot be reused. Close it and let the caller retry.
            await producer.stop()
            raise
        self._producer = producer
        logger.info("connected to Kafka at %s", self.bootstrap)

    async def publish(self, event: EditEvent) -> None:
        """Queue one event for delivery. Delivery errors are logged and counted."""
        if self._producer is None:
            raise RuntimeError("start() was not called")
        with self._span(event):
            delivery = await self._producer.send(
                self.topic,
                key=event.partition_key().encode("utf-8"),
                value=event.to_json().encode("utf-8"),
            )
        delivery.add_done_callback(self._on_delivery)

    async def flush(self) -> None:
        """Wait for all queued events."""
        if self._producer is not None:
            await self._producer.flush()

    async def close(self) -> None:
        """Flush and disconnect."""
        if self._producer is not None:
            await self._producer.flush()
            await self._producer.stop()
            self._producer = None

    def _on_delivery(self, delivery: asyncio.Future[Any]) -> None:
        """Called by aiokafka when the broker confirms (or rejects) one event."""
        if delivery.cancelled():
            return
        error = delivery.exception()
        if error is not None:
            self.delivery_errors += 1
            logger.error("Kafka delivery failed: %r", error)

    def _span(self, event: EditEvent) -> AbstractContextManager[Any]:
        """An OpenTelemetry span around one publish, or a no-op without OpenTelemetry."""
        if _tracer is None:  # pragma: no cover
            return nullcontext()
        return _tracer.start_as_current_span(
            "kafka.publish",
            attributes={
                "messaging.system": "kafka",
                "messaging.destination.name": self.topic,
                "editwar.wiki": event.wiki,
            },
        )


class InMemoryPublisher(EventPublisher):
    """Keep published events in a list. Used by tests and local experiments."""

    def __init__(self) -> None:
        self.events: list[EditEvent] = []
        self.flushes = 0
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def publish(self, event: EditEvent) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        self.flushes += 1

    async def close(self) -> None:
        self.closed = True
