"""Study session start, resume, Done/Again, and date rollover."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from constitution_memorizer.progress.learning_plan import LearningPlan, default_learning_plan
from constitution_memorizer.progress.local_date import user_today
from constitution_memorizer.progress.mix_selector import select_learning_mix
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.progress.study_models import StudySession
from constitution_memorizer.web.service import due_checklist

PACE_LABELS = {3: "Steady", 5: "Balanced", 7: "Intensive"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def close_stale_sessions(engine: ReminderEngine, *, today: date | None = None) -> int:
    today = today or user_today(engine)
    try:
        return engine.repo.abandon_stale_sessions(engine.user_id, today)
    except Exception:  # noqa: BLE001 — old DBs without the table
        return 0


def get_learning_plan(engine: ReminderEngine) -> LearningPlan:
    try:
        return engine.repo.get_learning_plan(engine.user_id)
    except Exception:  # noqa: BLE001
        return default_learning_plan(str(engine.user_id))


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
        try:
            engine.repo.abandon_unstarted_learning_sessions(engine.user_id)
        except Exception:  # noqa: BLE001 — missing table in old fixtures
            pass
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
        return engine.repo.get_study_session(engine.user_id, session_id)
    except Exception:  # noqa: BLE001
        return None


def active_same_day_session(
    engine: ReminderEngine, *, today: date | None = None
) -> StudySession | None:
    today = today or user_today(engine)
    close_stale_sessions(engine, today=today)
    try:
        revision = engine.repo.get_active_revision_session(engine.user_id)
        if revision is not None and revision.plan_date == today:
            return revision
        learning = engine.repo.get_active_learning_session(engine.user_id, today)
        return learning
    except Exception:  # noqa: BLE001
        return None


def start_or_resume_revision(
    engine: ReminderEngine, *, today: date | None = None
) -> StudySession | None:
    today = today or user_today(engine)
    close_stale_sessions(engine, today=today)
    existing = engine.repo.get_active_revision_session(engine.user_id)
    if existing is not None and existing.plan_date == today:
        return existing
    due = due_checklist(engine, as_of=today)
    if not due:
        return None
    return engine.repo.insert_study_session(
        engine.user_id,
        session_id=str(uuid4()),
        kind="revision",
        plan_date=today,
        unit_ids=[unit.id for unit in due],
    )


def start_or_resume_learning(
    engine: ReminderEngine,
    *,
    kind: str,
    count: int,
    today: date | None = None,
    article_allowed=None,
    rng=None,
) -> StudySession | None:
    today = today or user_today(engine)
    close_stale_sessions(engine, today=today)
    existing = engine.repo.get_active_learning_session(engine.user_id, today)
    if existing is not None:
        return existing
    mix = select_learning_mix(
        engine,
        count,
        rng=rng,
        article_allowed=article_allowed,
    )
    if not mix:
        return None
    return engine.repo.insert_study_session(
        engine.user_id,
        session_id=str(uuid4()),
        kind=kind,
        plan_date=today,
        unit_ids=[unit.id for unit in mix],
    )


def mark_item_done(
    engine: ReminderEngine, session_id: str, unit_id: str
) -> StudySession | None:
    return engine.repo.set_session_item_state(
        engine.user_id,
        session_id,
        unit_id,
        "completed",
        completed_at=_utc_now_iso(),
    )


def mark_item_deferred(
    engine: ReminderEngine, session_id: str, unit_id: str
) -> StudySession | None:
    return engine.repo.set_session_item_state(
        engine.user_id,
        session_id,
        unit_id,
        "deferred",
        deferred_at=_utc_now_iso(),
    )


def first_pending_id(session: StudySession | None) -> str | None:
    if session is None:
        return None
    pending = session.next_pending()
    return pending.learning_unit_id if pending is not None else None
