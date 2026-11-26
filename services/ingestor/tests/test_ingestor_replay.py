"""ReplayFileSource: delays, speed and looping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from editwar_ingestor.sources import ReplayFileSource


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def write_events(path: Path, timestamps: list[int | None]) -> Path:
    lines = []
    for number, timestamp in enumerate(timestamps):
        event: dict[str, Any] = {"n": number}
        if timestamp is not None:
            event["timestamp"] = timestamp
        lines.append(json.dumps(event))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def take(source: ReplayFileSource, limit: int) -> list[dict[str, Any]]:
    await source.connect()
    events = []
    stream = source.events()
    async for event in stream:
        events.append(event)
        if len(events) == limit:
            break
    await stream.aclose()  # type: ignore[attr-defined]
    await source.close()
    return events


async def test_original_delays_at_speed_one(tmp_path: Path) -> None:
    sleep = FakeSleep()
    path = write_events(tmp_path / "r.jsonl", [100, 102, 103])
    events = await take(ReplayFileSource(path, 1.0, loop=False, sleep=sleep), 10)
    assert [e["n"] for e in events] == [0, 1, 2]
    assert sleep.calls == [2.0, 1.0]


async def test_speed_divides_delays(tmp_path: Path) -> None:
    sleep = FakeSleep()
    path = write_events(tmp_path / "r.jsonl", [100, 102, 103])
    await take(ReplayFileSource(path, 4.0, loop=False, sleep=sleep), 10)
    assert sleep.calls == [0.5, 0.25]


@pytest.mark.parametrize("speed", [0.0, -1.0])
async def test_zero_or_negative_speed_means_no_delay(tmp_path: Path, speed: float) -> None:
    sleep = FakeSleep()
    path = write_events(tmp_path / "r.jsonl", [100, 200, 300])
    events = await take(ReplayFileSource(path, speed, loop=False, sleep=sleep), 10)
    assert len(events) == 3
    assert sleep.calls == []


async def test_out_of_order_and_missing_timestamps_do_not_wait(tmp_path: Path) -> None:
    sleep = FakeSleep()
    path = write_events(tmp_path / "r.jsonl", [105, 100, None, 101])
    events = await take(ReplayFileSource(path, 1.0, loop=False, sleep=sleep), 10)
    assert len(events) == 4
    assert sleep.calls == []


async def test_loops_forever_without_delay_at_the_wrap(tmp_path: Path) -> None:
    sleep = FakeSleep()
    path = write_events(tmp_path / "r.jsonl", [100, 101])
    source = ReplayFileSource(path, 1.0, sleep=sleep)
    events = await take(source, 7)
    assert [e["n"] for e in events] == [0, 1, 0, 1, 0, 1, 0]
    assert source.passes == 3
    # One delay of 1 s inside each full pass, nothing between passes.
    assert sleep.calls == [1.0, 1.0, 1.0]


async def test_skips_blank_and_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text('{"n": 0}\n\nnot json\n{"n": 1}\n', encoding="utf-8")
    events = await take(ReplayFileSource(path, 0, loop=False), 10)
    assert [event["n"] for event in events] == [0, 1]


async def test_empty_file_ends_even_with_loop(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    events = await take(ReplayFileSource(path, 0, loop=True), 10)
    assert events == []


async def test_missing_file_fails_on_connect(tmp_path: Path) -> None:
    source = ReplayFileSource(tmp_path / "missing.jsonl")
    with pytest.raises(FileNotFoundError):
        await source.connect()


async def test_replay_events_look_live_and_get_new_ids_after_first_pass(tmp_path) -> None:
    import json as _json
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from editwar_ingestor.sources import ReplayFileSource as _Replay

    path = tmp_path / "one.jsonl"
    path.write_text(_json.dumps({"meta": {"id": "abc", "dt": "2020-01-01T00:00:00Z"}}) + "\n")
    source = _Replay(path, speed=0, loop=True)
    seen = []
    async for event in source.events():
        seen.append(event)
        if len(seen) == 2:
            break
    assert seen[0]["meta"]["id"] == "abc"
    assert seen[1]["meta"]["id"] == "abc-r1"
    when = _datetime.fromisoformat(seen[0]["meta"]["dt"])
    assert (_datetime.now(_UTC) - when).total_seconds() < 5


async def test_out_of_order_events_do_not_add_delay(tmp_path: Path) -> None:
    path = tmp_path / "order.jsonl"
    lines = [{"n": 0, "timestamp": 100}, {"n": 1, "timestamp": 90}, {"n": 2, "timestamp": 100}]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    source = ReplayFileSource(path, 1.0, loop=False, sleep=fake_sleep)
    events = [event async for event in source.events()]
    assert [event["n"] for event in events] == [0, 1, 2]
    assert waits == []
