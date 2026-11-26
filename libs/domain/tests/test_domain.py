import uuid
from datetime import UTC, datetime

import pytest

from editwar_domain import (
    Alert,
    AlertStatus,
    DetectionRule,
    EditEvent,
    RevertEvent,
    RuleKind,
    RuleValidationError,
    Severity,
    default_rules,
)
from editwar_domain.settings import env_float, env_int, env_list
from editwar_domain.telemetry import configure_telemetry


def make_event(**overrides: object) -> EditEvent:
    values: dict[str, object] = {
        "event_id": "e1",
        "wiki": "enwiki",
        "title": "Python (programming language)",
        "user": "Alice",
        "is_bot": False,
        "timestamp": datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        "comment": "fix typo",
        "old_len": 100,
        "new_len": 120,
        "rev_id": 2,
        "old_rev_id": 1,
        "server_url": "https://en.wikipedia.org",
    }
    values.update(overrides)
    return EditEvent(**values)  # type: ignore[arg-type]


def test_edit_event_round_trip() -> None:
    event = make_event()
    assert EditEvent.from_json(event.to_json()) == event


def test_edit_event_helpers() -> None:
    event = make_event()
    assert event.size_delta() == 20
    assert event.partition_key() == "enwiki:Python (programming language)"
    assert event.page_url() == "https://en.wikipedia.org/wiki/Python_(programming_language)"
    assert event.diff_url().endswith("diff=2&oldid=1")


def test_revert_event_round_trip() -> None:
    revert = RevertEvent(
        event_id="e2",
        wiki="enwiki",
        title="X",
        user="Bob",
        timestamp=datetime(2026, 11, 1, tzinfo=UTC),
        reason="comment",
        server_url="https://en.wikipedia.org",
    )
    assert RevertEvent.from_json(revert.to_json()) == revert
    assert revert.partition_key() == "enwiki:X"


def test_rule_round_trip_and_toggle() -> None:
    rule = default_rules()[0]
    copy = DetectionRule.from_dict(rule.to_dict())
    assert copy.id == rule.id and copy.kind is RuleKind.REVERT_WAR
    rule.disable()
    assert not rule.enabled
    rule.enable()
    assert rule.enabled


@pytest.mark.parametrize(
    "field,value",
    [("name", " "), ("window_seconds", 5), ("threshold", 0), ("min_users", 0)],
)
def test_rule_validation(field: str, value: object) -> None:
    rule = default_rules()[1]
    setattr(rule, field, value)
    with pytest.raises(RuleValidationError):
        rule.validate()


def test_default_rules_are_valid() -> None:
    for rule in default_rules():
        rule.validate()


def test_alert_lifecycle_and_json() -> None:
    alert = Alert(
        rule_id=uuid.uuid4(),
        kind="revert_war",
        severity=Severity.HIGH,
        wiki="enwiki",
        title="Some page",
        server_url="https://en.wikipedia.org",
        evidence={"reverts": 3},
    )
    assert alert.page_url() == "https://en.wikipedia.org/wiki/Some_page"
    alert.acknowledge("mike")
    assert alert.status is AlertStatus.ACKNOWLEDGED and alert.acknowledged_by == "mike"
    alert.dismiss()
    copy = Alert.from_json(alert.to_json())
    assert copy.status is AlertStatus.DISMISSED and copy.id == alert.id


def test_wiki_wide_alert_url() -> None:
    alert = Alert(
        rule_id=uuid.uuid4(),
        kind="bot_spike",
        severity=Severity.LOW,
        wiki="enwiki",
        title="*",
        server_url="https://en.wikipedia.org",
        evidence={},
    )
    assert alert.page_url().endswith("Special:RecentChanges")


def test_env_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_INT", "7")
    monkeypatch.setenv("X_FLOAT", "")
    monkeypatch.setenv("X_LIST", "enwiki, eswiki,,")
    assert env_int("X_INT", 1) == 7
    assert env_float("X_FLOAT", 2.5) == 2.5
    assert env_list("X_LIST") == ["enwiki", "eswiki"]


def test_telemetry_is_off_without_connection_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    assert configure_telemetry("test") is False
