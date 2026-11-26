"""EventFilter: accepted and rejected cases."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from editwar_domain import EditEvent
from editwar_ingestor.filters import EventFilter


def make_event(wiki: str = "enwiki", namespace: int = 0, change_type: str = "edit") -> EditEvent:
    return EditEvent(
        event_id="id-1",
        wiki=wiki,
        title="Example",
        user="Someone",
        is_bot=False,
        timestamp=datetime(2026, 11, 25, tzinfo=UTC),
        comment="",
        old_len=10,
        new_len=20,
        rev_id=2,
        old_rev_id=1,
        server_url="https://en.wikipedia.org",
        namespace=namespace,
        change_type=change_type,
    )


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (make_event(), True),
        (make_event(change_type="new"), True),
        (make_event(wiki="eswiki"), True),
        (make_event(namespace=1), False),
        (make_event(namespace=14), False),
        (make_event(change_type="log"), False),
        (make_event(change_type="categorize"), False),
    ],
)
def test_default_filter(event: EditEvent, expected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WIKIS", raising=False)
    assert EventFilter().accept(event) is expected


@pytest.mark.parametrize(
    ("wiki", "expected"),
    [("enwiki", True), ("eswiki", True), ("dewiki", False), ("commonswiki", False)],
)
def test_wiki_list(wiki: str, expected: bool) -> None:
    event_filter = EventFilter(wikis=["enwiki", "eswiki"])
    assert event_filter.accept(make_event(wiki=wiki)) is expected


def test_wikis_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIKIS", "eswiki, frwiki")
    event_filter = EventFilter()
    assert event_filter.wikis == {"eswiki", "frwiki"}
    assert event_filter.accept(make_event(wiki="frwiki"))
    assert not event_filter.accept(make_event(wiki="enwiki"))


def test_empty_wiki_list_accepts_all() -> None:
    assert EventFilter(wikis=[]).accept(make_event(wiki="anywiki"))


@pytest.mark.parametrize(
    ("namespaces", "types", "event", "expected"),
    [
        ({0, 1}, {"edit"}, make_event(namespace=1), True),
        ({0}, {"edit"}, make_event(change_type="new"), False),
        ({14}, {"edit", "new"}, make_event(namespace=14, change_type="new"), True),
    ],
)
def test_custom_namespaces_and_types(
    namespaces: set[int], types: set[str], event: EditEvent, expected: bool
) -> None:
    event_filter = EventFilter(namespaces=namespaces, types=types, wikis=[])
    assert event_filter.accept(event) is expected
