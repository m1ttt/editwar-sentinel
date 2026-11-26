"""Detection strategies. Each Detector evaluates one DetectionRule (Strategy pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, ClassVar

from editwar_detector.window import SlidingWindow, article_key, wiki_key
from editwar_domain import Alert, DetectionRule, EditEvent, RuleKind, Severity

# Which window store a detector reads.
SCOPE_ARTICLE = "article"
SCOPE_WIKI = "wiki"

# Evidence lists are capped so one alert stays small.
MAX_EVIDENCE_ITEMS = 10


class Detector(ABC):
    """One detection rule applied to a sliding window.

    `cooldown_seconds` is the minimum time between two alerts for the same
    key, so one edit war does not raise an alert on every edit. When it is
    None, the cooldown equals the rule window.
    """

    kind: ClassVar[RuleKind]
    scope: ClassVar[str] = SCOPE_ARTICLE

    def __init__(self, rule: DetectionRule, cooldown_seconds: int | None = None) -> None:
        self.rule = rule
        self.cooldown_seconds = cooldown_seconds
        self.last_alert_at: dict[str, datetime] = {}

    @abstractmethod
    def evaluate(self, event: EditEvent, window: SlidingWindow) -> Alert | None:
        """Return an Alert when the rule fires for this event, else None."""

    def update_rule(self, rule: DetectionRule) -> None:
        """Use new rule values (hot reload). The cooldown state is kept."""
        self.rule = rule

    def window_key(self, event: EditEvent) -> str:
        """Key of the window this detector reads for `event`."""
        return article_key(event)

    def since(self, now: datetime) -> datetime:
        """Start of the rule window that ends at `now`."""
        return now - timedelta(seconds=self.rule.window_seconds)

    def cooldown(self) -> timedelta:
        if self.cooldown_seconds is None:
            return timedelta(seconds=self.rule.window_seconds)
        return timedelta(seconds=self.cooldown_seconds)

    def in_cooldown(self, key: str, now: datetime) -> bool:
        last = self.last_alert_at.get(key)
        return last is not None and now - last < self.cooldown()

    def forget_before(self, now: datetime) -> None:
        """Drop cooldown entries that expired, so the dict does not grow forever."""
        limit = now - self.cooldown()
        self.last_alert_at = {k: t for k, t in self.last_alert_at.items() if t >= limit}

    def build_alert(
        self,
        event: EditEvent,
        severity: Severity,
        evidence: dict[str, Any],
        title: str | None = None,
    ) -> Alert:
        """Create the Alert and start the cooldown for its key."""
        self.last_alert_at[self.window_key(event)] = event.timestamp
        return Alert(
            rule_id=self.rule.id,
            kind=self.rule.kind.value,
            severity=severity,
            wiki=event.wiki,
            title=event.title if title is None else title,
            server_url=event.server_url,
            evidence={
                "rule": self.rule.name,
                "window_seconds": self.rule.window_seconds,
                **evidence,
            },
            created_at=event.timestamp,
        )


class RevertWarDetector(Detector):
    """Many reverts by several users on one article.

    threshold = reverts in the window, min_users = distinct reverters.
    Severity is high when the reverts reach twice the threshold.
    """

    kind = RuleKind.REVERT_WAR

    def evaluate(self, event: EditEvent, window: SlidingWindow) -> Alert | None:
        now = event.timestamp
        if self.in_cooldown(self.window_key(event), now):
            return None
        since = self.since(now)
        reverts = window.revert_count(since)
        reverters = window.reverters(since)
        if reverts < self.rule.threshold or len(reverters) < self.rule.min_users:
            return None
        severity = Severity.HIGH if reverts >= 2 * self.rule.threshold else Severity.MEDIUM
        recent = window.recent_reverts(since)[:MAX_EVIDENCE_ITEMS]
        return self.build_alert(
            event,
            severity,
            {
                "reverts": reverts,
                "distinct_users": len(reverters),
                "users": reverters[:MAX_EVIDENCE_ITEMS],
                "event_ids": [revert.event_id for revert in recent],
            },
        )


class BurstDetector(Detector):
    """Many edits by several users on one article.

    threshold = edits in the window, min_users = distinct editors.
    """

    kind = RuleKind.BURST

    def evaluate(self, event: EditEvent, window: SlidingWindow) -> Alert | None:
        now = event.timestamp
        if self.in_cooldown(self.window_key(event), now):
            return None
        since = self.since(now)
        edits = window.count(since)
        users = window.users(since)
        if edits < self.rule.threshold or len(users) < self.rule.min_users:
            return None
        recent = window.recent(since)[:MAX_EVIDENCE_ITEMS]
        return self.build_alert(
            event,
            Severity.MEDIUM,
            {
                "edits": edits,
                "distinct_users": len(users),
                "users": users[:MAX_EVIDENCE_ITEMS],
                "event_ids": [edit.event_id for edit in recent],
            },
        )


class BotSpikeDetector(Detector):
    """Many bot edits on one wiki, reads the wiki-wide window.

    threshold = bot edits in the window, min_users = distinct bots, and bots
    must make at least `max_bot_ratio` of all edits in the window.
    """

    kind = RuleKind.BOT_SPIKE
    scope = SCOPE_WIKI

    def __init__(
        self,
        rule: DetectionRule,
        cooldown_seconds: int | None = None,
        max_bot_ratio: float = 0.8,
    ) -> None:
        super().__init__(rule, cooldown_seconds)
        self.max_bot_ratio = max_bot_ratio

    def window_key(self, event: EditEvent) -> str:
        return wiki_key(event.wiki)

    def evaluate(self, event: EditEvent, window: SlidingWindow) -> Alert | None:
        now = event.timestamp
        if self.in_cooldown(self.window_key(event), now):
            return None
        since = self.since(now)
        edits = window.count(since)
        bot_edits = window.bot_edits(since)
        bots = list(dict.fromkeys(edit.user for edit in bot_edits))
        if len(bot_edits) < self.rule.threshold or len(bots) < self.rule.min_users:
            return None
        ratio = len(bot_edits) / edits
        if ratio < self.max_bot_ratio:
            return None
        return self.build_alert(
            event,
            Severity.LOW,
            {
                "bot_edits": len(bot_edits),
                "edits": edits,
                "bot_ratio": round(ratio, 3),
                "distinct_users": len(bots),
                "users": bots[:MAX_EVIDENCE_ITEMS],
                "event_ids": [edit.event_id for edit in bot_edits[:MAX_EVIDENCE_ITEMS]],
            },
            title="*",
        )


DETECTOR_CLASSES: dict[RuleKind, type[Detector]] = {
    RuleKind.REVERT_WAR: RevertWarDetector,
    RuleKind.BURST: BurstDetector,
    RuleKind.BOT_SPIKE: BotSpikeDetector,
}


def create_detector(rule: DetectionRule) -> Detector:
    """Factory: the Detector class that matches the rule kind."""
    return DETECTOR_CLASSES[rule.kind](rule)
