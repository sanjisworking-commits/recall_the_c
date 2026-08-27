"""Calendar month grid view-model for Learn progress."""

from __future__ import annotations

import calendar as pycal
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from constitution_memorizer.progress.repository import ProgressRecord
from constitution_memorizer.progress.scheduler import (
    INTERVAL_LADDER,
    ReminderEngine,
    advance_interval,
)

ChipKind = Literal[
    "memorized", "review_done", "due", "scheduled", "new_planned", "review_capacity"
]

WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


@dataclass(frozen=True)
class CalendarChip:
    kind: ChipKind
    unit_id: str
    label: str
    title: str


@dataclass
class CalendarDay:
    day: int | None
    iso: str | None
    is_today: bool = False
    is_past: bool = False
    is_blank: bool = False
    chips: list[CalendarChip] = field(default_factory=list)

    @property
    def long_label(self) -> str:
        """"Fri 28 August" — the heading when a day is selected on the phone."""
        if not self.iso:
            return ""
        return date.fromisoformat(self.iso).strftime("%a %-d %B")

    @property
    def dominant_kind(self) -> str | None:
        """One state for the phone's day cell, derived from the chips already here.

        The phone grid marks a day with a single bar rather than the desktop's
        chip stack, so several units on one day collapse to the most urgent.
        ``ChipKind`` has no ``overdue``: ``build_calendar_month`` emits ``due``
        only for a row's ``next_revision``, so a *past* day carrying a ``due``
        chip is by definition a missed review.
        """
        if not self.chips:
            return None
        kinds = {chip.kind for chip in self.chips}
        if "due" in kinds:
            return "overdue" if self.is_past else "due"
        if "scheduled" in kinds or "review_capacity" in kinds:
            return "scheduled"
        if "new_planned" in kinds:
            return "new"
        if kinds & {"review_done", "memorized"}:
            return "done"
        return None


@dataclass(frozen=True)
class CalendarMonth:
    year: int
    month: int
    title: str
    today: date
    prev_year: int
    prev_month: int
    next_year: int
    next_month: int
    summary: str
    weekdays: tuple[str, ...]
    days: list[CalendarDay]
    memorized_count: int
    review_done_count: int
    scheduled_count: int


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def _chip_label(display_title: str) -> str:
    text = display_title.strip()
    if text.startswith("Article "):
        text = "Art " + text[len("Article ") :]
    if len(text) > 22:
        return text[:21] + "…"
    return text


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


def completed_review_history(
    row: ProgressRecord,
) -> list[tuple[date, ChipKind, int | None]]:
    """
    Infer past completion days by walking ``INTERVAL_LADDER`` backwards from
    ``last_completed``.

    ``mark_done`` stores only the latest date, so the calendar reconstructs
    earlier rungs (memorize, then 1 → 3 → 7 → …) assuming on-time reviews.
    Late reviews shift inferred earlier dates.

    Each tuple is ``(when, kind, rung)`` where ``rung`` is the completed
    interval in days, or ``None`` for the first memorize.
    """
    if row.last_completed is None or row.times_completed < 1:
        return []
    n_reviews = min(row.times_completed - 1, len(INTERVAL_LADDER))
    rungs = INTERVAL_LADDER[:n_reviews]
    cursor = row.last_completed
    events: list[tuple[date, ChipKind, int | None]] = []
    for rung in reversed(rungs):
        events.append((cursor, "review_done", rung))
        cursor = cursor - timedelta(days=rung)
    events.append((cursor, "memorized", None))
    events.reverse()
    return events


