"""Repository tests on a migrated in-memory SQLite database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api_fakes import make_alert

from editwar_api.repositories import AlertRepository, RuleRepository, as_utc
from editwar_domain import AlertStatus, DetectionRule, RuleKind, RuleValidationError


def make_rule(**overrides: object) -> DetectionRule:
    values: dict[str, object] = {
        "name": "Test rule",
        "kind": RuleKind.BURST,
        "window_seconds": 120,
        "threshold": 5,
        "min_users": 2,
    }
    values.update(overrides)
    return DetectionRule(**values)  # type: ignore[arg-type]


async def test_rule_crud(rule_repo: RuleRepository) -> None:
    rule = await rule_repo.create(make_rule())
    assert await rule_repo.get(rule.id) == rule
    assert await rule_repo.list() == [rule]

    updated = await rule_repo.update(rule.id, {"threshold": 9, "kind": "bot_spike", "x": 1})
    assert updated is not None
    assert updated.threshold == 9
    assert updated.kind is RuleKind.BOT_SPIKE
    assert await rule_repo.get(rule.id) == updated

    assert await rule_repo.delete(rule.id) is True
    assert await rule_repo.get(rule.id) is None
    assert await rule_repo.delete(rule.id) is False


async def test_rule_validation(rule_repo: RuleRepository) -> None:
    with pytest.raises(RuleValidationError):
        await rule_repo.create(make_rule(min_users=0))
    rule = await rule_repo.create(make_rule())
    with pytest.raises(RuleValidationError):
        await rule_repo.update(rule.id, {"window_seconds": 100_000})
    assert (await rule_repo.get(rule.id)) == rule


async def test_update_unknown_rule(rule_repo: RuleRepository) -> None:
    assert await rule_repo.update(uuid.uuid4(), {"threshold": 2}) is None


async def test_seed_defaults_only_once(rule_repo: RuleRepository) -> None:
    assert await rule_repo.seed_defaults() == 3
    assert await rule_repo.seed_defaults() == 0
    assert await rule_repo.count() == 3


async def test_seed_skipped_when_table_has_rules(rule_repo: RuleRepository) -> None:
    await rule_repo.create(make_rule())
    assert await rule_repo.seed_defaults() == 0
    assert await rule_repo.count() == 1


async def test_alert_create_is_idempotent(alert_repo: AlertRepository) -> None:
    alert = make_alert()
    assert await alert_repo.create(alert) == alert
    assert await alert_repo.create(alert) is None
    assert len(await alert_repo.list()) == 1


async def test_alert_round_trip_keeps_utc(alert_repo: AlertRepository) -> None:
    alert = make_alert(created_at=datetime(2026, 11, 1, 8, 30, tzinfo=UTC))
    await alert_repo.create(alert)
    stored = await alert_repo.get(alert.id)
    assert stored == alert
    assert stored is not None and stored.created_at.tzinfo is UTC
    assert await alert_repo.get(uuid.uuid4()) is None


async def test_alert_update_status(alert_repo: AlertRepository) -> None:
    alert = make_alert()
    await alert_repo.create(alert)

    acknowledged = await alert_repo.update_status(alert.id, AlertStatus.ACKNOWLEDGED, "Ana")
    assert acknowledged is not None
    assert (acknowledged.status, acknowledged.acknowledged_by) == (AlertStatus.ACKNOWLEDGED, "Ana")

    reopened = await alert_repo.update_status(alert.id, AlertStatus.OPEN)
    assert reopened is not None and reopened.status is AlertStatus.OPEN

    dismissed = await alert_repo.update_status(alert.id, AlertStatus.DISMISSED)
    assert dismissed is not None and dismissed.status is AlertStatus.DISMISSED
    assert await alert_repo.update_status(uuid.uuid4(), AlertStatus.DISMISSED) is None


async def test_alert_delete(alert_repo: AlertRepository) -> None:
    alert = make_alert()
    await alert_repo.create(alert)
    assert await alert_repo.delete(alert.id) is True
    assert await alert_repo.delete(alert.id) is False


async def test_purge_older_than(alert_repo: AlertRepository) -> None:
    now = datetime.now(UTC)
    old = make_alert(created_at=now - timedelta(days=40))
    older = make_alert(created_at=now - timedelta(days=31))
    recent = make_alert(created_at=now - timedelta(days=2))
    for alert in (old, older, recent):
        await alert_repo.create(alert)
    assert await alert_repo.purge_older_than(30) == 2
    assert [a.id for a in await alert_repo.list()] == [recent.id]
    assert await alert_repo.purge_older_than(30) == 0


async def test_count_open(alert_repo: AlertRepository) -> None:
    await alert_repo.create(make_alert())
    await alert_repo.create(make_alert())
    await alert_repo.create(make_alert(status=AlertStatus.DISMISSED))
    assert await alert_repo.count_open() == 2


def test_as_utc() -> None:
    naive = datetime(2026, 1, 1, 12, 0)
    assert as_utc(naive) == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    other_zone = datetime.fromisoformat("2026-01-01T06:00:00-06:00")
    assert as_utc(other_zone) == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
