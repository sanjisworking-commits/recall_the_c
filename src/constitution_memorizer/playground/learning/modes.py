"""Authoritative Playground learn-mode registry.

Type is the write-it-out method. There is no seventh Write mode.
"""

from __future__ import annotations

PLAYGROUND_LEARN_MODES: tuple[str, ...] = (
    "read",
    "cloze",
    "letters",
    "type",
    "recite",
    "test",
)
PLAYGROUND_LEARN_MODES_SET: frozenset[str] = frozenset(PLAYGROUND_LEARN_MODES)

PLAYGROUND_MODE_LABELS: dict[str, str] = {
    "read": "Read",
    "cloze": "Cloze",
    "letters": "Letters",
    "type": "Type",
    "recite": "Recite",
    "test": "Test",
}

PLAYGROUND_MODE_TASKS: dict[str, str] = {
    "read": "First, read it once.",
    "cloze": "Fill the gaps from memory.",
    "letters": "Rebuild it from first letters.",
    "type": "Write it out, word for word.",
    "recite": "Now recall it without looking.",
    "test": "A short checkpoint.",
}

PLAYGROUND_MODE_DECK: dict[str, tuple[str, str]] = {
    "read": ("Read it closely", "Bare Act wording, verbatim."),
    "cloze": ("Fill the gaps", "Tap a blank when you have the word."),
    "letters": ("First letters only", "Rebuild the clause from initials."),
    "type": ("Write it out", "Type it from memory — checked as you go."),
    "recite": ("Say it aloud", "Speak the clause; stop for your accuracy map."),
    "test": ("Quick check", "A short checkpoint on this provision."),
}

TOTAL_PLAYGROUND_MODES = len(PLAYGROUND_LEARN_MODES)


def is_playground_learn_mode(mode: str) -> bool:
    return mode in PLAYGROUND_LEARN_MODES_SET


def mode_index(mode: str) -> int:
    try:
        return PLAYGROUND_LEARN_MODES.index(mode)
    except ValueError:
        return -1


def next_learn_mode(completed: set[str] | frozenset[str] | tuple[str, ...]) -> str | None:
    done = set(completed)
    for mode in PLAYGROUND_LEARN_MODES:
        if mode not in done:
            return mode
    return None