def _overlay_capacity_markers(
    engine: ReminderEngine,
    by_day: dict[int, list[CalendarChip]],
    *,
    month_start: date,
    month_end: date,
    today: date,
    auto_entitled: bool,
) -> None:
    """Add NEW · N / REVIEW · N chips plus exact planned-unit titles."""
    from constitution_memorizer.planner.eligibility import is_unlearned
    from constitution_memorizer.planner.planner import LearningPlanner, _reviews_from_learn_date
    from constitution_memorizer.planner.roadmap import roadmap_horizon
    from constitution_memorizer.progress.repository import UserLearningPlan
    from constitution_memorizer.web.service import _is_missing_study_session_table

    try:
        plan = engine.get_learning_plan()
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise
        plan = UserLearningPlan()
    window_end = roadmap_horizon(today)
    persisted: dict[date, list[str]] = {}
    historical: dict[date, list[str]] = {}
    try:
        hist_start = month_start
        hist_days = engine.list_auto_plan_window(hist_start, month_end)
        for day in hist_days:
            ids = [item.learning_unit_id for item in day.items]
            if day.plan_date < today:
                historical[day.plan_date] = ids
            elif day.plan_date <= window_end:
                persisted[day.plan_date] = ids
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise
    today_session_ids: list[str] | None = None
    try:
        session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
        if session is not None:
            today_session_ids = [item.learning_unit_id for item in session.items]
            persisted[today] = today_session_ids
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise

    try:
        days = LearningPlanner().project(
            engine,
            plan,
            as_of=today,
            until=month_end,
            remaining_unseen=0,
            auto_entitled=auto_entitled,
        )
    except Exception as error:  # noqa: BLE001
        if not _is_missing_study_session_table(error):
            raise
        return

    hypothetical_labels: dict[date, list[tuple[str, str, str]]] = {}
    if auto_entitled and plan.is_auto:
        for plan_date, unit_ids in persisted.items():
            if not (today <= plan_date <= window_end):
                continue
            for unit_id in unit_ids:
                if not is_unlearned(engine, unit_id):
                    continue
                unit = engine.get_unit(unit_id)
                if unit is None:
                    continue
                label = _chip_label(unit.display_title)
                for when, _count in _reviews_from_learn_date(plan_date, 1).items():
                    if month_start <= when <= month_end:
                        hypothetical_labels.setdefault(when, []).append(
                            (unit_id, label, unit.display_title)
                        )

    for planned in days:
        if not (month_start <= planned.day <= month_end):
            continue
        if planned.kind == "review" and planned.review_count:
            chips = [
                CalendarChip(
                    kind="review_capacity",
                    unit_id="",
                    label=f"REVIEW · {planned.review_count}",
                    title=(
                        f"{planned.review_count} revision"
                        f"{'s' if planned.review_count != 1 else ''} on this day"
                    ),
                )
            ]
            for unit_id, label, title in hypothetical_labels.get(planned.day, []):
                chips.append(
                    CalendarChip(
                        kind="review_capacity",
                        unit_id=unit_id,
                        label=label,
                        title=f"{title} — projected review",
                    )
                )
            by_day[planned.day.day][0:0] = chips
        elif planned.kind == "new" and planned.new_capacity:
            ids = persisted.get(planned.day, [])
            chips = [
                CalendarChip(
                    kind="new_planned",
                    unit_id="",
                    label=f"NEW · {planned.new_capacity}",
                    title=(
                        f"{planned.new_capacity} new clause"
                        f"{'s' if planned.new_capacity != 1 else ''} planned"
                    ),
                )
            ]
            for unit_id in ids:
                unit = engine.get_unit(unit_id)
                title = unit.display_title if unit is not None else unit_id
                chips.append(
                    CalendarChip(
                        kind="new_planned",
                        unit_id=unit_id,
                        label=_chip_label(title),
                        title=title,
                    )
                )
            by_day[planned.day.day][0:0] = chips

    for plan_date, unit_ids in historical.items():
        if not (month_start <= plan_date <= month_end) or not unit_ids:
            continue
        chips = [
            CalendarChip(
                kind="new_planned",
                unit_id="",
                label=f"NEW · {len(unit_ids)}",
                title=f"{len(unit_ids)} new clauses planned that day",
            )
        ]
        for unit_id in unit_ids:
            unit = engine.get_unit(unit_id)
            title = unit.display_title if unit is not None else unit_id
            chips.append(
                CalendarChip(
                    kind="new_planned",
                    unit_id=unit_id,
                    label=_chip_label(title),
                    title=title,
                )
            )
        existing = by_day[plan_date.day]
        if not any(chip.kind == "new_planned" for chip in existing):
            by_day[plan_date.day][0:0] = chips


