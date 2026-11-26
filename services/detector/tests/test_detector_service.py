import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from aiokafka.errors import CommitFailedError, KafkaConnectionError
from aiokafka.structs import TopicPartition

from editwar_detector import service as service_module
from editwar_detector.engine import DetectionEngine
from editwar_detector.service import DeliveryError, DetectorService
from editwar_detector.sinks import AlertDispatcher, AlertSink
from editwar_domain import (
    TOPIC_ALERTS,
    TOPIC_EDITS,
    TOPIC_REVERTS,
    DetectionRule,
    RuleKind,
)

TP = TopicPartition(TOPIC_EDITS, 0)


class FakeRuleProvider:
    def __init__(self, rules):
        self.rules = rules
        self.calls = 0

    async def fetch(self):
        self.calls += 1
        return list(self.rules)


class FakeProducer:
    """Records the calls in a log shared with the consumer, to check the order."""

    def __init__(self, log, fail_starts=0, fail_send=False):
        self.log = log
        self.fail_starts = fail_starts
        self.fail_send = fail_send

    async def start(self):
        if self.fail_starts > 0:
            self.fail_starts -= 1
            raise KafkaConnectionError("no broker")
        self.log.append(("producer.start",))

    async def stop(self):
        self.log.append(("producer.stop",))

    async def send_and_wait(self, topic, value=None, key=None):
        if self.fail_send and topic == TOPIC_ALERTS:
            raise KafkaConnectionError("broker gone")
        self.log.append(("send", topic, key))


class FakeConsumer:
    def __init__(self, log, batches, service=None, commit_error=None):
        self.log = log
        self.batches = list(batches)
        self.service = service
        self.commit_error = commit_error
        self.highwaters = {}  # TopicPartition -> high-water mark (None = not fetched yet)
        self.positions = {}  # TopicPartition -> next offset to read

    async def start(self):
        self.log.append(("consumer.start",))

    async def stop(self):
        self.log.append(("consumer.stop",))

    async def getmany(self, *partitions, timeout_ms=0, max_records=None):
        if self.batches:
            return self.batches.pop(0)
        self.service.stop()
        return {}

    async def commit(self, offsets=None):
        if self.commit_error is not None:
            raise self.commit_error
        self.log.append(("commit", {tp.partition: off for tp, off in offsets.items()}))

    def assignment(self):
        return set(self.highwaters)

    def highwater(self, partition):
        return self.highwaters[partition]

    async def position(self, partition):
        position = self.positions[partition]
        if isinstance(position, Exception):
            raise position
        return position


def rules():
    return [
        DetectionRule(
            name="war", kind=RuleKind.REVERT_WAR, window_seconds=600, threshold=2, min_users=2
        )
    ]


def record(offset, event):
    return SimpleNamespace(offset=offset, value=event.to_json().encode())


def make_service(log, batches=(), rule_list=None, fail_send=False, **kwargs):
    producer = FakeProducer(log, fail_send=fail_send)
    consumer = FakeConsumer(log, batches)
    service = DetectorService(
        engine=DetectionEngine(),
        dispatcher=AlertDispatcher(),
        rule_provider=FakeRuleProvider(rules() if rule_list is None else rule_list),
        consumer_factory=lambda: consumer,
        producer_factory=lambda: producer,
        retry_initial_seconds=0.001,
        poll_timeout_ms=1,
        **kwargs,
    )
    consumer.service = service
    return service, producer, consumer


async def test_handle_publishes_revert_and_alert(make_event, clock):
    log = []
    service, producer, _ = make_service(log)
    service.engine.reload_rules(rules())
    service.producer = producer

    await service.handle(make_event(user="A", comment="rv"))
    clock.advance(1)
    result = await service.handle(make_event(user="B", comment="Reverted edits by A"))

    assert result.revert is not None
    assert [entry[1] for entry in log] == [TOPIC_REVERTS, TOPIC_REVERTS]
    assert log[0][2] == b"enwiki:Python (programming language)"
    stats = service.stats()
    assert stats["processed"] == 2
    assert stats["reverts"] == 2
    assert stats["alerts"] == 1
    assert stats["rules_loaded"] == 1
    assert stats["status"] == "starting"


async def test_handle_without_producer_fails(make_event):
    service, _, _ = make_service([])
    with pytest.raises(RuntimeError):
        await service.handle(make_event())


async def test_run_commits_after_outputs_are_sent(make_event, clock):
    log = []
    first = make_event(user="A", comment="rv")
    clock.advance(1)
    second = make_event(user="B", comment="rv")
    batches = [{TP: [record(10, first), record(11, second)]}]
    service, _, _ = make_service(log, batches)

    await service.run()

    sends = [i for i, entry in enumerate(log) if entry[0] == "send"]
    commits = [i for i, entry in enumerate(log) if entry[0] == "commit"]
    assert len(sends) == 3  # two reverts and one alert
    assert [log[i][1] for i in sends] == [TOPIC_REVERTS, TOPIC_REVERTS, TOPIC_ALERTS]
    assert commits == [max(sends) + 1]  # one commit, after every send
    assert log[commits[0]] == ("commit", {0: 12})  # next offset to read
    assert log[-2:] == [("consumer.stop",), ("producer.stop",)]
    assert service.stats()["last_offsets"] == {f"{TOPIC_EDITS}-0": 11}
    assert service.dispatcher.sinks == []  # the Kafka sink is removed on exit


