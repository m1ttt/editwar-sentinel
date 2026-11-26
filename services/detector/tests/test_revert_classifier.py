import pytest

from editwar_detector.classifier import REASON_COMMENT, REASON_SIZE_RESTORE, RevertClassifier
from editwar_detector.window import SlidingWindow

# Edit summaries in the format that MediaWiki and the common tools write.
COMMENT_CASES = [
    # English: rollback, undo, Twinkle, Huggle, short forms
    ("Reverted edits by 203.0.113.7 (talk) to last revision by ClueBot NG", True),
    ("Reverted 2 edits by Example (talk): unsourced", True),
    ("Undid revision 1187654321 by Example (talk)", True),
    ("Restored revision 1187654000 by Example (talk): rv vandalism", True),
    ("Reverting edit(s) by Example (talk) to rev. 1187 by Other (HG) (3.4.12)", True),
    ("/* Early life */ rv unsourced claim", True),
    ("rvv", True),
    ("revert, see talk page", True),
    # Spanish: rollback, undo, free text
    ("Revertidos los cambios de 198.51.100.2 (disc.) a la última edición de SeroBOT", True),
    ("Deshecha la revisión 154321987 de Ejemplo (disc.)", True),
    ("Deshecha la edición 154321987 de Ejemplo", True),
    ("Revertido a la versión anterior por vandalismo", True),
    ("revertir vandalismo", True),
    ("Restaurada la revisión 154321000", True),
    # Not reverts
    ("Fixed typo", False),
    ("Added reference to the 2024 census", False),
    ("/* History */ copyedit", False),
    ("convert units", False),
    ("Updated server list", False),
    ("preserve formatting", False),
    ("Revisión de estilo", False),
    ("Añadida referencia", False),
    ("", False),
]


@pytest.mark.parametrize(("comment", "expected"), COMMENT_CASES)
def test_comment_patterns(comment, expected):
    assert RevertClassifier().matches_comment(comment) is expected


def test_classify_by_comment(make_event):
    event = make_event(comment="Undid revision 1 by X")
    assert RevertClassifier().classify(event, SlidingWindow(60)) == REASON_COMMENT


def test_size_restore_by_another_user(make_event, clock):
    window = SlidingWindow(3600)
    window.add(make_event(user="Vandal", old_len=1000, new_len=1500))
    clock.advance(30)
    revert = make_event(user="Patroller", old_len=1500, new_len=1000, comment="")
    classifier = RevertClassifier()
    assert classifier.classify(revert, window) == REASON_SIZE_RESTORE
    assert classifier.is_revert(revert, window)


def test_size_restore_ignores_same_user(make_event):
    window = SlidingWindow(3600)
    window.add(make_event(user="Alice", old_len=1000, new_len=1500))
    event = make_event(user="Alice", old_len=1500, new_len=1000)
    assert RevertClassifier().classify(event, window) is None


def test_size_restore_ignores_zero_size_changes(make_event):
    window = SlidingWindow(3600)
    window.add(make_event(user="Alice", old_len=1000, new_len=1000))
    event = make_event(user="Bob", old_len=1000, new_len=1000)
    assert RevertClassifier().classify(event, window) is None


def test_size_restore_ignores_the_event_itself(make_event):
    window = SlidingWindow(3600)
    event = make_event(user="Bob", old_len=1000, new_len=1000 + 5)
    window.add(event)
    assert not RevertClassifier().restores_size(event, window)


def test_ordinary_edit_is_not_a_revert(make_event):
    window = SlidingWindow(3600)
    window.add(make_event(user="Alice", old_len=1000, new_len=1200))
    event = make_event(user="Bob", old_len=1200, new_len=1300)
    assert not RevertClassifier().is_revert(event, window)


def test_custom_patterns():
    classifier = RevertClassifier(patterns=[r"\bannulé\b"])
    assert classifier.matches_comment("Annulé la modification 123")
    assert not classifier.matches_comment("Reverted edits by X")
