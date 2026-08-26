"""Deterministic scrub of Docling/display artefacts in reviewed Articles."""

from __future__ import annotations

import re

from constitution_memorizer.schemas import Article, ConstitutionDocument, ProvisionNode

_FORMULA_RE = re.compile(r"<!--\s*formula-not-decoded\s*-->", re.IGNORECASE)
_PUA_RE = re.compile(r"[\ue000-\uf8ff]")
_MULTI_SPACE_RE = re.compile(r"[^\S\n\r]{2,}")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_LEADING_DASH_RE = re.compile(r"(?m)^-\s+")
_TRAILING_DASH_RE = re.compile(r"[ \t]+-[ \t]*$", re.MULTILINE)
# Diglot page running header glued into body, e.g. "(Part II.-Citizenship)".
_PART_RUNNING_HEADER_RE = re.compile(
    r"\s*\(Part\s+[IVXLC]+[A-Z]?\s*\.?\s*-\s*[^)]+\)\s*",
    re.IGNORECASE,
)
# Bare Act omission marker in a HEADING, e.g. "THE STATES 1 ***" — the "***"
# stands for words repealed by an amendment and the leading digit is the
# footnote reference that explains which one. Part VI reads that way because
# the Seventh Amendment (1956) dropped "IN PART A OF THE FIRST SCHEDULE" when
# it abolished the Part A/B/C classification of States.
#
# Faithful in a printed Bare Act, meaningless as a title in this app: nobody
# memorises a footnote marker. Only ever applied to headings — an omission
# inside article body text is real Bare Act wording and is left alone.
_HEADING_OMISSION_RE = re.compile(r"\s*\d*\s*\*{2,}\s*$")

# The other half of the same convention: square brackets mark words INSERTED
# by an amendment, again with a leading footnote digit. Part XXII prints
# "SHORT TITLE, COMMENCEMENT, 1 [AUTHORITATIVE TEXT IN HINDI] AND REPEALS"
# because the 58th Amendment (1987) added the bracketed words.
#
# Unlike an omission, the bracketed text IS part of the current heading, so
# only the markers come off — never what they wrap.
_HEADING_INSERT_OPEN_RE = re.compile(r"\s*\d+\s*\[\s*")
_HEADING_INSERT_CLOSE_RE = re.compile(r"\s*\]")

# Headings the extractor truncated rather than merely decorated. A regex
# cannot recover words that are not in the source, so the canonical text is
# supplied. Keyed by part_number; applied only when the extracted title is a
# prefix of the canonical one, so a corrected upstream extraction wins and
# this table quietly stops mattering.
_PART_TITLE_CANONICAL = {
    # Split across a line break after "AND"; the 7th Amendment substituted
    # this heading, hence the "1 [" the extractor also kept.
    "XXI": "TEMPORARY, TRANSITIONAL AND SPECIAL PROVISIONS",
}

_WS_RE = re.compile(r"\s+")
_CLAUSE_ONE_IN_BODY_RE = re.compile(r"(?:^|\n)\(1\)\s")
_CLAUSE_LABEL_RE = re.compile(r"^\((\d+)([A-Za-z]*)\)$")
# Diglot Part III (and similar) subsection titles glued onto article bodies.
_TRAILING_SECTION_HEADER_RE = re.compile(
    r"\s+(?:"
    r"Right to Equality|"
    r"Right to Freedom|"
    r"Right against Exploitation|"
    r"Right to Freedom of Religion|"
    r"Cultural and Educational Rights|"
    r"Saving of Certain Laws|"
    r"Right to Constitutional Remedies"
    r")\s*$",
    re.IGNORECASE,
)


def scrub_display_text(text: str) -> str:
    """
    Remove extraction junk that is not Bare Act wording.

    Does not paraphrase legal text — only drops Docling placeholders,
    private-use glyphs, and collapsed dash/whitespace debris.
    """
    if not text:
        return text
    cleaned = _FORMULA_RE.sub("", text)
    cleaned = _PUA_RE.sub("", cleaned)
    cleaned = _LEADING_DASH_RE.sub("", cleaned)
    cleaned = _TRAILING_DASH_RE.sub("", cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)
    cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
    return cleaned.strip()


def strip_heading_omission_marker(title: str | None) -> str | None:
    """Drop amendment footnote markers from a heading, keeping its words.

    Handles both halves of the convention: "***" for words omitted, and
    "N [ ... ]" for words inserted. The inserted words stay; only the markers
    that point at the footnote come off.
    """
    if not title:
        return title
    cleaned = _HEADING_OMISSION_RE.sub("", title)
    if _HEADING_INSERT_OPEN_RE.search(cleaned):
        cleaned = _HEADING_INSERT_OPEN_RE.sub(" ", cleaned)
        cleaned = _HEADING_INSERT_CLOSE_RE.sub("", cleaned)
    return _norm_ws(cleaned) or title


