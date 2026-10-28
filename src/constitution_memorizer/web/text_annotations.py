"""Bare Act footnotes for the Constitution's reading surfaces.

Anchors and notes are rendered in the shape the Bare Act reader uses, so both
read the same way: the marked run is underlined in place and its note goes to
one card at the foot of the reading column.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from markupsafe import Markup

from constitution_memorizer.utils.json_io import read_json

logger = logging.getLogger(__name__)

DEFAULT_ANNOTATIONS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "text_annotations.json"
)

ContentNodeType = Literal["text", "note_ref"]


@dataclass(frozen=True)
class NoteRecord:
    """Reusable secondary note referenced by note_ref content nodes."""

    id: str
    note: str


@dataclass(frozen=True)
class ContentText:
    value: str


@dataclass(frozen=True)
class ContentNoteRef:
    label: str
    note_id: str


ContentNode = ContentText | ContentNoteRef


AnnotationSurface = Literal["browse", "learn"]
DEFAULT_SURFACES: tuple[AnnotationSurface, ...] = ("browse", "learn")


@dataclass(frozen=True)
class TextAnnotation:
    """Word annotation: legacy flat note and/or structured tip content."""

    target: str
    note: str = ""
    content: tuple[ContentNode, ...] = ()
    # When omitted in JSON, annotation appears on both Learn and Browse.
    surfaces: tuple[AnnotationSurface, ...] = DEFAULT_SURFACES


@dataclass(frozen=True)
class TextAnnotationsCatalog:
    """Loaded annotations file: unit map + shared notes."""

    units: dict[str, list[TextAnnotation]] = field(default_factory=dict)
    notes: dict[str, NoteRecord] = field(default_factory=dict)

    def __contains__(self, key: object) -> bool:
        return key in self.units

    def __getitem__(self, key: str) -> list[TextAnnotation]:
        return self.units[key]

    def get(self, key: str, default: list[TextAnnotation] | None = None) -> list[TextAnnotation]:
        return self.units.get(key, [] if default is None else default)


def _parse_surfaces(raw: object) -> tuple[AnnotationSurface, ...]:
    """Parse optional surfaces list; default both Browse and Learn."""
    if raw is None:
        return DEFAULT_SURFACES
    if not isinstance(raw, list) or not raw:
        return DEFAULT_SURFACES
    out: list[AnnotationSurface] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value in ("browse", "learn") and value not in out:
            out.append(value)  # type: ignore[arg-type]
    return tuple(out) if out else DEFAULT_SURFACES


def filter_annotations_for_surface(
    annotations: list[TextAnnotation],
    surface: AnnotationSurface,
) -> list[TextAnnotation]:
    """Keep annotations allowed on the given surface (browse or learn)."""
    return [ann for ann in annotations if surface in ann.surfaces]


def _parse_content_nodes(raw: object) -> tuple[ContentNode, ...]:
    if not isinstance(raw, list):
        return ()
    nodes: list[ContentNode] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind == "text":
            value = str(item.get("value") or "")
            if value:
                nodes.append(ContentText(value=value))
        elif kind == "note_ref":
            label = str(item.get("label") or "").strip()
            note_id = str(item.get("note_id") or "").strip()
            if label and note_id:
                nodes.append(ContentNoteRef(label=label, note_id=note_id))
        else:
            logger.warning("Skipping unsupported annotation content type: %r", kind)
    return tuple(nodes)


def load_text_annotations(
    path: Path | str | None = None,
) -> TextAnnotationsCatalog:
    """Load unit-id → annotation list map and shared notes."""
    resolved = Path(path) if path is not None else DEFAULT_ANNOTATIONS_PATH
    if not resolved.exists():
        return TextAnnotationsCatalog()
    data = read_json(resolved)
    notes_raw = data.get("notes") or {}
    notes: dict[str, NoteRecord] = {}
    if isinstance(notes_raw, dict):
        for note_id, row in notes_raw.items():
            if not isinstance(row, dict):
                continue
            note_text = str(row.get("note") or "").strip()
            nid = str(note_id).strip()
            if nid and note_text:
                notes[nid] = NoteRecord(id=nid, note=note_text)

    units_raw = data.get("units") or {}
    out: dict[str, list[TextAnnotation]] = {}
    for unit_id, rows in units_raw.items():
        anns: list[TextAnnotation] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            target = str(row.get("target") or "").strip()
            if not target:
                continue
            note = str(row.get("note") or "").strip()
            content = _parse_content_nodes(row.get("content"))
            if not note and not content:
                continue
            surfaces = _parse_surfaces(row.get("surfaces"))
            anns.append(
                TextAnnotation(
                    target=target,
                    note=note,
                    content=content,
                    surfaces=surfaces,
                )
            )
        if anns:
            out[str(unit_id)] = anns
    return TextAnnotationsCatalog(units=out, notes=notes)


def annotations_for_unit(
    catalog: TextAnnotationsCatalog | dict[str, list[TextAnnotation]],
    unit_id: str | None,
    *,
    surface: AnnotationSurface | None = None,
) -> list[TextAnnotation]:
    if not unit_id:
        return []
    if isinstance(catalog, TextAnnotationsCatalog):
        anns = list(catalog.get(unit_id) or [])
    else:
        anns = list(catalog.get(unit_id) or [])
    if surface is None:
        return anns
    return filter_annotations_for_surface(anns, surface)


def annotations_for_article(
    catalog: TextAnnotationsCatalog | dict[str, list[TextAnnotation]],
    article_number: str | None,
    unit_ids: list[str] | None = None,
    *,
    surface: AnnotationSurface = "browse",
) -> list[TextAnnotation]:
    """
    Annotations for a Browse article page.

    Merges ``article-{n}`` keys with per-unit annotations, deduping by target
    so the first match in full article text wins.
    """
    if not article_number:
        return []
    from constitution_memorizer.utils.identifiers import article_id  # noqa: PLC0415

    ordered_ids: list[str] = [article_id(article_number)]
    for uid in unit_ids or []:
        if uid and uid not in ordered_ids:
            ordered_ids.append(uid)

    out: list[TextAnnotation] = []
    seen_targets: set[str] = set()
    for uid in ordered_ids:
        for ann in annotations_for_unit(catalog, uid, surface=surface):
            key = ann.target.casefold()
            if key in seen_targets:
                continue
            seen_targets.add(key)
            out.append(ann)
    return out


def _sanitize_id_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "x"

@dataclass(frozen=True)
class FootnoteNote:
    """One note, rendered into the page's footnote apparatus.

    Shaped like ``bare_acts.Footnote`` — ``id`` and ``text`` — so both readers
    feed the same ``partials/bare_act_footnotes.html``. ``text`` is a ``Markup``
    here because a note may itself cite another note; every part of it is
    escaped where it is built.
    """

    id: str
    text: Markup


@dataclass(frozen=True)
class AnnotatedText:
    """Annotated body text and the notes its anchors point at.

    The two travel together on purpose: the anchor ids and the note ids are
    minted in one pass, so a template cannot render one without the other and
    leave anchors describing nothing.
    """

    html: Markup
    footnotes: tuple[FootnoteNote, ...] = ()


def _anchor(note_id: str, inner: str, *, focusable: bool = True) -> str:
    """The one footnote anchor shape, shared with the Bare Act reader.

    Deliberately identical to the ``fn_anchor`` macro: ``tabindex`` with no
    role, because this is a run of statute text carrying a note, not a control,
    and the accessible name should stay the text itself.

    Anchors inside a note body are rendered ``tabindex="-1"``: that copy lives
    in the visually-hidden notes block, and a tab stop the eye cannot find is
    worse than no tab stop. The card re-enables them when it shows the note.
    """
    tabindex = "0" if focusable else "-1"
    return (
        f'<span class="bareact-fn" tabindex="{tabindex}" '
        f'data-bareact-fn="{note_id}" aria-describedby="fn-{note_id}">'
        f"{inner}</span>"
    )


def render_note_body(
    ann: TextAnnotation, notes: dict[str, NoteRecord]
) -> tuple[Markup, tuple[FootnoteNote, ...]]:
    """A note's own text, plus the notes it cites.

    All text is escaped. A ``note_ref`` becomes an anchor inside the note, so a
    note citing an amendment is read exactly the way body text citing one is —
    same anchor, same card. Missing ``note_id`` renders the label as plain text.
    """
    if not ann.content:
        return Markup(html.escape(ann.note)), ()

    chunks: list[str] = []
    cited: list[FootnoteNote] = []
    for node in ann.content:
        if isinstance(node, ContentText):
            chunks.append(html.escape(node.value))
            continue
        label = html.escape(node.label)
        record = notes.get(node.note_id)
        if record is None:
            logger.warning(
                "Missing annotation note_id %r; rendering plain label", node.note_id
            )
            chunks.append(label)
            continue
        nested_id = _sanitize_id_part(node.note_id)
        chunks.append(_anchor(nested_id, label, focusable=False))
        cited.append(
            FootnoteNote(id=nested_id, text=Markup(html.escape(record.note)))
        )
    return Markup("".join(chunks)), tuple(cited)


def annotate_plain_text(
    text: str,
    annotations: list[TextAnnotation],
    *,
    notes: dict[str, NoteRecord] | None = None,
    unit_id: str | None = None,
) -> AnnotatedText:
    """
    Escape plain Bare Act text and anchor the first whole-word hit of each target.

    Returns the marked-up text together with the notes it refers to; the caller
    renders those through the footnote partial. Memorized modes keep
    ``unit.text`` plain.
    """
    if not text:
        return AnnotatedText(Markup(""))
    if not annotations:
        return AnnotatedText(Markup(html.escape(text)))

    note_map = notes or {}
    prefix = _sanitize_id_part(unit_id or "fn")
    remaining = text
    chunks: list[str] = []
    collected: list[FootnoteNote] = []
    seen: set[str] = set()

    for index, ann in enumerate(annotations):
        pattern = re.compile(rf"(?<!\w)({re.escape(ann.target)})(?!\w)")
        match = pattern.search(remaining)
        if match is None:
            continue
        chunks.append(html.escape(remaining[: match.start()]))
        note_id = f"{prefix}-note-{index}"
        body, cited = render_note_body(ann, note_map)
        chunks.append(_anchor(note_id, html.escape(match.group(1))))
        for note in (FootnoteNote(id=note_id, text=body), *cited):
            if note.id in seen:
                continue
            seen.add(note.id)
            collected.append(note)
        remaining = remaining[match.end() :]

    chunks.append(html.escape(remaining))
    return AnnotatedText(Markup("".join(chunks)), tuple(collected))
