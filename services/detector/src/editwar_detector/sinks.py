"""Alert delivery (Observer pattern): the dispatcher sends each alert to every sink."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol

from editwar_domain import TOPIC_ALERTS, Alert

log = logging.getLogger("editwar.detector.sinks")


class MessageProducer(Protocol):
    """The part of aiokafka's AIOKafkaProducer that the detector uses."""

    async def send_and_wait(
        self, topic: str, value: bytes | None = None, key: bytes | None = None
    ) -> Any: ...


class AlertSink(ABC):
    """A destination for alerts.

    A critical sink is one whose failure must stop the offset commit, so the
    event is processed again after a restart.
    """

    critical: bool = False

    @abstractmethod
    async def send(self, alert: Alert) -> None:
        """Deliver one alert. Raise on failure."""


class KafkaAlertSink(AlertSink):
    """Publishes alerts to the wiki.alerts topic, keyed by alert id."""

    critical = True

    def __init__(self, producer: MessageProducer, topic: str = TOPIC_ALERTS) -> None:
        self.producer = producer
        self.topic = topic

    async def send(self, alert: Alert) -> None:
        await self.producer.send_and_wait(
            self.topic,
            value=alert.to_json().encode(),
            key=str(alert.id).encode(),
        )


class ConsoleAlertSink(AlertSink):
    """Writes alerts to the log, useful in docker compose and in the demo."""

    async def send(self, alert: Alert) -> None:
        log.info(
            "ALERT %s %s %s %s evidence=%s",
            alert.severity.value,
            alert.kind,
            alert.wiki,
            alert.title,
            alert.evidence,
        )


class AlertDispatcher:
    """Keeps the subscribed sinks and sends every alert to all of them."""

    def __init__(self) -> None:
        self.sinks: list[AlertSink] = []

    def subscribe(self, sink: AlertSink) -> None:
        if sink not in self.sinks:
            self.sinks.append(sink)

    def unsubscribe(self, sink: AlertSink) -> None:
        if sink in self.sinks:
            self.sinks.remove(sink)

    async def dispatch(self, alert: Alert) -> list[AlertSink]:
        """Send the alert to every sink. Return the sinks that failed.

        A failing sink is logged and does not stop the other sinks.
        """
        failed = []
        for sink in list(self.sinks):
            try:
                await sink.send(alert)
            except Exception:
                log.exception("sink %s failed for alert %s", type(sink).__name__, alert.id)
                failed.append(sink)
        return failed
