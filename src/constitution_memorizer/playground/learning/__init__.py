"""Playground law-learning engine. Persistence is Playground-owned.

RecallC ideology (Read → Cloze → Letters → Type → Recite → Test) without
Constitution persistence, reminder scheduling, or LearningUnit rows.
"""

from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    PLAYGROUND_LEARN_MODES_SET,
    PLAYGROUND_MODE_DECK,
    PLAYGROUND_MODE_LABELS,
    PLAYGROUND_MODE_TASKS,
    is_playground_learn_mode,
    mode_index,
    next_learn_mode,
)

__all__ = [
    "PLAYGROUND_LEARN_MODES",
    "PLAYGROUND_LEARN_MODES_SET",
    "PLAYGROUND_MODE_DECK",
    "PLAYGROUND_MODE_LABELS",
    "PLAYGROUND_MODE_TASKS",
    "is_playground_learn_mode",
    "mode_index",
    "next_learn_mode",
]
