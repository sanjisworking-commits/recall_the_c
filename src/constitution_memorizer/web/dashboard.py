"""Authenticated dashboard view-model (Multi-User Experience layout)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Literal

from constitution_memorizer.learning.schemas import LearningUnit
from constitution_memorizer.planner.eligibility import remaining_unseen_count
from constitution_memorizer.planner.models import pace_label
from constitution_memorizer.planner.planner import LearningPlanner
from constitution_memorizer.progress.repository import LEARN_MODES, StudySession, UserLearningPlan
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.completion import next_learn_url, session_entry_mode
from constitution_memorizer.web.progress_stats import (
    _is_completed,
    all_article_progress,
)
from constitution_memorizer.web.request_context import record_request_timing
from constitution_memorizer.web.service import (
    AUTO_LEARNING_KIND,
    DAY_PLAN_KIND,
    REVISION_KIND,
    _is_missing_optional_schema,
    continue_unit_id,
    daily_goal_streak,
    due_checklist,
    session_progress,
)

TodayKind = Literal["new", "review"]
TodayStatus = Literal["done", "current", "upcoming", "deferred"]


@dataclass(frozen=True)
class TodayUnit:
    """One node on Today's required path."""

    unit_id: str
    title: str
    article_label: str
    kind: TodayKind
    status: TodayStatus
    href: str
    position: int

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


def _article_label(unit: LearningUnit) -> str:
    if unit.article_number:
        return f"Article {unit.article_number}"
    return unit.display_title


def _today_units_from_session(
    engine: ReminderEngine,
    session: StudySession,
    *,
    multiuser: bool = True,
) -> list[TodayUnit]:
    kind: TodayKind = "review" if session.kind == REVISION_KIND else "new"
    pending_seen = False
    out: list[TodayUnit] = []
    for item in session.items:
        unit = engine.get_unit(item.learning_unit_id)
        if unit is None:
            continue
        if item.status == "completed":
            status: TodayStatus = "done"
        elif item.status == "deferred":
            status = "deferred"
        elif not pending_seen:
            status = "current"
            pending_seen = True
        else:
            status = "upcoming"
        href = next_learn_url(
            engine,
            unit.id,
            multiuser=multiuser,
            session_id=session.id,
            mode=session_entry_mode(session.kind),
        )
        out.append(
            TodayUnit(
                unit_id=unit.id,
                title=unit.display_title,
                article_label=_article_label(unit),
                kind=kind,
                status=status,
                href=href,
                position=item.position + 1,
            )
        )
    return out


def _today_units_from_preview(
    engine: ReminderEngine,
    units: list[LearningUnit],
    *,
    kind: TodayKind,
    multiuser: bool = True,
) -> list[TodayUnit]:
    out: list[TodayUnit] = []
    for index, unit in enumerate(units, start=1):
        href = next_learn_url(
            engine,
            unit.id,
            multiuser=multiuser,
            mode=session_entry_mode("revision" if kind == "review" else "auto_learning"),
        )
        out.append(
            TodayUnit(
                unit_id=unit.id,
                title=unit.display_title,
                article_label=_article_label(unit),
                kind=kind,
                status="current" if index == 1 else "upcoming",
                href=href,
                position=index,
            )
        )
    return out


