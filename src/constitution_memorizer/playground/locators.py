"""Deterministic locators for Playground overlay on Bare Act JSON."""

from __future__ import annotations

import re
from dataclasses import dataclass

PLAYGROUND_LAW_IDS = frozenset({"ndps", "bns"})

_LOCATOR_RE = re.compile(r"^(?P<law_id>ndps|bns):section:(?P<number>.+)$")


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
    return SectionLocator(law_id=match.group("law_id"), number=match.group("number"))


def section_locator(law_id: str, number: str) -> SectionLocator:
    law = str(law_id or "").strip()
    num = str(number or "").strip()
    if law not in PLAYGROUND_LAW_IDS or not num:
        raise LocatorError(f"invalid playground locator parts: {law_id!r} {number!r}")
    return SectionLocator(law_id=law, number=num)
