"""Canonical text and hashes for Bare Act sections — never rewrite JSON."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from constitution_memorizer.web import bare_acts as bare_act_registry
from constitution_memorizer.web.bare_acts import (
    ActSection,
    BareAct,
    BARE_ACTS,
    flatten_body,
)
from constitution_memorizer.playground.eligibility import is_playground_eligible_law
from constitution_memorizer.playground.locators import (
    SectionLocator,
    LocatorError,
    section_locator,
)


def canonical_body_text(section: ActSection) -> str:
    """Statutory wording in reading order. Labels are citation, not this string."""
    parts = [
        row.text.strip()
        for row in flatten_body(section.body, profile=section.profile)
        if row.text and row.text.strip()
    ]
    return " ".join(parts)


def hash_payload(section: ActSection) -> str:
    return f"{section.number}\n{section.title}\n{canonical_body_text(section)}"


def source_hash(section: ActSection) -> str:
    return sha256(hash_payload(section).encode("utf-8")).hexdigest()


def law_source_version(act: BareAct) -> str:
    document = act.raw.get("document") or {}
    schema = str(act.raw.get("schema_version") or "")
    stamp = str(
        document.get("last_update")
        or document.get("enactment_date")
        or ""
    )
    return f"{schema}|{act.act_number}|{stamp}"


def law_file_hash(law_id: str) -> str:
    spec = BARE_ACTS[law_id]
    packaged = Path(__file__).resolve().parents[1] / "web" / spec.filename
    return sha256(packaged.read_bytes()).hexdigest()


def resolve_section(locator: SectionLocator) -> tuple[BareAct, ActSection]:
    act = bare_act_registry.get_bare_act(locator.law_id)
    if act is None:
        raise LocatorError(f"unknown law: {locator.law_id}")
    section = act.section(locator.number)
    if section is None:
        raise LocatorError(f"unknown section: {locator.value}")
    return act, section


def locators_for_act(law_id: str) -> list[SectionLocator]:
    if not is_playground_eligible_law(law_id):
        raise LocatorError(f"unknown law: {law_id}")
    act = bare_act_registry.get_bare_act(law_id)
    if act is None:
        raise LocatorError(f"unknown law: {law_id}")
    out: list[SectionLocator] = []
    for section in act.section_order:
        if section.is_omitted:
            continue
        if not canonical_body_text(section):
            continue
        out.append(section_locator(law_id, section.number))
    return out
