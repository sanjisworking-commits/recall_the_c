"""Today and Calendar projections for Playground revisions.

Read models only. No new queue or calendar tables. No Act hydration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from constitution_memorizer.playground.eligibility import playground_catalogue_law
from constitution_memorizer.playground.lifecycle import (
    build_revision_mode_progress,
    days_overdue,
    overdue_label,
    parse_iso_date,
)
from constitution_memorizer.playground.locators import LocatorError, parse_locator
from constitution_memorizer.playground.roster.period import playground_today
from constitution_memorizer.playground.urls import law_path, learn_path
from constitution_memorizer.playground.view import catalog_titles
from constitution_memorizer.web.calendar_view import CalendarChip


@dataclass(frozen=True)
class LawRevisionTodayItem:
    law_id: str
    law_title: str
    short_title: str
    number: str
    source_locator: str
    rung_days: int
    next_revision: str
    is_overdue: bool
    days_overdue: int
    due_label: str
    href: str


def _active_law_ids(roster, user_id) -> list[str]:
    return [item.law_id for item in roster.active_roster_items(user_id)]


def _section_number(locator: str) -> str:
    try:
        return parse_locator(locator).number
    except LocatorError:
        if ":section:" in locator:
            return locator.split(":section:", 1)[1]
        return locator


def _revise_href(law_id: str, locator: str, next_mode: str | None) -> str:
    number = _section_number(locator)
    return learn_path(law_id, number, next_mode or "read", revision=True)


def law_revision_today_items(
    overlay,
    roster,
    user_id,
    *,
    as_of: date | None = None,
) -> list[LawRevisionTodayItem]:
    today = as_of or playground_today()
    active = _active_law_ids(roster, user_id)
    facts = overlay.list_due_revisions(user_id, today, active)
    items: list[LawRevisionTodayItem] = []
    for fact in facts:
        rows = overlay.list_revision_mode_progress(
            user_id, fact.law_id, fact.source_locator, fact.interval_days
        )
        cycle = build_revision_mode_progress(
            fact.source_locator, fact.interval_days, rows
        )
        overdue_n = days_overdue(fact.next_revision, today)
        title, short = catalog_titles(fact.law_id)
        items.append(
            LawRevisionTodayItem(
                law_id=fact.law_id,
                law_title=title,
                short_title=short,
                number=_section_number(fact.source_locator),
                source_locator=fact.source_locator,
                rung_days=fact.interval_days,
                next_revision=fact.next_revision,
                is_overdue=overdue_n > 0,
                days_overdue=overdue_n,
                due_label=overdue_label(overdue_n),
                href=_revise_href(fact.law_id, fact.source_locator, cycle.next_mode),
            )
        )
    items.sort(
        key=lambda row: (
            row.next_revision,
            row.law_id,
            row.source_locator,
        )
    )
    return items


def playground_today_context(request, *, as_of: date | None = None) -> dict[str, Any]:
    overlay = getattr(request.app.state, "playground", None)
    roster = getattr(request.app.state, "roster", None)
    if overlay is None or roster is None:
        return {"law_revisions": (), "law_revision_count": 0}
    user = getattr(request.state, "current_user", None)
    if request.app.state.multiuser_enabled:
        if user is None:
            return {"law_revisions": (), "law_revision_count": 0}
        user_id = user.id
    else:
        from constitution_memorizer.progress.user_ids import LOCAL_USER_ID

        user_id = LOCAL_USER_ID
    items = law_revision_today_items(overlay, roster, user_id, as_of=as_of)
    return {
        "law_revisions": tuple(items),
        "law_revision_count": len(items),
    }


def playground_calendar_chips(
    overlay,
    roster,
    user_id,
    *,
    month_start: date,
    month_end: date,
    today: date,
) -> dict[str, list[CalendarChip]]:
    active = _active_law_ids(roster, user_id)
    facts = overlay.list_revision_schedule(
        user_id, month_start, month_end, active
    )
    by_iso: dict[str, list[CalendarChip]] = {}
    for fact in facts:
        nxt = parse_iso_date(fact.next_revision)
        if nxt is None:
            continue
        catalog = playground_catalogue_law(fact.law_id)
        short = catalog.short_title if catalog is not None else fact.law_id
        number = _section_number(fact.source_locator)
        label = f"{short} · §{number}"
        title = f"{short} · Section {number} — Day {fact.interval_days} revision"
        due = nxt <= today
        if due:
            rows = overlay.list_revision_mode_progress(
                user_id, fact.law_id, fact.source_locator, fact.interval_days
            )
            cycle = build_revision_mode_progress(
                fact.source_locator, fact.interval_days, rows
            )
            href = _revise_href(fact.law_id, fact.source_locator, cycle.next_mode)
            kind = "due"
        else:
            href = law_path(fact.law_id)
            kind = "scheduled"
        by_iso.setdefault(nxt.isoformat(), []).append(
            CalendarChip(
                kind=kind,
                unit_id="",
                label=label,
                title=title,
                href=href,
                category="Law revision",
            )
        )
    return by_iso


def attach_playground_calendar_chips(view, extra: dict[str, list[CalendarChip]]) -> None:
    if not extra:
        return
    for day in view.days:
        if not day.iso:
            continue
        added = extra.get(day.iso)
        if added:
            day.chips.extend(added)
