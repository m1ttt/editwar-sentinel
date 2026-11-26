"""REST controllers for rules and alerts.

Each controller owns an APIRouter. Its methods are the endpoints, so the
method names match the class diagram (create_rule, list_alerts, ...).
Pydantic validates the request bodies. DetectionRule.validate() checks the
value ranges and its message comes back as a 422 response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from editwar_api.repositories import AlertRepository, RuleRepository
from editwar_domain import AlertStatus, DetectionRule, RuleKind, RuleValidationError

logger = logging.getLogger("editwar.api")


class RuleBody(BaseModel):
    """Request body of POST /api/rules and PUT /api/rules/{id}."""

    name: str
    kind: RuleKind
    window_seconds: int
    threshold: int
    min_users: int = 1
    enabled: bool = True


class AlertStatusBody(BaseModel):
    """Request body of PATCH /api/alerts/{id}."""

    status: Literal["acknowledged", "dismissed"]
    user: str | None = None


def not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


def invalid(error: RuleValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


class RuleController:
    """CRUD of detection rules under /api/rules."""

    def __init__(self, rules: RuleRepository) -> None:
        self._rules = rules
        self.router = APIRouter(prefix="/api/rules", tags=["rules"])
        self.router.add_api_route("", self.list_rules, methods=["GET"])
        self.router.add_api_route("", self.create_rule, methods=["POST"], status_code=201)
        self.router.add_api_route("/{rule_id}", self.get_rule, methods=["GET"])
        self.router.add_api_route("/{rule_id}", self.update_rule, methods=["PUT"])
        self.router.add_api_route(
            "/{rule_id}", self.delete_rule, methods=["DELETE"], status_code=204
        )

    @staticmethod
    def _log(action: str, rule_id: uuid.UUID, rule_name: str = "") -> None:
        logger.info(
            "rule %s %s",
            rule_id,
            action,
            extra={"rule_id": str(rule_id), "rule_name": rule_name, "action": action},
        )

    async def list_rules(self) -> list[dict[str, Any]]:
        return [rule.to_dict() for rule in await self._rules.list()]

    async def create_rule(self, body: RuleBody) -> dict[str, Any]:
        rule = DetectionRule(**body.model_dump())
        try:
            created = await self._rules.create(rule)
        except RuleValidationError as error:
            raise invalid(error) from error
        self._log("created", created.id, created.name)
        return created.to_dict()

    async def get_rule(self, rule_id: uuid.UUID) -> dict[str, Any]:
        rule = await self._rules.get(rule_id)
        if rule is None:
            raise not_found("rule")
        return rule.to_dict()

    async def update_rule(self, rule_id: uuid.UUID, body: RuleBody) -> dict[str, Any]:
        try:
            rule = await self._rules.update(rule_id, body.model_dump())
        except RuleValidationError as error:
            raise invalid(error) from error
        if rule is None:
            raise not_found("rule")
        self._log("updated", rule.id, rule.name)
        return rule.to_dict()

    async def delete_rule(self, rule_id: uuid.UUID) -> Response:
        if not await self._rules.delete(rule_id):
            raise not_found("rule")
        self._log("deleted", rule_id)
        return Response(status_code=204)


class AlertController:
    """Query, acknowledge, dismiss and delete alerts under /api/alerts."""

    def __init__(self, alerts: AlertRepository) -> None:
        self._alerts = alerts
        self.router = APIRouter(prefix="/api/alerts", tags=["alerts"])
        self.router.add_api_route("", self.list_alerts, methods=["GET"])
        self.router.add_api_route("/{alert_id}", self.get_alert, methods=["GET"])
        self.router.add_api_route("/{alert_id}", self.update_alert, methods=["PATCH"])
        self.router.add_api_route(
            "/{alert_id}", self.delete_alert, methods=["DELETE"], status_code=204
        )

    async def list_alerts(
        self,
        status: AlertStatus | None = None,
        kind: RuleKind | None = None,
        wiki: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, Any]]:
        alerts = await self._alerts.list(
            status=status.value if status else None,
            kind=kind.value if kind else None,
            wiki=wiki,
            limit=limit,
            offset=offset,
        )
        return [alert.to_dict() for alert in alerts]

    async def get_alert(self, alert_id: uuid.UUID) -> dict[str, Any]:
        alert = await self._alerts.get(alert_id)
        if alert is None:
            raise not_found("alert")
        return alert.to_dict()

    async def update_alert(self, alert_id: uuid.UUID, body: AlertStatusBody) -> dict[str, Any]:
        alert = await self._alerts.update_status(alert_id, AlertStatus(body.status), body.user)
        if alert is None:
            raise not_found("alert")
        logger.info(
            "alert %s %s",
            alert.id,
            alert.status.value,
            extra={
                "alert_id": str(alert.id),
                "status": alert.status.value,
                "user": alert.acknowledged_by or "",
            },
        )
        return alert.to_dict()

    async def delete_alert(self, alert_id: uuid.UUID) -> Response:
        if not await self._alerts.delete(alert_id):
            raise not_found("alert")
        logger.info("alert %s deleted", alert_id, extra={"alert_id": str(alert_id)})
        return Response(status_code=204)