def canonical_part_title(part_number: str, title: str | None) -> str | None:
    """Restore a heading the extractor cut short.

    Only fires when what was extracted is a prefix of the canonical text, so
    a future clean extraction is left alone rather than overwritten.
    """
    canonical = _PART_TITLE_CANONICAL.get((part_number or "").strip().upper())
    if not canonical:
        return title
    current = _norm_ws(title or "")
    if current == canonical:
        return title
    if current and canonical.startswith(current):
        return canonical
    return title


def strip_part_running_headers(text: str) -> str:
    """Remove diglot Part running headers glued into article text."""
    if not text:
        return text
    cleaned = _PART_RUNNING_HEADER_RE.sub(" ", text)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def _norm_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def fragment_already_present(haystack: str, fragment: str) -> bool:
    """True when fragment (or a long prefix) already appears in haystack."""
    hay = _norm_ws(haystack)
    frag = _norm_ws(fragment)
    if not frag:
        return True
    if not hay:
        return False
    if frag in hay:
        return True
    if len(frag) >= 60 and frag[:80] in hay:
        return True
    return False


def strip_trailing_section_headers(text: str) -> str:
    """Remove subsection titles glued after the last sentence of an article."""
    if not text:
        return text
    cleaned = _TRAILING_SECTION_HEADER_RE.sub("", text).rstrip()
    return cleaned.strip()


def clauses_skip_leading_clause_one(article: Article) -> bool:
    """
    True when body_text includes clause (1) but structured clauses start later.

    Browse/Learn prefer ``article.clauses`` over ``body_text``, so a missing
    ``(1)`` node drops the first clause from display even though it is present
    in the flat body (common Docling/diglot artefact, e.g. Article 18).
    """
    body = article.body_text or ""
    if not article.clauses:
        return False
    if not (
        _CLAUSE_ONE_IN_BODY_RE.search(body) or body.lstrip().startswith("(1)")
    ):
        return False
    saw_later = False
    for clause in article.clauses:
        label = (clause.label or "").strip()
        if label == "(1)":
            return False
        match = _CLAUSE_LABEL_RE.match(label)
        if not match:
            continue
        number = int(match.group(1))
        suffix = match.group(2)
        if number == 1 and suffix:
            saw_later = True
        elif number >= 2:
            saw_later = True
    return saw_later


def _extract_clause_one_text(body: str) -> str | None:
    """Return clause (1) wording from flat body_text, without the '(1)' label."""
    match = re.search(
        r"(?:^|\n)\(1\)\s*(.*?)(?=\n\(\d+[A-Za-z]*\)\s|\Z)",
        body,
        re.S,
    )
    if not match:
        return None
    text = match.group(1).strip()
    return text or None


def _prefer_body_when_clauses_skip_one(article: Article) -> str | None:
    """
    Recover leading clause (1) when structured clauses start at (2)+.

    Prefer the flat body when it already contains the later clauses. Otherwise
    prepend a synthetic (1) node taken from body_text so Browse/Learn keep the
    richer clause tree.
    """
    if not clauses_skip_leading_clause_one(article):
        return None
    clause_chars = 0
    stack = list(article.clauses)
    while stack:
        node = stack.pop()
        clause_chars += len(node.text or "")
        stack.extend(node.children)
    body_chars = len(article.body_text or "")
    if body_chars >= max(40, int(clause_chars * 0.6)):
        article.clauses = []
        return "cleared clauses missing leading (1); prefer body_text"

    clause_one = _extract_clause_one_text(article.body_text or "")
    if not clause_one:
        return None
    article.clauses.insert(
        0,
        ProvisionNode(
            id=f"{article.id}-clause-1",
            label="(1)",
            label_type="numeric",
            text=clause_one,
        ),
    )
    return "prepended clause (1) from body_text onto incomplete clause tree"


def _scrub_provision(node: ProvisionNode) -> bool:
    changed = False
    new_text = scrub_display_text(node.text)
    if new_text != node.text:
        node.text = new_text
        changed = True
    for child in node.children:
        if _scrub_provision(child):
            changed = True
    for index, proviso in enumerate(list(node.provisos)):
        cleaned = scrub_display_text(proviso)
        if cleaned != proviso:
            node.provisos[index] = cleaned
            changed = True
    for index, expl in enumerate(list(node.explanations)):
        cleaned = scrub_display_text(expl)
        if cleaned != expl:
            node.explanations[index] = cleaned
            changed = True
    return changed


def _dedupe_opening_against_body(article: Article) -> str | None:
    """
    Clear opening_text when it duplicates or is a prefix of body_text.

    Browse/Learn concatenate opening + body; duplicate openings cause
    visible repetition across hundreds of Articles.
    """
    opening = article.opening_text.strip()
    body = article.body_text.strip()
    if not opening or not body:
        return None
    if opening == body:
        article.opening_text = ""
        return "cleared opening identical to body"
    if body.startswith(opening):
        article.opening_text = ""
        return "cleared opening that prefixes body"
    if opening.startswith(body) and len(opening) > len(body) + 20:
        article.body_text = article.opening_text
        article.opening_text = ""
        return "moved longer opening into body; cleared opening"
    return None


