"""Authenticated dashboard view-model (Multi-User Experience layout)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from constitution_memorizer.learning.schemas import LearningUnit
from constitution_memorizer.planner.eligibility import remaining_unseen_count
from constitution_memorizer.planner.models import pace_label
from constitution_memorizer.planner.planner import LearningPlanner
from constitution_memorizer.progress.repository import LEARN_MODES, UserLearningPlan
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.progress_stats import (
    _is_completed,
    all_article_progress,
)
from constitution_memorizer.web.service import (
    AUTO_LEARNING_KIND,
    DAY_PLAN_KIND,
    REVISION_KIND,
    _is_missing_study_session_table,
    active_revision_session,
    continue_unit_id,
    due_checklist,
    session_progress,
)

MODE_LABELS = {
    "read": "Read",
    "cloze": "Cloze",
    "letters": "Letters",
    "type": "Type recall",
    "recite": "Recite",
    "test": "Test",
}


def first_name(display_label: str) -> str:
    token = (display_label or "").strip().split()
    return token[0] if token else "Learner"


def relative_time(iso: str, *, now: datetime | None = None) -> str:
    """Format an ISO timestamp as a short relative label."""
    now = now or datetime.now(timezone.utc)
    try:
        raw = iso.replace("Z", "+00:00")
        when = datetime.fromisoformat(raw)
    except ValueError:
        return iso[:10] if iso else ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - when
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return when.date().isoformat()


def due_minutes(units: list[LearningUnit]) -> int:
    if not units:
        return 0
    total_seconds = sum(max(1, u.estimated_learning_time) for u in units)
    return max(1, math.ceil(total_seconds / 60))


def due_article_chips(
    units: list[LearningUnit], *, limit: int = 3
) -> tuple[list[str], int]:
    """Return up to `limit` unique Article labels and a leftover count."""
    seen: list[str] = []
    for unit in units:
        if unit.article_number:
            label = f"Article {unit.article_number}"
        else:
            label = unit.display_title
        if label not in seen:
            seen.append(label)
    if len(seen) <= limit:
        return seen, 0
    return seen[:limit], len(seen) - limit


def day_streak(engine: ReminderEngine, *, as_of: date | None = None) -> int:
    """
    Consecutive calendar days with at least one completion, ending today
    (or yesterday if today has none yet).
    """
    today = as_of or date.today()
    days_with_work: set[date] = set()
    for row in engine.list_all_progress():
        if row.times_completed <= 0 and row.status == "new":
            continue
        if row.last_completed is not None:
            days_with_work.add(row.last_completed)
            continue
        # Fall back to updated_at date when last_completed is unset.
        try:
            days_with_work.add(date.fromisoformat(row.updated_at[:10]))
        except ValueError:
            continue
    if not days_with_work:
        return 0
    cursor = today if today in days_with_work else today - timedelta(days=1)
    if cursor not in days_with_work:
        return 0
    streak = 0
    while cursor in days_with_work:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def progress_strip(engine: ReminderEngine, *, as_of: date | None = None) -> dict[str, int]:
    today = as_of or date.today()
    articles = all_article_progress(engine)
    articles_started = sum(1 for a in articles if a.completed > 0)
    units_completed = sum(
        1 for unit in engine.units.values() if _is_completed(engine, unit.id)
    )
    stats = engine.stats()
    revisions = sum(row.times_completed for row in engine.list_all_progress())
    return {
        "articles_started": articles_started,
        "units_completed": units_completed,
        "units_mastered": stats["mastered"],
        "day_streak": day_streak(engine, as_of=today),
        "revisions_done": revisions,
    }


def continue_meta(unit: LearningUnit) -> str:
    bits: list[str] = []
    if unit.title:
        bits.append(unit.title)
    if unit.type.value == "CLAUSE" and unit.article_number:
        # Prefer clause hint from display_title parenthetical if present.
        pass
    if unit.type.value == "SUBCLAUSE" and unit.article_number:
        bits.append(f"Article {unit.article_number}")
    return " · ".join(bits) if bits else ""


def continue_mode_line(engine: ReminderEngine, unit: LearningUnit) -> tuple[str, int]:
    """Return (mode label line, percent 0–100) for the continue card."""
    seen = engine.modes_seen(unit.id)
    count = len(seen)
    pct_modes = int(round(100 * count / 6)) if count else 0
    done_count, _pos, chain_len = session_progress(engine, unit)
    pct_session = int(round(100 * done_count / chain_len)) if chain_len else 0
    pct = max(pct_modes, pct_session)
    # Prefer the last mode in LEARN_MODES order that was seen.
    mode_name = "Read"
    for mode in LEARN_MODES:
        if mode in seen:
            mode_name = MODE_LABELS.get(mode, mode.title())
    if count:
        line = f"Mode: {mode_name} · {count}/6 modes · {pct}% through"
    else:
        line = f"Mode: {mode_name} · {pct}% through"
    return line, pct


def _upcoming_day_label(when: date, today: date) -> str:
    """Tomorrow / weekday / "Mon 25" — the phone's Upcoming card headings."""
    delta = (when - today).days
    if delta == 1:
        return "Tomorrow"
    if delta < 7:
        return when.strftime("%A")
    return when.strftime("%a %-d")


