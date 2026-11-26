"""Detection rules. The api stores them, the detector evaluates them."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class RuleKind(StrEnum):
    # threshold = reverts in the window, min_users = distinct users that reverted
    REVERT_WAR = "revert_war"
    # threshold = edits on one article in the window, min_users = distinct editors
    BURST = "burst"
    # threshold = bot edits on one wiki in the window, min_users = distinct bots
    BOT_SPIKE = "bot_spike"


class RuleValidationError(ValueError):
    """A rule has values that the detector cannot evaluate."""


@dataclass(slots=True)
class DetectionRule:
    name: str
    kind: RuleKind
    window_seconds: int
    threshold: int
    min_users: int = 1
    enabled: bool = True
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def validate(self) -> None:
        if not self.name.strip():
            raise RuleValidationError("name must not be empty")
        if not 10 <= self.window_seconds <= 86_400:
            raise RuleValidationError("window_seconds must be between 10 and 86400")
        if self.threshold < 1:
            raise RuleValidationError("threshold must be at least 1")
        if self.min_users < 1:
            raise RuleValidationError("min_users must be at least 1")

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = str(self.id)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectionRule:
        values = dict(data)
        values["kind"] = RuleKind(values["kind"])
        if "id" in values:
            values["id"] = uuid.UUID(str(values["id"]))
        return cls(**values)


def default_rules() -> list[DetectionRule]:
    """Rules that the api seeds on first start and the detector uses when the api is down.

    The ids are fixed so that both services agree on them.
    """
    return [
        DetectionRule(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Guerra de edición",
            kind=RuleKind.REVERT_WAR,
            window_seconds=3600,
            threshold=3,
            min_users=2,
        ),
        DetectionRule(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            name="Ráfaga de ediciones",
            kind=RuleKind.BURST,
            window_seconds=300,
            threshold=10,
            min_users=3,
        ),
        DetectionRule(
            id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            name="Pico de bots",
            kind=RuleKind.BOT_SPIKE,
            window_seconds=60,
            threshold=100,
            min_users=1,
        ),
    ]
