import pytest

from editwar_detector.detectors import (
    MAX_TIMELINE_ITEMS,
    BotSpikeDetector,
    BurstDetector,
    RevertWarDetector,
    create_detector,
)
from editwar_detector.window import SlidingWindow
from editwar_domain import DetectionRule, RevertEvent, RuleKind, Severity


def rule(kind, threshold, min_users, window_seconds=600):
    return DetectionRule(
        name=f"test {kind}",
        kind=kind,
        window_seconds=window_seconds,
        threshold=threshold,
        min_users=min_users,
    )


def add_reverts(window, make_event, users):
    """Add one edit and one revert per user, return the last edit."""
    event = None
    for user in users:
        event = make_event(user=user, comment="rv")
        window.add(event)
        window.add_revert(
            RevertEvent(
                event_id=event.event_id,
                wiki=event.wiki,
                title=event.title,
                user=user,
                timestamp=event.timestamp,
                reason="comment",
                server_url=event.server_url,
            )
        )
    return event


# --- RevertWarDetector -------------------------------------------------------


@pytest.mark.parametrize(
    ("users", "expected"),
    [
        (["A", "B"], None),  # below threshold
        (["A", "B", "A"], Severity.MEDIUM),  # exactly at threshold
        (["A", "B", "A", "B", "A"], Severity.MEDIUM),  # above threshold
        (["A", "B", "A", "B", "A", "B"], Severity.HIGH),  # twice the threshold
    ],
)
def test_revert_war_threshold(make_event, users, expected):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, threshold=3, min_users=2))
    window = SlidingWindow(600)
    event = add_reverts(window, make_event, users)
    alert = detector.evaluate(event, window)
    if expected is None:
        assert alert is None
    else:
        assert alert is not None
        assert alert.severity is expected
        assert alert.kind == "revert_war"
        assert alert.title == event.title
        assert alert.evidence["reverts"] == len(users)
        assert alert.evidence["distinct_users"] == 2
        assert alert.evidence["rule"] == "test revert_war"
        assert alert.evidence["window_seconds"] == 600
        assert alert.created_at == event.timestamp


def test_revert_war_needs_min_users(make_event):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, threshold=3, min_users=2))
    window = SlidingWindow(600)
    event = add_reverts(window, make_event, ["A", "A", "A", "A"])
    assert detector.evaluate(event, window) is None


def test_revert_war_counts_only_inside_rule_window(make_event, clock):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 3, 2, window_seconds=60))
    window = SlidingWindow(3600)  # the store keeps more than this rule needs
    add_reverts(window, make_event, ["A", "B"])
    clock.advance(120)
    event = add_reverts(window, make_event, ["A"])
    assert detector.evaluate(event, window) is None


def test_revert_war_cooldown(make_event, clock):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 3, 2), cooldown_seconds=300)
    window = SlidingWindow(600)
    event = add_reverts(window, make_event, ["A", "B", "A"])
    assert detector.evaluate(event, window) is not None

    clock.advance(10)
    event = add_reverts(window, make_event, ["B"])
    assert detector.evaluate(event, window) is None  # same war, still in cooldown

    clock.advance(300)
    event = add_reverts(window, make_event, ["A", "B", "A"])
    assert detector.evaluate(event, window) is not None


def test_cooldown_defaults_to_rule_window(make_event, clock):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 1, 1, window_seconds=100))
    window = SlidingWindow(600)
    assert detector.evaluate(add_reverts(window, make_event, ["A"]), window) is not None
    clock.advance(99)
    assert detector.evaluate(add_reverts(window, make_event, ["A"]), window) is None
    clock.advance(1)
    assert detector.evaluate(add_reverts(window, make_event, ["A"]), window) is not None


def test_cooldown_is_per_article(make_event):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 1, 1))
    first = SlidingWindow(600)
    assert detector.evaluate(add_reverts(first, make_event, ["A"]), first) is not None
    other = SlidingWindow(600)
    event = make_event(title="Other article", comment="rv")
    other.add(event)
    other.add_revert(
        RevertEvent(event.event_id, event.wiki, event.title, "A", event.timestamp, "comment", "x")
    )
    assert detector.evaluate(event, other) is not None


def test_forget_before_drops_expired_cooldowns(make_event, clock):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 1, 1), cooldown_seconds=60)
    window = SlidingWindow(600)
    detector.evaluate(add_reverts(window, make_event, ["A"]), window)
    assert len(detector.last_alert_at) == 1
    clock.advance(30)
    detector.forget_before(clock.now)
    assert len(detector.last_alert_at) == 1
    clock.advance(31)
    detector.forget_before(clock.now)
    assert detector.last_alert_at == {}