def upcoming_revisions(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
    limit: int = 3,
) -> list[dict[str, str]]:
    """The next scheduled revisions after today, soonest first."""
    today = as_of or date.today()
    rows = [
        row
        for row in engine.list_all_progress()
        if row.next_revision is not None and row.next_revision > today
    ]
    rows.sort(key=lambda r: (r.next_revision, r.learning_unit_id))
    out: list[dict[str, str]] = []
    for row in rows[:limit]:
        unit = engine.get_unit(row.learning_unit_id)
        if unit is None:
            continue
        assert row.next_revision is not None
        out.append(
            {
                "when": _upcoming_day_label(row.next_revision, today),
                "title": unit.display_title,
                "rung": f"Day {row.interval_days if row.interval_days > 0 else 1}",
                "href": f"/learn/{row.learning_unit_id}",
            }
        )
    return out


def _learning_plan_or_default(engine: ReminderEngine) -> UserLearningPlan:
    try:
        return engine.get_learning_plan()
    except Exception as error:  # noqa: BLE001 — schema-gap window
        if not _is_missing_study_session_table(error):
            raise
        return UserLearningPlan()


def _session_for_day(engine: ReminderEngine, kind: str, today: date):
    try:
        return engine.study_session_for_day(kind=kind, plan_date=today)  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise
        return None



