"""Decides if an edit is a revert of an earlier edit."""

from __future__ import annotations

import re
from collections.abc import Iterable

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


class RevertClassifier:
    """Finds reverts with two signals: the edit summary and a size restore."""

    def __init__(self, patterns: Iterable[str] | None = None) -> None:
        sources = DEFAULT_REVERT_PATTERNS if patterns is None else list(patterns)
        self.patterns = [re.compile(source, re.IGNORECASE) for source in sources]

    def matches_comment(self, comment: str) -> bool:
        """True when the edit summary says that the edit is a revert."""
        return any(pattern.search(comment) for pattern in self.patterns)

    def restores_size(self, event: EditEvent, window: SlidingWindow) -> bool:
        """True when the edit brings the article back to the size it had before
        an earlier edit by another user.

        Both edits must change the size, so two typo fixes of the same length
        are not a revert.
        """
        if event.size_delta() == 0:
            return False
        for earlier in window.recent():
            if earlier.event_id == event.event_id:
                continue
            if (
                earlier.user != event.user
                and earlier.size_delta() != 0
                and earlier.old_len == event.new_len
            ):
                return True
        return False

    def classify(self, event: EditEvent, window: SlidingWindow) -> str | None:
        """Return "comment", "size_restore" or None when the edit is not a revert."""
        if self.matches_comment(event.comment):
            return REASON_COMMENT
        if self.restores_size(event, window):
            return REASON_SIZE_RESTORE
        return None

    def is_revert(self, event: EditEvent, window: SlidingWindow) -> bool:
        return self.classify(event, window) is not None