def test_evidence_lists_are_capped(make_event):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 3, 2))
    window = SlidingWindow(600)
    users = [f"user{i}" for i in range(15)]
    event = add_reverts(window, make_event, users)
    alert = detector.evaluate(event, window)
    assert alert is not None
    assert len(alert.evidence["users"]) == 10
    assert len(alert.evidence["event_ids"]) == 10
    assert alert.evidence["event_ids"][0] == event.event_id  # newest first


def test_update_rule_keeps_cooldown(make_event):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 1, 1))
    window = SlidingWindow(600)
    detector.evaluate(add_reverts(window, make_event, ["A"]), window)
    new_rule = rule(RuleKind.REVERT_WAR, 5, 1)
    detector.update_rule(new_rule)
    assert detector.rule is new_rule
    assert len(detector.last_alert_at) == 1


# --- BurstDetector -----------------------------------------------------------


def fill(window, make_event, users, **kwargs):
    event = None
    for user in users:
        event = make_event(user=user, **kwargs)
        window.add(event)
    return event


@pytest.mark.parametrize(
    ("count", "fires"),
    [(4, False), (5, True), (8, True)],
)
def test_burst_threshold(make_event, count, fires):
    detector = BurstDetector(rule(RuleKind.BURST, threshold=5, min_users=3))
    window = SlidingWindow(600)
    users = ["A", "B", "C", "D", "E", "F", "G", "H"][:count]
    event = fill(window, make_event, users)
    alert = detector.evaluate(event, window)
    assert (alert is not None) is fires
    if alert is not None:
        assert alert.severity is Severity.MEDIUM
        assert alert.evidence["edits"] == count
        assert alert.evidence["distinct_users"] == count


def test_burst_needs_min_users(make_event):
    detector = BurstDetector(rule(RuleKind.BURST, threshold=5, min_users=3))
    window = SlidingWindow(600)
    event = fill(window, make_event, ["A", "B", "A", "B", "A", "B"])
    assert detector.evaluate(event, window) is None


def test_burst_cooldown(make_event, clock):
    detector = BurstDetector(rule(RuleKind.BURST, 2, 2), cooldown_seconds=60)
    window = SlidingWindow(600)
    assert detector.evaluate(fill(window, make_event, ["A", "B"]), window) is not None
    clock.advance(30)
    assert detector.evaluate(fill(window, make_event, ["C"]), window) is None
    clock.advance(30)
    assert detector.evaluate(fill(window, make_event, ["D"]), window) is not None


# --- BotSpikeDetector --------------------------------------------------------


def test_bot_spike_at_threshold(make_event):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, threshold=4, min_users=2))
    window = SlidingWindow(60)
    event = fill(window, make_event, ["Bot1", "Bot2", "Bot1", "Bot2"], is_bot=True)
    alert = detector.evaluate(event, window)
    assert alert is not None
    assert alert.title == "*"
    assert alert.severity is Severity.LOW
    assert alert.evidence["bot_edits"] == 4
    assert alert.evidence["bot_ratio"] == 1.0
    assert alert.page_url().endswith("Special:RecentChanges")
    assert detector.window_key(event) == "wiki:enwiki"


def test_bot_spike_above_threshold(make_event):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, threshold=4, min_users=2))
    window = SlidingWindow(60)
    event = fill(window, make_event, ["Bot1", "Bot2", "Bot3"] * 3, is_bot=True)
    alert = detector.evaluate(event, window)
    assert alert is not None
    assert alert.evidence["bot_edits"] == 9
    assert alert.evidence["distinct_users"] == 3


def test_bot_spike_below_threshold(make_event):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, threshold=4, min_users=1))
    window = SlidingWindow(60)
    event = fill(window, make_event, ["Bot1", "Bot1", "Bot1"], is_bot=True)
    assert detector.evaluate(event, window) is None


def test_bot_spike_needs_distinct_bots(make_event):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, threshold=3, min_users=2))
    window = SlidingWindow(60)
    event = fill(window, make_event, ["Bot1", "Bot1", "Bot1"], is_bot=True)
    assert detector.evaluate(event, window) is None


def test_bot_spike_needs_bot_ratio(make_event):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, 4, 1), max_bot_ratio=0.8)
    window = SlidingWindow(60)
    fill(window, make_event, ["Bot1"] * 4, is_bot=True)
    event = fill(window, make_event, ["Human1", "Human2"])  # ratio 4/6
    assert detector.evaluate(event, window) is None

    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, 4, 1), max_bot_ratio=0.6)
    assert detector.evaluate(event, window) is not None


