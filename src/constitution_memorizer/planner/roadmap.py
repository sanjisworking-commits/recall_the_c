"""Persisted rolling 15-day Auto NEW roadmap.

Occupancy math stays in ``planner.planner`` (actual SRS + hypothetical reviews
from current/future unskipped NEW). This module only assigns exact unit IDs
inside ``[as_of, as_of+14]`` and never writes ``plan_date < as_of``.
"""

from __future__ import annotations

import hashlib
import random
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.eligibility import (
    article_slot_policy,
    sequential_prerequisites_satisfied,
)
from constitution_memorizer.planner.models import MixCandidate
from constitution_memorizer.planner.planner import (
    _actual_review_occupancy,
    _reviews_from_learn_date,
)
from constitution_memorizer.planner.relationships import (
    build_candidate,
    candidates_from_units,
)
from constitution_memorizer.planner.selector import LearningMixSelector, recency_key
from constitution_memorizer.progress.repository import (
    AutoPlanDay,
    AutoPlanItem,
    AutoPlanSnapshot,
    ProgressRecord,
    SplitMode,
    StudySession,
    UserLearningPlan,
    VALID_DAILY_TARGETS,
)
from constitution_memorizer.progress.scheduler import ReminderEngine

WINDOW_DAYS = 15


def roadmap_horizon(as_of: date) -> date:
    return as_of + timedelta(days=WINDOW_DAYS - 1)


def day_rng(user_id: str, day: date, daily_target: int) -> random.Random:
    digest = hashlib.sha256(
        f"{user_id}:{day.isoformat()}:{daily_target}".encode()
    ).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _unlearned(progress: Mapping[str, ProgressRecord], unit_id: str) -> bool:
    row = progress.get(unit_id)
    if row is None:
        return True
    if row.times_completed > 0:
        return False
    return row.status == "new"


def _visible_for_preference(
    unit: LearningUnit, splits: Mapping[str, SplitMode]
) -> bool:
    if unit.type == LearningUnitType.SUBCLAUSE and unit.parent_clause_id:
        mode = splits.get(unit.parent_clause_id) or "whole"
        return mode == "letters"
    if unit.allows_letter_split:
        mode = splits.get(unit.id) or "whole"
        if mode == "letters":
            return False
    return True


def _eligible_for_mix(unit: LearningUnit, splits: Mapping[str, SplitMode]) -> bool:
    if not _visible_for_preference(unit, splits):
        return False
    if unit.allows_letter_split and splits.get(unit.id) is None:
        return False
    return True


def _window_unit_eligible(
    unit: LearningUnit | None,
    progress: Mapping[str, ProgressRecord],
    splits: Mapping[str, SplitMode],
    *,
    units: Mapping[str, LearningUnit],
    claimed: set[str],
    remaining_slots: int,
    entitlements_on: bool,
) -> bool:
    """Same mix-selection filter used for selector tail fill and queue pop."""
    if unit is None or unit.type == LearningUnitType.PART_OVERVIEW:
        return False
    if not _unlearned(progress, unit.id):
        return False
    if not _eligible_for_mix(unit, splits):
        return False
    if entitlements_on:
        article = unit.article_number
        if article and article not in claimed and remaining_slots <= 0:
            return False
    if not sequential_prerequisites_satisfied(
        unit, units=units, progress=progress, splits=splits
    ):
        return False
    return True


def _session_for_day(
    sessions: Sequence[StudySession], *, kind: str, plan_date: date
) -> StudySession | None:
    matches = [session for session in sessions if session.kind == kind and session.plan_date == plan_date]
    if not matches:
        return None
    matches.sort(key=lambda session: (session.created_at, session.id))
    return matches[0]


def _deferred_unlearned_ids(
    sessions: Sequence[StudySession],
    progress: Mapping[str, ProgressRecord],
    *,
    until: date,
) -> list[str]:
    ids: list[str] = []
    ordered = sorted(
        (session for session in sessions if session.plan_date <= until),
        key=lambda session: (session.plan_date, session.created_at, session.id),
    )
    for session in ordered:
        for item in session.items:
            if item.status == "deferred" and _unlearned(progress, item.learning_unit_id):
                ids.append(item.learning_unit_id)
    return ids


