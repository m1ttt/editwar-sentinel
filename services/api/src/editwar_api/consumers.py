"""Kafka consumers of the api.

- AlertConsumer reads TOPIC_ALERTS with the group "<KAFKA_GROUP_ID>-alerts"
  ("api-alerts" by default). The replicas share the work: each alert is stored
  once, then sent to the dashboards.
- LiveConsumer reads TOPIC_EDITS, TOPIC_REVERTS and TOPIC_ALERTS for the live
  view and the stats. It uses no consumer group and starts at the latest offset,
  so every api replica sees every message and nothing is committed. For reverts
  and alerts it also looks up the article coordinates and sends a "geo" message.

Both consumers run as background tasks. When Kafka is down they log a warning
and try again with a growing delay; the api keeps answering HTTP requests.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer
from opentelemetry import trace

from editwar_api.geo import GeoPoint, GeoService
from editwar_api.repositories import AlertRepository
from editwar_api.stats import StatsService, page_url
from editwar_api.websocket import WebSocketHub
from editwar_domain import TOPIC_ALERTS, TOPIC_EDITS, TOPIC_REVERTS, Alert, EditEvent, RevertEvent

logger = logging.getLogger("editwar.api")
tracer = trace.get_tracer("editwar.api")

MAX_RETRY_DELAY_SECONDS = 30.0


class Message(Protocol):
    """The fields of an aiokafka ConsumerRecord that the handlers read."""

    topic: str
    value: bytes | None


class KafkaConsumer(Protocol):
    """The part of AIOKafkaConsumer that run_consumer uses. Tests use fakes."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def __aiter__(self) -> AsyncIterator[Any]: ...


ConsumerFactory = Callable[[], KafkaConsumer]


def kafka_factory(bootstrap_servers: str, topics: list[str], **options: Any) -> ConsumerFactory:
    """Return a function that creates a new AIOKafkaConsumer for the topics."""

    def create() -> KafkaConsumer:
        return AIOKafkaConsumer(*topics, bootstrap_servers=bootstrap_servers, **options)

    return create


async def run_consumer(
    name: str,
    factory: ConsumerFactory,
    handle: Callable[[Any], Awaitable[None]],
    retry_delay: float = 1.0,
    on_state: Callable[[bool], None] | None = None,
) -> None:
    """Consume messages forever and reconnect when Kafka fails.

    A message that fails in handle() is logged and skipped, so one bad message
    does not stop the consumer.
    """
    delay = retry_delay
    while True:
        consumer = factory()
        try:
            await consumer.start()
            logger.info("kafka consumer %s connected", name)
            if on_state:
                on_state(True)
            delay = retry_delay
            async for message in consumer:
                try:
                    await handle(message)
                except Exception:
                    logger.exception("kafka consumer %s could not process a message", name)
        except Exception as error:
            logger.warning("kafka consumer %s failed: %s. Retry in %.0f s", name, error, delay)
        finally:
            if on_state:
                on_state(False)
            try:
                await consumer.stop()
            except Exception:
                logger.debug("kafka consumer %s did not stop cleanly", name)
        await asyncio.sleep(delay)
        delay = min(delay * 2, MAX_RETRY_DELAY_SECONDS)


class AlertConsumer:
    """Stores the alerts from the detector.

    All api replicas share one consumer group, so each alert is stored once.
    LiveConsumer sends the alert to the dashboards of every replica.
    """

    def __init__(self, alerts: AlertRepository, hub: WebSocketHub) -> None:
        self._alerts = alerts
        self._hub = hub
        self.connected = False

    def _set_connected(self, value: bool) -> None:
        self.connected = value

    async def handle(self, message: Message) -> bool:
        """Store one alert message. Returns False for a duplicate alert."""
        if message.value is None:
            return False
        with tracer.start_as_current_span("process alert", kind=trace.SpanKind.CONSUMER) as span:
            alert = Alert.from_json(message.value)
            span.set_attribute("editwar.alert_id", str(alert.id))
            stored = await self._alerts.create(alert)
            if stored is None:
                logger.info("duplicate alert %s ignored", alert.id)
                return False
            logger.info(
                "alert %s stored: %s on %s %s",
                alert.id,
                alert.kind,
                alert.wiki,
                alert.title,
                extra={
                    "alert_id": str(alert.id),
                    "alert_kind": alert.kind,
                    "wiki": alert.wiki,
                    "article": alert.title,
                    "severity": alert.severity.value,
                },
            )
            return True

    async def _handle_message(self, message: Message) -> None:
        await self.handle(message)

    async def run(self, factory: ConsumerFactory, retry_delay: float = 1.0) -> None:
        await run_consumer(
            "alerts", factory, self._handle_message, retry_delay, self._set_connected
        )

    @staticmethod
    def default_factory(bootstrap_servers: str, group_id: str) -> ConsumerFactory:
        return kafka_factory(
            bootstrap_servers,
            [TOPIC_ALERTS],
            group_id=f"{group_id}-alerts",
            auto_offset_reset="earliest",
        )


