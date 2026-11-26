import logging
import uuid

from editwar_detector.detectors import BurstDetector, Detector, RevertWarDetector
from editwar_detector.engine import MIN_ARTICLE_SPAN_SECONDS, DetectionEngine
from editwar_domain import DetectionRule, RuleKind, default_rules


def rule(kind=RuleKind.BURST, threshold=1, min_users=1, window_seconds=600, **kwargs):
    return DetectionRule(
        name=f"rule {kind}",
        kind=kind,
        window_seconds=window_seconds,
        threshold=threshold,
        min_users=min_users,
        **kwargs,
    )


class FakeDetector(Detector):
    """Records the events it sees and returns a fixed answer."""

    kind = RuleKind.BURST

    def __init__(self, rule, answer=None, error=None):
        super().__init__(rule)
        self.answer = answer
        self.error = error
        self.seen = []

    def evaluate(self, event, window):
        self.seen.append((event, window.count()))
        if self.error is not None:
            raise self.error
        return self.answer


def test_register_and_unregister():
    engine = DetectionEngine()
    detector = FakeDetector(rule())
    engine.register(detector)
    assert engine.rule_count() == 1
    assert engine.unregister(detector.rule.id) is True
    assert engine.unregister(detector.rule.id) is False
    assert engine.rule_count() == 0


def test_process_adds_event_before_evaluating(make_event):
    engine = DetectionEngine()
    detector = FakeDetector(rule())
    engine.register(detector)
    engine.process(make_event())
    engine.process(make_event())
    assert [count for _, count in detector.seen] == [1, 2]


def test_process_returns_revert_and_alerts(make_event, clock):
    engine = DetectionEngine()
    engine.register(RevertWarDetector(rule(RuleKind.REVERT_WAR, threshold=2, min_users=2)))

    first = engine.process(make_event(user="A", comment="Undid revision 1 by B"))
    assert first.revert is not None
    assert first.revert.reason == "comment"
    assert first.revert.user == "A"
    assert first.alerts == []

    clock.advance(5)
    second = engine.process(make_event(user="B", comment="Reverted edits by A"))
    assert second.revert is not None
    assert len(second.alerts) == 1
    assert second.alerts[0].kind == "revert_war"


def test_process_detects_size_restore(make_event, clock):
    engine = DetectionEngine()
    assert engine.process(make_event(user="A", old_len=100, new_len=900)).revert is None
    clock.advance(5)
    result = engine.process(make_event(user="B", old_len=900, new_len=100, comment=""))
    assert result.revert is not None
    assert result.revert.reason == "size_restore"


def test_failing_detector_does_not_stop_others(make_event, caplog):
    engine = DetectionEngine()
    broken = FakeDetector(rule(), error=RuntimeError("boom"))
    working = BurstDetector(rule(RuleKind.BURST, threshold=1, min_users=1))
    engine.register(broken)
    engine.register(working)
    with caplog.at_level(logging.ERROR, logger="editwar.detector.engine"):
        result = engine.process(make_event())
    assert len(result.alerts) == 1
    assert "failed" in caplog.text


def test_wiki_window_only_with_wiki_rules(make_event):
    engine = DetectionEngine()
    engine.reload_rules([rule(RuleKind.BURST, threshold=99)])
    engine.process(make_event())
    assert engine.wikis.size() == 0
    assert engine.articles.size() == 1

    engine.reload_rules([rule(RuleKind.BOT_SPIKE, threshold=2, window_seconds=60)])
    bot = make_event(user="Bot1", is_bot=True)
    engine.process(bot)
    result = engine.process(make_event(user="Bot1", is_bot=True, title="Other"))
    assert engine.wikis.size() == 1
    assert len(result.alerts) == 1
    assert result.alerts[0].title == "*"


def test_reload_rules_adds_updates_and_removes():
    engine = DetectionEngine()
    keep = rule(RuleKind.REVERT_WAR, threshold=3)
    drop = rule(RuleKind.BURST, threshold=10)
    engine.reload_rules([keep, drop])
    assert engine.rule_count() == 2
    detector = engine.detectors[keep.id]

    changed = DetectionRule.from_dict({**keep.to_dict(), "threshold": 5})
    new = rule(RuleKind.BOT_SPIKE, threshold=50, window_seconds=60)
    engine.reload_rules([changed, new])

    assert set(engine.detectors) == {keep.id, new.id}
    assert engine.detectors[keep.id] is detector  # updated in place, cooldown kept
    assert detector.rule.threshold == 5


def test_reload_rules_unchanged_rule_keeps_object():
    engine = DetectionEngine()
    first = rule()
    engine.reload_rules([first])
    detector = engine.detectors[first.id]
    same = DetectionRule.from_dict(first.to_dict())
    engine.reload_rules([same])
    assert engine.detectors[first.id] is detector
    assert detector.rule is first


def test_reload_rules_kind_change_replaces_detector():
    engine = DetectionEngine()
    first = rule(RuleKind.BURST)
    engine.reload_rules([first])
    changed = rule(RuleKind.REVERT_WAR, id=first.id)
    engine.reload_rules([changed])
    assert isinstance(engine.detectors[first.id], RevertWarDetector)


def test_reload_rules_skips_disabled_and_invalid(caplog):
    engine = DetectionEngine()
    disabled = rule(enabled=False)
    invalid = rule(threshold=0)
    good = rule()
    with caplog.at_level(logging.WARNING, logger="editwar.detector.engine"):
        engine.reload_rules([disabled, invalid, good])
    assert set(engine.detectors) == {good.id}
    assert "invalid rule" in caplog.text


def test_spans_follow_largest_enabled_rule():
    engine = DetectionEngine()
    engine.reload_rules(default_rules())
    assert engine.articles.span_seconds == 3600
    assert engine.wikis.span_seconds == 60

    engine.reload_rules([rule(RuleKind.BURST, window_seconds=120)])
    assert engine.articles.span_seconds == MIN_ARTICLE_SPAN_SECONDS
    assert engine.wikis.span_seconds == 0


def test_prune_frees_windows_and_cooldowns(make_event, clock):
    engine = DetectionEngine()
    engine.reload_rules([rule(RuleKind.BURST, window_seconds=60)])
    engine.process(make_event(title="A"))
    engine.process(make_event(title="B"))
    detector = engine.detectors[next(iter(engine.detectors))]
    assert engine.window_count() == 2
    assert len(detector.last_alert_at) == 2

    clock.advance(MIN_ARTICLE_SPAN_SECONDS + 1)
    assert engine.prune(clock.now) == 2
    assert engine.window_count() == 0
    assert detector.last_alert_at == {}


def test_unknown_rule_id_unregister():
    assert DetectionEngine().unregister(uuid.uuid4()) is False
