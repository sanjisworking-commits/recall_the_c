"""Playground overlay operations on live Bare Act JSON."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from constitution_memorizer.playground.cloze import has_cloze_blanks
from constitution_memorizer.playground.eligibility import (
    PlaygroundLawError,
    is_playground_eligible_law,
    playground_catalogue_law,
    playground_law_source_identity,
)
from constitution_memorizer.playground.locators import (
    LocatorError,
    PlaygroundLocator,
    SectionLocator,
    UnitLocator,
    parse_locator,
    section_locator,
)
from constitution_memorizer.playground.repository import PlaygroundProgress, PlaygroundSummary
from constitution_memorizer.playground.source import (
    canonical_body_text,
    locators_for_act,
    resolve_section,
    source_hash,
)
from constitution_memorizer.playground.source_review import is_law_registry_outdated
from constitution_memorizer.playground.units import (
    enumerate_selectable_units,
    resolve_unit,
    source_hash_for_locator,
)
from constitution_memorizer.web import bare_acts as bare_act_registry


def require_playground_law(law_id: str):
    if not is_playground_eligible_law(law_id):
        raise PlaygroundLawError(law_id)
    act = bare_act_registry.get_bare_act(law_id)
    if act is None:
        raise PlaygroundLawError(law_id)
    return act


def activate_law(repo, user_id: UUID | str, law_id: str):
    """Persist activation from registry identity. Does not hydrate the Act."""
    identity = playground_law_source_identity(law_id)
    return repo.add_item(
        user_id,
        identity.law_id,
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )


def playground_home_cards(summaries: list[PlaygroundSummary]) -> list[dict]:
    """Card view-models from DB summaries + catalogue/registry metadata."""
    cards: list[dict] = []
    for row in summaries:
        if not is_playground_eligible_law(row.law_id):
            continue
        catalog = playground_catalogue_law(row.law_id)
        if catalog is None:
            continue
        identity = playground_law_source_identity(row.law_id)
        outdated = is_law_registry_outdated(row, identity)
        cards.append(
            {
                "law_id": row.law_id,
                "title": catalog.title,
                "short_title": catalog.short_title,
                "selected_count": row.selected_count,
                "learned_count": row.learned_count,
                "to_learn": row.to_learn_count,
                "due": row.due_count,
                "outdated": outdated,
            }
        )
    return cards


def _locator_hash(loc: PlaygroundLocator, section) -> str:
    return source_hash_for_locator(loc, section, section_hash=source_hash)


def _learnable_section(section) -> bool:
    return section is not None and not section.is_omitted and bool(canonical_body_text(section))


def normalize_selection_locators(
    law_id: str,
    numbers: list[str] | None,
    *,
    entire: bool,
    units: list[str] | None = None,
    act=None,
) -> list[PlaygroundLocator]:
    """Server-authoritative selection. Whole section XOR units per section.

    Ticking every selectable unit stores the whole-section locator (promotion).
    Learning every unit still does **not** mark the section learned — this
    function only normalizes the selection layer.
    """
    if act is None:
        act = require_playground_law(law_id)
    if entire:
        return list(locators_for_act(law_id, act=act))

    whole: dict[str, SectionLocator] = {}
    for number in numbers or []:
        try:
            loc = section_locator(law_id, number)
        except LocatorError:
            continue
        section = act.section(loc.section_number)
        if not _learnable_section(section):
            continue
        whole[loc.section_number] = loc

    by_section: dict[str, list[UnitLocator]] = {}
    for raw in units or []:
        try:
            loc = parse_locator(raw)
        except LocatorError:
            continue
        if not isinstance(loc, UnitLocator) or loc.law_id != law_id:
            continue
        if loc.section_number in whole:
            continue
        section = act.section(loc.section_number)
        if not _learnable_section(section):
            continue
        try:
            resolve_unit(loc, act=act, section=section)
        except LocatorError:
            continue
        bucket = by_section.setdefault(loc.section_number, [])
        if loc not in bucket:
            bucket.append(loc)

    out: list[PlaygroundLocator] = list(whole.values())
    for number, chosen in by_section.items():
        section = act.section(number)
        selectable = enumerate_selectable_units(section, law_id=law_id)
        if not selectable:
            continue
        chosen_keys = {(item.kind, item.label, item.ordinal) for item in chosen}
        all_keys = {(item.kind, item.label, item.ordinal) for item in selectable}
        if chosen_keys == all_keys:
            out.append(section_locator(law_id, number))
            continue
        out.extend(chosen)
    return out


def selection_rows(
    law_id: str,
    numbers: list[str] | None,
    *,
    entire: bool,
    act=None,
    units: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    if act is None:
        act = require_playground_law(law_id)
    version = playground_law_source_identity(law_id).source_version
    locators = normalize_selection_locators(
        law_id, numbers, entire=entire, units=units, act=act
    )
    rows: list[tuple[str, str, str]] = []
    for loc in locators:
        section = act.section(loc.section_number)
        if section is None:
            continue
        rows.append((loc.value, version, _locator_hash(loc, section)))
    return rows


def provision_for_learn(
    law_id: str, number: str, *, act=None
) -> tuple[SectionLocator, str, str, str, bool]:
    loc = section_locator(law_id, number)
    if act is None:
        act, section = resolve_section(loc)
    else:
        section = act.section(loc.section_number)
        if section is None:
            raise LocatorError(f"unknown section: {loc.value}")
    body = canonical_body_text(section)
    version = playground_law_source_identity(law_id).source_version
    return loc, body, source_hash(section), version, has_cloze_blanks(body)


def mark_outdated(progress: PlaygroundProgress | None, live_hash: str) -> PlaygroundProgress | None:
    if progress is None:
        return None
    return PlaygroundProgress(
        source_locator=progress.source_locator,
        status=progress.status,
        cloze_done=progress.cloze_done,
        times_completed=progress.times_completed,
        last_completed=progress.last_completed,
        next_revision=progress.next_revision,
        interval_days=progress.interval_days,
        source_version=progress.source_version,
        source_hash=progress.source_hash,
        source_outdated=progress.source_hash != live_hash,
        learned_at=progress.learned_at,
    )


def selected_locator_set(selections) -> set[str]:
    return {row.source_locator for row in selections}


def live_source_hash(law_id: str, locator: str) -> str:
    loc = parse_selected_locator(locator, law_id)
    if loc is None:
        return ""
    try:
        _, section = resolve_section(loc)
    except LocatorError:
        return ""
    return _locator_hash(loc, section)


def parse_selected_locator(raw: str, law_id: str) -> PlaygroundLocator | None:
    try:
        loc = parse_locator(raw)
    except LocatorError:
        return None
    if loc.law_id != law_id:
        return None
    return loc


def due_revision_count(progress_rows: list[PlaygroundProgress], as_of: date) -> int:
    today = as_of.isoformat()
    count = 0
    for row in progress_rows:
        if row.status == "mastered":
            continue
        if row.next_revision and row.next_revision <= today:
            count += 1
    return count
