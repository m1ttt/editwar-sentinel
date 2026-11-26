"""EventNormalizer against real recorded events and broken inputs."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from editwar_domain import EditEvent
from editwar_ingestor.normalizer import EventNormalizer

FIXTURE = Path(__file__).parent / "fixtures" / "recentchange-sample.jsonl"
REPLAY = Path(__file__).parents[3] / "data" / "replay.jsonl"


def load(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


SAMPLE = load(FIXTURE)


def first(predicate: Any) -> dict[str, Any]:
    return copy.deepcopy(next(raw for raw in SAMPLE if predicate(raw)))


def test_sample_covers_every_case() -> None:
    types = {raw["type"] for raw in SAMPLE}
    assert {"edit", "new", "log", "categorize"} <= types
    assert any(raw["bot"] for raw in SAMPLE)
    assert any(raw["namespace"] != 0 for raw in SAMPLE)


@pytest.mark.parametrize("raw", SAMPLE, ids=lambda raw: f"{raw['type']}-{raw['meta']['id'][:8]}")
def test_parse_real_events(raw: dict[str, Any]) -> None:
    event = EventNormalizer().parse(raw)
    if raw["type"] in ("edit", "new"):
        assert isinstance(event, EditEvent)
        assert event.event_id == raw["meta"]["id"]
        assert event.wiki == raw["wiki"]
        assert event.title == raw["title"]
        assert event.user == raw["user"]
        assert event.is_bot == raw["bot"]
        assert event.namespace == raw["namespace"]
        assert event.change_type == raw["type"]
        assert event.rev_id == raw["revision"]["new"]
        assert event.new_len == raw["length"]["new"]
        assert event.timestamp.tzinfo == UTC
    else:
        assert event is None


def test_edit_maps_every_field() -> None:
    raw = first(lambda r: r["type"] == "edit" and not r["bot"])
    event = EventNormalizer().parse(raw)
    assert event is not None
    assert event.old_len == raw["length"]["old"]
    assert event.old_rev_id == raw["revision"]["old"]
    assert event.server_url == raw["server_url"]
    assert event.comment == raw["comment"]
    assert event.size_delta() == raw["length"]["new"] - raw["length"]["old"]
    assert event.partition_key() == f"{raw['wiki']}:{raw['title']}"


def test_new_page_has_zero_old_values() -> None:
    raw = first(lambda r: r["type"] == "new")
    event = EventNormalizer().parse(raw)
    assert event is not None
    assert event.old_len == 0
    assert event.old_rev_id == 0
    assert event.size_delta() == raw["length"]["new"]


def test_bot_edit() -> None:
    event = EventNormalizer().parse(first(lambda r: r["type"] == "edit" and r["bot"]))
    assert event is not None
    assert event.is_bot is True


def test_round_trip_through_json() -> None:
    event = EventNormalizer().parse(first(lambda r: r["type"] == "edit"))
    assert event is not None
    assert EditEvent.from_json(event.to_json()) == event


def test_timestamp_comes_from_meta_dt() -> None:
    raw = first(lambda r: r["type"] == "edit")
    raw["meta"]["dt"] = "2026-11-25T18:40:00Z"
    event = EventNormalizer().parse(raw)
    assert event is not None
    assert event.timestamp == datetime(2026, 11, 25, 18, 40, tzinfo=UTC)


def test_missing_comment_becomes_empty_string() -> None:
    raw = first(lambda r: r["type"] == "edit")
    del raw["comment"]
    event = EventNormalizer().parse(raw)
    assert event is not None
    assert event.comment == ""


REMOVE = "<remove>"  # marker: delete the field instead of setting a value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("meta", REMOVE),
        ("meta.id", REMOVE),
        ("meta.dt", REMOVE),
        ("type", REMOVE),
        ("revision", REMOVE),
        ("revision.new", REMOVE),
        ("revision.old", REMOVE),
        ("length", REMOVE),
        ("length.new", REMOVE),
        ("title", REMOVE),
        ("user", REMOVE),
        ("wiki", REMOVE),
        ("server_url", REMOVE),
        ("meta.dt", "not a date"),
        ("title", ""),
        ("revision.new", "abc"),
        ("meta.domain", "canary"),
        ("type", "log"),
        ("type", "categorize"),
    ],
)
def test_unusable_events_return_none(path: str, value: str) -> None:
    raw = first(lambda r: r["type"] == "edit")
    # Walk a dotted path such as "revision.old" down to the parent dict.
    *parents, last = path.split(".")
    target = raw
    for key in parents:
        target = target[key]
    if value == REMOVE:
        del target[last]
    else:
        target[last] = value
    assert EventNormalizer().parse(raw) is None


@pytest.mark.parametrize("raw", [None, "text", 42, [], {}])
def test_wrong_input_types_return_none(raw: Any) -> None:
    assert EventNormalizer().parse(raw) is None


def test_canary_event_is_ignored() -> None:
    raw = {
        "meta": {"domain": "canary", "id": "x", "dt": "2026-11-25T00:00:00Z"},
        "type": "edit",
    }
    assert EventNormalizer().parse(raw) is None


def test_whole_replay_file_parses() -> None:
    """Every edit or new page in the demo replay file becomes an EditEvent."""
    raws = load(REPLAY)
    edits = [raw for raw in raws if raw.get("type") in ("edit", "new")]
    parsed = [EventNormalizer().parse(raw) for raw in edits]
    assert len(raws) >= 1000
    assert all(event is not None for event in parsed)