def _dedupe_list_against_body(
    article: Article,
    field_name: str,
) -> list[str]:
    """
    Drop provisos/explanations already present in body/opening.

    Browse and Learn append these arrays after body_text; when the parser
    also left the same proviso inside body_text, the UI shows it twice.
    """
    notes: list[str] = []
    values: list[str] = getattr(article, field_name)
    if not values:
        return notes
    blob = f"{article.opening_text}\n{article.body_text}"
    kept: list[str] = []
    dropped = 0
    for item in values:
        cleaned = scrub_display_text(item)
        if not cleaned:
            dropped += 1
            continue
        if fragment_already_present(blob, cleaned):
            dropped += 1
            continue
        kept.append(cleaned)
    if dropped or kept != values:
        setattr(article, field_name, kept)
        if dropped:
            notes.append(
                f"{article.id}: dropped {dropped} duplicate/empty {field_name}"
            )
    return notes


def scrub_article(article: Article) -> list[str]:
    """Scrub one article; return human-readable change notes."""
    notes: list[str] = []
    for field in ("opening_text", "body_text"):
        raw = getattr(article, field) or ""
        cleaned = scrub_display_text(raw)
        cleaned = strip_part_running_headers(cleaned)
        if field == "body_text":
            cleaned = strip_trailing_section_headers(cleaned)
        if cleaned != raw:
            setattr(article, field, cleaned)
            notes.append(f"{article.id}: scrubbed {field}")

    if article.title:
        cleaned_title = " ".join(scrub_display_text(article.title).split())
        if cleaned_title != article.title:
            article.title = cleaned_title or None
            notes.append(f"{article.id}: scrubbed title")

    for index, proviso in enumerate(list(article.provisos)):
        cleaned = scrub_display_text(proviso)
        if cleaned != proviso:
            article.provisos[index] = cleaned
            notes.append(f"{article.id}: scrubbed proviso")
    for index, expl in enumerate(list(article.explanations)):
        cleaned = scrub_display_text(expl)
        if cleaned != expl:
            article.explanations[index] = cleaned
            notes.append(f"{article.id}: scrubbed explanation")

    notes.extend(_dedupe_list_against_body(article, "provisos"))
    notes.extend(_dedupe_list_against_body(article, "explanations"))

    for clause in article.clauses:
        if _scrub_provision(clause):
            notes.append(f"{article.id}: scrubbed clause text")

    prefer_body = _prefer_body_when_clauses_skip_one(article)
    if prefer_body:
        notes.append(f"{article.id}: {prefer_body}")

    dedupe = _dedupe_opening_against_body(article)
    if dedupe:
        notes.append(f"{article.id}: {dedupe}")
    return notes


def scrub_document(doc: ConstitutionDocument) -> list[str]:
    """Scrub every article and schedule field in a reviewed document copy."""
    notes: list[str] = []
    for part in doc.parts:
        cleaned_title = canonical_part_title(
            part.part_number, strip_heading_omission_marker(part.title)
        )
        if cleaned_title != part.title:
            notes.append(f"part {part.part_number}: title {part.title!r} -> {cleaned_title!r}")
            part.title = cleaned_title
        for article in part.articles:
            notes.extend(scrub_article(article))
        for chapter in part.chapters:
            for article in chapter.articles:
                notes.extend(scrub_article(article))

    for schedule in doc.schedules:
        for field in ("title", "body_text"):
            raw = getattr(schedule, field) or ""
            if not isinstance(raw, str) or not raw:
                continue
            cleaned = scrub_display_text(raw)
            if field == "title":
                cleaned = " ".join(cleaned.split())
            if cleaned != raw:
                setattr(schedule, field, cleaned)
                notes.append(f"{schedule.id}: scrubbed {field}")
        for section in schedule.sections:
            for field in ("title", "body_text"):
                raw = getattr(section, field) or ""
                if not isinstance(raw, str) or not raw:
                    continue
                cleaned = scrub_display_text(raw)
                if field == "title":
                    cleaned = " ".join(cleaned.split())
                if cleaned != raw:
                    setattr(section, field, cleaned)
                    notes.append(f"{section.id or schedule.id}: scrubbed section {field}")
        for lst in schedule.lists:
            for field in ("name", "body_text"):
                raw = getattr(lst, field) or ""
                if not isinstance(raw, str) or not raw:
                    continue
                cleaned = scrub_display_text(raw)
                if cleaned != raw:
                    setattr(lst, field, cleaned)
                    notes.append(f"{lst.id or schedule.id}: scrubbed list {field}")
            new_items: list[str] = []
            items_changed = False
            for item in lst.items:
                cleaned = scrub_display_text(item)
                new_items.append(cleaned)
                if cleaned != item:
                    items_changed = True
            if items_changed:
                lst.items = new_items
                notes.append(f"{lst.id or schedule.id}: scrubbed list items")
    return notes


def should_include_opening(opening: str, body: str) -> bool:
    """False when opening would duplicate body in concatenated display text."""
    op = opening.strip()
    bd = body.strip()
    if not op:
        return False
    if not bd:
        return True
    if op == bd:
        return False
    if bd.startswith(op):
        return False
    return True
