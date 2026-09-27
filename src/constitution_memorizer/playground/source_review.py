"""Playground source-integrity review.

Cheap gate: registry ``BareActSpec`` identity vs stored overlay item.
Targeted scan: hydrate one Act and compare user-relevant section hashes.

Does not rewrite learning, revision, selection, or lifecycle rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from constitution_memorizer.playground.eligibility import (
    playground_bare_act_spec,
    playground_law_source_identity,
)
from constitution_memorizer.playground.lifecycle import LIFECYCLE_ACTIVE
from constitution_memorizer.playground.locators import LocatorError, parse_locator
from constitution_memorizer.playground.learning.models import MODE_STATUS_COMPLETED
from constitution_memorizer.playground.source import source_hash
from constitution_memorizer.playground.urls import (
    source_review_path,
    source_review_section_path,
)

CHANGE_KIND_CHANGED = "changed"
CHANGE_KIND_MISSING = "missing"
CHANGE_KIND_OMITTED = "omitted"
CHANGE_KINDS = frozenset(
    {CHANGE_KIND_CHANGED, CHANGE_KIND_MISSING, CHANGE_KIND_OMITTED}
)

STATUS_PENDING = "pending"
STATUS_REVIEWED = "reviewed"

LAW_STATUS_UNCHANGED = "unchanged"
LAW_STATUS_UPDATE_DETECTED = "update_detected"
LAW_STATUS_REVIEW_REQUIRED = "review_required"
LAW_STATUS_REVIEWED = "reviewed"

ORIGIN_RANK = {
    "revision_mode": 0,
    "mode": 1,
    "progress": 2,
    "selection": 3,
}


class StaleSourceReviewError(Exception):
    """Review POST targets a source identity that is no longer current."""


@dataclass(frozen=True)
class HistoricalSectionIdentity:
    source_locator: str
    source_version: str
    source_hash: str
    origin: str
    at: str


@dataclass(frozen=True)
class SourceChangeRecord:
    law_id: str
    source_locator: str
    detected_source_version: str
    detected_law_source_hash: str
    previous_source_version: str
    previous_section_hash: str
    current_source_version: str
    current_law_source_hash: str
    current_section_hash: str
    change_kind: str
    status: str
    had_learning: bool
    had_selection: bool
    detected_at: str
    reviewed_at: str | None


@dataclass(frozen=True)
class SourceScanRecord:
    law_id: str
    scanned_source_version: str
    scanned_law_source_hash: str
    scanned_at: str
    affected_total: int
    affected_learned_count: int
    affected_selected_only_count: int
    unchanged_user_relevant_count: int
    missing_count: int


@dataclass(frozen=True)
class LawSourceState:
    law_id: str
    stored_source_version: str
    stored_identity_token: str
    current_source_version: str
    current_identity_token: str
    registry_outdated: bool
    identity_is_filename_fallback: bool
    status: str
    pending_learned_count: int
    pending_total: int
    affected_learned_count: int
    review_href: str
    outdated_badge: bool
    home_note: str


@dataclass(frozen=True)
class AffectedProvision:
    source_locator: str
    number: str
    change_kind: str
    status: str
    previous_source_version: str
    previous_section_hash: str
    current_section_hash: str
    lifecycle_status: str
    interval_days: int
    next_revision: str | None
    had_learning: bool
    had_selection: bool
    current_title: str
    current_body: str
    href: str


@dataclass(frozen=True)
class SourceChangeSummary:
    law_id: str
    registry_outdated: bool
    hydrated: bool
    status: str
    affected_total: int
    affected_learned_count: int
    affected_selected_only_count: int
    unchanged_user_relevant_count: int
    missing_count: int
    omitted_count: int
    changes: tuple[SourceChangeRecord, ...]
    scan: SourceScanRecord | None
    current_source_version: str
    current_identity_token: str
    identity_is_filename_fallback: bool


def is_law_registry_outdated(item: Any, current_identity: Any) -> bool:
    """Metadata only. No Act hydration."""

    if item is None or current_identity is None:
        return False
    return (
        str(getattr(item, "source_version", "") or "")
        != str(getattr(current_identity, "source_version", "") or "")
        or str(getattr(item, "law_source_hash", "") or "")
        != str(getattr(current_identity, "identity_token", "") or "")
    )


def identity_is_filename_fallback(law_id: str) -> bool:
    spec = playground_bare_act_spec(law_id)
    return spec is not None and not spec.source_hash


def provenance_lines(law_id: str) -> tuple[str, ...]:
    """Only values the registry actually has. Never invent Gazette metadata."""

    spec = playground_bare_act_spec(law_id)
    if spec is None:
        return ()
    return (f"Source version {spec.source_version}",)


def historical_section_identity(
    candidates: list[HistoricalSectionIdentity] | tuple[HistoricalSectionIdentity, ...],
) -> HistoricalSectionIdentity | None:
    """Most recent practiced/learned source for change detection only.

    Practiced rows (revision-mode, initial mode, lifecycle) outrank selection
    even when a later re-select timestamp exists. Selection is the fallback
    for users who never practiced the locator. Historical rows are not rewritten.
    """

    if not candidates:
        return None
    practiced = [row for row in candidates if row.origin != "selection"]
    pool = practiced or list(candidates)
    return max(
        pool,
        key=lambda row: (
            str(row.at or ""),
            -ORIGIN_RANK.get(row.origin, 9),
        ),
    )


def _locator_number(locator: str) -> str:
    try:
        return parse_locator(locator).number
    except LocatorError:
        if ":section:" in locator:
            return locator.split(":section:", 1)[1]
        return locator


def _had_learning(
    *,
    mode_by: dict[str, list[Any]],
    rev_by: dict[str, list[Any]],
    progress_by: dict[str, Any],
    locator: str,
) -> bool:
    if any(
        getattr(row, "status", "") == MODE_STATUS_COMPLETED
        for row in mode_by.get(locator, ())
    ):
        return True
    progress = progress_by.get(locator)
    if progress is not None and str(progress.status or "") in LIFECYCLE_ACTIVE:
        return True
    return bool(rev_by.get(locator))


def _candidates_for_locator(
    *,
    locator: str,
    mode_by: dict[str, list[Any]],
    rev_by: dict[str, list[Any]],
    progress_by: dict[str, Any],
    selection_by: dict[str, Any],
) -> list[HistoricalSectionIdentity]:
    out: list[HistoricalSectionIdentity] = []
    for row in rev_by.get(locator, ()):
        out.append(
            HistoricalSectionIdentity(
                source_locator=locator,
                source_version=row.source_version,
                source_hash=row.source_hash,
                origin="revision_mode",
                at=str(row.last_attempt_at or row.completed_at or ""),
            )
        )
    for row in mode_by.get(locator, ()):
        out.append(
            HistoricalSectionIdentity(
                source_locator=locator,
                source_version=row.source_version,
                source_hash=row.source_hash,
                origin="mode",
                at=str(row.last_attempt_at or row.completed_at or ""),
            )
        )
    progress = progress_by.get(locator)
    if progress is not None:
        out.append(
            HistoricalSectionIdentity(
                source_locator=locator,
                source_version=progress.source_version,
                source_hash=progress.source_hash,
                origin="progress",
                at=str(progress.last_completed or progress.learned_at or ""),
            )
        )
    selection = selection_by.get(locator)
    if selection is not None:
        out.append(
            HistoricalSectionIdentity(
                source_locator=locator,
                source_version=selection.source_version,
                source_hash=selection.source_hash,
                origin="selection",
                at=str(selection.selected_at or ""),
            )
        )
    return out


def _classify_section(act: Any, number: str, stored_hash: str) -> tuple[str, str] | None:
    section = act.section(number)
    if section is None:
        return CHANGE_KIND_MISSING, ""
    if section.is_omitted:
        live = source_hash(section)
        return CHANGE_KIND_OMITTED, live
    live = source_hash(section)
    if live != stored_hash:
        return CHANGE_KIND_CHANGED, live
    return None


_UNSET = object()


def law_source_state(
    overlay: Any,
    user_id: UUID | str,
    law_id: str,
    *,
    item: Any = _UNSET,
    scans: dict[tuple[str, str, str], SourceScanRecord] | None = None,
    pending_by_law: dict[str, list[SourceChangeRecord]] | None = None,
) -> LawSourceState:
    """Cheap presentation state. No Act hydration."""

    if item is _UNSET:
        item = overlay.get_item(user_id, law_id)
    stored_version = str(getattr(item, "source_version", "") or "") if item else ""
    stored_token = str(getattr(item, "law_source_hash", "") or "") if item else ""
    spec = playground_bare_act_spec(law_id)
    if spec is None:
        return LawSourceState(
            law_id=law_id,
            stored_source_version=stored_version,
            stored_identity_token=stored_token,
            current_source_version="",
            current_identity_token="",
            registry_outdated=False,
            identity_is_filename_fallback=False,
            status=LAW_STATUS_UNCHANGED,
            pending_learned_count=0,
            pending_total=0,
            affected_learned_count=0,
            review_href="",
            outdated_badge=False,
            home_note="",
        )
    identity = playground_law_source_identity(law_id)
    outdated = is_law_registry_outdated(item, identity)
    filename_fallback = identity_is_filename_fallback(law_id)
    scan = None
    if scans is not None:
        scan = scans.get(
            (law_id, identity.source_version, identity.identity_token)
        )
    else:
        scan = overlay.get_source_scan(
            user_id, law_id, identity.source_version, identity.identity_token
        )
    pending: list[SourceChangeRecord] = []
    if pending_by_law is not None:
        pending = [
            row
            for row in pending_by_law.get(law_id, ())
            if row.current_source_version == identity.source_version
            and row.current_law_source_hash == identity.identity_token
        ]
    elif outdated:
        pending = [
            row
            for row in overlay.list_source_changes(
                user_id, law_id, status=STATUS_PENDING
            )
            if row.current_source_version == identity.source_version
            and row.current_law_source_hash == identity.identity_token
        ]
    pending_learned = sum(1 for row in pending if row.had_learning)
    pending_total = len(pending)
    review_href = source_review_path(law_id) if outdated else ""
    if not outdated:
        status = LAW_STATUS_UNCHANGED
        badge = False
        note = ""
        learned_count = 0
    elif scan is None:
        status = LAW_STATUS_UPDATE_DETECTED
        badge = True
        note = "Review affected provisions"
        learned_count = 0
    elif pending_learned > 0:
        status = LAW_STATUS_REVIEW_REQUIRED
        badge = True
        noun = "provision" if pending_learned == 1 else "provisions"
        note = f"Law updated · {pending_learned} affected {noun}"
        learned_count = pending_learned
    elif pending_total > 0:
        status = LAW_STATUS_REVIEW_REQUIRED
        badge = True
        note = "Review affected provisions"
        learned_count = 0
    else:
        status = LAW_STATUS_REVIEWED
        badge = False
        note = ""
        learned_count = int(scan.affected_learned_count or 0) if scan else 0
    return LawSourceState(
        law_id=law_id,
        stored_source_version=stored_version,
        stored_identity_token=stored_token,
        current_source_version=identity.source_version,
        current_identity_token=identity.identity_token,
        registry_outdated=outdated,
        identity_is_filename_fallback=filename_fallback,
        status=status,
        pending_learned_count=pending_learned,
        pending_total=pending_total,
        affected_learned_count=learned_count,
        review_href=review_href,
        outdated_badge=badge,
        home_note=note,
    )


def batch_source_presentations(
    overlay: Any,
    user_id: UUID | str,
    law_ids: list[str] | tuple[str, ...],
) -> dict[str, LawSourceState]:
    """Batched overlay/scan/change reads. No Act hydration. No per-card queries."""

    ids = list(dict.fromkeys(law_ids))
    if not ids:
        return {}
    wanted = set(ids)
    items = {
        row.law_id: row
        for row in overlay.list_items(user_id)
        if row.law_id in wanted
    }
    scans_list = overlay.list_source_scans(user_id, ids)
    scans = {
        (row.law_id, row.scanned_source_version, row.scanned_law_source_hash): row
        for row in scans_list
    }
    pending_rows = overlay.list_source_changes(
        user_id, law_ids=ids, status=STATUS_PENDING
    )
    pending_by: dict[str, list[SourceChangeRecord]] = {}
    for row in pending_rows:
        pending_by.setdefault(row.law_id, []).append(row)
    return {
        law_id: law_source_state(
            overlay,
            user_id,
            law_id,
            item=items.get(law_id),
            scans=scans,
            pending_by_law=pending_by,
        )
        for law_id in ids
    }


def detect_source_changes(
    overlay: Any,
    user_id: UUID | str,
    law_id: str,
    *,
    hydrate: Callable[[str], Any] | None = None,
) -> SourceChangeSummary:
    """Targeted comparison. Hydrates at most the requested Act, and only if stale."""

    from constitution_memorizer.playground.service import require_playground_law

    identity = playground_law_source_identity(law_id)
    filename_fallback = identity_is_filename_fallback(law_id)
    item = overlay.get_item(user_id, law_id)
    outdated = is_law_registry_outdated(item, identity)
    empty = SourceChangeSummary(
        law_id=law_id,
        registry_outdated=outdated,
        hydrated=False,
        status=LAW_STATUS_UNCHANGED if not outdated else LAW_STATUS_UPDATE_DETECTED,
        affected_total=0,
        affected_learned_count=0,
        affected_selected_only_count=0,
        unchanged_user_relevant_count=0,
        missing_count=0,
        omitted_count=0,
        changes=(),
        scan=None,
        current_source_version=identity.source_version,
        current_identity_token=identity.identity_token,
        identity_is_filename_fallback=filename_fallback,
    )
    if not outdated:
        return empty

    mode_rows = overlay.list_mode_progress(user_id, law_id)
    rev_rows = overlay.list_revision_mode_progress(user_id, law_id)
    progress_rows = overlay.list_progress(user_id, law_id)
    selections = overlay.list_selection(user_id, law_id)
    mode_by: dict[str, list[Any]] = {}
    for row in mode_rows:
        mode_by.setdefault(row.source_locator, []).append(row)
    rev_by: dict[str, list[Any]] = {}
    for row in rev_rows:
        rev_by.setdefault(row.source_locator, []).append(row)
    progress_by = {row.source_locator: row for row in progress_rows}
    selection_by = {row.source_locator: row for row in selections}
    locators = sorted(
        set(mode_by)
        | set(rev_by)
        | set(progress_by)
        | set(selection_by)
    )

    def _empty_scan(*, hydrated: bool) -> SourceChangeSummary:
        scan = overlay.upsert_source_scan(
            user_id,
            law_id,
            scanned_source_version=identity.source_version,
            scanned_law_source_hash=identity.identity_token,
            affected_total=0,
            affected_learned_count=0,
            affected_selected_only_count=0,
            unchanged_user_relevant_count=0,
            missing_count=0,
        )
        return SourceChangeSummary(
            law_id=law_id,
            registry_outdated=True,
            hydrated=hydrated,
            status=LAW_STATUS_REVIEWED,
            affected_total=0,
            affected_learned_count=0,
            affected_selected_only_count=0,
            unchanged_user_relevant_count=0,
            missing_count=0,
            omitted_count=0,
            changes=(),
            scan=scan,
            current_source_version=identity.source_version,
            current_identity_token=identity.identity_token,
            identity_is_filename_fallback=filename_fallback,
        )

    if not locators:
        return _empty_scan(hydrated=False)

    loader = hydrate or require_playground_law
    act = loader(law_id)

    unchanged = 0
    missing = 0
    omitted = 0
    records: list[SourceChangeRecord] = []
    for locator in locators:
        number = _locator_number(locator)
        baseline = historical_section_identity(
            _candidates_for_locator(
                locator=locator,
                mode_by=mode_by,
                rev_by=rev_by,
                progress_by=progress_by,
                selection_by=selection_by,
            )
        )
        if baseline is None:
            continue
        classified = _classify_section(act, number, baseline.source_hash)
        if classified is None:
            unchanged += 1
            continue
        kind, live_hash = classified
        if kind == CHANGE_KIND_MISSING:
            missing += 1
        elif kind == CHANGE_KIND_OMITTED:
            omitted += 1
        had_learn = _had_learning(
            mode_by=mode_by,
            rev_by=rev_by,
            progress_by=progress_by,
            locator=locator,
        )
        had_sel = locator in selection_by
        record = overlay.upsert_source_change(
            user_id,
            law_id,
            locator,
            detected_source_version=identity.source_version,
            detected_law_source_hash=identity.identity_token,
            previous_source_version=baseline.source_version,
            previous_section_hash=baseline.source_hash,
            current_source_version=identity.source_version,
            current_law_source_hash=identity.identity_token,
            current_section_hash=live_hash,
            change_kind=kind,
            had_learning=had_learn,
            had_selection=had_sel,
        )
        records.append(record)

    learned = sum(1 for row in records if row.had_learning)
    selected_only = sum(
        1 for row in records if row.had_selection and not row.had_learning
    )
    scan = overlay.upsert_source_scan(
        user_id,
        law_id,
        scanned_source_version=identity.source_version,
        scanned_law_source_hash=identity.identity_token,
        affected_total=len(records),
        affected_learned_count=learned,
        affected_selected_only_count=selected_only,
        unchanged_user_relevant_count=unchanged,
        missing_count=missing,
    )
    pending = [row for row in records if row.status == STATUS_PENDING]
    pending_learned = sum(1 for row in pending if row.had_learning)
    if pending_learned > 0 or pending:
        status = LAW_STATUS_REVIEW_REQUIRED
    else:
        status = LAW_STATUS_REVIEWED
    return SourceChangeSummary(
        law_id=law_id,
        registry_outdated=True,
        hydrated=True,
        status=status,
        affected_total=len(records),
        affected_learned_count=learned,
        affected_selected_only_count=selected_only,
        unchanged_user_relevant_count=unchanged,
        missing_count=missing,
        omitted_count=omitted,
        changes=tuple(records),
        scan=scan,
        current_source_version=identity.source_version,
        current_identity_token=identity.identity_token,
        identity_is_filename_fallback=filename_fallback,
    )


def list_source_changes(
    overlay: Any,
    user_id: UUID | str,
    law_id: str,
    *,
    current_only: bool = True,
) -> list[SourceChangeRecord]:
    identity = playground_law_source_identity(law_id)
    rows = overlay.list_source_changes(user_id, law_id)
    if not current_only:
        return rows
    return [
        row
        for row in rows
        if row.current_source_version == identity.source_version
        and row.current_law_source_hash == identity.identity_token
    ]


def mark_source_change_reviewed(
    overlay: Any,
    user_id: UUID | str,
    law_id: str,
    source_locator: str,
    *,
    detected_source_version: str,
    detected_law_source_hash: str,
) -> SourceChangeRecord:
    identity = playground_law_source_identity(law_id)
    if (
        identity.source_version != detected_source_version
        or identity.identity_token != detected_law_source_hash
    ):
        raise StaleSourceReviewError("stale_source_review")
    return overlay.mark_source_change_reviewed(
        user_id,
        law_id,
        source_locator,
        detected_source_version=detected_source_version,
        detected_law_source_hash=detected_law_source_hash,
    )


def affected_provision_view(
    record: SourceChangeRecord,
    *,
    progress: Any = None,
    act: Any = None,
) -> AffectedProvision:
    number = _locator_number(record.source_locator)
    title = ""
    body = ""
    if act is not None and record.change_kind != CHANGE_KIND_MISSING:
        section = act.section(number)
        if section is not None:
            from constitution_memorizer.playground.source import canonical_body_text

            title = section.list_title
            if record.change_kind != CHANGE_KIND_MISSING:
                body = canonical_body_text(section)
    return AffectedProvision(
        source_locator=record.source_locator,
        number=number,
        change_kind=record.change_kind,
        status=record.status,
        previous_source_version=record.previous_source_version,
        previous_section_hash=record.previous_section_hash,
        current_section_hash=record.current_section_hash,
        lifecycle_status=str(getattr(progress, "status", "") or ""),
        interval_days=int(getattr(progress, "interval_days", 0) or 0) if progress else 0,
        next_revision=getattr(progress, "next_revision", None) if progress else None,
        had_learning=record.had_learning,
        had_selection=record.had_selection,
        current_title=title,
        current_body=body,
        href=source_review_section_path(record.law_id, number),
    )


def change_copy(kind: str) -> str:
    if kind == CHANGE_KIND_MISSING:
        return "No longer present in the current source"
    if kind == CHANGE_KIND_OMITTED:
        return "This provision is omitted in the current source"
    return "Changed since you learned it"


