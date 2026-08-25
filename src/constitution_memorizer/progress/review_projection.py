"""Canonical remaining-review projection for real and hypothetical progress.

Calendar, Google Calendar sync, and LearningPlanner all import from here so
``INTERVAL_LADDER`` is walked in one place.
"""

from __future__ import annotations

from datetime import date, timedelta

from constitution_memorizer.progress.repository import ProgressRecord
from constitution_memorizer.progress.scheduler import (
    DEFAULT_EASE_FACTOR,
    INTERVAL_LADDER,
    advance_interval,
)


def remaining_review_schedule(row: ProgressRecord) -> list[tuple[date, int]]:
    """
    Project remaining spaced-repetition dates for a progress row.

    Starts at ``next_revision`` (current rung = ``interval_days``), then assumes
    on-time completion for each later step of ``INTERVAL_LADDER``
    (1 → 3 → 7 → 15 → 30 → 60).
    """
    if row.next_revision is None or row.status not in ("review", "mastered"):
        return []
    cursor = row.next_revision
    current = row.interval_days if row.interval_days > 0 else INTERVAL_LADDER[0]
    out: list[tuple[date, int]] = [(cursor, current)]
    while True:
        nxt = advance_interval(current)
        if nxt is None:
            break
        cursor = cursor + timedelta(days=nxt)
        out.append((cursor, nxt))
        current = nxt
    return out


def projected_reviews_after_new_completion(
    learned_on: date,
) -> list[tuple[date, int]]:
    """Full remaining ladder as if a new unit was first completed on ``learned_on``."""
    first = INTERVAL_LADDER[0]
    synthetic = ProgressRecord(
        learning_unit_id="__hypothetical__",
        status="review",
        times_completed=1,
        last_completed=learned_on,
        next_revision=learned_on + timedelta(days=first),
        interval_days=first,
        ease_factor=DEFAULT_EASE_FACTOR,
        created_at="",
        updated_at="",
    )
    return remaining_review_schedule(synthetic)
