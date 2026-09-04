"""Bare Act registry — full statutes read end to end, not clause extracts.

`laws_data.py` holds the other half of /laws: hand-seeded clauses mapped to
Articles. This half serves whole Acts from their canonical parsed JSON, and is
deliberately generic — a second Act costs a JSON file and a `BARE_ACTS` entry,
not another reader.

The adapter is non-destructive. View models expose what the templates need, but
nothing here mutates or re-derives the canonical file: annotations, footnote
ids, source pages and per-cell table annotations all survive on the parsed
nodes, unread for now, so footnote markers and amendment history have them when
that work lands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from constitution_memorizer.utils.json_io import read_json

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEB_DIR = Path(__file__).resolve().parent

# Words that stay lowercase mid-title when an ALL-CAPS chapter heading is
# title-cased. Matches the design prototype's list exactly.
_MINOR_WORDS = frozenset(
    {"and", "of", "for", "in", "the", "from", "or", "to", "under"}
)

EN_DASH = "–"

# Print leader dots ("Opium . . . . . ." ) carry the eye across a printed
# column rule. On screen the column does that job, and the dots read as data.
_LEADER_DOTS = re.compile(r"(?:\s*\.){3,}\s*$")


class BareActMissing(RuntimeError):
    """A registered Act's canonical JSON is not on disk. Fail, never degrade."""


@dataclass(frozen=True)
class BareActSpec:
    """Registry entry: everything about an Act that is not in its JSON."""

    slug: str
    filename: str
    short_name: str
    back_label: str


BARE_ACTS: dict[str, BareActSpec] = {
    "ndps": BareActSpec(
        slug="ndps",
        filename="ndps_act_final.json",
        short_name="The NDPS Act, 1985",
        back_label="← The NDPS Act, 1985",
    ),
}


@dataclass(frozen=True)
class ProvisionRow:
    """One body node, flattened into reading order with its nesting depth."""

    depth: int
    kind: str
    label: str
    text: str
    table: dict[str, Any] | None = None

    @property
    def is_table(self) -> bool:
        return self.table is not None

    @property
    def is_omission(self) -> bool:
        return self.kind == "omission"

    @property
    def is_aside(self) -> bool:
        """Proviso and Explanation: unlabelled, set apart, still in the flow."""
        return self.kind in {"proviso", "explanation"}

    @property
    def table_columns(self) -> tuple[str, ...]:
        if not self.table:
            return ()
        return tuple(str(c) for c in self.table.get("columns") or ())

    @property
    def table_body(self) -> tuple[tuple[str, ...], ...]:
        """Rows as display strings, in column order. Values are not rewritten."""
        if not self.table:
            return ()
        columns = self.table_columns
        return tuple(
            tuple(_strip_leader_dots(row.get(column)) for column in columns)
            for row in self.table.get("rows") or ()
        )


@dataclass(frozen=True)
class ActSection:
    number: str
    title: str
    status: str
    former_title: str | None
    omission_note: str | None
    chapter_number: str
    chapter_title: str
    body: tuple[dict[str, Any], ...]

    @property
    def is_omitted(self) -> bool:
        return self.status == "omitted"

    @property
    def list_title(self) -> str:
        """Section 65's canonical title is the literal string "[Omitted]".

        Rendered as a plain word instead: the brackets are a print convention,
        and the status field already says this authoritatively.
        """
        if self.is_omitted:
            return "Omitted"
        return self.title

    @property
    def rows(self) -> tuple[ProvisionRow, ...]:
        return flatten_body(self.body)


@dataclass(frozen=True)
class ActChapter:
    number: str
    title: str
    sections: tuple[ActSection, ...]

    @property
    def range_label(self) -> str:
        if not self.sections:
            return ""
        first = self.sections[0].number
        last = self.sections[-1].number
        if first == last:
            return first
        return f"{first}{EN_DASH}{last}"


@dataclass(frozen=True)
class BareAct:
    slug: str
    title: str
    short_name: str
    back_label: str
    act_number: str
    chapters: tuple[ActChapter, ...]
    section_order: tuple[ActSection, ...]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def section_range(self) -> str:
        if not self.section_order:
            return ""
        return (
            f"{self.section_order[0].number}{EN_DASH}"
            f"{self.section_order[-1].number}"
        )

    @property
    def meta_label(self) -> str:
        """"8 Chapters · Sections 1–83" — derived, never typed into a template."""
        return (
            f"{self.chapter_count} Chapters · "
            f"Sections {self.section_range}"
        )

    def section(self, number: str) -> ActSection | None:
        return self._by_number.get(str(number))

    @property
    def _by_number(self) -> dict[str, ActSection]:
        return {s.number: s for s in self.section_order}

    def neighbours(self, number: str) -> tuple[ActSection | None, ActSection | None]:
        """Previous/next across the whole Act, so chapter edges are not walls."""
        order = self.section_order
        for index, section in enumerate(order):
            if section.number != str(number):
                continue
            previous = order[index - 1] if index > 0 else None
            following = order[index + 1] if index + 1 < len(order) else None
            return previous, following
        return None, None