def build_today_units(
    engine: ReminderEngine,
    *,
    today: date,
    due_units: list[LearningUnit],
    auto_selected: bool,
    today_new_ids: list[str],
    multiuser: bool = True,
    sessions: dict[str, StudySession | None] | None = None,
) -> list[TodayUnit]:
    """Read-only Today path. Never creates a study_session row."""
    revision_today = (
        sessions.get(REVISION_KIND) if sessions is not None else _session_for_day(engine, REVISION_KIND, today)
    )
    if revision_today is not None and revision_today.items:
        return _today_units_from_session(engine, revision_today, multiuser=multiuser)
    if due_units:
        return _today_units_from_preview(
            engine, due_units, kind="review", multiuser=multiuser
        )
    auto_today = (
        sessions.get(AUTO_LEARNING_KIND)
        if sessions is not None
        else _session_for_day(engine, AUTO_LEARNING_KIND, today)
    )
    if auto_today is not None and auto_today.items:
        return _today_units_from_session(engine, auto_today, multiuser=multiuser)
    if auto_selected and today_new_ids:
        preview = [
            unit
            for unit_id in today_new_ids
            if (unit := engine.get_unit(unit_id)) is not None
        ]
        return _today_units_from_preview(
            engine, preview, kind="new", multiuser=multiuser
        )
    day_today = (
        sessions.get(DAY_PLAN_KIND)
        if sessions is not None
        else _session_for_day(engine, DAY_PLAN_KIND, today)
    )
    if day_today is not None and day_today.items:
        return _today_units_from_session(engine, day_today, multiuser=multiuser)
    return []


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
        if not _is_missing_optional_schema(error):
            raise
        return UserLearningPlan()


def _session_for_day(engine: ReminderEngine, kind: str, today: date):
    try:
        return engine.study_session_for_day(kind=kind, plan_date=today)  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise
        return None



def _has_started(
    engine: ReminderEngine, *, today: date, strip: dict[str, int]
) -> bool:
    """Has this account begun learning at all?

    Deliberately NOT ``is_new``. That flag means "nothing completed", which is
    a different question: a user part-way through their first unit, or one who
    finished today's Auto session (session items complete without writing a
    learning_unit_progress completion), has plainly started and must not be
    told "You haven't started yet."

    Any progress row and any of today's sessions count. A stored plan does
    not: setting one is a preference, not a first Article, and the design
    reaches the plan intro from this very screen.
    """
    if strip["articles_started"] or strip["units_completed"]:
        return True
    if engine.list_all_progress():
        return True
    return any(
        _session_for_day(engine, kind, today) is not None
        for kind in ("revision", "auto_learning", "day_plan")
    )


# The design's "Good places to begin" list. Each row is only rendered when its
# target actually resolves, so a corpus gap shows one fewer row rather than a
# dead link. The Preamble is in the design but has no learning unit in
# data/output/learning_units.json — the parser supports one, the corpus has
# none — so it is absent until that content exists.
STARTER_UNITS: tuple[dict[str, str], ...] = (
    {
        "unit_id": "article-14",
        "title": "Article 14",
        "subtitle": "Equality before law — one clause, a classic first pick",
        "kind": "session",
    },
    {
        "article_number": "19",
        "title": "Article 19",
        "subtitle": "The six freedoms — the heart of Part III",
        "kind": "detail",
    },
)


def starter_rows(engine: ReminderEngine) -> list[dict[str, str]]:
    """Resolve STARTER_UNITS against the corpus, dropping anything missing.

    "session" rows open a learn session directly; "detail" rows open the
    Article page. A row whose unit or article is absent is skipped entirely.
    """
    rows: list[dict[str, str]] = []
    for spec in STARTER_UNITS:
        unit_id = spec.get("unit_id")
        if unit_id:
            if engine.get_unit(unit_id) is None:
                continue
            href = f"/learn/{unit_id}"
        else:
            number = spec.get("article_number") or ""
            if not any(
                u.article_number == number for u in engine.units.values()
            ):
                continue
            href = f"/browse/article/{number}"
        rows.append(
            {"title": spec["title"], "subtitle": spec["subtitle"], "href": href}
        )
    return rows


def build_guest_dashboard_context(engine: ReminderEngine) -> dict[str, Any]:
    """Today for a signed-out reader — diff.md item 2's guest branch.

    The design branches the first-run screen by tier instead of sending guests
    to a gate page of their own: same hero and starter list, no name and no
    streak, and a sign-in card where a signed-in user gets plan and tour. The
    gate is not removed, only moved one step later — the CTA goes through
    /login, so nothing a guest could not already do becomes possible here.

    A guest has no stored progress, so has_started is false by construction
    and the screen is corpus plus copy; no per-user read happens at all.
    """
    return {
        # No account, so no avatar and no profile — the header falls back to
        # the guest "?" mark. The key must be present: the template's Jinja
        # environment is strict about undefined names.
        "user": None,
        "dashboard_state": "ok",
        "has_started": False,
        "show_first_run": True,
        "starter_rows": starter_rows(engine),
        "display_label": "",
        "first_name": "",
        "greeting": "Welcome.",
        "subtext": "Reading as a guest",
        "daily_goal_streak": 0,
        "access": None,
        "subscription": None,
        "completion": None,
        "learning_cta": "browse",
    }


