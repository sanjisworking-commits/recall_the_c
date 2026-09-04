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
from time import perf_counter
from typing import Any

from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.request_context import (
    record_request_counter,
    record_request_note,
    record_request_timing,
    snapshot_request_counters,
)

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
    # Companion files the upstream parse ships separately. Folded in at load
    # rather than merged on disk: both are frozen artifacts, and rewriting one
    # into the other would replace the canonical dataset with our own.
    patch_filenames: tuple[str, ...] = ()


BARE_ACTS: dict[str, BareActSpec] = {
    "ndps": BareActSpec(
        slug="ndps",
        filename="ndps_act_final.json",
        short_name="The NDPS Act, 1985",
        back_label="← The NDPS Act, 1985",
        patch_filenames=("ndps_schedule_patch.json",),
    ),
}


@dataclass(frozen=True)
class Footnote:
    """An amendment note: which Act changed this provision, and from when."""

    id: str
    marker: str
    text: str


@dataclass(frozen=True)
class FootnoteSpan:
    """A run of text, carrying a footnote reference when it has one."""

    text: str
    note_id: str | None = None
    marker: str = ""

    @property
    def is_anchor(self) -> bool:
        return self.note_id is not None


@dataclass(frozen=True)
class ProvisionRow:
    """One body node, flattened into reading order with its nesting depth."""

    depth: int
    kind: str
    label: str
    text: str
    table: dict[str, Any] | None = None
    annotations: tuple[dict[str, Any], ...] = ()
    label_annotations: tuple[dict[str, Any], ...] = ()

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
    def segments(self) -> tuple[FootnoteSpan, ...]:
        """`text` split into plain runs and footnote anchors, in order.

        Offsets index the text as stored, which is already free of the source's
        inline markers — so this slices `text` directly. Re-cleaning it first
        would shift every offset after the first edit.
        """
        if self.is_omission or self.is_table:
            # Omissions display "Omitted." in place of the source's "* * * * *",
            # so the stored offsets describe text that is never rendered.
            return (FootnoteSpan(self.text),)
        return split_on_footnotes(self.text, self.annotations)

    @property
    def label_note_id(self) -> str | None:
        """Labels carry their marker whole — `(iii)` is the anchor, not part of it."""
        return _first_footnote_id(self.label_annotations)

    @property
    def note_ids(self) -> tuple[str, ...]:
        ids = [s.note_id for s in self.segments if s.note_id]
        if self.label_note_id:
            ids.append(self.label_note_id)
        return tuple(ids)

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
class ScheduleEntry:
    serial_number: str
    inn: str
    other_names: str
    chemical_name: str
    serial_note_id: str | None = None

    @property
    def cells(self) -> tuple[str, ...]:
        return (self.serial_number, self.inn, self.other_names, self.chemical_name)


@dataclass(frozen=True)
class Schedule:
    slug: str
    title: str
    reference: str
    heading: str
    columns: tuple[str, ...]
    entries: tuple[ScheduleEntry, ...]

    @property
    def display_heading(self) -> str:
        return title_case_chapter(self.heading)

    @property
    def range_label(self) -> str:
        if not self.entries:
            return ""
        first = self.entries[0].serial_number
        last = self.entries[-1].serial_number
        return first if first == last else f"{first}{EN_DASH}{last}"

    @property
    def note_ids(self) -> tuple[str, ...]:
        return tuple(e.serial_note_id for e in self.entries if e.serial_note_id)


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

    @property
    def note_ids(self) -> tuple[str, ...]:
        """Every footnote this section cites, once each, in reading order."""
        seen: list[str] = []
        for row in self.rows:
            for note_id in row.note_ids:
                if note_id not in seen:
                    seen.append(note_id)
        return tuple(seen)


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
    footnotes: dict[str, Footnote] = field(default_factory=dict)
    schedules: tuple[Schedule, ...] = ()
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    def schedule(self, slug: str) -> Schedule | None:
        for sched in self.schedules:
            if sched.slug == slug:
                return sched
        return None

    def notes(self, note_ids) -> tuple[Footnote, ...]:
        """Resolve ids to notes, skipping any the data does not carry."""
        return tuple(
            self.footnotes[n] for n in note_ids if n in self.footnotes
        )

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


def _first_footnote_id(annotations) -> str | None:
    for ann in annotations or []:
        if ann.get("type") == "footnote" and ann.get("note_id"):
            return str(ann["note_id"])
    return None


def split_on_footnotes(text: str, annotations) -> tuple[FootnoteSpan, ...]:
    """Split `text` into plain runs and footnote anchors.

    Malformed spans are dropped rather than raising: a bad offset should cost
    one anchor, not a whole section. Spans are clamped to the text and
    overlaps resolved by taking the earlier one, so the pieces always rejoin
    to exactly the input.
    """
    body = str(text or "")
    spans = sorted(
        (
            a
            for a in annotations or []
            if a.get("type") == "footnote"
            and isinstance(a.get("start"), int)
            and isinstance(a.get("end"), int)
            and a["end"] > a["start"]
        ),
        key=lambda a: a["start"],
    )
    out: list[FootnoteSpan] = []
    pos = 0
    for ann in spans:
        start = max(int(ann["start"]), pos)
        end = min(int(ann["end"]), len(body))
        if end <= start:
            continue
        if start > pos:
            out.append(FootnoteSpan(body[pos:start]))
        out.append(
            FootnoteSpan(
                body[start:end],
                note_id=str(ann.get("note_id") or "") or None,
                marker=str(ann.get("marker") or ""),
            )
        )
        pos = end
    if pos < len(body):
        out.append(FootnoteSpan(body[pos:]))
    return tuple(out) or (FootnoteSpan(body),)


