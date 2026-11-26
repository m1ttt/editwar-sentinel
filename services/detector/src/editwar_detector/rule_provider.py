"""Loads detection rules from the api, with a fallback when the api is down."""

from __future__ import annotations

import dataclasses
import logging

import httpx

from editwar_domain import DetectionRule, default_rules

log = logging.getLogger("editwar.detector.rules")

# Fields of DetectionRule. Extra fields from the api (for example created_at) are ignored.
RULE_FIELDS = {f.name for f in dataclasses.fields(DetectionRule)}


def parse_rules(payload: object) -> list[DetectionRule]:
    """Build rules from the JSON list that GET /api/rules returns."""
    if not isinstance(payload, list):
        raise ValueError("expected a JSON list of rules")
    rules = []
    for item in payload:
        values = {key: value for key, value in item.items() if key in RULE_FIELDS}
        rules.append(DetectionRule.from_dict(values))
    return rules


class RuleProvider:
    """Fetches GET {api_url}/api/rules.

    On error it keeps the last good rules. When no fetch has worked yet, it
    uses editwar_domain.default_rules().
    """

    def __init__(
        self,
        api_url: str,
        refresh_seconds: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = f"{api_url.rstrip('/')}/api/rules"
        self.refresh_seconds = refresh_seconds
        self.client = client or httpx.AsyncClient(timeout=5.0)
        self.rules: list[DetectionRule] | None = None

    async def fetch(self) -> list[DetectionRule]:
        """Return the current rules from the api, or the fallback."""
        try:
            response = await self.client.get(self.url)
            response.raise_for_status()
            rules = parse_rules(response.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            if self.rules is None:
                log.warning("cannot load rules from %s (%s), using defaults", self.url, error)
                self.rules = default_rules()
            else:
                log.warning("cannot load rules from %s (%s), keeping last rules", self.url, error)
            return list(self.rules)
        self.rules = rules
        return list(rules)

    async def aclose(self) -> None:
        await self.client.aclose()
