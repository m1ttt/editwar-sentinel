from datetime import timedelta

from editwar_detector.window import SlidingWindow, WindowStore, article_key, wiki_key
from editwar_domain import RevertEvent


def make_revert(event, user=None):
    return RevertEvent(
        event_id=event.event_id,
        wiki=event.wiki,
        title=event.title,
        user=user or event.user,
        timestamp=event.timestamp,
        reason="comment",
        server_url=event.server_url,
    )


def test_keys(make_event):
    event = make_event(wiki="eswiki", title="Madrid")
    assert article_key(event) == "eswiki:Madrid"
    assert wiki_key("eswiki") == "wiki:eswiki"


def test_counts_and_distinct_users(make_event):
    window = SlidingWindow(60)
    for user in ["Alice", "Bob", "Alice"]:
        window.add(make_event(user=user))
    assert window.count() == 3
    assert window.distinct_users() == 2
    assert window.users() == ["Alice", "Bob"]


def test_evict_drops_only_events_older_than_span(make_event, clock):
    window = SlidingWindow(60)
    window.add(make_event(user="old"))
    clock.advance(30)
    window.add(make_event(user="mid"))
    clock.advance(30)
    window.add(make_event(user="new"))

    # Exactly 60 s after the first event: it is still inside the window.
    assert window.evict(clock.now) == 0
    assert window.count() == 3

    clock.advance(1)
    assert window.evict(clock.now) == 1
    assert window.users() == ["new", "mid"]


def test_since_counts_only_recent_events(make_event, clock):
    window = SlidingWindow(3600)
    window.add(make_event(user="Alice"))
    clock.advance(600)
    window.add(make_event(user="Bob"))
    since = clock.now - timedelta(seconds=300)
    assert window.count(since) == 1
    assert window.distinct_users(since) == 1
    assert window.count() == 2


def test_out_of_order_events_are_counted(make_event, clock):
    # A wiki window mixes Kafka partitions, so an older edit can arrive last.
    window = SlidingWindow(600)
    start = clock.now
    clock.advance(100)
    window.add(make_event(user="new"))
    window.add(make_event(user="late", timestamp=start))
    clock.advance(10)
    window.add(make_event(user="newest"))
    since = start - timedelta(seconds=1)
    assert window.count(since) == 3
    assert window.count(start + timedelta(seconds=50)) == 2


def test_reverts_are_counted_and_evicted(make_event, clock):
    window = SlidingWindow(60)
    first = make_event(user="Alice")
    window.add(first)
    window.add_revert(make_revert(first))
    clock.advance(10)
    second = make_event(user="Bob")
    window.add(second)
    window.add_revert(make_revert(second))
    third = make_event(user="Bob")
    window.add_revert(make_revert(third))

    assert window.revert_count() == 3
    assert window.distinct_reverters() == 2
    assert window.reverters() == ["Bob", "Alice"]

    clock.advance(55)
    window.evict(clock.now)
    assert window.revert_count() == 2
    assert window.distinct_reverters() == 1


def test_bot_edits(make_event):
    window = SlidingWindow(60)
    window.add(make_event(user="Bot1", is_bot=True))
    window.add(make_event(user="Human"))
    assert [e.user for e in window.bot_edits()] == ["Bot1"]


def test_is_empty(make_event, clock):
    window = SlidingWindow(10)
    assert window.is_empty()
    window.add(make_event())
    assert not window.is_empty()
    clock.advance(11)
    window.evict(clock.now)
    assert window.is_empty()


def test_store_get_creates_once_with_store_span():
    store = WindowStore(120)
    window = store.get("enwiki:A")
    assert store.get("enwiki:A") is window
    assert window.span_seconds == 120
    assert store.size() == 1


def test_store_set_span_updates_existing_windows():
    store = WindowStore(60)
    window = store.get("enwiki:A")
    store.set_span(300)
    assert window.span_seconds == 300
    assert store.get("enwiki:B").span_seconds == 300


def test_store_prune_frees_empty_windows(make_event, clock):
    store = WindowStore(60)
    store.get("enwiki:Old").add(make_event(title="Old"))
    clock.advance(50)
    store.get("enwiki:New").add(make_event(title="New"))
    store.get("enwiki:Never")  # created but never used

    clock.advance(20)
    assert store.prune(clock.now) == 2
    assert store.size() == 1
    assert "enwiki:New" in store.windows