def build_calendar_month(
    engine: ReminderEngine,
    *,
    year: int,
    month: int,
    today: date | None = None,
    auto_entitled: bool = True,
) -> CalendarMonth:
    """Build a Sunday-first month grid with progress + projected ladder chips."""
    if month < 1 or month > 12:
        raise ValueError("month must be 1–12")
    today = today or date.today()
    month_start = date(year, month, 1)
    last_day = pycal.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    # calendar.monthdayscalendar is Monday-first; convert to Sunday-first.
    cal = pycal.Calendar(firstweekday=6)
    weeks = cal.monthdayscalendar(year, month)

    by_day: dict[int, list[CalendarChip]] = {d: [] for d in range(1, last_day + 1)}
    memorized_count = 0
    review_done_count = 0
    scheduled_count = 0

    for row in engine.list_all_progress():
        unit = engine.get_unit(row.learning_unit_id)
        if unit is None:
            continue
        label = _chip_label(unit.display_title)
        full = unit.display_title

        for when, kind, rung in completed_review_history(row):
            if not (month_start <= when <= month_end):
                continue
            if kind == "memorized":
                memorized_count += 1
                tip = f"{full} — memorized"
                chip_label = label
            else:
                review_done_count += 1
                tip = (
                    f"{full} — {rung}-day review done"
                    if rung is not None
                    else f"{full} — review done"
                )
                chip_label = f"{label} ✓"
            by_day[when.day].append(
                CalendarChip(
                    kind=kind,
                    unit_id=row.learning_unit_id,
                    label=chip_label,
                    title=tip,
                )
            )

        for rev_date, rung in remaining_review_schedule(row):
            if not (month_start <= rev_date <= month_end):
                continue
            if rev_date <= today:
                # Only the actionable next_revision is due; skip past projections.
                if row.next_revision is None or rev_date != row.next_revision:
                    continue
                kind = "due"
                tip = f"{full} — {rung}-day review due"
            else:
                kind = "scheduled"
                tip = f"{full} — {rung}-day review"
                scheduled_count += 1
            by_day[rev_date.day].append(
                CalendarChip(
                    kind=kind,
                    unit_id=row.learning_unit_id,
                    label=label,
                    title=tip,
                )
            )

    _overlay_capacity_markers(
        engine,
        by_day,
        month_start=month_start,
        month_end=month_end,
        today=today,
        auto_entitled=auto_entitled,
    )

    days: list[CalendarDay] = []
    for week in weeks:
        for day_num in week:
            if day_num == 0:
                days.append(CalendarDay(day=None, iso=None, is_blank=True))
                continue
            d = date(year, month, day_num)
            days.append(
                CalendarDay(
                    day=day_num,
                    iso=d.isoformat(),
                    is_today=d == today,
                    is_past=d < today,
                    chips=by_day.get(day_num, []),
                )
            )

    prev_year, prev_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    title = month_start.strftime("%B %Y")
    summary = (
        f"{memorized_count} unit{'s' if memorized_count != 1 else ''} memorized this month · "
        f"{review_done_count} review{'s' if review_done_count != 1 else ''} completed · "
        f"{scheduled_count} review{'s' if scheduled_count != 1 else ''} scheduled"
    )
    return CalendarMonth(
        year=year,
        month=month,
        title=title,
        today=today,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        summary=summary,
        weekdays=WEEKDAYS,
        days=days,
        memorized_count=memorized_count,
        review_done_count=review_done_count,
        scheduled_count=scheduled_count,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mobile "Revisions" screen (design 19). Same data as the month grid, folded
# into a week strip + today's list + the interval ladder, which is what fits
# a 390 px phone without hiding anything the grid shows.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RevisionWeekDay:
    dow: str
    day: int
    iso: str
    is_today: bool
    has_revision: bool


@dataclass(frozen=True)
class RevisionRow:
    unit_id: str
    title: str
    state: Literal["overdue", "due", "done"]
    meta: str
    href: str


@dataclass(frozen=True)
class RevisionLadderRung:
    label: str
    count: int
    percent: int


@dataclass(frozen=True)
class RevisionsView:
    month_label: str
    week: list[RevisionWeekDay]
    rows: list[RevisionRow]
    today_label: str
    ladder: list[RevisionLadderRung]


def _rung_label(interval_days: int) -> str:
    return f"Day {interval_days if interval_days > 0 else INTERVAL_LADDER[0]}"


def build_revisions_view(
    engine: ReminderEngine,
    *,
    today: date | None = None,
) -> RevisionsView:
    """Week strip, today's units and the ladder — the phone shape of /calendar."""
    today = today or date.today()
    rows_all = list(engine.list_all_progress())

    # Week strip: yesterday through the next six days, so "today" sits second.
    scheduled_days: set[date] = set()
    for row in rows_all:
        for when, _rung in remaining_review_schedule(row):
            scheduled_days.add(when)

    week: list[RevisionWeekDay] = []
    for offset in range(-1, 6):
        day = today + timedelta(days=offset)
        week.append(
            RevisionWeekDay(
                dow=day.strftime("%a").upper(),
                day=day.day,
                iso=day.isoformat(),
                is_today=day == today,
                has_revision=day in scheduled_days and day != today,
            )
        )

    rows: list[RevisionRow] = []
    for row in rows_all:
        unit = engine.get_unit(row.learning_unit_id)
        if unit is None:
            continue
        rung = _rung_label(row.interval_days)
        if row.next_revision is not None and row.next_revision <= today:
            state: Literal["overdue", "due", "done"] = (
                "overdue" if row.next_revision < today else "due"
            )
            overdue_days = (today - row.next_revision).days
            meta = (
                f"Overdue by {overdue_days} day{'s' if overdue_days != 1 else ''} · {rung}"
                if state == "overdue"
                else f"Due today · {rung}"
            )
        elif row.last_completed == today and row.times_completed > 0:
            state = "done"
            meta = f"Done · {rung}"
        else:
            continue
        rows.append(
            RevisionRow(
                unit_id=row.learning_unit_id,
                title=unit.display_title,
                state=state,
                meta=meta,
                href=f"/learn/{row.learning_unit_id}",
            )
        )
    order = {"overdue": 0, "due": 1, "done": 2}
    rows.sort(key=lambda r: (order[r.state], r.title))

    # Ladder: how many units sit on each rung of 1 → 3 → 7 → 15 → 30 → 60.
    counts = {rung: 0 for rung in INTERVAL_LADDER}
    for row in rows_all:
        if row.status not in ("review", "mastered"):
            continue
        rung = row.interval_days if row.interval_days in counts else INTERVAL_LADDER[0]
        counts[rung] += 1
    peak = max(counts.values()) if counts else 0
    ladder = [
        RevisionLadderRung(
            label=f"Day {rung}",
            count=counts[rung],
            percent=int(round(100 * counts[rung] / peak)) if peak else 0,
        )
        for rung in INTERVAL_LADDER
    ]

    pending = sum(1 for r in rows if r.state != "done")
    if pending:
        today_label = f"Today · {pending} unit{'s' if pending != 1 else ''}"
    elif rows:
        today_label = "Today · all done"
    else:
        today_label = "Today · nothing due"
    return RevisionsView(
        month_label=today.strftime("%B %Y"),
        week=week,
        rows=rows,
        today_label=today_label,
        ladder=ladder,
    )
