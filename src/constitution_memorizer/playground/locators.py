"""Deterministic locators for Playground overlay on Bare Act JSON.

Grammar::

    {law_id}:section:{section_number}
    {law_id}:section:{section_number}:{kind}:{label}
    {law_id}:section:{section_number}:{kind}:{label}~{ordinal}

``kind`` is ``subsection`` or ``clause``. ``label`` is the printed label
without parentheses. ``ordinal`` defaults to 1; ``~n`` is wire-only and is
omitted when ``n`` is 1.

``parse_locator`` reconstructs the discriminated type and checks that the law
is Playground-eligible. It does not hydrate Acts or prove the node exists.
Malformed unit locators are rejected; they are never coerced into section
locators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from constitution_memorizer.playground.eligibility import is_playground_eligible_law

# Syntax only. Corpus policy lives in is_playground_eligible_law.
_LAW_SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
# Bounded: a greedy `.+` would swallow `:subsection:` / `:clause:`.
_SECTION_NUMBER = r"[^:]+"
_KIND = r"subsection|clause"
_LABEL = r"[^:~]+"
_SECTION_RE = re.compile(
    rf"^(?P<law_id>{_LAW_SLUG}):section:(?P<section_number>{_SECTION_NUMBER})$"
)
_UNIT_RE = re.compile(
    rf"^(?P<law_id>{_LAW_SLUG}):section:(?P<section_number>{_SECTION_NUMBER}):"
    rf"(?P<kind>{_KIND}):(?P<label>{_LABEL})"
    rf"(?:~(?P<ordinal>[1-9]\d*))?$"
)

UNIT_KINDS = frozenset({"subsection", "clause"})


class LocatorError(ValueError):
    """The string is not a reconstructable Playground locator."""


@dataclass(frozen=True)
class SectionLocator:
    law_id: str
    section_number: str

    @property
    def value(self) -> str:
        return f"{self.law_id}:section:{self.section_number}"

    @property
    def unit_key(self) -> str:
        return ""


@dataclass(frozen=True)
class UnitLocator:
    law_id: str
    section_number: str
    kind: str
    label: str
    ordinal: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind or "").strip())
        object.__setattr__(self, "label", str(self.label or "").strip())
        ordinal = int(self.ordinal or 1)
        object.__setattr__(self, "ordinal", ordinal)
        if self.kind not in UNIT_KINDS or not self.label or ordinal < 1:
            raise LocatorError(
                f"invalid unit locator parts: {self.kind!r} {self.label!r} {ordinal!r}"
            )

    @property
    def unit_key(self) -> str:
        key = f"{self.kind}:{self.label}"
        if self.ordinal != 1:
            key += f"~{self.ordinal}"
        return key

    @property
    def value(self) -> str:
        return f"{self.law_id}:section:{self.section_number}:{self.unit_key}"

    @property
    def display_label(self) -> str:
        """Printed label. Never includes ``~n``."""
        return f"({self.label})"


PlaygroundLocator = SectionLocator | UnitLocator


def parse_locator(raw: str) -> PlaygroundLocator:
    text = str(raw or "").strip()
    section_match = _SECTION_RE.fullmatch(text)
    if section_match:
        law_id = section_match.group("law_id")
        number = section_match.group("section_number")
        if not is_playground_eligible_law(law_id):
            raise LocatorError(f"invalid playground locator: {raw!r}")
        return SectionLocator(law_id=law_id, section_number=number)
    unit_match = _UNIT_RE.fullmatch(text)
    if unit_match:
        law_id = unit_match.group("law_id")
        if not is_playground_eligible_law(law_id):
            raise LocatorError(f"invalid playground locator: {raw!r}")
        ordinal_raw = unit_match.group("ordinal")
        ordinal = int(ordinal_raw) if ordinal_raw else 1
        return UnitLocator(
            law_id=law_id,
            section_number=unit_match.group("section_number"),
            kind=unit_match.group("kind"),
            label=unit_match.group("label"),
            ordinal=ordinal,
        )
    raise LocatorError(f"invalid playground locator: {raw!r}")


def section_locator(law_id: str, number: str) -> SectionLocator:
    law = str(law_id or "").strip()
    num = str(number or "").strip()
    if not num or ":" in num or not is_playground_eligible_law(law):
        raise LocatorError(f"invalid playground locator parts: {law_id!r} {number!r}")
    return SectionLocator(law_id=law, section_number=num)


def unit_locator(
    law_id: str,
    section_number: str,
    kind: str,
    label: str,
    ordinal: int = 1,
) -> UnitLocator:
    law = str(law_id or "").strip()
    num = str(section_number or "").strip()
    if not num or ":" in num or not is_playground_eligible_law(law):
        raise LocatorError(
            f"invalid playground locator parts: {law_id!r} {section_number!r}"
        )
    return UnitLocator(
        law_id=law,
        section_number=num,
        kind=kind,
        label=label,
        ordinal=ordinal,
    )


def locator_section_number(locator: PlaygroundLocator | str) -> str:
    if isinstance(locator, (SectionLocator, UnitLocator)):
        return locator.section_number
    return parse_locator(locator).section_number


def is_section_locator(locator: object) -> bool:
    return isinstance(locator, SectionLocator)


def is_unit_locator(locator: object) -> bool:
    return isinstance(locator, UnitLocator)
