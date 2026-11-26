import json
import logging
import uuid

from editwar_detector.sinks import (
    AlertDispatcher,
    AlertSink,
    ConsoleAlertSink,
    KafkaAlertSink,
)
from editwar_domain import TOPIC_ALERTS, Alert, Severity


def make_alert():
    return Alert(
        rule_id=uuid.uuid4(),
        kind="burst",
        severity=Severity.MEDIUM,
        wiki="enwiki",
        title="Python",
        server_url="https://en.wikipedia.org",
        evidence={"edits": 10},
    )


class RecordingSink(AlertSink):
    def __init__(self):
        self.received = []

    async def send(self, alert):
        self.received.append(alert)


class FailingSink(AlertSink):
    async def send(self, alert):
        raise ConnectionError("down")


class FakeProducer:
    def __init__(self):
        self.sent = []

    async def send_and_wait(self, topic, value=None, key=None):
        self.sent.append((topic, key, value))


async def test_dispatch_reaches_every_sink():
    dispatcher = AlertDispatcher()
    first, second = RecordingSink(), RecordingSink()
    dispatcher.subscribe(first)
    dispatcher.subscribe(second)
    alert = make_alert()
    assert await dispatcher.dispatch(alert) == []
    assert first.received == [alert]
    assert second.received == [alert]


async def test_failing_sink_does_not_block_others(caplog):
    dispatcher = AlertDispatcher()
    failing, recording = FailingSink(), RecordingSink()
    dispatcher.subscribe(failing)
    dispatcher.subscribe(recording)
    with caplog.at_level(logging.ERROR, logger="editwar.detector.sinks"):
        failed = await dispatcher.dispatch(make_alert())
    assert failed == [failing]
    assert len(recording.received) == 1
    assert "FailingSink failed" in caplog.text


async def test_subscribe_twice_and_unsubscribe():
    dispatcher = AlertDispatcher()
    sink = RecordingSink()
    dispatcher.subscribe(sink)
    dispatcher.subscribe(sink)
    assert dispatcher.sinks == [sink]
    dispatcher.unsubscribe(sink)
    dispatcher.unsubscribe(sink)
    await dispatcher.dispatch(make_alert())
    assert sink.received == []


async def test_kafka_sink_publishes_json_keyed_by_alert_id():
    producer = FakeProducer()
    sink = KafkaAlertSink(producer)
    alert = make_alert()
    await sink.send(alert)
    topic, key, value = producer.sent[0]
    assert topic == TOPIC_ALERTS
    assert key == str(alert.id).encode()
    assert json.loads(value)["id"] == str(alert.id)
    assert sink.critical is True


async def test_console_sink_logs(caplog):
    sink = ConsoleAlertSink()
    with caplog.at_level(logging.INFO, logger="editwar.detector.sinks"):
        await sink.send(make_alert())
    assert "ALERT medium burst enwiki Python" in caplog.text
    assert sink.critical is False
