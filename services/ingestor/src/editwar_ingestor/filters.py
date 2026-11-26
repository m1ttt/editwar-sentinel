"""Decide which edits the ingestor publishes."""

from __future__ import annotations

from collections.abc import Iterable

from editwar_domain import EditEvent
from editwar_domain.settings import WIKIS, env_list

DEFAULT_NAMESPACES = frozenset({0})  # 0 = articles
DEFAULT_TYPES = frozenset({"edit", "new"})


class EventFilter:
    """Accept only edits in the configured namespaces, change types and wikis."""

    def __init__(
        self,
        namespaces: Iterable[int] | None = None,
        types: Iterable[str] | None = None,
        wikis: Iterable[str] | None = None,
    ) -> None:
        self.namespaces = set(namespaces) if namespaces is not None else set(DEFAULT_NAMESPACES)
        self.types = set(types) if types is not None else set(DEFAULT_TYPES)
        # An empty wiki set means "all wikis".
        self.wikis = set(wikis) if wikis is not None else set(env_list(WIKIS))

    def accept(self, event: EditEvent) -> bool:
        """Return True when the event passes every rule."""
        if event.namespace not in self.namespaces:
            return False
        if event.change_type not in self.types:
            return False
        return not self.wikis or event.wiki in self.wikis
