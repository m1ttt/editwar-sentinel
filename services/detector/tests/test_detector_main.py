import asyncio
import signal

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from editwar_detector import main as main_module
from editwar_detector.service import DetectorService
from editwar_detector.sinks import ConsoleAlertSink


async def test_build_service_reads_environment(monkeypatch):
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    monkeypatch.setenv("KAFKA_GROUP_ID", "detector-test")
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("RULES_REFRESH_SECONDS", "7")

    service = main_module.build_service()

    assert isinstance(service, DetectorService)
    assert service.refresh_seconds == 7
    assert service.rule_provider.url == "http://api:8000/api/rules"
    assert isinstance(service.dispatcher.sinks[0], ConsoleAlertSink)
    # The factories only build the clients. Nothing connects here.
    consumer = service.consumer_factory()
    producer = service.producer_factory()
    assert isinstance(consumer, AIOKafkaConsumer)
    assert isinstance(producer, AIOKafkaProducer)
    assert consumer._enable_auto_commit is False
    assert consumer._group_id == "detector-test"
    await service.rule_provider.aclose()


async def test_run_detector_starts_health_and_handles_sigterm(monkeypatch):
    monkeypatch.setenv("HEALTH_PORT", "0")
    seen = {}

    async def fake_run(self):
        seen["run"] = True
        signal.raise_signal(signal.SIGTERM)  # the handler calls service.stop()
        await self._stopping.wait()

    monkeypatch.setattr(DetectorService, "run", fake_run)
    await asyncio.wait_for(main_module.run_detector(), timeout=2)
    assert seen == {"run": True}
    loop = asyncio.get_running_loop()
    loop.remove_signal_handler(signal.SIGTERM)
    loop.remove_signal_handler(signal.SIGINT)


def test_main_configures_telemetry_and_runs(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "configure_telemetry", lambda name: calls.append(name))

    async def fake_run_detector():
        calls.append("run")

    monkeypatch.setattr(main_module, "run_detector", fake_run_detector)
    main_module.main()
    assert calls == ["detector", "run"]
