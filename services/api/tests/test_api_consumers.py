"""AlertConsumer, LiveConsumer and the reconnect loop, with fake Kafka consumers."""

from __future__ import annotations

import json

import pytest
from aiokafka import AIOKafkaConsumer
from api_fakes import FakeClock, FakeConsumer, FakeMessage, FakeWebSocket, make_alert, make_edit
from api_fakes import make_revert as make_revert_event

from editwar_api.consumers import AlertConsumer, LiveConsumer, kafka_factory, run_consumer
from editwar_api.repositories import AlertRepository
from editwar_api.stats import StatsService
from editwar_api.websocket import WebSocketHub
from editwar_domain import TOPIC_ALERTS, TOPIC_EDITS, TOPIC_REVERTS


class StopTest(Exception):
    """Raised by a fake factory to leave the endless consumer loop."""


def factory_from(consumers: list[FakeConsumer]):  # type: ignore[no-untyped-def]
    """A consumer factory that hands out the given fakes, then stops the loop."""
    remaining = list(consumers)

    def create() -> FakeConsumer:
        if not remaining:
            raise StopTest
        return remaining.pop(0)

    return create


async def connected_hub() -> tuple[WebSocketHub, FakeWebSocket]:
    hub = WebSocketHub(edits_per_second=100, clock=FakeClock())
    client = FakeWebSocket()
    await hub.connect(client)
    return hub, client


async def test_alert_is_stored_without_broadcast(alert_repo: AlertRepository) -> None:
    hub, client = await connected_hub()
    consumer = AlertConsumer(alert_repo, hub)
    alert = make_alert()

    assert await consumer.handle(FakeMessage(TOPIC_ALERTS, alert.to_json().encode())) is True

    assert await alert_repo.get(alert.id) == alert
    assert client.sent == []


async def test_duplicate_alert_is_ignored(alert_repo: AlertRepository) -> None:
    hub, client = await connected_hub()
    consumer = AlertConsumer(alert_repo, hub)
    message = FakeMessage(TOPIC_ALERTS, make_alert().to_json().encode())

    assert await consumer.handle(message) is True
    assert await consumer.handle(message) is False

    assert len(await alert_repo.list()) == 1
    assert client.sent == []


async def test_empty_alert_message_is_ignored(alert_repo: AlertRepository) -> None:
    hub, client = await connected_hub()
    assert await AlertConsumer(alert_repo, hub).handle(FakeMessage(TOPIC_ALERTS, None)) is False
    assert client.sent == []


async def test_live_consumer_records_and_broadcasts() -> None:
    hub, client = await connected_hub()
    stats = StatsService(clock=FakeClock())
    consumer = LiveConsumer(stats, hub)

    await consumer.handle(FakeMessage(TOPIC_EDITS, make_edit().to_json().encode()))
    await consumer.handle(FakeMessage(TOPIC_REVERTS, make_revert_event().to_json().encode()))
    await consumer.handle(FakeMessage(TOPIC_EDITS, None))
    await consumer.handle(FakeMessage("other.topic", b"{}"))

    assert (stats.total_edits, stats.total_reverts) == (1, 1)
    edit, revert = (json.loads(text) for text in client.sent)
    assert edit["type"] == "edit"
    assert edit["data"]["diff_url"] == "https://en.wikipedia.org/w/index.php?diff=2&oldid=1"
    assert edit["data"]["page_url"].endswith("/wiki/Python_(programming_language)")
    assert revert["type"] == "revert"
    assert revert["data"]["user"] == "Bob"
    assert revert["data"]["page_url"].endswith("/wiki/Python_(programming_language)")


async def test_run_consumer_retries_and_skips_bad_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handled: list[str] = []
    states: list[bool] = []

    async def handle(message: FakeMessage) -> None:
        if message.value == b"bad":
            raise ValueError("cannot parse")
        handled.append(message.topic)

    down = FakeConsumer(fail_start=True)
    up = FakeConsumer(
        [FakeMessage("t1", b"ok"), FakeMessage("t2", b"bad"), FakeMessage("t3", b"ok")],
        fail_stop=True,
    )
    with pytest.raises(StopTest):
        await run_consumer("test", factory_from([down, up]), handle, 0.001, states.append)

    assert handled == ["t1", "t3"]
    assert down.stopped and up.stopped
    assert states == [False, True, False]
    assert "kafka consumer test failed: kafka is down" in caplog.text
    assert "could not process a message" in caplog.text


async def test_alert_consumer_run_updates_connected(alert_repo: AlertRepository) -> None:
    hub, client = await connected_hub()
    consumer = AlertConsumer(alert_repo, hub)
    message = FakeMessage(TOPIC_ALERTS, make_alert().to_json().encode())
    with pytest.raises(StopTest):
        await consumer.run(factory_from([FakeConsumer([message])]), retry_delay=0.001)
    assert consumer.connected is False
    assert len(await alert_repo.list()) == 1


async def test_live_consumer_run() -> None:
    hub, client = await connected_hub()
    consumer = LiveConsumer(StatsService(clock=FakeClock()), hub)
    message = FakeMessage(TOPIC_EDITS, make_edit().to_json().encode())
    with pytest.raises(StopTest):
        await consumer.run(factory_from([FakeConsumer([message])]), retry_delay=0.001)
    assert len(client.sent) == 1


async def test_default_factories_build_kafka_consumers() -> None:
    alert_consumer = AlertConsumer.default_factory("kafka:9092", "api")()
    live_consumer = LiveConsumer.default_factory("kafka:9092")()
    assert isinstance(alert_consumer, AIOKafkaConsumer)
    assert isinstance(live_consumer, AIOKafkaConsumer)
    assert alert_consumer._group_id == "api-alerts"
    assert live_consumer._group_id is None
    assert kafka_factory("kafka:9092", ["x"])() is not None


async def test_live_consumer_broadcasts_alerts() -> None:
    hub, client = await connected_hub()
    consumer = LiveConsumer(StatsService(clock=FakeClock()), hub)
    alert = make_alert()
    await consumer.handle(FakeMessage(TOPIC_ALERTS, alert.to_json().encode()))
    assert json.loads(client.sent[0]) == {"type": "alert", "data": alert.to_dict()}
