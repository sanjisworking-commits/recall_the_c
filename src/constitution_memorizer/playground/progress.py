"""Act workspace read model. Does not write lifecycle or selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constitution_memorizer.playground.lifecycle import (
    LIFECYCLE_LEARNED,
    LIFECYCLE_MASTERED,
    LIFECYCLE_REVIEW,
    REVISION_RUNGS,
)
from constitution_memorizer.playground.locators import LocatorError, UnitLocator, parse_locator
from constitution_memorizer.playground.source import locators_for_act
from constitution_memorizer.playground.source_review import (
    CHANGE_KIND_MISSING,
    CHANGE_KIND_OMITTED,
)
from constitution_memorizer.playground.view import STATUS_DUE, STATUS_LABELS, provisions_label

_EXCLUDED_CHANGE = frozenset({CHANGE_KIND_MISSING, CHANGE_KIND_OMITTED})


@dataclass(frozen=True)
class WaffleCell:
    locator: str
    citation: str
    status: str
    status_label: str
    title: str


@dataclass(frozen=True)
class LadderRung:
    days: int
    count: int
    height_pct: int
    label: str


@dataclass(frozen=True)
class ActProgress:
    """Presentation facts for one Act workspace. No Jinja arithmetic."""

    selected_count: int
    learning_count: int
    learned_count: int
    review_count: int
    mastered_count: int
    due_count: int
    overdue_count: int
    completed_scope_count: int
    ring_pct: int
    fraction_label: str
    headline: str
    subhead: str
    scope_kind: str
    scope_label: str
    entire_act: bool
    next_locator: str
    next_citation: str
    next_status: str
    next_href: str
    next_cta: str
    waffle: tuple[WaffleCell, ...]
    rungs: tuple[LadderRung, ...]


def choose_next_workspace_row(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    """Identity with the Stage 1 workspace Next loop. Do not rewrite the rule."""

    for row in rows:
        if (
            row.get("due")
            and not row.get("missing")
            and row.get("source_change_kind") != CHANGE_KIND_MISSING
        ):
            return row
    for row in rows:
        if int(row.get("completed_count") or 0) < 6 and not row.get("source_change_kind"):
            return row
    return next(
        (row for row in rows if row.get("source_change_kind") != CHANGE_KIND_MISSING),
        None,
    )


def _effective_learnable(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if row.get("missing"):
            continue
        if row.get("source_change_kind") in _EXCLUDED_CHANGE:
            continue
        locator = str(row.get("locator") or "")
        if locator:
            out.append(locator)
    return out


def _lifecycle_status(row: dict[str, Any]) -> str:
    progress = row.get("progress")
    return str(getattr(progress, "status", "") or "") if progress is not None else ""


def _histogram(rows: list[dict[str, Any]]) -> tuple[LadderRung, ...]:
    counts = {int(days): 0 for days in REVISION_RUNGS}
    for row in rows:
        status = _lifecycle_status(row)
        if status == LIFECYCLE_MASTERED:
            continue
        if status == LIFECYCLE_LEARNED:
            counts[1] = counts.get(1, 0) + 1
            continue
        if status == LIFECYCLE_REVIEW:
            days = int(getattr(row.get("progress"), "interval_days", 0) or 0)
            if days in counts:
                counts[days] += 1
    peak = max(counts.values()) if counts else 0
    rungs: list[LadderRung] = []
    for days in REVISION_RUNGS:
        n = counts[int(days)]
        height = 8 if peak == 0 else max(8, int(round(100 * n / peak)))
        rungs.append(
            LadderRung(
                days=int(days),
                count=n,
                height_pct=height,
                label=f"day {days}",
            )
        )
    return tuple(rungs)


def _waffle(rows: list[dict[str, Any]]) -> tuple[WaffleCell, ...]:
    cells: list[WaffleCell] = []
    for row in rows:
        status = str(row.get("status") or "not_started")
        if row.get("missing") or row.get("source_change_kind") in _EXCLUDED_CHANGE:
            status = "missing"
        citation = str(row.get("citation") or "")
        label = STATUS_LABELS.get(status, status.replace("_", " ").title())
        cells.append(
            WaffleCell(
                locator=str(row.get("locator") or ""),
                citation=citation,
                status=status,
                status_label=label,
                title=f"{citation} · {label}",
            )
        )
    return tuple(cells)


def build_act_progress(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    law_id: str,
    act: Any = None,
) -> ActProgress:
    row_list = list(rows)
    selected_count = len(row_list)
    learned_count = 0
    review_count = 0
    mastered_count = 0
    learning_count = 0
    due_count = 0
    overdue_count = 0
    for row in row_list:
        life = _lifecycle_status(row)
        if life == LIFECYCLE_MASTERED:
            mastered_count += 1
        elif life == LIFECYCLE_REVIEW:
            review_count += 1
        elif life == LIFECYCLE_LEARNED:
            learned_count += 1
        elif int(row.get("completed_count") or 0) > 0:
            learning_count += 1
        if row.get("status") == STATUS_DUE:
            due_count += 1
            due_label = str(row.get("due_label") or "")
            if due_label and "overdue" in due_label.lower():
                overdue_count += 1
    completed_scope_count = learned_count + review_count + mastered_count
    if selected_count <= 0:
        ring_pct = 0
        fraction_label = "0/0"
    else:
        ring_pct = int(round(100 * completed_scope_count / selected_count))
        fraction_label = f"{completed_scope_count}/{selected_count}"

    entire_ids: set[str] = set()
    if act is not None and law_id:
        try:
            entire_ids = {loc.value for loc in locators_for_act(law_id, act=act)}
        except Exception:
            entire_ids = set()
    effective = _effective_learnable(row_list)
    entire_act = bool(entire_ids) and set(effective) == entire_ids and selected_count > 0
    has_unit = False
    has_section = False
    for row in row_list:
        try:
            parsed = parse_locator(str(row.get("locator") or ""))
        except LocatorError:
            continue
        if isinstance(parsed, UnitLocator):
            has_unit = True
        else:
            has_section = True
    if selected_count == 0:
        scope_kind = "empty"
        scope_label = "No provisions"
    elif entire_act:
        scope_kind = "entire"
        scope_label = "Entire Act"
    elif has_unit and has_section:
        scope_kind = "mixed"
        scope_label = provisions_label(selected_count)
    else:
        scope_kind = "provisions"
        scope_label = provisions_label(selected_count)

    if selected_count == 0:
        headline = "Nothing selected yet"
        subhead = "Choose sections to start."
    elif completed_scope_count == 0:
        headline = "Not started"
        subhead = f"{provisions_label(selected_count)} selected"
    elif mastered_count == selected_count:
        headline = "Mastered, verbatim."
        subhead = f"{mastered_count} of {selected_count} mastered"
    elif completed_scope_count == selected_count:
        headline = "Learned."
        subhead = f"{completed_scope_count} of {selected_count} learned"
    else:
        headline = f"{completed_scope_count} of {selected_count} learned"
        subhead = f"{learning_count} in progress" if learning_count else ""

    nxt = choose_next_workspace_row(row_list)
    next_locator = str(nxt.get("locator") or "") if nxt else ""
    next_citation = str(nxt.get("citation") or "") if nxt else ""
    next_status = str(nxt.get("status") or "") if nxt else ""
    next_href = str(nxt.get("href") or "") if nxt else ""
    if nxt is None:
        next_cta = "Manage sections"
    elif nxt.get("cta") == "Start learning":
        next_cta = f"Learn {next_citation}".strip()
    else:
        next_cta = str(nxt.get("cta") or "Continue")

    return ActProgress(
        selected_count=selected_count,
        learning_count=learning_count,
        learned_count=learned_count,
        review_count=review_count,
        mastered_count=mastered_count,
        due_count=due_count,
        overdue_count=overdue_count,
        completed_scope_count=completed_scope_count,
        ring_pct=ring_pct,
        fraction_label=fraction_label,
        headline=headline,
        subhead=subhead,
        scope_kind=scope_kind,
        scope_label=scope_label,
        entire_act=entire_act,
        next_locator=next_locator,
        next_citation=next_citation,
        next_status=next_status,
        next_href=next_href,
        next_cta=next_cta,
        waffle=_waffle(row_list),
        rungs=_histogram(row_list),
    )
