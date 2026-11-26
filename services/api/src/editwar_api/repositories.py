"""Repository pattern: the only code that talks to the database.

The repositories receive and return the domain dataclasses (DetectionRule and
Alert), never SQLAlchemy rows, so the rest of the api does not depend on the
database. Each method opens its own short session.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from editwar_api.db import AlertRow, RuleRow
from editwar_domain import (
    Alert,
    AlertStatus,
    DetectionRule,
    RuleKind,
    Severity,
    default_rules,
)

Sessions = async_sessionmaker[AsyncSession]

RULE_FIELDS = ("name", "kind", "window_seconds", "threshold", "min_users", "enabled")


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes. Treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RuleRepository:
    """CRUD for detection rules."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    @staticmethod
    def _to_domain(row: RuleRow) -> DetectionRule:
        return DetectionRule(
            id=row.id,
            name=row.name,
            kind=RuleKind(row.kind),
            window_seconds=row.window_seconds,
            threshold=row.threshold,
            min_users=row.min_users,
            enabled=row.enabled,
        )

    @staticmethod
    def _copy_to_row(rule: DetectionRule, row: RuleRow) -> None:
        row.name = rule.name
        row.kind = rule.kind.value
        row.window_seconds = rule.window_seconds
        row.threshold = rule.threshold
        row.min_users = rule.min_users
        row.enabled = rule.enabled

    async def create(self, rule: DetectionRule) -> DetectionRule:
        """Validate and store a new rule. Raises RuleValidationError."""
        rule.validate()
        row = RuleRow(id=rule.id)
        self._copy_to_row(rule, row)
        async with self._sessions() as session, session.begin():
            session.add(row)
        return self._to_domain(row)

    async def get(self, rule_id: uuid.UUID) -> DetectionRule | None:
        async with self._sessions() as session:
            row = await session.get(RuleRow, rule_id)
            return self._to_domain(row) if row else None

    async def list(self) -> list[DetectionRule]:
        async with self._sessions() as session:
            rows = await session.scalars(select(RuleRow).order_by(RuleRow.created_at, RuleRow.id))
            return [self._to_domain(row) for row in rows]

    async def update(self, rule_id: uuid.UUID, data: dict[str, Any]) -> DetectionRule | None:
        """Change the fields in data. Returns None when the rule does not exist.

        Raises RuleValidationError when the new values are not valid.
        """
        async with self._sessions() as session, session.begin():
            row = await session.get(RuleRow, rule_id)
            if row is None:
                return None
            changes = {key: value for key, value in data.items() if key in RULE_FIELDS}
            if "kind" in changes:
                changes["kind"] = RuleKind(changes["kind"])
            rule = replace(self._to_domain(row), **changes)
            rule.validate()
            self._copy_to_row(rule, row)
        return rule

    async def delete(self, rule_id: uuid.UUID) -> bool:
        """Delete a rule. Returns False when it does not exist."""
        async with self._sessions() as session, session.begin():
            result = await session.execute(delete(RuleRow).where(RuleRow.id == rule_id))
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def count(self) -> int:
        async with self._sessions() as session:
            return int(await session.scalar(select(func.count()).select_from(RuleRow)) or 0)

    async def seed_defaults(self) -> int:
        """Store default_rules() when the table is empty. Returns how many were added."""
        if await self.count() > 0:
            return 0
        rules = default_rules()
        for rule in rules:
            await self.create(rule)
        return len(rules)


class AlertRepository:
    """Storage and queries for alerts."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    @staticmethod
    def _to_domain(row: AlertRow) -> Alert:
        return Alert(
            id=row.id,
            rule_id=row.rule_id,
            kind=row.kind,
            severity=Severity(row.severity),
            wiki=row.wiki,
            title=row.title,
            server_url=row.server_url,
            evidence=row.evidence,
            status=AlertStatus(row.status),
            acknowledged_by=row.acknowledged_by,
            created_at=as_utc(row.created_at),
        )

    @staticmethod
    def _to_row(alert: Alert) -> AlertRow:
        return AlertRow(
            id=alert.id,
            rule_id=alert.rule_id,
            kind=alert.kind,
            severity=alert.severity.value,
            wiki=alert.wiki,
            title=alert.title,
            server_url=alert.server_url,
            evidence=alert.evidence,
            status=alert.status.value,
            acknowledged_by=alert.acknowledged_by,
            created_at=alert.created_at,
        )

    async def create(self, alert: Alert) -> Alert | None:
        """Store a new alert.

        Kafka can deliver the same message twice, so the method is idempotent:
        it returns None when an alert with this id is already stored.
        """
        try:
            async with self._sessions() as session, session.begin():
                if await session.get(AlertRow, alert.id) is not None:
                    return None
                session.add(self._to_row(alert))
        except IntegrityError:  # another api replica stored it at the same time
            return None
        return alert

    async def get(self, alert_id: uuid.UUID) -> Alert | None:
        async with self._sessions() as session:
            row = await session.get(AlertRow, alert_id)
            return self._to_domain(row) if row else None

    async def list(
        self,
        status: str | None = None,
        kind: str | None = None,
        wiki: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Alert]:
        """Alerts that match all the given filters, newest first."""
        query = select(AlertRow)
        if status:
            query = query.where(AlertRow.status == status)
        if kind:
            query = query.where(AlertRow.kind == kind)
        if wiki:
            query = query.where(AlertRow.wiki == wiki)
        query = query.order_by(AlertRow.created_at.desc(), AlertRow.id).limit(limit).offset(offset)
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return [self._to_domain(row) for row in rows]

    async def update_status(
        self, alert_id: uuid.UUID, status: AlertStatus, user: str | None = None
    ) -> Alert | None:
        """Acknowledge or dismiss an alert. Returns None when it does not exist."""
        async with self._sessions() as session, session.begin():
            row = await session.get(AlertRow, alert_id)
            if row is None:
                return None
            alert = self._to_domain(row)
            if status == AlertStatus.ACKNOWLEDGED:
                alert.acknowledge(user or "anonymous")
            elif status == AlertStatus.DISMISSED:
                alert.dismiss()
            else:
                alert.status = status
            row.status = alert.status.value
            row.acknowledged_by = alert.acknowledged_by
        return alert

    async def delete(self, alert_id: uuid.UUID) -> bool:
        """Delete an alert. Returns False when it does not exist."""
        async with self._sessions() as session, session.begin():
            result = await session.execute(delete(AlertRow).where(AlertRow.id == alert_id))
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def purge_older_than(self, days: int) -> int:
        """Delete alerts created more than `days` days ago. Returns how many."""
        limit = datetime.now(UTC) - timedelta(days=days)
        async with self._sessions() as session, session.begin():
            result = await session.execute(delete(AlertRow).where(AlertRow.created_at < limit))
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def count_open(self) -> int:
        """Number of alerts with status "open". Used by the stats."""
        query = select(func.count()).select_from(AlertRow).where(AlertRow.status == "open")
        async with self._sessions() as session:
            return int(await session.scalar(query) or 0)
