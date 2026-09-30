"""Single authority for Playground subsection/clause units.

Enumerate selectable units, resolve locators onto canonical nodes, extract
unit text / lead-in / tail, citation labels, duplicate-label ordinals, and
unit hashes. Routes, templates, source review, learning, and schedule call
this module instead of walking Bare Act trees themselves.

A selectable unit is a labelled statutory subsection or clause, including its
own descendants. Sections with fewer than two selectable units stay
section-only. Nested clauses inside a parent unit are descendants, not extra
picker rows. Unlabelled introductory material is lead-in context, not its own
unit. Closing provisos/explanations after the last unit are section tail and
are not attached to the final unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from constitution_memorizer.playground.locators import (
    LocatorError,
    PlaygroundLocator,
    SectionLocator,
    UnitLocator,
    UNIT_KINDS,
    parse_locator,
    unit_locator,
)
from constitution_memorizer.web.bare_acts import ActSection, BareAct, flatten_body
from constitution_memorizer.web import bare_acts as bare_act_registry

_PREVIEW_CHARS = 88
_UNLABELLED_DESCENT_TYPES = frozenset({"paragraph", "text", ""})


@dataclass(frozen=True)
class SelectableUnit:
    locator: UnitLocator
    kind: str
    label: str
    ordinal: int
    display_label: str
    canonical_text: str
    lead_in: str
    preview: str

    @property
    def hash_payload(self) -> str:
        return (
            f"{self.locator.section_number}\n"
            f"{self.kind}:{self.label}\n"
            f"{self.lead_in}\n"
            f"{self.canonical_text}"
        )


@dataclass(frozen=True)
class SectionUnitMap:
    section_number: str
    units: tuple[SelectableUnit, ...]
    lead_in: str
    tail: str

    @property
    def section_only(self) -> bool:
        return len(self.units) < 2

    def unit_for(self, locator: UnitLocator) -> SelectableUnit | None:
        for unit in self.units:
            if (
                unit.kind == locator.kind
                and unit.label == locator.label
                and unit.ordinal == locator.ordinal
            ):
                return unit
        return None


def printed_label(node: dict[str, Any] | None) -> str:
    """Label without wrapping parentheses. ``~n`` is never part of a label."""
    raw = str((node or {}).get("label") or "").strip()
    if raw.startswith("(") and raw.endswith(")") and len(raw) >= 3:
        inner = raw[1:-1]
        if "(" not in inner and ")" not in inner:
            return inner
    return raw


def display_printed_label(label: str) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    if text.startswith("(") and text.endswith(")"):
        return text
    return f"({text})"


def is_selectable_node(node: dict[str, Any] | None) -> bool:
    if not node:
        return False
    kind = str(node.get("type") or "").strip()
    return kind in UNIT_KINDS and bool(printed_label(node))


def citation_label(locator: PlaygroundLocator | str) -> str:
    loc = parse_locator(locator) if isinstance(locator, str) else locator
    if isinstance(loc, UnitLocator):
        return f"Section {loc.section_number}{loc.display_label}"
    return f"Section {loc.section_number}"


def canonical_nodes_text(nodes: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None, *, profile: str) -> str:
    parts = [
        row.text.strip()
        for row in flatten_body(nodes, profile=profile)
        if row.text and row.text.strip()
    ]
    return " ".join(parts)


def _preview(text: str) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= _PREVIEW_CHARS:
        return compact
    return compact[: _PREVIEW_CHARS - 1].rstrip() + "…"


def _peer_nodes(body: tuple[dict[str, Any], ...] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    nodes = list(body or [])
    if sum(1 for node in nodes if is_selectable_node(node)) >= 2:
        return nodes
    descended: list[dict[str, Any]] = []
    for node in nodes:
        if is_selectable_node(node):
            descended.append(node)
            continue
        kind = str(node.get("type") or "").strip()
        if printed_label(node):
            continue
        if kind not in _UNLABELLED_DESCENT_TYPES:
            continue
        children = list(node.get("children") or [])
        if any(is_selectable_node(child) for child in children):
            descended.extend(children)
    if sum(1 for node in descended if is_selectable_node(node)) >= 2:
        return descended
    return nodes


def section_unit_map(section: ActSection) -> SectionUnitMap:
    peers = _peer_nodes(section.body)
    selectable_indexes = [i for i, node in enumerate(peers) if is_selectable_node(node)]
    if len(selectable_indexes) < 2:
        lead = canonical_nodes_text(peers, profile=section.profile) if not selectable_indexes else canonical_nodes_text(
            peers[: selectable_indexes[0]], profile=section.profile
        )
        tail = ""
        if selectable_indexes:
            tail = canonical_nodes_text(
                peers[selectable_indexes[-1] + 1 :], profile=section.profile
            )
        return SectionUnitMap(
            section_number=section.number,
            units=(),
            lead_in=lead,
            tail=tail,
        )
    lead_nodes = peers[: selectable_indexes[0]]
    tail_nodes = peers[selectable_indexes[-1] + 1 :]
    lead_in = canonical_nodes_text(lead_nodes, profile=section.profile)
    tail = canonical_nodes_text(tail_nodes, profile=section.profile)
    seen: dict[tuple[str, str], int] = {}
    units: list[SelectableUnit] = []
    last_index = len(selectable_indexes) - 1
    for ordinal_i, index in enumerate(selectable_indexes):
        node = peers[index]
        kind = str(node.get("type") or "").strip()
        label = printed_label(node)
        seen[(kind, label)] = seen.get((kind, label), 0) + 1
        ordinal = seen[(kind, label)]
        if ordinal_i == last_index:
            following: list[dict[str, Any]] = []
        else:
            following = [
                peers[j]
                for j in range(index + 1, selectable_indexes[ordinal_i + 1])
                if not is_selectable_node(peers[j])
            ]
        canonical = canonical_nodes_text([node, *following], profile=section.profile)
        loc = UnitLocator(
            law_id="",
            section_number=section.number,
            kind=kind,
            label=label,
            ordinal=ordinal,
        )
        units.append(
            SelectableUnit(
                locator=loc,
                kind=kind,
                label=label,
                ordinal=ordinal,
                display_label=display_printed_label(label),
                canonical_text=canonical,
                lead_in=lead_in,
                preview=_preview(canonical),
            )
        )
    return SectionUnitMap(
        section_number=section.number,
        units=tuple(units),
        lead_in=lead_in,
        tail=tail,
    )


def enumerate_selectable_units(
    section: ActSection, *, law_id: str = ""
) -> tuple[SelectableUnit, ...]:
    mapped = section_unit_map(section)
    if mapped.section_only:
        return ()
    if not law_id:
        return mapped.units
    return tuple(
        SelectableUnit(
            locator=unit_locator(
                law_id,
                section.number,
                unit.kind,
                unit.label,
                unit.ordinal,
            ),
            kind=unit.kind,
            label=unit.label,
            ordinal=unit.ordinal,
            display_label=unit.display_label,
            canonical_text=unit.canonical_text,
            lead_in=unit.lead_in,
            preview=unit.preview,
        )
        for unit in mapped.units
    )


def section_lead_in(section: ActSection) -> str:
    return section_unit_map(section).lead_in


def section_tail(section: ActSection) -> str:
    return section_unit_map(section).tail


def resolve_unit(
    locator: UnitLocator, *, act: BareAct | None = None, section: ActSection | None = None
) -> SelectableUnit:
    host = section
    if host is None:
        if act is None:
            act = bare_act_registry.get_bare_act(locator.law_id)
        if act is None:
            raise LocatorError(f"unknown law: {locator.law_id}")
        host = act.section(locator.section_number)
    if host is None:
        raise LocatorError(f"unknown section: {locator.value}")
    if host.is_omitted:
        raise LocatorError(f"omitted section: {locator.value}")
    units = enumerate_selectable_units(host, law_id=locator.law_id)
    for unit in units:
        if (
            unit.kind == locator.kind
            and unit.label == locator.label
            and unit.ordinal == locator.ordinal
        ):
            return unit
    raise LocatorError(f"unknown unit: {locator.value}")


def unit_hash(unit: SelectableUnit) -> str:
    return sha256(unit.hash_payload.encode("utf-8")).hexdigest()


def unit_hash_for_locator(
    locator: UnitLocator, section: ActSection, *, law_id: str = ""
) -> str:
    resolved = resolve_unit(
        locator
        if locator.law_id
        else unit_locator(
            law_id or locator.law_id,
            locator.section_number,
            locator.kind,
            locator.label,
            locator.ordinal,
        ),
        section=section,
    )
    return unit_hash(resolved)


def source_hash_for_locator(
    locator: PlaygroundLocator,
    section: ActSection,
    *,
    section_hash,
) -> str:
    """Hash the active learning target. ``section_hash`` is the whole-section digest."""
    if isinstance(locator, UnitLocator):
        return unit_hash_for_locator(locator, section, law_id=locator.law_id)
    return section_hash(section)


def canonical_text_for_locator(
    locator: PlaygroundLocator, section: ActSection
) -> str:
    if isinstance(locator, UnitLocator):
        return resolve_unit(locator, section=section).canonical_text
    return canonical_nodes_text(section.body, profile=section.profile)


def bind_unit_locator(law_id: str, section: ActSection, unit: SelectableUnit) -> UnitLocator:
    return unit_locator(law_id, section.number, unit.kind, unit.label, unit.ordinal)