def _strip_leader_dots(value: Any) -> str:
    return _LEADER_DOTS.sub("", str(value or "")).strip()


def title_case_chapter(text: str) -> str:
    """ALL-CAPS chapter heading to Title Case, keeping minor words lowercase.

    The source is shouted ("NATIONAL FUND FOR CONTROL OF DRUG ABUSE"); the
    design sets chapter titles in sentence-weight type, where all caps reads as
    an error rather than as emphasis.
    """
    words = str(text or "").split(" ")
    out: list[str] = []
    for index, word in enumerate(words):
        lowered = word.lower()
        stripped = lowered.strip(",.;:()")
        if index > 0 and stripped in _MINOR_WORDS:
            out.append(lowered)
            continue
        out.append(_capitalise(lowered))
    return " ".join(out)


def _capitalise(word: str) -> str:
    """Uppercase the first letter after any opening punctuation or dash."""
    result: list[str] = []
    seen_letter = False
    for char in word:
        if not seen_letter and char.isalpha():
            result.append(char.upper())
            seen_letter = True
            continue
        if char in "-—(":
            # A hyphen or dash starts a new word: "SUB-DIVISION" -> "Sub-Division".
            seen_letter = False
        result.append(char)
    return "".join(result)


def flatten_body(nodes, depth: int = 0) -> tuple[ProvisionRow, ...]:
    """Depth-first walk into reading order, carrying nesting depth.

    Flattening happens here rather than in a recursive Jinja macro so the
    nesting rules are unit-testable. This is a *presentation* sequence — the
    stored tree is untouched.
    """
    rows: list[ProvisionRow] = []
    for node in nodes or []:
        rows.append(
            ProvisionRow(
                depth=depth,
                kind=str(node.get("type") or "paragraph"),
                label=str(node.get("label") or ""),
                text=str(node.get("text") or ""),
                table=node.get("table"),
            )
        )
        rows.extend(flatten_body(node.get("children") or [], depth + 1))
    return tuple(rows)


def _act_path(spec: BareActSpec) -> Path:
    repo = _REPO_ROOT / "data" / "reference" / spec.filename
    packaged = _WEB_DIR / spec.filename
    for candidate in (repo, packaged):
        if candidate.exists():
            return candidate
    raise BareActMissing(
        f"bare Act {spec.slug!r} not found at {repo} or {packaged}. "
        "The Act is reference material shipped with the app: a missing file "
        "means it was not packaged, not that the Act has no sections."
    )


def _parse(spec: BareActSpec, data: dict[str, Any]) -> BareAct:
    document = data.get("document") or {}
    chapters: list[ActChapter] = []
    order: list[ActSection] = []
    for raw_chapter in data.get("chapters") or []:
        chapter_number = str(raw_chapter.get("number") or "")
        chapter_title = title_case_chapter(raw_chapter.get("title") or "")
        sections: list[ActSection] = []
        for raw_section in raw_chapter.get("sections") or []:
            section = ActSection(
                # Never an int: 7A, 25A, 68-I, 68-O and 68Z are all real.
                number=str(raw_section.get("number") or ""),
                title=str(raw_section.get("title") or ""),
                status=str(raw_section.get("status") or "active"),
                former_title=raw_section.get("former_title"),
                omission_note=raw_section.get("omission_note"),
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                body=tuple(raw_section.get("body") or []),
            )
            sections.append(section)
            order.append(section)
        chapters.append(
            ActChapter(
                number=chapter_number,
                title=chapter_title,
                sections=tuple(sections),
            )
        )
    return BareAct(
        slug=spec.slug,
        title=str(document.get("title") or spec.short_name),
        short_name=spec.short_name,
        back_label=spec.back_label,
        act_number=str(document.get("act_number") or ""),
        chapters=tuple(chapters),
        # One ordered list of every section in the Act, in the Act's own order.
        section_order=tuple(order),
        raw=data,
    )


@lru_cache(maxsize=4)
def _load_cached(slug: str) -> BareAct:
    spec = BARE_ACTS[slug]
    return _parse(spec, read_json(_act_path(spec)))


def get_bare_act(slug: str) -> BareAct | None:
    """The Act for this slug, or None — 404 is the caller's decision."""
    if slug not in BARE_ACTS:
        return None
    return _load_cached(slug)


def list_bare_acts() -> list[BareAct]:
    return [_load_cached(slug) for slug in BARE_ACTS]
