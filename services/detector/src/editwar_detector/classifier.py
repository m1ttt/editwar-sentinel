"""Decides if an edit is a revert of an earlier edit."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from editwar_detector.window import SlidingWindow
from editwar_domain import EditEvent

REASON_COMMENT = "comment"
REASON_SIZE_RESTORE = "size_restore"

# Edit summaries that MediaWiki, rollback and the usual tools write for a revert.
# They are matched case-insensitively against the whole comment, so a leading
# "/* Section */" does not matter.
DEFAULT_REVERT_PATTERNS = [
    # English
    r"\breverted\b",  # rollback: "Reverted edits by X (talk) to last revision by Y"
    r"\breverting\b",  # Huggle: "Reverting edit(s) by X"
    r"\brevert\b",  # free text: "revert vandalism"
    r"\bundid revision\b",  # undo: "Undid revision 123 by X (talk)"
    r"\brestored revision\b",  # "Restored revision 123 by X"
    r"\brvv?\b",  # short forms: "rv", "rvv" (revert vandalism)
    # Spanish
    r"\brevertidos los cambios\b",  # rollback: "Revertidos los cambios de X a la última..."
    r"\bdeshecha la (revisión|edición)\b",  # undo: "Deshecha la revisión 123 de X"
    r"\brevertir\b",
    r"\brevertid[oa]s?\b",
    r"\brestaurad[ao] la (revisión|versión)\b",
]


# Summaries that name the author of the undone edit, followed by that user.
# MediaWiki writes the user as a link ("[[Special:Contributions/X|X]]"), older
# tools and some wikis as plain text ("X (talk)"). Summaries such as
# "Restored revision N by X" or "Revert to revision N by X" are left out on
# purpose: there X wrote the version that came back, not the one undone.
_DIFF_OR_NUMBER = r"(?:\[\[[^\]]*\]\]|(?:edici[oó]n|revisi[oó]n)?\s*\d+)"
_REVERTED_USER_LEADS = [
    # English
    r"\breverted (?:\d+ )?edits? by",  # rollback, Twinkle
    r"\breverting (?:edit\(s\)|edits?) by",  # Huggle
    rf"\bundid revision\s+{_DIFF_OR_NUMBER}\s+by",  # undo
    # Spanish
    r"\brevertidos los cambios de",  # rollback
    rf"\bdeshecha la\s+{_DIFF_OR_NUMBER}\s+de",  # undo
    r"\brevertid[oa]s? (?:\d+ )?(?:ediciones|edici[oó]n|cambios) de",
]
_USER = (
    r"\s*(?:"
    # [[Special:Contributions/X|X]] or [[Especial:Contribuciones/X|X]]
    r"\[\[\s*(?:special|especial)\s*:\s*(?:contributions|contribuciones)/(?P<contrib>[^\]|]+)"
    r"|\[\[\s*(?:user|usuario|usuaria)\s*:\s*(?P<page>[^\]|/]+)"  # [[User:X|X]]
    # plain text, up to "(talk)", ": reason", "," or "to last revision"
    r"|(?P<plain>[^\[\]()|,\s](?:[^\[\]()|,]*?[^\[\]()|,\s])?)"
    r"(?=\s*\(|:\s|\s*,|\s*$|\s+to\s|\s+a\s+la\s)"
    r")"
)
REVERTED_USER_PATTERNS = [re.compile(lead + _USER, re.IGNORECASE) for lead in _REVERTED_USER_LEADS]


def reverted_user_from_comment(comment: str) -> str | None:
    """Best-effort: the user whose edit a revert summary says was undone, or None."""
    for pattern in REVERTED_USER_PATTERNS:
        found = pattern.search(comment)
        if found is None:
            continue
        name = found.group("contrib") or found.group("page") or found.group("plain")
        name = name.replace("_", " ").strip()
        if name:
            return name
    return None


@dataclass(frozen=True, slots=True)
class RevertMatch:
    """Why an edit is a revert and, when known, whose edit it undid."""

    reason: str  # REASON_COMMENT or REASON_SIZE_RESTORE
    reverted_user: str | None = None


class RevertClassifier:
    """Finds reverts with two signals: the edit summary and a size restore."""

    def __init__(self, patterns: Iterable[str] | None = None) -> None:
        sources = DEFAULT_REVERT_PATTERNS if patterns is None else list(patterns)
        self.patterns = [re.compile(source, re.IGNORECASE) for source in sources]

    def matches_comment(self, comment: str) -> bool:
        """True when the edit summary says that the edit is a revert."""
        return any(pattern.search(comment) for pattern in self.patterns)

    def restored_edit(self, event: EditEvent, window: SlidingWindow) -> EditEvent | None:
        """The most recent earlier edit by another user that `event` undoes by size.

        The edit undoes it when it brings the article back to the size it had
        before that edit. Both edits must change the size, so two typo fixes
        of the same length are not a revert.
        """
        if event.size_delta() == 0:
            return None
        for earlier in window.recent():
            if earlier.event_id == event.event_id:
                continue
            if (
                earlier.user != event.user
                and earlier.size_delta() != 0
                and earlier.old_len == event.new_len
            ):
                return earlier
        return None

    def restores_size(self, event: EditEvent, window: SlidingWindow) -> bool:
        """True when the edit brings the article back to the size it had before
        an earlier edit by another user.
        """
        return self.restored_edit(event, window) is not None

    def match(self, event: EditEvent, window: SlidingWindow) -> RevertMatch | None:
        """Classify the edit and find whose edit it undid. None when it is not a revert.

        For a comment revert the user comes from the summary; when the summary
        does not name one, the size-restore match (if any) is used instead.
        """
        if self.matches_comment(event.comment):
            user = reverted_user_from_comment(event.comment)
            if user is None:
                restored = self.restored_edit(event, window)
                user = restored.user if restored is not None else None
            return RevertMatch(REASON_COMMENT, user)
        restored = self.restored_edit(event, window)
        if restored is not None:
            return RevertMatch(REASON_SIZE_RESTORE, restored.user)
        return None

    def classify(self, event: EditEvent, window: SlidingWindow) -> str | None:
        """Return "comment", "size_restore" or None when the edit is not a revert."""
        found = self.match(event, window)
        return None if found is None else found.reason

    def is_revert(self, event: EditEvent, window: SlidingWindow) -> bool:
        return self.classify(event, window) is not None
