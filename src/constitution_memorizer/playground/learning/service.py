"""Playground learning orchestration. No Constitution persistence."""

from __future__ import annotations

from constitution_memorizer.playground.eligibility import playground_law_source_identity
from constitution_memorizer.playground.learning.cloze import cloze_can_run, cloze_needs_fallback
from constitution_memorizer.playground.learning.models import (
    ModeProgressRow,
    ProvisionModeProgress,
    build_provision_mode_progress,
    empty_provision_mode_progress,
    group_provision_mode_progress,
)
from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    PLAYGROUND_MODE_DECK,
    PLAYGROUND_MODE_LABELS,
    PLAYGROUND_MODE_TASKS,
    is_playground_learn_mode,
)
from constitution_memorizer.playground.learning.test import (
    build_section_quiz,
    coerce_quiz_answers,
    grade_section_quiz,
    has_section_quiz,
)
from constitution_memorizer.playground.locators import (
    LocatorError,
    UnitLocator,
    parse_locator,
    section_locator,
)
from constitution_memorizer.playground.source import canonical_body_text, resolve_section, source_hash
from constitution_memorizer.playground.units import resolve_unit, source_hash_for_locator


class LearnProvisionError(ValueError):
    """Section cannot enter Playground learning (omitted, empty, unknown)."""


def mode_definitions() -> list[dict[str, object]]:
    """Server-provided mode list for templates. No second list in JS."""

    out: list[dict[str, object]] = []
    for index, mode in enumerate(PLAYGROUND_LEARN_MODES, start=1):
        title, lede = PLAYGROUND_MODE_DECK[mode]
        out.append(
            {
                "id": mode,
                "label": PLAYGROUND_MODE_LABELS[mode],
                "task": PLAYGROUND_MODE_TASKS[mode],
                "title": title,
                "lede": lede,
                "ordinal": index,
                "ordinal_label": f"{index:02d}",
            }
        )
    return out


def load_learn_provision(law_id: str, number: str, *, act=None, unit: str | None = None):
    if unit:
        loc = parse_locator(f"{law_id}:section:{number}:{unit}")
        if not isinstance(loc, UnitLocator) or loc.law_id != law_id:
            raise LocatorError(f"invalid playground locator: {law_id}:section:{number}:{unit}")
    else:
        loc = section_locator(law_id, number)
    if act is None:
        act, section = resolve_section(loc)
    else:
        section = act.section(loc.section_number)
        if section is None:
            raise LocatorError(f"unknown section: {loc.value}")
    if section.is_omitted:
        raise LearnProvisionError(f"omitted section: {loc.value}")
    if unit:
        try:
            resolved = resolve_unit(loc, act=act, section=section)
        except LocatorError as exc:
            raise LearnProvisionError(f"unknown unit: {loc.value}") from exc
        body = resolved.canonical_text
        live = source_hash_for_locator(loc, section, section_hash=source_hash)
    else:
        body = canonical_body_text(section)
        live = source_hash(section)
    if not body:
        raise LearnProvisionError(f"empty section: {loc.value}")
    version = playground_law_source_identity(law_id).source_version
    return loc, act, section, body, live, version


def provision_mode_view(
    *,
    source_locator: str,
    rows: list[ModeProgressRow] | tuple[ModeProgressRow, ...],
    live_hash: str = "",
) -> ProvisionModeProgress:
    return build_provision_mode_progress(source_locator, rows, live_hash=live_hash)


def summaries_for_locators(
    rows: list[ModeProgressRow],
    locators: list[str],
    *,
    live_hashes: dict[str, str] | None = None,
) -> dict[str, ProvisionModeProgress]:
    return group_provision_mode_progress(rows, locators, live_hashes=live_hashes or {})


def quiz_for_attempt(
    *,
    law_id: str,
    source_locator: str,
    canonical_body: str,
    cycle: int,
    source_hash: str,
    rung_days: int | None = None,
):
    return build_section_quiz(
        law_id=law_id,
        source_locator=source_locator,
        canonical_body=canonical_body,
        cycle=cycle,
        source_hash=source_hash,
        rung_days=rung_days,
    )


__all__ = [
    "LearnProvisionError",
    "cloze_can_run",
    "cloze_needs_fallback",
    "coerce_quiz_answers",
    "empty_provision_mode_progress",
    "grade_section_quiz",
    "has_section_quiz",
    "is_playground_learn_mode",
    "load_learn_provision",
    "mode_definitions",
    "provision_mode_view",
    "quiz_for_attempt",
    "summaries_for_locators",
]