async def test_bad_record_is_skipped_and_committed(caplog):
    log = []
    batches = [{TP: [SimpleNamespace(offset=5, value=b"{not json")]}]
    service, _, _ = make_service(log, batches)
    with caplog.at_level(logging.WARNING, logger="editwar.detector.service"):
        await service.run()
    assert ("commit", {0: 6}) in log
    assert service.stats()["skipped"] == 1
    assert "skipping bad record" in caplog.text


async def test_alert_publish_failure_stops_before_commit(make_event, clock):
    log = []
    first = make_event(user="A", comment="rv")
    clock.advance(1)
    second = make_event(user="B", comment="rv")
    batches = [{TP: [record(1, first), record(2, second)]}]
    service, _, _ = make_service(log, batches, fail_send=True)

    with pytest.raises(DeliveryError):
        await service.run()
    assert not any(entry[0] == "commit" for entry in log)
    assert ("consumer.stop",) in log


async def test_non_critical_sink_failure_does_not_stop(make_event, clock):
    class Broken(AlertSink):
        async def send(self, alert):
            raise RuntimeError("console broken")

    log = []
    service, producer, _ = make_service(log)
    service.dispatcher.subscribe(Broken())
    service.engine.reload_rules(rules())
    service.producer = producer
    await service.handle(make_event(user="A", comment="rv"))
    clock.advance(1)
    result = await service.handle(make_event(user="B", comment="rv"))
    assert len(result.alerts) == 1
    assert service.stats()["alerts"] == 1


async def test_commit_failure_is_logged(make_event, caplog):
    log = []
    service, producer, consumer = make_service(log)
    consumer.commit_error = CommitFailedError("rebalance")
    service.producer, service.consumer = producer, consumer
    with caplog.at_level(logging.WARNING, logger="editwar.detector.service"):
        await service.process_batch({TP: [record(3, make_event())]})
    assert "commit failed" in caplog.text
    assert service.stats()["last_offsets"] == {}


async def test_commit_without_consumer_fails():
    service, _, _ = make_service([])
    with pytest.raises(RuntimeError):
        await service._commit({TP: 1})


async def test_empty_batch_does_not_commit():
    log = []
    service, _, consumer = make_service(log)
    service.consumer = consumer
    await service.process_batch({})
    assert log == []


async def test_connect_retries_until_kafka_is_up(caplog):
    log = []
    service, producer, _ = make_service(log)
    producer.fail_starts = 2
    with caplog.at_level(logging.WARNING, logger="editwar.detector.service"):
        await service.run()
    assert "cannot connect to Kafka" in caplog.text
    assert log.count(("producer.start",)) == 1
    # The failed attempts also called stop() to clean up.
    assert log.count(("producer.stop",)) == 3


async def test_stop_during_retry_exits_without_consuming():
    log = []
    service, producer, _ = make_service(log)
    producer.fail_starts = 1_000
    service.retry_initial_seconds = 0.01

    task = asyncio.create_task(service.run())
    await asyncio.sleep(0.05)
    service.stop()
    await asyncio.wait_for(task, timeout=1)
    assert ("consumer.start",) not in log


async def test_consumer_failure_stops_the_producer():
    log = []
    service, _, consumer = make_service(log)

    async def broken_start():
        service.stop()
        raise KafkaConnectionError("no broker")

    consumer.start = broken_start
    await service.run()
    assert log[-1] == ("producer.stop",)
    assert service.consumer is None


async def test_rules_are_refreshed_while_running():
    log = []
    service, _, consumer = make_service(log, refresh_seconds=0.01)
    consumer.batches = []

    async def slow_getmany(*partitions, timeout_ms=0, max_records=None):
        await asyncio.sleep(0.05)
        service.stop()
        return {}

    consumer.getmany = slow_getmany
    await service.run()
    assert service.rule_provider.calls >= 2


async def test_rule_reload_error_is_logged(caplog):
    service, _, _ = make_service([], refresh_seconds=0.01)

    def broken_reload(rules):
        service.stop()
        raise RuntimeError("bad rules")

    service.engine.reload_rules = broken_reload
    with caplog.at_level(logging.ERROR, logger="editwar.detector.service"):
        await service._refresh_rules()
    assert "rule reload failed" in caplog.text


async def test_windows_are_pruned_by_event_time(make_event, clock):
    service, producer, _ = make_service([], prune_interval_seconds=60)
    service.producer = producer
    await service.handle(make_event(title="Old"))
    clock.advance(30)
    await service.handle(make_event(title="Mid"))
    assert service.engine.window_count() == 2

    clock.advance(3600)
    await service.handle(make_event(title="New"))
    assert service.engine.window_count() == 1


async def test_handle_sets_span_attributes(make_event, monkeypatch):
    attributes = {}

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def set_attribute(self, key, value):
            attributes[key] = value

    class FakeTracer:
        def start_as_current_span(self, name):
            attributes["name"] = name
            return FakeSpan()

    monkeypatch.setattr(service_module, "_tracer", FakeTracer())
    service, producer, _ = make_service([])
    service.producer = producer
    await service.handle(make_event(comment="rv"))
    assert attributes == {
        "name": "detector.handle",
        "editwar.wiki": "enwiki",
        "editwar.revert": True,
        "editwar.alerts": 0,
    }


def test_stats_are_json_serializable():
    service, _, _ = make_service([])
    assert json.loads(json.dumps(service.stats()))["windows"] == 0
