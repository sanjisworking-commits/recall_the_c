"""Today and Calendar projections for Playground revisions.

Read models only. No new queue or calendar tables. No Act hydration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any, Sequence

from constitution_memorizer.calendar_sync.projection import DayItem
from constitution_memorizer.playground.access import playground_view_access
from constitution_memorizer.playground.eligibility import playground_catalogue_law
from constitution_memorizer.playground.learning.modes import next_learn_mode
from constitution_memorizer.playground.lifecycle import (
    LIFECYCLE_ACTIVE,
    build_revision_mode_progress,
    days_overdue,
    overdue_label,
    parse_iso_date,
)
from constitution_memorizer.playground.locators import LocatorError, locator_section_number, parse_locator
from constitution_memorizer.playground.revision import advance_interval
from constitution_memorizer.playground.roster.period import playground_today
from constitution_memorizer.playground.source_review import (
    CHANGE_KIND_MISSING,
    CHANGE_KIND_OMITTED,
    STATUS_PENDING,
)
from constitution_memorizer.playground.urls import law_path, learn_path_for_locator
from constitution_memorizer.playground.units import citation_label
from constitution_memorizer.playground.view import catalog_titles
from constitution_memorizer.web.calendar_view import CalendarChip
from constitution_memorizer.web.dashboard import TodayUnit
from constitution_memorizer.web.service import _is_missing_optional_schema


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
        return locator_section_number(locator)
    except LocatorError:
        return locator


def _revise_href(law_id: str, locator: str, next_mode: str | None) -> str:
    try:
        loc = parse_locator(locator)
    except LocatorError:
        return learn_path_for_locator(
            f"{law_id}:section:{_section_number(locator)}",
            next_mode or "read",
            revision=True,
        )
    return learn_path_for_locator(loc, next_mode or "read", revision=True)


def _chip_number_label(locator: str) -> str:
    try:
        loc = parse_locator(locator)
        cited = citation_label(loc)
        if cited.startswith("Section "):
            return cited[len("Section ") :]
        return cited
    except LocatorError:
        return _section_number(locator)


def _chip_title_provision(locator: str) -> str:
    try:
        return citation_label(locator)
    except LocatorError:
        return f"Section {_section_number(locator)}"


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


def _empty_today_context() -> dict[str, Any]:
    return {
        "law_revisions": (),
        "law_revision_count": 0,
        "playground_due_units": (),
        "playground_new_unit": None,
        "playground_due_count": 0,
    }


def playground_today_context(request, *, as_of: date | None = None) -> dict[str, Any]:
    overlay = getattr(request.app.state, "playground", None)
    roster = getattr(request.app.state, "roster", None)
    if overlay is None or roster is None:
        return _empty_today_context()
    try:
        access = playground_view_access(request)
        if not access.can_open or access.user_id is None:
            return _empty_today_context()
        user_id = access.user_id
        items = law_revision_today_items(overlay, roster, user_id, as_of=as_of)
        due_units = tuple(_today_unit_from_revision(item) for item in items)
        new_unit = playground_new_today_unit(
            overlay, roster, user_id, as_of=as_of
        )
        return {
            "law_revisions": (),
            "law_revision_count": len(due_units),
            "playground_due_units": due_units,
            "playground_new_unit": new_unit,
            "playground_due_count": len(due_units),
        }
    except Exception as error:  # noqa: BLE001 — T32 missing-schema only
        if not _is_missing_optional_schema(error):
            raise
        return _empty_today_context()


def playground_calendar_chips(
    overlay,
    roster,
    user_id,
    *,
    month_start: date,
    month_end: date,
    today: date,
) -> dict[str, list[CalendarChip]]:
    try:
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
            number = _chip_number_label(fact.source_locator)
            label = f"{short} · §{number} · Playground"
            title = (
                f"{short} · {_chip_title_provision(fact.source_locator)}"
                f" — Day {fact.interval_days} revision · Playground"
            )
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
                    category="Playground",
                )
            )
        return by_iso
    except Exception as error:  # noqa: BLE001 — T32 missing-schema only
        if not _is_missing_optional_schema(error):
            raise
        return {}


def attach_playground_calendar_chips(view, extra: dict[str, list[CalendarChip]]) -> None:
    if not extra:
        return
    for day in view.days:
        if not day.iso:
            continue
        added = extra.get(day.iso)
        if added:
            day.chips.extend(added)


def _playground_review_eyebrow(rung: int) -> str:
    nxt = advance_interval(rung)
    if nxt is None:
        return f"Day {rung} · Playground"
    return f"Day {rung} → {nxt} · Playground"


def _today_unit_from_revision(item: LawRevisionTodayItem) -> TodayUnit:
    cited = _chip_title_provision(item.source_locator)
    eyebrow = _playground_review_eyebrow(item.rung_days)
    return TodayUnit(
        unit_id=item.source_locator,
        title=f"{cited} — {item.short_title}",
        article_label=cited,
        kind="review",
        status="upcoming",
        href=item.href,
        position=0,
        subtitle=item.due_label,
        day_label=eyebrow,
        source="playground",
        eyebrow=eyebrow,
        cta_label="Start revision →",
    )


def _section_order_key(number: str) -> tuple:
    parts: list[tuple[int, int | str]] = []
    buf = ""
    for ch in number:
        if ch.isdigit():
            buf += ch
            continue
        if buf:
            parts.append((0, int(buf)))
            buf = ""
        parts.append((1, ch.lower()))
    if buf:
        parts.append((0, int(buf)))
    return tuple(parts)


def _act_order_key(locator: str) -> tuple:
    return (_section_order_key(_section_number(locator)), locator)


def _most_recently_active_law(overlay, roster, user_id) -> str | None:
    active = set(_active_law_ids(roster, user_id))
    if not active:
        return None
    items = [row for row in overlay.list_items(user_id) if row.law_id in active]
    if not items:
        return None
    items.sort(key=lambda row: row.last_activity_at, reverse=True)
    return items[0].law_id


def _blocked_locators(overlay, user_id, law_id: str) -> set[str]:
    blocked: set[str] = set()
    for row in overlay.list_source_changes(
        user_id, law_id, status=STATUS_PENDING
    ):
        if row.change_kind in {CHANGE_KIND_MISSING, CHANGE_KIND_OMITTED}:
            blocked.add(row.source_locator)
    return blocked


def playground_new_today_unit(
    overlay,
    roster,
    user_id,
    *,
    as_of: date | None = None,
) -> TodayUnit | None:
    del as_of
    law_id = _most_recently_active_law(overlay, roster, user_id)
    if not law_id:
        return None
    blocked = _blocked_locators(overlay, user_id, law_id)
    progress = {
        row.source_locator: row for row in overlay.list_progress(user_id, law_id)
    }
    candidates: list[str] = []
    for sel in overlay.list_selection(user_id, law_id):
        loc = sel.source_locator
        if loc in blocked:
            continue
        row = progress.get(loc)
        if row is not None and str(row.status or "") in LIFECYCLE_ACTIVE:
            continue
        candidates.append(loc)
    if not candidates:
        return None
    candidates.sort(key=_act_order_key)
    loc = candidates[0]
    cited = _chip_title_provision(loc)
    _title, short = catalog_titles(law_id)
    del _title
    mode = "read"
    rows = overlay.list_mode_progress(user_id, law_id, loc)
    completed = {
        getattr(row, "mode", "")
        for row in rows
        if getattr(row, "status", "") == "completed"
    }
    nxt = next_learn_mode(completed)
    if nxt:
        mode = nxt
    return TodayUnit(
        unit_id=loc,
        title=f"{cited} — {short}",
        article_label=cited,
        kind="new",
        status="upcoming",
        href=learn_path_for_locator(loc, mode),
        position=0,
        subtitle="New · Playground",
        day_label="New · Playground",
        source="playground",
        eyebrow="New · Playground",
        cta_label="Learn →",
    )


def _restamp_today_path(units: Sequence[TodayUnit]) -> list[TodayUnit]:
    out: list[TodayUnit] = []
    pending_seen = False
    for index, unit in enumerate(units, start=1):
        if unit.status in {"done", "deferred"}:
            out.append(replace(unit, position=index))
            continue
        if not pending_seen:
            status = "current"
            pending_seen = True
        else:
            status = "upcoming"
        eyebrow = unit.eyebrow
        if unit.source == "constitution":
            eyebrow = unit.day_label if status == "current" else ""
        out.append(replace(unit, status=status, position=index, eyebrow=eyebrow))
    return out


def merge_today_path(
    constitution: Sequence[TodayUnit],
    playground_dues: Sequence[TodayUnit],
    playground_new: TodayUnit | None,
) -> list[TodayUnit]:
    """Due Playground revisions, then Constitution pending, then at most one New."""
    dones = [unit for unit in constitution if unit.status == "done"]
    deferred = [unit for unit in constitution if unit.status == "deferred"]
    pending_const = [
        unit for unit in constitution if unit.status not in {"done", "deferred"}
    ]
    pending = list(playground_dues) + pending_const
    if playground_new is not None:
        pending.append(playground_new)
    return _restamp_today_path([*dones, *pending, *deferred])


def apply_merged_today_hero(ctx: dict[str, Any]) -> dict[str, Any]:
    """Align Today's Recall with the merged path. Mutates ``ctx``.

    ``due_count`` on entry is Constitution-only. Playground New never enters
    ``due_count``, ``revision_count``, or the goal denominator. A Playground
    review CTA is the current node's href — not ``POST /revision/start``.
    """
    playground_due_n = int(ctx.get("playground_due_count") or 0)
    ctx["due_count"] = int(ctx.get("due_count") or 0) + playground_due_n
    if ctx["due_count"] > 0:
        was_revision = ctx.get("today_mode") == "revision"
        ctx["today_mode"] = "revision"
        ctx["show_plan_prompt"] = False
        ctx["plan_my_day_available"] = False
        if not was_revision:
            ctx["revision_count"] = ctx["due_count"]
        elif playground_due_n:
            ctx["revision_count"] = int(ctx.get("revision_count") or 0) + playground_due_n
    path_for_goal = [
        unit
        for unit in (ctx.get("today_units") or [])
        if unit.status != "deferred"
        and not (getattr(unit, "source", "") == "playground" and unit.kind == "new")
    ]
    ctx["goal_done"] = sum(1 for unit in path_for_goal if unit.status == "done")
    ctx["goal_total"] = len(path_for_goal)
    ctx["goal_pct"] = (
        int(round(100 * ctx["goal_done"] / ctx["goal_total"]))
        if ctx["goal_total"]
        else 0
    )
    current = next(
        (unit for unit in (ctx.get("today_units") or []) if unit.status == "current"),
        None,
    )
    ctx["today_current"] = current
    if (
        current is not None
        and getattr(current, "source", "") == "playground"
        and current.kind == "review"
    ):
        ctx["hero_cta_kind"] = "playground_review"
        ctx["hero_cta_href"] = current.href
        ctx["hero_cta_label"] = current.cta_label or "Start revision →"
    else:
        ctx["hero_cta_kind"] = "constitution_revision"
        ctx["hero_cta_href"] = ""
        ctx["hero_cta_label"] = ""
    return ctx


def playground_projection_extra(
    overlay,
    roster,
    user_id,
    *,
    today: date,
    horizon_days: int,
    entitled: bool,
) -> dict[date, list[DayItem]]:
    """Pending Playground rung only. Never the rest of the ladder."""
    if not entitled:
        return {}
    try:
        active = _active_law_ids(roster, user_id)
        end = today + timedelta(days=horizon_days)
        facts = overlay.list_revision_schedule(
            user_id, date(1970, 1, 1), end, active
        )
        buckets: dict[date, list[DayItem]] = {}
        for fact in facts:
            nxt = parse_iso_date(fact.next_revision)
            if nxt is None:
                continue
            target = nxt if nxt > today else today
            if target > end:
                continue
            catalog = playground_catalogue_law(fact.law_id)
            short = catalog.short_title if catalog is not None else fact.law_id
            number = _chip_number_label(fact.source_locator)
            buckets.setdefault(target, []).append(
                DayItem(
                    unit_id=fact.source_locator,
                    label=(
                        f"{short} · §{number} — Day {fact.interval_days}"
                        " · Playground"
                    ),
                )
            )
        return buckets
    except Exception as error:  # noqa: BLE001 — T32 missing-schema only
        if not _is_missing_optional_schema(error):
            raise
        return {}


def playground_google_extra(request, *, today: date, horizon_days: int) -> dict[date, list[DayItem]]:
    """Entitlement-gated extra days for Google Calendar. Never raises to callers."""
    overlay = getattr(request.app.state, "playground", None)
    roster = getattr(request.app.state, "roster", None)
    if overlay is None or roster is None:
        return {}
    try:
        access = playground_view_access(request)
        if not access.can_open or access.user_id is None:
            return {}
        return playground_projection_extra(
            overlay,
            roster,
            access.user_id,
            today=today,
            horizon_days=horizon_days,
            entitled=True,
        )
    except Exception:  # noqa: BLE001 — T31: Playground must not fail Constitution sync
        return {}
