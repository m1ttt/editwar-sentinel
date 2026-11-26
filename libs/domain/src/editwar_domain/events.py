"""Edit and revert events that travel through Kafka."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EditEvent:
    """One normalized edit from the Wikimedia recentchange stream."""

    event_id: str
    wiki: str  # for example "enwiki"
    title: str
    user: str
    is_bot: bool
    timestamp: datetime  # always UTC
    comment: str
    old_len: int
    new_len: int
    rev_id: int
    old_rev_id: int
    server_url: str  # for example "https://en.wikipedia.org"
    namespace: int = 0
    change_type: str = "edit"  # "edit" or "new"

    def size_delta(self) -> int:
        return self.new_len - self.old_len

    def partition_key(self) -> str:
        """Kafka key. All edits of one article go to the same partition."""
        return f"{self.wiki}:{self.title}"

    def page_url(self) -> str:
        return f"{self.server_url}/wiki/{self.title.replace(' ', '_')}"

    def diff_url(self) -> str:
        return f"{self.server_url}/w/index.php?diff={self.rev_id}&oldid={self.old_rev_id}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EditEvent:
        values = dict(data)
        values["timestamp"] = _parse_time(values["timestamp"])
        return cls(**values)

    @classmethod
    def from_json(cls, raw: str | bytes) -> EditEvent:
        return cls.from_dict(json.loads(raw))


@dataclass(frozen=True, slots=True)
class RevertEvent:
    """An edit that the detector classified as a revert of an earlier edit."""

    event_id: str
    wiki: str
    title: str
    user: str
    timestamp: datetime
    reason: str  # "comment" or "size_restore"
    server_url: str

    def partition_key(self) -> str:
        return f"{self.wiki}:{self.title}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RevertEvent:
        values = dict(data)
        values["timestamp"] = _parse_time(values["timestamp"])
        return cls(**values)

    @classmethod
    def from_json(cls, raw: str | bytes) -> RevertEvent:
        return cls.from_dict(json.loads(raw))
