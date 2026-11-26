"""DetectorService: consumes wiki.edits, runs the engine and publishes the outputs.

Delivery is at least once. The service commits the offsets of a batch only
after every event of the batch was processed and its revert and alerts were
sent. If the pod dies before the commit, Kafka gives the same events to the
next pod, so no event is lost (some can be processed twice).

The windows live in memory. After a restart they fill again from new events.

Metrics (see editwar_detector.metrics) are recorded next to the /healthz
counters. After each batch the loop also computes the consumer lag of this pod
and caches it for the consumer_lag gauge.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from aiokafka.errors import KafkaError

from editwar_detector.engine import DetectionEngine, ProcessResult
from editwar_detector.metrics import DetectorMetrics
from editwar_detector.rule_provider import RuleProvider
from editwar_detector.sinks import AlertDispatcher, KafkaAlertSink
from editwar_domain import TOPIC_REVERTS, EditEvent

log = logging.getLogger("editwar.detector.service")

_tracer: Any
try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("editwar.detector")
except ImportError:  # pragma: no cover - opentelemetry comes with editwar-domain[telemetry]
    _tracer = None


class KafkaClient(Protocol):
    """A Kafka client that can connect and disconnect."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class KafkaConsumer(KafkaClient, Protocol):
    """The part of aiokafka's AIOKafkaConsumer that the service uses."""

    async def getmany(
        self, *partitions: Any, timeout_ms: int = 0, max_records: Any = None
    ) -> Any: ...
    async def commit(self, offsets: Any = None) -> None: ...
    def assignment(self) -> Any: ...
    def highwater(self, partition: Any) -> int | None: ...
    async def position(self, partition: Any) -> int: ...


class KafkaProducer(KafkaClient, Protocol):
    """The part of aiokafka's AIOKafkaProducer that the service uses."""

    async def send_and_wait(
        self, topic: str, value: bytes | None = None, key: bytes | None = None
    ) -> Any: ...


class DeliveryError(RuntimeError):
    """A critical output was not sent. The batch is not committed."""


@dataclass
class DetectorStats:
    """Counters shown by GET /healthz."""

    processed: int = 0
    reverts: int = 0
    alerts: int = 0
    skipped: int = 0
    last_offsets: dict[str, int] = field(default_factory=dict)  # "topic-partition" -> offset


