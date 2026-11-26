"""KafkaEventPublisher with a fake aiokafka producer, and InMemoryPublisher."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from editwar_domain import TOPIC_EDITS, EditEvent
from editwar_ingestor.publisher import InMemoryPublisher, KafkaEventPublisher


def make_event() -> EditEvent:
    return EditEvent(
        event_id="evt-1",
        wiki="eswiki",
        title="Guadalajara",
        user="Editor",
        is_bot=False,
        timestamp=datetime(2026, 11, 25, 18, 0, tzinfo=UTC),
        comment="ajuste",
        old_len=100,
        new_len=120,
        rev_id=2,
        old_rev_id=1,
        server_url="https://es.wikipedia.org",
    )


class FakeProducer:
    """Records the calls that KafkaEventPublisher makes on AIOKafkaProducer."""

    instances: list[FakeProducer] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.flushes = 0
        self.sent: list[tuple[str, bytes, bytes]] = []
        self.fail_start = False
        self.delivery_error: Exception | None = None
        FakeProducer.instances.append(self)

    async def start(self) -> None:
        if self.fail_start:
            raise ConnectionError("broker down")
        self.started = True

    async def send(self, topic: str, key: bytes, value: bytes) -> asyncio.Future[Any]:
        self.sent.append((topic, key, value))
        delivery: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        if self.delivery_error is not None:
            delivery.set_exception(self.delivery_error)
        else:
            delivery.set_result("metadata")
        return delivery

    async def flush(self) -> None:
        self.flushes += 1

    async def stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def reset_instances() -> None:
    FakeProducer.instances = []


async def test_start_configures_a_safe_producer() -> None:
    publisher = KafkaEventPublisher("kafka:9092", producer_factory=FakeProducer)
    await publisher.start()
    producer = FakeProducer.instances[0]
    assert producer.started
    assert producer.kwargs["bootstrap_servers"] == "kafka:9092"
    assert producer.kwargs["acks"] == "all"
    assert producer.kwargs["enable_idempotence"] is True
    assert producer.kwargs["linger_ms"] == 20
    assert publisher.topic == TOPIC_EDITS


async def test_publish_uses_partition_key_and_json() -> None:
    publisher = KafkaEventPublisher("kafka:9092", producer_factory=FakeProducer)
    await publisher.start()
    event = make_event()
    await publisher.publish(event)
    await asyncio.sleep(0)  # let the delivery callback run
    topic, key, value = FakeProducer.instances[0].sent[0]
    assert topic == "wiki.edits"
    assert key == b"eswiki:Guadalajara"
    assert EditEvent.from_json(value) == event
    assert publisher.delivery_errors == 0


async def test_delivery_error_is_counted() -> None:
    publisher = KafkaEventPublisher("kafka:9092", producer_factory=FakeProducer)
    await publisher.start()
    FakeProducer.instances[0].delivery_error = RuntimeError("not enough replicas")
    await publisher.publish(make_event())
    await asyncio.sleep(0)
    assert publisher.delivery_errors == 1


async def test_cancelled_delivery_is_ignored() -> None:
    publisher = KafkaEventPublisher("kafka:9092", producer_factory=FakeProducer)
    delivery: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    delivery.cancel()
    publisher._on_delivery(delivery)
    assert publisher.delivery_errors == 0


async def test_failed_start_stops_the_producer_and_raises() -> None:
    def failing_factory(**kwargs: Any) -> FakeProducer:
        producer = FakeProducer(**kwargs)
        producer.fail_start = True
        return producer

    publisher = KafkaEventPublisher("kafka:9092", producer_factory=failing_factory)
    with pytest.raises(ConnectionError):
        await publisher.start()
    assert FakeProducer.instances[0].stopped
    with pytest.raises(RuntimeError):
        await publisher.publish(make_event())


async def test_flush_and_close() -> None:
    publisher = KafkaEventPublisher("kafka:9092", producer_factory=FakeProducer)
    await publisher.flush()  # no producer yet: nothing happens
    await publisher.close()
    await publisher.start()
    producer = FakeProducer.instances[0]
    await publisher.flush()
    await publisher.close()
    assert producer.flushes == 2
    assert producer.stopped


async def test_in_memory_publisher() -> None:
    publisher = InMemoryPublisher()
    await publisher.start()
    await publisher.publish(make_event())
    await publisher.flush()
    await publisher.close()
    assert publisher.started and publisher.closed
    assert publisher.events == [make_event()]
    assert publisher.flushes == 1
