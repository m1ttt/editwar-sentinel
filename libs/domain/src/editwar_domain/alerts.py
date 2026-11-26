"""Alerts produced by the detector and managed through the api."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class Alert:
    rule_id: uuid.UUID
    kind: str  # a RuleKind value
    severity: Severity
    wiki: str
    title: str  # article title, or "*" for wiki-wide alerts such as bot_spike
    server_url: str
    evidence: dict[str, Any]  # counts, users and event ids that triggered the rule
    status: AlertStatus = AlertStatus.OPEN
    acknowledged_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def acknowledge(self, user: str) -> None:
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = user

    def dismiss(self) -> None:
        self.status = AlertStatus.DISMISSED

    def page_url(self) -> str:
        if self.title == "*":
            return f"{self.server_url}/wiki/Special:RecentChanges"
        return f"{self.server_url}/wiki/{self.title.replace(' ', '_')}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = str(self.id)
        data["rule_id"] = str(self.rule_id)
        data["severity"] = self.severity.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["page_url"] = self.page_url()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Alert:
        values = {k: v for k, v in data.items() if k != "page_url"}
        values["id"] = uuid.UUID(str(values["id"]))
        values["rule_id"] = uuid.UUID(str(values["rule_id"]))
        values["severity"] = Severity(values["severity"])
        values["status"] = AlertStatus(values.get("status", AlertStatus.OPEN))
        values["created_at"] = datetime.fromisoformat(values["created_at"]).astimezone(UTC)
        return cls(**values)

    @classmethod
    def from_json(cls, raw: str | bytes) -> Alert:
        return cls.from_dict(json.loads(raw))
