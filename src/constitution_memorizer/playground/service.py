"""Playground overlay operations on live Bare Act JSON."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from constitution_memorizer.playground.cloze import has_cloze_blanks
from constitution_memorizer.playground.eligibility import (
    PlaygroundLawError,
    is_playground_eligible_law,
)
from constitution_memorizer.playground.locators import (
    LocatorError,
    SectionLocator,
    parse_locator,
    section_locator,
)
from constitution_memorizer.playground.repository import PlaygroundProgress
from constitution_memorizer.playground.source import (
    canonical_body_text,
    law_file_hash,
    law_source_version,
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
    act = require_playground_law(law_id)
    return repo.add_item(
        user_id,
        law_id,
        source_version=law_source_version(act),
        law_source_hash=law_file_hash(law_id),
    )


def selection_rows(law_id: str, numbers: list[str] | None, *, entire: bool) -> list[tuple[str, str, str]]:
    act = require_playground_law(law_id)
    version = law_source_version(act)
    if entire:
        locators = locators_for_act(law_id)
    else:
        locators = []
        for number in numbers or []:
            try:
                loc = section_locator(law_id, number)
            except LocatorError:
                continue
            try:
                _, section = resolve_section(loc)
            except LocatorError:
                continue
            if section.is_omitted or not canonical_body_text(section):
                continue
            locators.append(loc)
    rows: list[tuple[str, str, str]] = []
    for loc in locators:
        _, section = resolve_section(loc)
        rows.append((loc.value, version, source_hash(section)))
    return rows


def provision_for_learn(law_id: str, number: str) -> tuple[SectionLocator, str, str, str, bool]:
    loc = section_locator(law_id, number)
    act, section = resolve_section(loc)
    body = canonical_body_text(section)
    return loc, body, source_hash(section), law_source_version(act), has_cloze_blanks(body)


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
