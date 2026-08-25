"""Learning-plan preference plus auto/day-plan session start on the session foundation."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from constitution_memorizer.progress.learning_plan import LearningPlan, default_learning_plan
from constitution_memorizer.progress.local_date import user_today
from constitution_memorizer.progress.mix_selector import select_learning_mix
from constitution_memorizer.progress.repository import StudySession
from constitution_memorizer.progress.scheduler import ReminderEngine

LEARNING_KINDS = ("auto_learning", "day_plan")
PACE_LABELS = {3: "Steady", 5: "Balanced", 7: "Intensive"}


def close_stale_sessions(engine: ReminderEngine, *, today: date | None = None) -> int:
    """No-op: main scopes active queues by ``plan_date``, so yesterday is ignored.

    Kept so calendar/dashboard call sites that expected a rollover still compile.
    """
    del engine, today
    return 0


def get_learning_plan(engine: ReminderEngine) -> LearningPlan:
    try:
        return engine.repo.get_learning_plan(engine.user_id)
    except Exception:  # noqa: BLE001 — old DBs without the table
        return default_learning_plan(str(engine.user_id))


def _complete_unstarted_learning(engine: ReminderEngine) -> None:
    today = user_today(engine)
    for kind in LEARNING_KINDS:
        try:
            session = engine.active_study_session(kind=kind, plan_date=today)
        except Exception:  # noqa: BLE001
            continue
        if session is None or session.completed_count > 0:
            continue
        engine.complete_study_session(session.id)


def save_learning_plan(
    engine: ReminderEngine,
    *,
    mode: str,
    daily_target: int | None,
    activated_at: date | None = None,
    plan_prompt_dismissed_on: date | None = None,
) -> LearningPlan:
    current = get_learning_plan(engine)
    if activated_at is None:
        activated_at = current.activated_at if mode == "auto" else None
    if plan_prompt_dismissed_on is None:
        plan_prompt_dismissed_on = current.plan_prompt_dismissed_on
    if mode == "self_paced":
        daily_target = None
        activated_at = None
        _complete_unstarted_learning(engine)
    return engine.repo.upsert_learning_plan(
        engine.user_id,
        mode=mode,
        daily_target=daily_target,
        activated_at=activated_at,
        plan_prompt_dismissed_on=plan_prompt_dismissed_on,
    )


def maybe_activate_auto_plan(
    engine: ReminderEngine,
    *,
    was_new_unit: bool,
    today: date | None = None,
) -> None:
    if not was_new_unit:
        return
    plan = get_learning_plan(engine)
    if not plan.is_unanchored_auto:
        return
    today = today or user_today(engine)
    engine.repo.upsert_learning_plan(
        engine.user_id,
        mode=plan.mode,
        daily_target=plan.daily_target,
        activated_at=today,
        plan_prompt_dismissed_on=plan.plan_prompt_dismissed_on,
    )


def get_session(engine: ReminderEngine, session_id: str | None) -> StudySession | None:
    if not session_id:
        return None
    try:
        session = engine.get_study_session(session_id)
    except Exception:  # noqa: BLE001
        return None
    return reconcile_session_progress(engine, session)


def reconcile_session_progress(
    engine: ReminderEngine, session: StudySession | None
) -> StudySession | None:
    """Mark pending items already completed today as completed.

    Safety net for a crash between progress commit and session-item update.
    """
    if session is None or session.status != "active":
        return session
    changed = False
    for item in session.items:
        if item.status != "pending":
            continue
        try:
            progress = engine.get_progress(item.learning_unit_id)
        except Exception:  # noqa: BLE001
            continue
        if (
            progress is not None
            and progress.times_completed >= 1
            and progress.last_completed == session.plan_date
        ):
            engine.set_study_item_status(
                session_id=session.id,
                unit_id=item.learning_unit_id,
                status="completed",
            )
            changed = True
    if not changed:
        return session
    try:
        return engine.get_study_session(session.id)
    except Exception:  # noqa: BLE001
        return session


def active_same_day_session(
    engine: ReminderEngine, *, today: date | None = None
) -> StudySession | None:
    today = today or user_today(engine)
    try:
        revision = engine.active_study_session(kind="revision", plan_date=today)
        if revision is not None:
            return revision
        for kind in LEARNING_KINDS:
            learning = engine.active_study_session(kind=kind, plan_date=today)
            if learning is not None:
                return learning
    except Exception:  # noqa: BLE001
        return None
    return None


def start_or_resume_learning(
    engine: ReminderEngine,
    *,
    kind: str,
    count: int,
    today: date | None = None,
    article_allowed=None,
    rng=None,
) -> StudySession | None:
    if kind not in LEARNING_KINDS:
        raise ValueError(f"Invalid learning session kind: {kind}")
    today = today or user_today(engine)
    existing = active_same_day_session(engine, today=today)
    if existing is not None and existing.kind in LEARNING_KINDS:
        return reconcile_session_progress(engine, existing)
    mix = select_learning_mix(
        engine,
        count,
        rng=rng,
        article_allowed=article_allowed,
    )
    if not mix:
        return None
    return engine.create_study_session(
        session_id=uuid4().hex,
        kind=kind,  # type: ignore[arg-type]
        plan_date=today,
        unit_ids=[unit.id for unit in mix],
    )


def first_pending_id(session: StudySession | None) -> str | None:
    if session is None:
        return None
    return session.next_pending_after(None)