def _schedule_slug(raw_id: str) -> str:
    """`schedule_psychotropic_substances` -> `psychotropic-substances`."""
    stem = str(raw_id or "schedule")
    if stem.startswith("schedule_"):
        stem = stem[len("schedule_") :]
    return stem.replace("_", "-").strip("-") or "schedule"


def _parse_schedule(raw: dict[str, Any]) -> Schedule:
    entries = tuple(
        ScheduleEntry(
            # Strings throughout: 105A and 110ZT are serial numbers too.
            serial_number=str(e.get("serial_number") or ""),
            inn=str(e.get("international_non_proprietary_name") or ""),
            other_names=str(e.get("other_nonproprietary_names") or ""),
            chemical_name=str(e.get("chemical_name") or ""),
            serial_note_id=_first_footnote_id(e.get("serial_annotations")),
        )
        for e in raw.get("entries") or []
    )
    return Schedule(
        slug=_schedule_slug(str(raw.get("id") or "")),
        title=str(raw.get("title") or "The Schedule"),
        reference=str(raw.get("reference") or ""),
        heading=str(raw.get("heading") or ""),
        columns=tuple(str(c) for c in raw.get("columns") or ()),
        entries=entries,
    )


def _collect_footnotes(sources) -> dict[str, Footnote]:
    """One lookup across the Act and its patches. Collisions are fatal.

    A patch that silently overwrote a note would print the wrong amendment
    against a provision — a quieter failure than a crash, and a worse one.
    """
    notes: dict[str, Footnote] = {}
    for label, raw_notes in sources:
        for raw in raw_notes or []:
            note_id = str(raw.get("id") or "")
            if not note_id:
                continue
            if note_id in notes:
                raise BareActMissing(
                    f"footnote id {note_id!r} appears twice ({label} redefines it). "
                    "Footnote ids must be unique across an Act and its patches."
                )
            notes[note_id] = Footnote(
                id=note_id,
                marker=str(raw.get("marker") or ""),
                text=str(raw.get("text") or ""),
            )
    return notes


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
                annotations=tuple(node.get("annotations") or ()),
                label_annotations=tuple(node.get("label_annotations") or ()),
            )
        )
        rows.extend(flatten_body(node.get("children") or [], depth + 1))
    return tuple(rows)


def _data_path(filename: str) -> Path:
    repo = _REPO_ROOT / "data" / "reference" / filename
    packaged = _WEB_DIR / filename
    for candidate in (repo, packaged):
        if candidate.exists():
            return candidate
    raise BareActMissing(
        f"bare Act data {filename!r} not found at {repo} or {packaged}. "
        "The Act is reference material shipped with the app: a missing file "
        "means it was not packaged, not that the Act has no sections."
    )


def _parse(
    spec: BareActSpec, data: dict[str, Any], patches: list[dict[str, Any]]
) -> BareAct:
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
    schedules = [_parse_schedule(s) for s in data.get("schedules") or []]
    for patch in patches:
        schedules.extend(_parse_schedule(s) for s in patch.get("schedules") or [])
    footnotes = _collect_footnotes(
        [(spec.filename, data.get("footnotes"))]
        + [
            (name, patch.get("footnotes"))
            for name, patch in zip(spec.patch_filenames, patches)
        ]
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
        footnotes=footnotes,
        schedules=tuple(schedules),
        raw=data,
    )


@lru_cache(maxsize=4)
def _load_cached(slug: str) -> BareAct:
    # Diagnostics live *inside* the cached body, which by construction runs only
    # when this request actually parsed the Act. Comparing cache_info() around a
    # call would be wrong: it is process-global, so concurrent requests would
    # read each other's deltas.
    started = perf_counter()
    spec = BARE_ACTS[slug]
    patches = [read_json(_data_path(name)) for name in spec.patch_filenames]
    act = _parse(spec, read_json(_data_path(spec.filename)), patches)
    record_request_timing("bare_act_load", started)
    record_request_counter("bare_act_cache_misses", 1)
    return act


def _note_cache_outcome(before: int) -> None:
    """Hit or miss for *this* request, from its own counter.

    Not a claim about the process: `functools.lru_cache` holds no lock across
    the call, so two concurrent first-touch requests may each run the loader
    body and each honestly record a miss.
    """
    after = snapshot_request_counters().get("bare_act_cache_misses", 0)
    record_request_note("bare_act_cache", "miss" if after > before else "hit")


def get_bare_act(slug: str) -> BareAct | None:
    """The Act for this slug, or None — 404 is the caller's decision."""
    if slug not in BARE_ACTS:
        return None
    before = snapshot_request_counters().get("bare_act_cache_misses", 0)
    act = _load_cached(slug)
    _note_cache_outcome(before)
    return act


def list_bare_acts() -> list[BareAct]:
    before = snapshot_request_counters().get("bare_act_cache_misses", 0)
    acts = [_load_cached(slug) for slug in BARE_ACTS]
    _note_cache_outcome(before)
    return acts
