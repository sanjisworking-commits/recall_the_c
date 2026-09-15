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
    SectionLocator,
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
        outdated = (
            row.source_version != identity.source_version
            or row.law_source_hash != identity.identity_token
        )
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


def selection_rows(
    law_id: str,
    numbers: list[str] | None,
    *,
    entire: bool,
    act=None,
) -> list[tuple[str, str, str]]:
    if act is None:
        act = require_playground_law(law_id)
    version = playground_law_source_identity(law_id).source_version
    if entire:
        locators = locators_for_act(law_id, act=act)
    else:
        locators = []
        for number in numbers or []:
            try:
                loc = section_locator(law_id, number)
            except LocatorError:
                continue
            section = act.section(loc.number)
            if section is None or section.is_omitted or not canonical_body_text(section):
                continue
            locators.append(loc)
    rows: list[tuple[str, str, str]] = []
    for loc in locators:
        section = act.section(loc.number)
        if section is None:
            continue
        rows.append((loc.value, version, source_hash(section)))
    return rows


def provision_for_learn(
    law_id: str, number: str, *, act=None
) -> tuple[SectionLocator, str, str, str, bool]:
    loc = section_locator(law_id, number)
    if act is None:
        act, section = resolve_section(loc)
    else:
        section = act.section(loc.number)
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
    return source_hash(section)


def parse_selected_locator(raw: str, law_id: str) -> SectionLocator | None:
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
        if not row.cloze_done:
            continue
        if row.status == "mastered":
            continue
        if row.next_revision and row.next_revision <= today:
            count += 1
    return count
