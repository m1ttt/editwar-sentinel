import pytest

from editwar_detector.classifier import (
    REASON_COMMENT,
    REASON_SIZE_RESTORE,
    RevertClassifier,
    RevertMatch,
    reverted_user_from_comment,
)
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


# Summaries as MediaWiki writes them in the recentchange stream (wikitext links)
# and in plain text, with the user whose edit was undone.
REVERTED_USER_CASES = [
    (
        "Undid revision [[Special:Diff/1387916198|1387916198]] by "
        "[[Special:Contributions/Vebasebali99|Vebasebali99]] ([[User talk:Vebasebali99|talk]])",
        "Vebasebali99",
    ),
    (
        "Reverted edits by [[Special:Contributions/203.0.113.7|203.0.113.7]] "
        "([[User talk:203.0.113.7|talk]]) to last revision by ClueBot NG",
        "203.0.113.7",
    ),
    ("Reverted edits by 203.0.113.7 (talk) to last revision by ClueBot NG", "203.0.113.7"),
    ("Reverted 2 edits by Some User (talk): unsourced", "Some User"),
    ("Reverted 1 edit by 2001:db8::1: vandalism", "2001:db8::1"),
    ("Undid revision 1187654321 by Example (talk)", "Example"),
    ("Reverting edit(s) by Example (talk) to rev. 1187 by Other (HG) (3.4.12)", "Example"),
    ("Reverted edits by [[User:Alice|Alice]]", "Alice"),
    (
        "Revertidos los cambios de [[Special:Contributions/Foo_Bar|Foo Bar]] "
        "([[User talk:Foo Bar|disc.]]) a la última edición de SeroBOT",
        "Foo Bar",
    ),
    (
        "Revertidos los cambios de 198.51.100.2 (disc.) a la última edición de SeroBOT",
        "198.51.100.2",
    ),
    (
        "Deshecha la [[Especial:Diff/176466579|edición 176466579]] de "
        "[[Especial:Contribuciones/Nautv|Nautv]] ([[Usuario Discusión:Nautv|disc.]])",
        "Nautv",
    ),
    ("Deshecha la revisión 154321987 de Ejemplo (disc.)", "Ejemplo"),
    ("Deshecha la edición 154321987 de Ejemplo", "Ejemplo"),
    # The user named here wrote the restored version, not the undone one.
    ("Restored revision 1187654000 by Example (talk): rv vandalism", None),
    ("Revert to revision 1187654000 by Example", None),
    ("rvv", None),
    ("revert, see talk page", None),
    ("Reverted edits by", None),
    ("", None),
]


@pytest.mark.parametrize(("comment", "expected"), REVERTED_USER_CASES)
def test_reverted_user_from_comment(comment, expected):
    assert reverted_user_from_comment(comment) == expected


def test_match_comment_revert_names_the_reverted_user(make_event):
    event = make_event(user="Bob", comment="Undid revision 5 by Alice (talk)")
    assert RevertClassifier().match(event, SlidingWindow(60)) == RevertMatch(
        REASON_COMMENT, "Alice"
    )


def test_match_comment_revert_falls_back_to_size_restore(make_event, clock):
    window = SlidingWindow(3600)
    window.add(make_event(user="Vandal", old_len=1000, new_len=1500))
    clock.advance(10)
    event = make_event(user="Patroller", old_len=1500, new_len=1000, comment="rvv")
    assert RevertClassifier().match(event, window) == RevertMatch(REASON_COMMENT, "Vandal")


def test_match_comment_revert_without_any_user(make_event):
    event = make_event(user="Bob", comment="rv")
    assert RevertClassifier().match(event, SlidingWindow(60)) == RevertMatch(REASON_COMMENT)


def test_match_size_restore_names_the_restored_edit_author(make_event, clock):
    window = SlidingWindow(3600)
    window.add(make_event(user="Older", old_len=1000, new_len=1200))
    clock.advance(10)
    window.add(make_event(user="Vandal", old_len=1200, new_len=1500))
    clock.advance(10)
    event = make_event(user="Patroller", old_len=1500, new_len=1200, comment="")
    found = RevertClassifier().match(event, window)
    assert found == RevertMatch(REASON_SIZE_RESTORE, "Vandal")
    assert RevertClassifier().restored_edit(event, window).user == "Vandal"


def test_match_not_a_revert(make_event):
    assert RevertClassifier().match(make_event(), SlidingWindow(60)) is None
