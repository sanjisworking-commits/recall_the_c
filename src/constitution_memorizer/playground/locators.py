"""Deterministic locators for Playground overlay on Bare Act JSON.

Grammar: ``{law_id}:section:{number}``.

``parse_locator`` reconstructs the structured locator and checks that the
law is Playground-eligible. It does not hydrate Acts or prove the Section
exists — that is ``resolve_section``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from constitution_memorizer.playground.eligibility import is_playground_eligible_law

# Syntax only. Corpus policy lives in is_playground_eligible_law.
_LAW_SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
_LOCATOR_RE = re.compile(rf"^(?P<law_id>{_LAW_SLUG}):section:(?P<number>.+)$")


class LocatorError(ValueError):
    """The string is not a reconstructable Playground section locator."""


@dataclass(frozen=True)
class SectionLocator:
    law_id: str
    number: str

    @property
    def value(self) -> str:
        return f"{self.law_id}:section:{self.number}"


def parse_locator(raw: str) -> SectionLocator:
    match = _LOCATOR_RE.fullmatch(str(raw or "").strip())
    if not match:
        raise LocatorError(f"invalid playground locator: {raw!r}")
    law_id = match.group("law_id")
    number = match.group("number")
    if not is_playground_eligible_law(law_id):
        raise LocatorError(f"invalid playground locator: {raw!r}")
    return SectionLocator(law_id=law_id, number=number)


def section_locator(law_id: str, number: str) -> SectionLocator:
    law = str(law_id or "").strip()
    num = str(number or "").strip()
    if not num or not is_playground_eligible_law(law):
        raise LocatorError(f"invalid playground locator parts: {law_id!r} {number!r}")
    return SectionLocator(law_id=law, number=num)