def test_bot_spike_cooldown(make_event, clock):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, 2, 1, window_seconds=60))
    window = SlidingWindow(60)
    assert detector.evaluate(fill(window, make_event, ["B", "B"], is_bot=True), window)
    clock.advance(5)
    assert detector.evaluate(fill(window, make_event, ["B"], is_bot=True), window) is None


# --- factory -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "cls"),
    [
        (RuleKind.REVERT_WAR, RevertWarDetector),
        (RuleKind.BURST, BurstDetector),
        (RuleKind.BOT_SPIKE, BotSpikeDetector),
    ],
)
def test_create_detector(kind, cls):
    detector = create_detector(rule(kind, 1, 1))
    assert isinstance(detector, cls)
    assert detector.kind is kind


# --- timeline evidence -------------------------------------------------------

TIMELINE_KEYS = {
    "event_id",
    "user",
    "is_bot",
    "timestamp",
    "comment",
    "rev_id",
    "old_rev_id",
    "old_len",
    "new_len",
    "size_delta",
    "is_revert",
    "revert_reason",
    "reverted_user",
    "diff_url",
}


def test_revert_war_timeline_entries(make_event, clock):
    detector = RevertWarDetector(rule(RuleKind.REVERT_WAR, 1, 1))
    window = SlidingWindow(600)
    edit = make_event(user="Vandal", old_len=1000, new_len=1400, comment="spam", is_bot=False)
    window.add(edit)
    clock.advance(10)
    revert_edit = make_event(user="Patroller", old_len=1400, new_len=1000, comment="")
    window.add(revert_edit)
    window.add_revert(
        RevertEvent(
            event_id=revert_edit.event_id,
            wiki=revert_edit.wiki,
            title=revert_edit.title,
            user="Patroller",
            timestamp=revert_edit.timestamp,
            reason="size_restore",
            server_url=revert_edit.server_url,
            reverted_user="Vandal",
        )
    )
    alert = detector.evaluate(revert_edit, window)
    assert alert is not None
    first, second = alert.evidence["timeline"]
    assert set(first) == TIMELINE_KEYS
    assert first == {
        "event_id": edit.event_id,
        "user": "Vandal",
        "is_bot": False,
        "timestamp": edit.timestamp.isoformat(),
        "comment": "spam",
        "rev_id": edit.rev_id,
        "old_rev_id": edit.old_rev_id,
        "old_len": 1000,
        "new_len": 1400,
        "size_delta": 400,
        "is_revert": False,
        "revert_reason": None,
        "reverted_user": None,
        "diff_url": edit.diff_url(),
    }
    assert second["is_revert"] is True
    assert second["revert_reason"] == "size_restore"
    assert second["reverted_user"] == "Vandal"
    assert second["size_delta"] == -400
    assert alert.evidence["timeline_truncated"] is False
    # existing evidence keys are still there
    assert {"reverts", "distinct_users", "users", "event_ids"} <= set(alert.evidence)


def test_timeline_is_oldest_first_and_capped(make_event, clock):
    detector = BurstDetector(rule(RuleKind.BURST, threshold=5, min_users=2))
    window = SlidingWindow(600)
    events = []
    for n in range(30):
        events.append(make_event(user=f"user{n % 3}"))
        window.add(events[-1])
        clock.advance(1)
    alert = detector.evaluate(events[-1], window)
    assert alert is not None
    timeline = alert.evidence["timeline"]
    assert len(timeline) == MAX_TIMELINE_ITEMS == 25
    assert [entry["event_id"] for entry in timeline] == [e.event_id for e in events[5:]]
    stamps = [entry["timestamp"] for entry in timeline]
    assert stamps == sorted(stamps)
    assert alert.evidence["timeline_truncated"] is True
    assert all(entry["is_revert"] is False for entry in timeline)


def test_timeline_only_has_edits_inside_rule_window(make_event, clock):
    detector = BurstDetector(rule(RuleKind.BURST, threshold=2, min_users=2, window_seconds=60))
    window = SlidingWindow(3600)
    window.add(make_event(user="Old"))
    clock.advance(120)
    fill(window, make_event, ["A"])
    event = fill(window, make_event, ["B"])
    alert = detector.evaluate(event, window)
    assert alert is not None
    assert [entry["user"] for entry in alert.evidence["timeline"]] == ["A", "B"]


def test_bot_spike_has_no_timeline(make_event):
    detector = BotSpikeDetector(rule(RuleKind.BOT_SPIKE, threshold=2, min_users=1))
    window = SlidingWindow(60)
    alert = detector.evaluate(fill(window, make_event, ["Bot1", "Bot1"], is_bot=True), window)
    assert alert is not None
    assert "timeline" not in alert.evidence
    assert "timeline_truncated" not in alert.evidence