def build_dashboard_context(
    eng: ReminderEngine,
    *,
    display_label: str,
    as_of: date | None = None,
    now: datetime | None = None,
    auto_entitled: bool = True,
    mix_eligibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    today = as_of or date.today()
    now = now or datetime.now(timezone.utc)
    try:
        eng.ensure_planner_bundle(as_of=today)
    except Exception as error:  # noqa: BLE001 — schema-gap window
        if not _is_missing_optional_schema(error):
            raise
    today_sessions = {
        REVISION_KIND: _session_for_day(eng, REVISION_KIND, today),
        AUTO_LEARNING_KIND: _session_for_day(eng, AUTO_LEARNING_KIND, today),
        DAY_PLAN_KIND: _session_for_day(eng, DAY_PLAN_KIND, today),
    }
    name = first_name(display_label)
    due_units = due_checklist(eng, as_of=today)
    chips, chips_more = due_article_chips(due_units)
    strip = progress_strip(eng, as_of=today)
    is_new = strip["articles_started"] == 0 and strip["units_completed"] == 0
    has_started = _has_started(eng, today=today, strip=strip)

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
    revision_today = today_sessions[REVISION_KIND]
    revision_session = (
        revision_today
        if revision_today is not None and revision_today.status == "active"
        else None
    )
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

    revision_completed_today = revision_today.completed_count if revision_today else 0

    plan = _learning_plan_or_default(eng)
    auto_selected = bool(plan.is_auto and auto_entitled)
    auto_active = bool(plan.is_active_auto and auto_entitled)

    if auto_selected:
        from constitution_memorizer.web.service import ensure_auto_roadmap

        try:
            ensure_auto_roadmap(
                eng,
                as_of=today,
                auto_entitled=auto_entitled,
                **(mix_eligibility or {}),
            )
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise

    learning_session = None
    if today_mode == "learning":
        for kind in (AUTO_LEARNING_KIND, DAY_PLAN_KIND):
            candidate = today_sessions.get(kind)
            if candidate is not None and candidate.status == "active":
                learning_session = candidate
                break
    learning_remaining = learning_session.remaining if learning_session else 0

    learning_today = learning_session
    if learning_today is None and today_mode == "learning":
        for kind in (AUTO_LEARNING_KIND, DAY_PLAN_KIND):
            learning_today = today_sessions.get(kind)
            if learning_today is not None:
                break

    unseen = 0
    try:
        unseen = remaining_unseen_count(eng, as_of=today, **(mix_eligibility or {}))
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise

    today_new_ids: list[str] = []
    today_new_titles: list[str] = []
    try:
        planned_today = eng.list_auto_plan_day(today)
        if planned_today is not None:
            today_new_ids = [item.learning_unit_id for item in planned_today.items]
            for unit_id in today_new_ids:
                unit = eng.get_unit(unit_id)
                if unit is not None:
                    today_new_titles.append(unit.display_title)
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise
    if today_session_ids_from_session := (
        [item.learning_unit_id for item in learning_today.items]
        if learning_today is not None and learning_today.kind == AUTO_LEARNING_KIND
        else None
    ):
        today_new_ids = today_session_ids_from_session
        today_new_titles = [
            unit.display_title
            for unit_id in today_new_ids
            if (unit := eng.get_unit(unit_id)) is not None
        ]

    next_learning_day = None
    today_new_count = len(today_new_ids) if auto_selected else 0
    today_pace = pace_label(plan.daily_target if auto_selected else None)
    started = perf_counter()
    try:
        from constitution_memorizer.planner.roadmap import roadmap_horizon

        planner = LearningPlanner()
        persisted_days = {
            day.plan_date: [item.learning_unit_id for item in day.items]
            for day in eng.list_auto_plan_window(today, roadmap_horizon(today))
        }
        projected = planner.project(
            eng,
            plan,
            as_of=today,
            until=roadmap_horizon(today),
            remaining_unseen=unseen,
            auto_entitled=auto_entitled,
            persisted_days=persisted_days,
            today_auto_session=today_sessions.get(AUTO_LEARNING_KIND),
        )
        today_plan = next((day for day in projected if day.day == today), None)
        next_learning_day = next(
            (
                day.day
                for day in projected
                if day.kind == "new" and day.new_capacity > 0
            ),
            None,
        )
        if today_plan is not None and today_plan.kind == "review":
            today_new_count = 0
            today_new_ids = []
            today_new_titles = []
        elif today_plan is not None and today_plan.new_capacity:
            today_new_count = today_plan.new_capacity
            today_pace = pace_label(plan.daily_target)
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise
    record_request_timing("planner_project", started)

    sections_started = perf_counter()
    learning_cta = "browse"
    if today_mode == "learning":
        if learning_remaining:
            learning_cta = "continue_session"
        elif learning_today is not None and (
            learning_today.status == "complete" or learning_today.remaining == 0
        ):
            learning_cta = "learning_complete"
        elif auto_selected and today_new_count > 0:
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
    # diff.md item 6: Plan my day is an affordance on the hero card, not only
    # a state the dashboard happens to be in. It is offered whenever the mix
    # could actually be planned — self-paced, nothing due, material left —
    # which includes days where "Not today" has already been tapped. Offering
    # it when the post would be refused would be worse than not offering it.
    plan_my_day_available = (
        today_mode == "learning"
        and learning_today is None
        and not auto_selected
        and unseen > 0
        and (plan is None or plan.mode == "self_paced")
    )

    today_units = build_today_units(
        eng,
        today=today,
        due_units=due_units,
        auto_selected=auto_selected,
        today_new_ids=today_new_ids,
        multiuser=True,
        sessions=today_sessions,
    )
    goal_done = sum(1 for item in today_units if item.status == "done")
    goal_total = sum(1 for item in today_units if item.status != "deferred")
    goal_pct = int(round(100 * goal_done / goal_total)) if goal_total else 0
    streak = daily_goal_streak(eng, as_of=today)
    record_request_timing("dashboard_sections", sections_started)

    # The zero state says "Nothing due today · You haven't started yet". The
    # first half has to be true as well: an Auto Plan places clauses for today
    # on an account with no progress yet, and gating on has_started alone hid
    # the whole of Today behind the first-run screen.
    show_first_run = not has_started and goal_total == 0

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
        "plan_my_day_available": plan_my_day_available,
        "today_new_count": today_new_count,
        "today_new_titles": today_new_titles,
        "today_pace_label": today_pace,
        "next_learning_day": next_learning_day,
        "display_label": display_label,
        "first_name": name,
        "greeting": greeting,
        "subtext": subtext,
        "is_new": is_new,
        # The design's first-run zero state lives at this route, branching on
        # has_started (not is_new — see _has_started). Rows are only built when
        # they will actually be shown.
        "has_started": has_started,
        "show_first_run": show_first_run,
        "starter_rows": [] if not show_first_run else starter_rows(eng),
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
        "today_units": today_units,
        "goal_done": goal_done,
        "goal_total": goal_total,
        "goal_pct": goal_pct,
        "daily_goal_streak": streak,
        # All completions today (revision + voluntary new learning). Do not
        # use this for "N revisions completed today" — that is
        # revision_completed_today from the revision session's completed_count.
        "completed_today": sum(
            1
            for row in eng.list_all_progress()
            if row.last_completed == today and row.times_completed > 0
        ),
    }