class LiveConsumer:
    """Feeds the stats and the live view with edits, reverts and alerts.

    It has no consumer group, so every api replica reads every message.
    """

    def __init__(
        self, stats: StatsService, hub: WebSocketHub, geo: GeoService | None = None
    ) -> None:
        self._stats = stats
        self._hub = hub
        self._geo = geo
        self._geo_tasks: set[asyncio.Task[None]] = set()
        self.connected = False

    def _set_connected(self, value: bool) -> None:
        self.connected = value

    async def handle(self, message: Message) -> None:
        if message.value is None:
            return
        if message.topic == TOPIC_EDITS:
            edit = EditEvent.from_json(message.value)
            self._stats.record_edit(edit)
            data = edit.to_dict() | {"page_url": edit.page_url(), "diff_url": edit.diff_url()}
            await self._hub.broadcast_edit(data)
        elif message.topic == TOPIC_REVERTS:
            revert = RevertEvent.from_json(message.value)
            self._stats.record_revert(revert)
            data = revert.to_dict() | {"page_url": page_url(revert.server_url, revert.title)}
            await self._hub.broadcast({"type": "revert", "data": data})
            self._locate_later(
                "revert", revert.server_url, revert.wiki, revert.title, data["timestamp"]
            )
        elif message.topic == TOPIC_ALERTS:
            alert = Alert.from_json(message.value)
            data = alert.to_dict()
            await self._hub.broadcast({"type": "alert", "data": data})
            self._locate_later(
                "alert",
                alert.server_url,
                alert.wiki,
                alert.title,
                data["created_at"],
                severity=alert.severity.value,
                alert_kind=alert.kind,
            )

    def _locate_later(
        self,
        kind: str,
        server_url: str,
        wiki: str,
        title: str,
        timestamp: str,
        severity: str | None = None,
        alert_kind: str | None = None,
    ) -> None:
        """Look up the coordinates in the background, so the live feed never waits."""
        if self._geo is None:
            return
        task = asyncio.create_task(
            self.locate(kind, server_url, wiki, title, timestamp, severity, alert_kind)
        )
        self._geo_tasks.add(task)
        task.add_done_callback(self._geo_tasks.discard)

    async def locate(
        self,
        kind: str,
        server_url: str,
        wiki: str,
        title: str,
        timestamp: str,
        severity: str | None = None,
        alert_kind: str | None = None,
    ) -> None:
        """Send a "geo" message when the article has coordinates."""
        if self._geo is None:
            return
        found = await self._geo.coordinates(server_url, title)
        if found is None:
            return
        point = GeoPoint(
            kind=kind,
            wiki=wiki,
            title=title,
            lat=found[0],
            lon=found[1],
            page_url=page_url(server_url, title),
            timestamp=timestamp,
            severity=severity,
            alert_kind=alert_kind,
        )
        self._geo.add(point)
        await self._hub.broadcast({"type": "geo", "data": point.to_dict()})

    async def drain(self) -> None:
        """Wait for the pending coordinate lookups (used by tests and shutdown)."""
        await asyncio.gather(*self._geo_tasks, return_exceptions=True)

    async def run(self, factory: ConsumerFactory, retry_delay: float = 1.0) -> None:
        await run_consumer("live", factory, self.handle, retry_delay, self._set_connected)

    @staticmethod
    def default_factory(bootstrap_servers: str) -> ConsumerFactory:
        return kafka_factory(
            bootstrap_servers,
            [TOPIC_EDITS, TOPIC_REVERTS, TOPIC_ALERTS],
            group_id=None,
            auto_offset_reset="latest",
        )
