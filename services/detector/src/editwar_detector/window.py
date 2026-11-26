"""Sliding time windows that keep the recent edits and reverts of one key.

A key is an article ("enwiki:Title") or a whole wiki ("wiki:enwiki"). The
window keeps events for `span_seconds`. A detector with a shorter rule window
passes a `since` cutoff, so one window serves rules with different spans.

The clock is the event time (`EditEvent.timestamp`), never the wall clock.
That keeps replayed streams and tests deterministic.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime, timedelta

from editwar_domain import EditEvent, RevertEvent


def article_key(event: EditEvent) -> str:
    """Window key for the article of an edit, the same as its Kafka key."""
    return event.partition_key()


def wiki_key(wiki: str) -> str:
    """Window key for a whole wiki, used by wiki-wide rules such as bot_spike."""
    return f"wiki:{wiki}"


def _distinct(values: Iterable[str]) -> list[str]:
    """Return the distinct values in first-seen order."""
    return list(dict.fromkeys(values))


class SlidingWindow:
    """Edits and reverts of one key inside the last `span_seconds`.

    Events are kept in arrival order. For an article (one Kafka partition)
    that is also time order. A wiki window mixes partitions, so its events can
    be slightly out of order: the counting methods check every timestamp, and
    evict() drops old events from the left until it finds a recent one.
    """

    def __init__(self, span_seconds: int) -> None:
        self.span_seconds = span_seconds
        self.events: deque[EditEvent] = deque()
        self.reverts: deque[RevertEvent] = deque()

    def add(self, event: EditEvent) -> None:
        """Append an edit to the window."""
        self.events.append(event)

    def add_revert(self, revert: RevertEvent) -> None:
        """Record that an edit in this window was a revert."""
        self.reverts.append(revert)

    def evict(self, now: datetime) -> int:
        """Drop edits and reverts older than `now - span_seconds`. Return edits dropped."""
        limit = now - timedelta(seconds=self.span_seconds)
        removed = 0
        while self.events and self.events[0].timestamp < limit:
            self.events.popleft()
            removed += 1
        while self.reverts and self.reverts[0].timestamp < limit:
            self.reverts.popleft()
        return removed

    def is_empty(self) -> bool:
        return not self.events and not self.reverts

    def recent(self, since: datetime | None = None) -> list[EditEvent]:
        """Edits with timestamp >= since, newest first."""
        return [e for e in reversed(self.events) if since is None or e.timestamp >= since]

    def recent_reverts(self, since: datetime | None = None) -> list[RevertEvent]:
        """Reverts with timestamp >= since, newest first."""
        return [r for r in reversed(self.reverts) if since is None or r.timestamp >= since]

    def count(self, since: datetime | None = None) -> int:
        """Number of edits."""
        return len(self.recent(since))

    def users(self, since: datetime | None = None) -> list[str]:
        """Distinct editors, newest first."""
        return _distinct(event.user for event in self.recent(since))

    def distinct_users(self, since: datetime | None = None) -> int:
        """Number of distinct editors."""
        return len(self.users(since))

    def revert_count(self, since: datetime | None = None) -> int:
        """Number of reverts."""
        return len(self.recent_reverts(since))

    def reverters(self, since: datetime | None = None) -> list[str]:
        """Distinct users that reverted, newest first."""
        return _distinct(revert.user for revert in self.recent_reverts(since))

    def distinct_reverters(self, since: datetime | None = None) -> int:
        """Number of distinct users that reverted."""
        return len(self.reverters(since))

    def bot_edits(self, since: datetime | None = None) -> list[EditEvent]:
        """Edits made by bots, newest first."""
        return [event for event in self.recent(since) if event.is_bot]


class WindowStore:
    """All windows of one scope (articles or wikis), created on demand."""

    def __init__(self, span_seconds: int) -> None:
        self.span_seconds = span_seconds
        self.windows: dict[str, SlidingWindow] = {}

    def get(self, key: str) -> SlidingWindow:
        """Return the window of `key`, creating it if needed."""
        window = self.windows.get(key)
        if window is None:
            window = SlidingWindow(self.span_seconds)
            self.windows[key] = window
        return window

    def set_span(self, span_seconds: int) -> None:
        """Change the span of the store and of every existing window."""
        self.span_seconds = span_seconds
        for window in self.windows.values():
            window.span_seconds = span_seconds

    def prune(self, now: datetime) -> int:
        """Evict old events everywhere and free empty windows. Return windows freed."""
        empty = []
        for key, window in self.windows.items():
            window.evict(now)
            if window.is_empty():
                empty.append(key)
        for key in empty:
            del self.windows[key]
        return len(empty)

    def size(self) -> int:
        """Number of windows in memory."""
        return len(self.windows)