def _skipped_on(session: StudySession | None) -> set[str]:
    if session is None:
        return set()
    return {
        item.learning_unit_id
        for item in session.items
        if item.status == "deferred"
    }


def _pending_on(session: StudySession | None) -> set[str]:
    if session is None:
        return set()
    return {
        item.learning_unit_id
        for item in session.items
        if item.status == "pending"
    }


def _dedupe_keep_first(unit_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for unit_id in unit_ids:
        if unit_id in seen:
            continue
        seen.add(unit_id)
        out.append(unit_id)
    return out


def _day(
    plan_date: date,
    daily_target: int,
    unit_ids: Sequence[str],
) -> AutoPlanDay:
    return AutoPlanDay(
        plan_date=plan_date,
        daily_target=int(daily_target),
        items=tuple(
            AutoPlanItem(
                plan_date=plan_date,
                learning_unit_id=unit_id,
                position=index,
            )
            for index, unit_id in enumerate(unit_ids)
        ),
    )


def _occupancy_from_progress(
    progress: Sequence[ProgressRecord], *, as_of: date
) -> dict[date, int]:
    """Same occupancy as ReminderEngine.list_all_progress without a live engine."""

    class _ProgressView:
        def list_all_progress(self) -> list[ProgressRecord]:
            return list(progress)

    return _actual_review_occupancy(_ProgressView(), as_of=as_of)  # type: ignore[arg-type]


def _mix_candidates(
    units: Mapping[str, LearningUnit],
    progress: Mapping[str, ProgressRecord],
    splits: Mapping[str, SplitMode],
    *,
    exclude: set[str],
    claimed: set[str],
    remaining_slots: int,
    entitlements_on: bool,
) -> list[MixCandidate]:
    eligible: list[LearningUnit] = []
    slots = max(0, remaining_slots)
    for unit in units.values():
        if unit.id in exclude:
            continue
        if not _window_unit_eligible(
            unit,
            progress,
            splits,
            units=units,
            claimed=claimed,
            remaining_slots=slots,
            entitlements_on=entitlements_on,
        ):
            continue
        eligible.append(unit)
    eligible.sort(key=lambda item: (item.revision_order, item.id))
    return candidates_from_units(eligible)


def _carryover_for_day(
    queue: deque[str],
    *,
    target: int,
    assigned: set[str],
    units: Mapping[str, LearningUnit],
    progress: Mapping[str, ProgressRecord],
    splits: Mapping[str, SplitMode],
    claimed: set[str],
    remaining_slots: int,
    entitlements_on: bool,
    allow,
) -> list[MixCandidate]:
    """Pop up to ``target`` still-valid owed units, oldest commitment first.

    Validation happens once, here, so the selector can treat the result as
    settled: dropping owed work later would lose it silently. Both gates run —
    hard eligibility, and the article-slot policy applied progressively against
    what this day has already taken, which is the only place the count of
    distinct new Articles per day can actually be bounded.
    """
    chosen: list[MixCandidate] = []
    while len(chosen) < target and queue:
        unit_id = queue.popleft()
        if unit_id in assigned or any(item.id == unit_id for item in chosen):
            continue
        unit = units.get(unit_id)
        if not _window_unit_eligible(
            unit,
            progress,
            splits,
            units=units,
            claimed=claimed,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
        ):
            continue
        candidate = build_candidate(unit)
        if allow is not None and not allow(candidate, [c for c in chosen]):
            continue
        chosen.append(candidate)
    return chosen


def compute_auto_window(
    snapshot: AutoPlanSnapshot,
    *,
    as_of: date,
    horizon: date,
    units: Mapping[str, LearningUnit],
    claimed: set[str],
    remaining_slots: int,
    entitlements_on: bool,
) -> list[AutoPlanDay]:
    plan = snapshot.plan
    target = int(plan.daily_target or 0)
    if target not in VALID_DAILY_TARGETS:
        return []
    progress = {row.learning_unit_id: row for row in snapshot.progress}
    items = [item for day in snapshot.days for item in day.items]
    items.sort(key=lambda item: (item.plan_date, item.position))
    today_session = _session_for_day(
        snapshot.sessions, kind="auto_learning", plan_date=as_of
    )
    compaction_start = as_of if today_session is None else as_of + timedelta(days=1)

    historical = [
        item.learning_unit_id
        for item in items
        if item.plan_date < as_of and _unlearned(progress, item.learning_unit_id)
    ]
    skipped = _deferred_unlearned_ids(snapshot.sessions, progress, until=as_of)
    future = [
        item.learning_unit_id
        for item in items
        if item.plan_date >= compaction_start
        and _unlearned(progress, item.learning_unit_id)
    ]
    queue: deque[str] = deque(_dedupe_keep_first([*historical, *skipped, *future]))

    occupied = _occupancy_from_progress(snapshot.progress, as_of=as_of)
    assigned: set[str] = set()
    if today_session is not None:
        assigned.update(
            item.learning_unit_id
            for item in today_session.items
            if item.status in {"pending", "completed"}
        )
        pending = _pending_on(today_session)
        skipped_today = _skipped_on(today_session)
        for item in today_session.items:
            unit_id = item.learning_unit_id
            if unit_id in skipped_today:
                continue
            if unit_id not in pending:
                continue
            if not _unlearned(progress, unit_id):
                continue
            for when, count in _reviews_from_learn_date(as_of, 1).items():
                occupied[when] += count

    recent_theme = plan.last_anchor_theme
    claimed_keys = set(claimed) | set(snapshot.claimed_articles)
    written: list[AutoPlanDay] = []
    cursor = as_of
    while cursor <= horizon:
        if cursor == as_of and today_session is not None:
            written.append(
                _day(
                    cursor,
                    target,
                    [item.learning_unit_id for item in today_session.items],
                )
            )
            cursor += timedelta(days=1)
            continue
        reviews = occupied.get(cursor, 0)
        if reviews > 0:
            written.append(_day(cursor, target, ()))
            cursor += timedelta(days=1)
            continue
        allow = article_slot_policy(
            claimed=claimed_keys,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
        )
        # Work already owed to the learner, oldest commitment first. It is
        # revalidated here — against hard eligibility AND, progressively,
        # against the article-slot policy. _window_unit_eligible only knows
        # whether *a* Free slot remains; it cannot see how many distinct new
        # Articles this day has already introduced, so trusting the queue
        # blindly let one day spend the Free cap twice over.
        committed = _carryover_for_day(
            queue,
            target=target,
            assigned=assigned,
            units=units,
            progress=progress,
            splits=snapshot.split_preferences,
            claimed=claimed_keys,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
            allow=allow,
        )
        chosen: list[str] = [candidate.id for candidate in committed]
        anchor_candidate = committed[0] if committed else None
        if len(chosen) < target:
            exclude = set(assigned) | set(chosen) | set(queue)
            candidates = _mix_candidates(
                units,
                progress,
                snapshot.split_preferences,
                exclude=exclude,
                claimed=claimed_keys,
                remaining_slots=remaining_slots,
                entitlements_on=entitlements_on,
            )
            # One canonical Recall Mix: the same selector Plan My Day uses.
            # Carryover goes in as `committed`, so it anchors the day and its
            # own buckets are subtracted from the composition rather than a
            # fresh full-target mix being appended and truncated.
            mix = LearningMixSelector().select(
                candidates,
                target,
                rng=day_rng(snapshot.user_id, cursor, target),
                allow=allow,
                recent_theme=recent_theme,
                committed=committed,
            )
            if mix:
                chosen = [candidate.id for candidate in mix]
                anchor_candidate = mix[0]
        if anchor_candidate is not None:
            # The day's anchor, not its last unit — recency follows what the
            # day was built around.
            recent_theme = recency_key(anchor_candidate)
        assigned.update(chosen)
        written.append(_day(cursor, target, chosen))
        if chosen:
            for _unit_id in chosen:
                for when, count in _reviews_from_learn_date(cursor, 1).items():
                    occupied[when] += count
        cursor += timedelta(days=1)
    return written


def auto_roadmap_needs_reconcile_from_snapshot(
    plan: UserLearningPlan,
    *,
    as_of: date,
    auto_entitled: bool,
    window_days: Sequence[AutoPlanDay],
    has_tail: bool,
    today_auto_session: StudySession | None,
) -> bool:
    """In-memory freshness check over an already-loaded Auto snapshot."""
    horizon = roadmap_horizon(as_of)
    in_window = [day for day in window_days if as_of <= day.plan_date <= horizon]
    if not (auto_entitled and plan.is_auto):
        beyond = [day for day in window_days if day.plan_date >= as_of]
        return bool(beyond) or has_tail

    covered = {day.plan_date for day in in_window}
    expected = {as_of + timedelta(days=offset) for offset in range(WINDOW_DAYS)}
    if covered != expected:
        return True
    if has_tail:
        return True

    today_frozen = today_auto_session is not None
    target = plan.daily_target
    for day in in_window:
        if day.plan_date == as_of and today_frozen:
            continue
        if day.daily_target != target:
            return True
    return False


def auto_roadmap_needs_reconcile(
    engine: ReminderEngine,
    plan: UserLearningPlan,
    *,
    as_of: date,
    auto_entitled: bool,
) -> bool:
    """True when a GET should run one durable reconcile.

    Freshness is structural: day coverage and plan metadata. An
    ``auto_plan_day`` with zero items is valid (REVIEW-only or exhausted
    unseen curriculum) and is not treated as stale.

    A current Auto roadmap is fresh when:

    * an ``auto_plan_day`` exists for every local date ``as_of`` … ``as_of+14``
    * no Auto day rows remain beyond that horizon
    * mutable future days carry the current plan ``daily_target``
    * today's started/completed session is left frozen (its day target may
      differ from the current plan)

    GET may reconcile once when the window is missing, the local date rolled
    over, target metadata is unapplied on mutable days, leftover tail rows
    exist, or migration 0015 just landed. Split-preference and occupancy
    changes are write-path triggers, not GET freshness signals.
    """
    horizon = roadmap_horizon(as_of)
    bundle = getattr(engine, "_planner_bundle", None)
    if (
        bundle is not None
        and bundle.as_of == as_of
        and bundle.auto_start <= as_of
        and bundle.auto_until >= horizon
        and bundle.horizon == horizon
    ):
        return auto_roadmap_needs_reconcile_from_snapshot(
            plan,
            as_of=as_of,
            auto_entitled=auto_entitled,
            window_days=bundle.auto_plan_days,
            has_tail=bundle.has_auto_plan_tail,
            today_auto_session=bundle.session("auto_learning"),
        )

    far = horizon + timedelta(days=366)
    if not (auto_entitled and plan.is_auto):
        return bool(engine.list_auto_plan_window(as_of, far))

    days = engine.list_auto_plan_window(as_of, horizon)
    today_session = None
    try:
        today_session = engine.study_session_for_day(kind="auto_learning", plan_date=as_of)
    except Exception as error:  # noqa: BLE001 — missing session tables: treat as unfrozen
        from constitution_memorizer.web.service import _is_missing_optional_schema

        if not _is_missing_optional_schema(error):
            raise
        today_session = None
    has_tail = bool(engine.list_auto_plan_window(horizon + timedelta(days=1), far))
    return auto_roadmap_needs_reconcile_from_snapshot(
        plan,
        as_of=as_of,
        auto_entitled=auto_entitled,
        window_days=days,
        has_tail=has_tail,
        today_auto_session=today_session,
    )


def reconcile_auto_roadmap(
    engine: ReminderEngine,
    plan: UserLearningPlan,
    *,
    as_of: date,
    auto_entitled: bool,
    claimed: set[str] | None = None,
    remaining_slots: int | None = None,
    entitlements_on: bool = False,
) -> None:
    """Rebuild the mutable Auto window. Never mutates dates before ``as_of``."""
    if not (auto_entitled and plan.is_auto):
        engine.clear_future_auto_plan(as_of)
        return
    horizon = roadmap_horizon(as_of)
    claimed_keys = {str(item) for item in (claimed or set())}
    slots = 0 if remaining_slots is None else max(0, remaining_slots)
    catalog = engine.units

    def builder(snapshot: AutoPlanSnapshot) -> list[AutoPlanDay]:
        live_plan = snapshot.plan if snapshot.plan.is_auto else plan
        return compute_auto_window(
            snapshot,
            as_of=as_of,
            horizon=horizon,
            units=catalog,
            claimed=claimed_keys,
            remaining_slots=slots,
            entitlements_on=entitlements_on,
        ) if live_plan.is_auto else []

    engine.apply_auto_plan_reconcile(as_of, horizon, builder)