"""Turn raw Wikimedia recentchange events into EditEvent objects."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from editwar_domain import EditEvent

logger = logging.getLogger("editwar.ingestor.normalizer")

# Change types that carry a revision. "log" and "categorize" do not.
SUPPORTED_TYPES = ("edit", "new")


class EventNormalizer:
    """Map the raw recentchange JSON to the shared EditEvent model."""

    def parse(self, raw: Any) -> EditEvent | None:
        """Return an EditEvent, or None when the raw event is not a usable edit."""
        try:
            return self._parse(raw)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.debug("skipping unusable event: %r", exc)
            return None

    def _parse(self, raw: dict[str, Any]) -> EditEvent | None:
        meta = raw["meta"]
        # Wikimedia sends synthetic "canary" events to check that the stream works.
        if meta.get("domain") == "canary":
            return None

        change_type = raw["type"]
        if change_type not in SUPPORTED_TYPES:
            return None

        revision = raw["revision"]
        length = raw["length"]
        is_new_page = change_type == "new"

        return EditEvent(
            event_id=_text(meta, "id"),
            wiki=_text(raw, "wiki"),
            title=_text(raw, "title"),
            user=_text(raw, "user"),
            is_bot=bool(raw.get("bot", False)),
            timestamp=_parse_time(_text(meta, "dt")),
            comment=str(raw.get("comment") or ""),
            old_len=0 if is_new_page else int(length["old"]),
            new_len=int(length["new"]),
            rev_id=int(revision["new"]),
            old_rev_id=0 if is_new_page else int(revision["old"]),
            server_url=_text(raw, "server_url"),
            namespace=int(raw.get("namespace", 0)),
            change_type=change_type,
        )


def _text(data: dict[str, Any], key: str) -> str:
    """Read a required, non-empty string field."""
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"field {key!r} must be a non-empty string")
    return value


def _parse_time(value: str) -> datetime:
    """Parse an ISO 8601 time such as 2026-11-25T18:40:00Z and convert it to UTC."""
    return datetime.fromisoformat(value).astimezone(UTC)
