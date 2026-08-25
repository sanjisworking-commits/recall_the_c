"""Authenticated dashboard view-model (Multi-User Experience layout)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from constitution_memorizer.learning.schemas import LearningUnit
from constitution_memorizer.progress.repository import LEARN_MODES
from constitution_memorizer.progress.planner import project_new_capacity
from constitution_memorizer.progress.local_date import user_today
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.progress.study_session import (
    active_same_day_session,
    close_stale_sessions,
    get_learning_plan,
)
from constitution_memorizer.web.progress_stats import (
    _is_completed,
    all_article_progress,
)
from constitution_memorizer.web.service import (
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


def activity_sentence(status: str, title: str) -> str:
    if status == "mastered":
        return f"Mastered {title}"
    if status == "review":
        return f"Reviewed {title}"
    return f"Started {title}"


def activity_tone(status: str) -> str:
    if status == "mastered":
        return "mastered"
    if status == "review":
        return "review"
    return "new"


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


def build_dashboard_context(
    eng: ReminderEngine,
    *,
    display_label: str,
    as_of: date | None = None,
    now: datetime | None = None,
    entitled: bool = True,
) -> dict[str, Any]:
    today = as_of or user_today(eng)
    now = now or datetime.now(timezone.utc)
    close_stale_sessions(eng, today=today)
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

    recent_rows = sorted(
        eng.list_all_progress(),
        key=lambda r: r.updated_at,
        reverse=True,
    )[:5]
    recent: list[dict[str, str]] = []
    for row in recent_rows:
        unit = eng.get_unit(row.learning_unit_id)
        title = unit.display_title if unit is not None else row.learning_unit_id
        recent.append(
            {
                "unit_id": row.learning_unit_id,
                "text": activity_sentence(row.status, title),
                "relative": relative_time(row.updated_at, now=now),
                "tone": activity_tone(row.status),
                "href": f"/learn/{row.learning_unit_id}",
            }
        )

    greeting = f"Welcome, {name}." if is_new else f"Good morning, {name}."
    subtext = (
        "Your account is ready. Here's a good first step."
        if is_new
        else "Here's where you left off."
    )

    first_due_id = due_units[0].id if due_units else None
    plan = get_learning_plan(eng)
    active = active_same_day_session(eng, today=today)
    today_mode = "caught_up"
    revision_left = 0
    learning_count = 0
    continue_learning_label = ""
    pace_label = plan.pace_label
    show_plan_prompt = False
    if (
        active is not None
        and active.kind == "revision"
        and active.pending_count > 0
        and active.plan_date == today
    ):
        today_mode = "continue_revision"
        revision_left = active.pending_count
        first_due_id = active.next_pending().learning_unit_id if active.next_pending() else first_due_id
    elif due_units:
        today_mode = "start_revision"
    elif (
        active is not None
        and active.kind in ("one_day_learning", "auto_learning")
        and active.pending_count > 0
        and active.plan_date == today
    ):
        today_mode = "continue_learning"
        learning_count = active.pending_count
        nxt = active.next_pending()
        first_due_id = nxt.learning_unit_id if nxt is not None else first_due_id
        if active.kind == "one_day_learning":
            continue_learning_label = f"Continue today's plan · {learning_count} left"
        else:
            continue_learning_label = f"Continue learning · {learning_count} left"
    elif entitled and plan.is_auto:
        today_mode = "auto_learning"
        learning_count = int(plan.daily_target or 0)
        from constitution_memorizer.progress.mix_selector import eligible_new_units

        if not eligible_new_units(eng):
            today_mode = "caught_up"
            learning_count = 0
    else:
        today_mode = "self_paced"
        from constitution_memorizer.progress.mix_selector import eligible_new_units

        eligible = eligible_new_units(eng)
        dismissed = plan.plan_prompt_dismissed_on == today
        show_plan_prompt = bool(eligible) and not dismissed
        if not eligible and not cont_unit:
            today_mode = "caught_up"

    next_learning_day = None
    if plan.is_anchored and entitled:
        capacity = project_new_capacity(eng, plan, today=today, entitled=True)
        future = [d for d in sorted(capacity) if d >= today]
        next_learning_day = future[0] if future else None

    return {
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
        "recent": recent,
        "upcoming": upcoming_revisions(eng, as_of=today),
        "today_mode": today_mode,
        "revision_left": revision_left,
        "learning_count": learning_count,
        "continue_learning_label": continue_learning_label,
        "pace_label": pace_label,
        "show_plan_prompt": show_plan_prompt,
        "learning_plan": plan,
        "next_learning_day": next_learning_day,
        "active_session_id": active.id if active is not None else "",
        "can_auto_plan": entitled,
    }