def build_dashboard_context(
    eng: ReminderEngine,
    *,
    display_label: str,
    as_of: date | None = None,
    now: datetime | None = None,
    auto_entitled: bool = True,
) -> dict[str, Any]:
    today = as_of or date.today()
    now = now or datetime.now(timezone.utc)
    name = first_name(display_label)
    due_units = due_checklist(eng, as_of=today)
    chips, chips_more = due_article_chips(due_units)
    strip = progress_strip(eng, as_of=today)
    is_new = strip["articles_started"] == 0 and strip["units_completed"] == 0

    cont_id = continue_unit_id(eng, as_of=today)
    cont_unit = eng.get_unit(cont_id) if cont_id else None
    cont_mode_line = ""
    cont_pct = 0
    cont_meta = ""
    if cont_unit is not None:
        cont_mode_line, cont_pct = continue_mode_line(eng, cont_unit)
        cont_meta = continue_meta(cont_unit)


    greeting = f"Welcome, {name}." if is_new else f"Good morning, {name}."
    subtext = (
        "Your account is ready. Here's a good first step."
        if is_new
        else "Here's where you left off."
    )

    first_due_id = due_units[0].id if due_units else None

    # Today is one thing or the other. Revision outranks learning: new
    # material on top of an unrevised backlog is how the backlog grows.
    revision_session = active_revision_session(eng, as_of=today)
    session_remaining = revision_session.remaining if revision_session else 0
    if session_remaining:
        # Mid-session the queue is the snapshot, not the live due list —
        # completing an item already pushed its next_revision forward.
        pending_ids = {i.learning_unit_id for i in revision_session.pending}
        queue_units = [u for u in due_units if u.id in pending_ids]
        if len(queue_units) < session_remaining:
            queue_units = [
                unit
                for unit in (
                    eng.get_unit(i.learning_unit_id) for i in revision_session.pending
                )
                if unit is not None
            ]
    else:
        queue_units = due_units
    today_mode = "revision" if (due_units or session_remaining) else "learning"
    revision_chips, revision_chips_more = due_article_chips(queue_units)

    revision_today = _session_for_day(eng, REVISION_KIND, today)
    revision_completed_today = revision_today.completed_count if revision_today else 0

    plan = _learning_plan_or_default(eng)
    auto_selected = bool(plan.is_auto and auto_entitled)
    auto_active = bool(plan.is_active_auto and auto_entitled)

    learning_session = None
    if today_mode == "learning":
        for kind in (AUTO_LEARNING_KIND, DAY_PLAN_KIND):
            try:
                learning_session = eng.active_study_session(kind=kind, plan_date=today)
            except Exception as error:  # noqa: BLE001
                if not _is_missing_study_session_table(error):
                    raise
                learning_session = None
                break
            if learning_session:
                break
    learning_remaining = learning_session.remaining if learning_session else 0

    learning_today = learning_session
    if learning_today is None and today_mode == "learning":
        for kind in (AUTO_LEARNING_KIND, DAY_PLAN_KIND):
            learning_today = _session_for_day(eng, kind, today)
            if learning_today is not None:
                break

    unseen = 0
    try:
        unseen = remaining_unseen_count(eng, as_of=today)
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise

    next_learning_day = None
    today_new_count = int(plan.daily_target or 0) if auto_selected else 0
    today_pace = pace_label(plan.daily_target if auto_selected else None)
    try:
        planner = LearningPlanner()
        next_learning_day = planner.next_learning_day(
            eng,
            plan,
            as_of=today,
            remaining_unseen=unseen,
            auto_entitled=auto_entitled,
        )
        today_plan = next(
            (
                day
                for day in planner.project(
                    eng,
                    plan,
                    as_of=today,
                    until=today,
                    remaining_unseen=unseen,
                    auto_entitled=auto_entitled,
                )
                if day.day == today
            ),
            None,
        )
        if today_plan is not None and today_plan.new_capacity:
            today_new_count = today_plan.new_capacity
            today_pace = pace_label(plan.daily_target)
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise

    learning_cta = "browse"
    if today_mode == "learning":
        if learning_remaining:
            learning_cta = "continue_session"
        elif learning_today is not None and (
            learning_today.status == "complete" or learning_today.remaining == 0
        ):
            learning_cta = "learning_complete"
        elif auto_selected and unseen > 0:
            learning_cta = "start_auto"
        elif (
            learning_today is None
            and (plan is None or plan.prompt_dismissed_on != today)
            and unseen > 0
        ):
            learning_cta = "plan_prompt"
        elif cont_unit is not None:
            learning_cta = "continue_unit"
        else:
            learning_cta = "caught_up"

    show_plan_prompt = learning_cta == "plan_prompt"

    return {
        "today_mode": today_mode,
        "revision_session_id": revision_session.id if revision_session else None,
        "revision_remaining": session_remaining,
        "revision_count": session_remaining or len(due_units),
        "revision_minutes": due_minutes(queue_units),
        "revision_chips": revision_chips,
        "revision_chips_more": revision_chips_more,
        "revision_completed_today": revision_completed_today,
        "learning_session_id": learning_session.id if learning_session else None,
        "learning_remaining": learning_remaining,
        "learning_kind": learning_session.kind if learning_session else None,
        "learning_cta": learning_cta,
        "plan_mode": plan.mode if plan else "self_paced",
        "plan_daily_target": plan.daily_target if plan else None,
        "plan_activated": bool(plan and plan.activated_at),
        "auto_entitled": auto_entitled,
        "auto_active": auto_active,
        "show_plan_prompt": show_plan_prompt,
        "today_new_count": today_new_count,
        "today_pace_label": today_pace,
        "next_learning_day": next_learning_day,
        "display_label": display_label,
        "first_name": name,
        "greeting": greeting,
        "subtext": subtext,
        "is_new": is_new,
        "nothing_due": len(due_units) == 0,
        "due_count": len(due_units),
        "due_minutes": due_minutes(due_units),
        "due_chips": chips,
        "due_chips_more": chips_more,
        "first_due_id": first_due_id,
        "continue_unit": cont_unit,
        "continue_meta": cont_meta,
        "continue_mode_line": cont_mode_line,
        "continue_pct": cont_pct,
        "strip": strip,
        "upcoming": upcoming_revisions(eng, as_of=today),
        # All completions today (revision + voluntary new learning). Do not
        # use this for "N revisions completed today" — that is
        # revision_completed_today from the revision session's completed_count.
        "completed_today": sum(
            1
            for row in eng.list_all_progress()
            if row.last_completed == today and row.times_completed > 0
        ),
    }