class DetectorService:
    """Connects Kafka, the rule provider, the engine and the alert dispatcher."""

    def __init__(
        self,
        engine: DetectionEngine,
        dispatcher: AlertDispatcher,
        rule_provider: RuleProvider,
        consumer_factory: Callable[[], KafkaConsumer],
        producer_factory: Callable[[], KafkaProducer],
        *,
        refresh_seconds: float = 30,
        prune_interval_seconds: float = 60,
        retry_initial_seconds: float = 1,
        retry_max_seconds: float = 30,
        poll_timeout_ms: int = 1000,
        max_records: int = 500,
        metrics: DetectorMetrics | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.engine = engine
        self.dispatcher = dispatcher
        self.rule_provider = rule_provider
        self.consumer_factory = consumer_factory
        self.producer_factory = producer_factory
        self.refresh_seconds = refresh_seconds
        self.prune_interval_seconds = prune_interval_seconds
        self.retry_initial_seconds = retry_initial_seconds
        self.retry_max_seconds = retry_max_seconds
        self.poll_timeout_ms = poll_timeout_ms
        self.max_records = max_records
        self.metrics = metrics or DetectorMetrics()
        self.metrics.window_count = engine.window_count
        self._clock = clock
        self.consumer: KafkaConsumer | None = None
        self.producer: KafkaProducer | None = None
        self.connected = False
        self.stats_data = DetectorStats()
        self._stopping = asyncio.Event()
        self._last_prune: datetime | None = None

    async def run(self) -> None:
        """Load rules, connect to Kafka (with retries) and consume until stop()."""
        self.engine.reload_rules(await self.rule_provider.fetch())
        producer = await self._connect(self.producer_factory, "producer")
        if producer is None:
            return
        consumer = await self._connect(self.consumer_factory, "consumer")
        if consumer is None:
            await producer.stop()
            return
        self.producer, self.consumer = producer, consumer
        kafka_sink = KafkaAlertSink(producer)
        self.dispatcher.subscribe(kafka_sink)
        self.connected = True
        refresher = asyncio.create_task(self._refresh_rules())
        try:
            while not self._stopping.is_set():
                batch = await consumer.getmany(
                    timeout_ms=self.poll_timeout_ms, max_records=self.max_records
                )
                await self.process_batch(batch)
                await self._update_lag(consumer)
        finally:
            self.connected = False
            self.metrics.consumer_lag = None  # this pod no longer reads
            refresher.cancel()
            with suppress(asyncio.CancelledError):
                await refresher
            self.dispatcher.unsubscribe(kafka_sink)
            await consumer.stop()
            await producer.stop()
            log.info("detector stopped")

    def stop(self) -> None:
        """Ask run() to finish the current batch, commit it and exit."""
        log.info("stop requested")
        self._stopping.set()

    async def process_batch(self, batch: Mapping[Any, Sequence[Any]]) -> None:
        """Handle every record of a getmany() batch, then commit the batch."""
        offsets: dict[Any, int] = {}
        for partition, records in batch.items():
            for record in records:
                await self.handle_record(record)
                offsets[partition] = record.offset + 1
        if offsets:
            await self._commit(offsets)

    async def handle_record(self, record: Any) -> None:
        """Decode one Kafka record. A record that does not parse is logged and skipped."""
        try:
            event = EditEvent.from_json(record.value)
        except (ValueError, KeyError, TypeError) as error:
            self.stats_data.skipped += 1
            log.warning("skipping bad record at offset %s: %s", record.offset, error)
            return
        await self.handle(event)

    async def handle(self, event: EditEvent) -> ProcessResult:
        """Process one edit and send its revert and alerts. Traced when OpenTelemetry is on."""
        started = self._clock()
        if _tracer is None:  # pragma: no cover
            result = await self._handle(event)
        else:
            with _tracer.start_as_current_span("detector.handle") as span:
                span.set_attribute("editwar.wiki", event.wiki)
                result = await self._handle(event)
                span.set_attribute("editwar.revert", result.revert is not None)
                span.set_attribute("editwar.alerts", len(result.alerts))
        self.metrics.processing_time(self._clock() - started)
        return result

    async def _handle(self, event: EditEvent) -> ProcessResult:
        if self.producer is None:
            raise RuntimeError("the producer is not connected")
        result = self.engine.process(event)
        self.stats_data.processed += 1
        self.metrics.edit_processed()
        if result.revert is not None:
            await self.producer.send_and_wait(
                TOPIC_REVERTS,
                value=result.revert.to_json().encode(),
                key=result.revert.partition_key().encode(),
            )
            self.stats_data.reverts += 1
            self.metrics.revert(result.revert.reason)
        for alert in result.alerts:
            failed = await self.dispatcher.dispatch(alert)
            if any(sink.critical for sink in failed):
                raise DeliveryError(f"alert {alert.id} was not published")
            self.stats_data.alerts += 1
            self.metrics.alert(alert.kind, alert.severity.value)
        self._maybe_prune(event.timestamp)
        return result

    def stats(self) -> dict[str, Any]:
        """Numbers for GET /healthz."""
        return {
            "status": "ok" if self.connected else "starting",
            "processed": self.stats_data.processed,
            "reverts": self.stats_data.reverts,
            "alerts": self.stats_data.alerts,
            "skipped": self.stats_data.skipped,
            "rules_loaded": self.engine.rule_count(),
            "windows": self.engine.window_count(),
            "last_offsets": dict(self.stats_data.last_offsets),
        }

    async def _commit(self, offsets: dict[Any, int]) -> None:
        if self.consumer is None:
            raise RuntimeError("the consumer is not connected")
        try:
            await self.consumer.commit(offsets)
        except KafkaError as error:
            # Usually a rebalance. Kafka gives these events to the new owner again.
            log.warning("commit failed (%s), the events will be processed again", error)
            return
        for partition, offset in offsets.items():
            name = f"{partition.topic}-{partition.partition}"
            self.stats_data.last_offsets[name] = offset - 1

    async def _update_lag(self, consumer: KafkaConsumer) -> None:
        """Cache the messages this pod is behind: high-water mark minus position.

        Only partitions with a known high-water mark count. The mark comes with
        a fetch answer, so their position is known too and position() returns
        at once instead of waiting for an offset reset.
        """
        lag = 0
        try:
            for partition in consumer.assignment():
                highwater = consumer.highwater(partition)
                if highwater is None:
                    continue
                lag += max(0, highwater - await consumer.position(partition))
        except (KafkaError, AssertionError) as error:
            # A rebalance took a partition away. Keep the last value until the next batch.
            log.debug("consumer lag not updated: %r", error)
            return
        self.metrics.consumer_lag = lag

    def _maybe_prune(self, now: datetime) -> None:
        """Every prune_interval_seconds of event time, free old windows."""
        if self._last_prune is None:
            self._last_prune = now
            return
        if (now - self._last_prune).total_seconds() >= self.prune_interval_seconds:
            freed = self.engine.prune(now)
            self._last_prune = now
            log.debug("pruned %s windows, %s left", freed, self.engine.window_count())

    async def _connect[C: KafkaClient](self, factory: Callable[[], C], name: str) -> C | None:
        """Create and start a Kafka client, retrying with backoff until stop()."""
        delay = self.retry_initial_seconds
        while not self._stopping.is_set():
            client = factory()
            try:
                await client.start()
            except Exception as error:
                log.warning("%s cannot connect to Kafka (%s), retry in %.1fs", name, error, delay)
                with suppress(Exception):
                    await client.stop()
            else:
                log.info("%s connected to Kafka", name)
                return client
            if await self._wait_for_stop(delay):
                break
            delay = min(delay * 2, self.retry_max_seconds)
        return None

    async def _refresh_rules(self) -> None:
        """Reload the rules every refresh_seconds until stop()."""
        while not await self._wait_for_stop(self.refresh_seconds):
            try:
                self.engine.reload_rules(await self.rule_provider.fetch())
            except Exception:
                log.exception("rule reload failed")

    async def _wait_for_stop(self, seconds: float) -> bool:
        """Sleep up to `seconds`. Return True when stop() was called."""
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True
