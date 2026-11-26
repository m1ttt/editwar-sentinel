"""DetectionEngine: keeps the windows and runs every registered detector."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from editwar_detector.classifier import RevertClassifier
from editwar_detector.detectors import SCOPE_WIKI, Detector, create_detector
from editwar_detector.window import WindowStore, article_key, wiki_key
from editwar_domain import (
    Alert,
    DetectionRule,
    EditEvent,
    RevertEvent,
    RuleValidationError,
)

log = logging.getLogger("editwar.detector.engine")

# Article windows keep at least this span, so the size-restore check of the
# classifier has history even when no article rule is enabled.
MIN_ARTICLE_SPAN_SECONDS = 300


@dataclass
class ProcessResult:
    """What one edit produced: the revert (if the edit is one) and the alerts."""

    revert: RevertEvent | None = None
    alerts: list[Alert] = field(default_factory=list)


class DetectionEngine:
    """Classifies reverts, updates the windows and evaluates every detector.

    Article windows use the key "wiki:title". Wiki-wide windows use the key
    "wiki:<wiki>" and live in a second store, because their rules use short
    spans and a whole wiki produces many edits.
    """

    def __init__(self, classifier: RevertClassifier | None = None) -> None:
        self.classifier = classifier or RevertClassifier()
        self.detectors: dict[uuid.UUID, Detector] = {}
        self.articles = WindowStore(MIN_ARTICLE_SPAN_SECONDS)
        self.wikis = WindowStore(0)

    def register(self, detector: Detector) -> None:
        """Add a detector, or replace the one with the same rule id."""
        self.detectors[detector.rule.id] = detector
        self._update_spans()

    def unregister(self, rule_id: uuid.UUID) -> bool:
        """Remove the detector of `rule_id`. Return False when it was not registered."""
        removed = self.detectors.pop(rule_id, None) is not None
        self._update_spans()
        return removed

    def reload_rules(self, rules: Iterable[DetectionRule]) -> None:
        """Hot reload: add new rules, update changed ones, remove deleted or disabled ones."""
        wanted: dict[uuid.UUID, DetectionRule] = {}
        for rule in rules:
            try:
                rule.validate()
            except RuleValidationError as error:
                log.warning("skipping invalid rule %s: %s", rule.id, error)
                continue
            if rule.enabled:
                wanted[rule.id] = rule

        for rule_id in list(self.detectors):
            if rule_id not in wanted:
                self.unregister(rule_id)
                log.info("rule %s removed", rule_id)

        for rule in wanted.values():
            current = self.detectors.get(rule.id)
            if current is None or current.rule.kind != rule.kind:
                self.register(create_detector(rule))
                log.info("rule %s (%s) loaded", rule.name, rule.kind.value)
            elif current.rule != rule:
                current.update_rule(rule)
                log.info("rule %s (%s) updated", rule.name, rule.kind.value)
        self._update_spans()

    def process(self, event: EditEvent) -> ProcessResult:
        """Handle one edit and return the revert and the alerts it produced."""
        now = event.timestamp
        result = ProcessResult()

        # 1. Classify before adding the edit: size restore compares with earlier edits.
        article = self.articles.get(article_key(event))
        article.evict(now)
        found = self.classifier.match(event, article)
        article.add(event)
        if found is not None:
            # Same event_id as the edit, so the alert timeline can mark it as a revert.
            result.revert = RevertEvent(
                event_id=event.event_id,
                wiki=event.wiki,
                title=event.title,
                user=event.user,
                timestamp=event.timestamp,
                reason=found.reason,
                server_url=event.server_url,
                reverted_user=found.reverted_user,
            )
            article.add_revert(result.revert)

        # 2. Wiki-wide window, only when a wiki rule needs it.
        if self.wikis.span_seconds > 0:
            wiki = self.wikis.get(wiki_key(event.wiki))
            wiki.evict(now)
            wiki.add(event)

        # 3. Evaluate every detector. One failing detector must not stop the others.
        for detector in list(self.detectors.values()):
            store = self.wikis if detector.scope == SCOPE_WIKI else self.articles
            try:
                alert = detector.evaluate(event, store.get(detector.window_key(event)))
            except Exception:
                log.exception("detector for rule %s failed", detector.rule.id)
                continue
            if alert is not None:
                result.alerts.append(alert)
        return result

    def prune(self, now: datetime) -> int:
        """Free empty windows and expired cooldowns. Return windows freed."""
        for detector in self.detectors.values():
            detector.forget_before(now)
        return self.articles.prune(now) + self.wikis.prune(now)

    def rule_count(self) -> int:
        return len(self.detectors)

    def window_count(self) -> int:
        return self.articles.size() + self.wikis.size()

    def _update_spans(self) -> None:
        """Size each store to the largest window of the detectors that read it."""
        article_spans = [MIN_ARTICLE_SPAN_SECONDS]
        wiki_spans = [0]
        for detector in self.detectors.values():
            spans = wiki_spans if detector.scope == SCOPE_WIKI else article_spans
            spans.append(detector.rule.window_seconds)
        self.articles.set_span(max(article_spans))
        self.wikis.set_span(max(wiki_spans))
