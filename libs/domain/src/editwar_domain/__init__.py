"""Shared contract for every EditWar Sentinel service.

All services import their messages, topic names and settings from this package,
so a change to the wire format happens in one place.
"""

from editwar_domain.alerts import Alert, AlertStatus, Severity
from editwar_domain.events import EditEvent, RevertEvent
from editwar_domain.rules import DetectionRule, RuleKind, RuleValidationError, default_rules
from editwar_domain.topics import TOPIC_ALERTS, TOPIC_EDITS, TOPIC_REVERTS

__all__ = [
    "TOPIC_ALERTS",
    "TOPIC_EDITS",
    "TOPIC_REVERTS",
    "Alert",
    "AlertStatus",
    "DetectionRule",
    "EditEvent",
    "RevertEvent",
    "RuleKind",
    "RuleValidationError",
    "Severity",
    "default_rules",
]
