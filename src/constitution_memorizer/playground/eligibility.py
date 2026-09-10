"""Single Playground law-eligibility authority.

A law is eligible only when it is a catalogue entry whose primary content is
a full Bare Act and whose ``full_act`` ref resolves to a ``BareActSpec``.

Uses catalogue/registry metadata only. Never hydrates runtime Act JSON.
"""

from __future__ import annotations

import re

from constitution_memorizer.web.bare_acts import BARE_ACTS, BareActSpec
from constitution_memorizer.web.law_catalog import load_catalog

# Safe generic slug: lowercase, digits, hyphenated segments. Catalogue ids
# such as uapa-1967 match; they still fail eligibility unless they are a
# full Bare Act with a BareActSpec.
_LAW_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class PlaygroundLawError(LookupError):
    """Law is not Playground-eligible (or the runtime Act is missing)."""


def _normalize_law_id(law_id: str) -> str:
    return str(law_id or "").strip()


def _catalogue_full_act_ref(law_id: str) -> str | None:
    """Return the Bare Act slug if this catalogue law is a full Act.

    Matches the Playground/Bare Act slug (``full_act_ref``) or the catalogue
    id. Does not consult ``get_bare_act`` / ``list_bare_acts``.
    """
    slug = _normalize_law_id(law_id)
    if not slug or _LAW_SLUG_RE.fullmatch(slug) is None:
        return None
    for law in load_catalog().laws:
        if law.primary_content != "full_act":
            continue
        ref = law.full_act_ref
        if not ref:
            continue
        if slug != law.id and slug != ref:
            continue
        return ref
    return None


def is_playground_eligible_law(law_id: str) -> bool:
    """True iff *law_id* is a catalogue full Bare Act with a ``BareActSpec``."""
    ref = _catalogue_full_act_ref(law_id)
    return ref is not None and ref in BARE_ACTS


def playground_bare_act_spec(law_id: str) -> BareActSpec | None:
    """Registry spec for an eligible law, or None. Metadata only."""
    ref = _catalogue_full_act_ref(law_id)
    if ref is None:
        return None
    return BARE_ACTS.get(ref)


def list_playground_eligible_laws() -> tuple[str, ...]:
    """Bare Act slugs that are Playground-eligible, in catalogue order."""
    seen: list[str] = []
    for law in load_catalog().laws:
        if law.primary_content != "full_act":
            continue
        ref = law.full_act_ref
        if not ref or ref not in BARE_ACTS:
            continue
        if ref not in seen:
            seen.append(ref)
    return tuple(seen)
