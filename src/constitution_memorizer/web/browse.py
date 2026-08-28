"""Browse helpers: Article views from reviewed Bare Act JSON (Sprint 5 / 21)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import re

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.repository import LEARN_MODES
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.schemas import Article, ConstitutionDocument
from constitution_memorizer.utils.identifiers import (
    article_sort_key,
    parse_article_number,
    roman_to_int,
)
from constitution_memorizer.utils.json_io import read_json

_PACKAGE_PARTS_SEED = Path(__file__).resolve().parent / "browse_parts.seed.json"
_REPO_PARTS_SEED = Path(__file__).resolve().parents[3] / "data" / "reference" / "browse_parts.seed.json"
_PACKAGE_CHAPTERS_SEED = Path(__file__).resolve().parent / "browse_chapters.seed.json"
_REPO_CHAPTERS_SEED = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "browse_chapters.seed.json"
)
from constitution_memorizer.web.amendments import (
    Amendment,
    ArticleAmendments,
    get_article_amendments,
)
from constitution_memorizer.web.explainers import has_visual_explainer
from constitution_memorizer.web.progress_stats import path_units_for_article
from constitution_memorizer.web.service import due_checklist

_PART_TAG_RE = re.compile(r"^Part\s+([IVXLCDM]+)$", re.IGNORECASE)


@dataclass
class ArticleBrowseView:
    """Renderable Article for the Browse page."""

    article_number: str
    title: str | None
    part_number: str | None
    status: str
    full_text: str
    learn_units: list[LearningUnit] = field(default_factory=list)
    # None = article not in amendment seed; [] = curated unamended
    amendments: list[Amendment] | None = None
    amendment_meta: str | None = None
    show_unamended: bool = False


@dataclass(frozen=True)
class BrowseMarkSpec:
    """One Browse mark type. Add a key here plus a colour token/class — not a filter branch."""

    key: str
    legend_label: str
    aria_label: str
    title: str


BROWSE_MARKS: tuple[BrowseMarkSpec, ...] = (
    BrowseMarkSpec(
        key="news",
        legend_label="In news",
        aria_label="Show Articles in the news",
        title="In news",
    ),
    BrowseMarkSpec(
        key="visualise",
        legend_label="Visualise",
        aria_label="Show Articles with Visual Explainers",
        title="Visual Explainer available",
    ),
)
BROWSE_MARKS_BY_KEY: dict[str, BrowseMarkSpec] = {m.key: m for m in BROWSE_MARKS}


def marks_for_article(number: str, *, in_news: bool) -> tuple[str, ...]:
    """Ordered mark keys present on this Article (registry order)."""
    keys: list[str] = []
    if in_news:
        keys.append("news")
    if has_visual_explainer(number):
        keys.append("visualise")
    return tuple(keys)


@dataclass(frozen=True)
class BrowseArticleCard:
    article_number: str
    title: str
    href: str
    tracked: bool
    due_count: int = 0
    due_kind: str | None = None  # "due" | "overdue"
    in_news: bool = False
    marks: tuple[str, ...] = ()


def parse_news_articles(raw: str | None) -> set[str]:
    """Parse comma/space-separated article numbers into a normalized set."""
    if not raw:
        return set()
    parts = raw.replace(",", " ").split()
    return {p.strip() for p in parts if p.strip()}


@dataclass(frozen=True)
class BrowseChapterGroup:
    chapter_number: str
    chapter_title: str
    article_range: str
    cards: list[BrowseArticleCard] = field(default_factory=list)


@dataclass(frozen=True)
class BrowsePartSection:
    part_number: str
    part_title: str
    article_range: str
    cards: list[BrowseArticleCard] = field(default_factory=list)
    chapters: list[BrowseChapterGroup] = field(default_factory=list)
    note: str | None = None


def present_browse_marks(sections: list[BrowsePartSection]) -> list[BrowseMarkSpec]:
    """Registry entries that appear on at least one card, in registry order."""
    seen: set[str] = set()
    for section in sections:
        for card in section.cards:
            seen.update(card.marks)
        for chapter in section.chapters:
            for card in chapter.cards:
                seen.update(card.marks)
    return [spec for spec in BROWSE_MARKS if spec.key in seen]


@dataclass(frozen=True)
class ArticleDueSummary:
    due_count: int
    due_kind: str | None


def article_due_summaries(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> dict[str, ArticleDueSummary]:
    """Map article_number → due/overdue unit counts (Home visibility rules)."""
    today = as_of or date.today()
    counts: dict[str, int] = {}
    kinds: dict[str, str] = {}
    for unit in due_checklist(engine, as_of=today):
        number = unit.article_number
        if not number:
            continue
        counts[number] = counts.get(number, 0) + 1
        progress = engine.get_progress(unit.id)
        rev = progress.next_revision if progress is not None else None
        if rev is None:
            continue
        if rev < today:
            kinds[number] = "overdue"
        elif rev == today and kinds.get(number) != "overdue":
            kinds[number] = "due"
    return {
        number: ArticleDueSummary(due_count=count, due_kind=kinds.get(number))
        for number, count in counts.items()
    }


def browse_due_total(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> int:
    """Total Constitution due+overdue units for the Browse nav badge."""
    return len(due_checklist(engine, as_of=as_of))


def load_reviewed_document(path: Path | None) -> ConstitutionDocument | None:
    if path is None or not path.exists():
        return None
    return ConstitutionDocument.model_validate(read_json(path))


def _article_full_text(article: Article) -> str:
    from constitution_memorizer.corrections.artefact_scrub import (  # noqa: PLC0415
        scrub_display_text,
        should_include_opening,
    )

    chunks: list[str] = []
    opening = scrub_display_text(article.opening_text).strip()
    body = scrub_display_text(article.body_text).strip()
    if article.clauses:
        if opening:
            chunks.append(opening)
        for clause in article.clauses:
            head = scrub_display_text(f"{clause.label} {clause.text}").strip()
            if head:
                chunks.append(head)
            for child in clause.children:
                child_head = scrub_display_text(f"{child.label} {child.text}").strip()
                if child_head:
                    chunks.append(child_head)
                for grand in child.children:
                    g = scrub_display_text(f"{grand.label} {grand.text}").strip()
                    if g:
                        chunks.append(g)
    elif body:
        if should_include_opening(opening, body):
            chunks.append(opening)
        chunks.append(body)
    elif opening:
        chunks.append(opening)
    for proviso in article.provisos:
        cleaned = scrub_display_text(proviso)
        if cleaned:
            chunks.append(cleaned)
    for expl in article.explanations:
        cleaned = scrub_display_text(expl)
        if cleaned:
            chunks.append(cleaned)
    return "\n\n".join(c for c in chunks if c).strip()


def iter_articles(doc: ConstitutionDocument) -> list[Article]:
    articles: list[Article] = []
    for part in doc.parts:
        articles.extend(part.articles)
        for chapter in part.chapters:
            articles.extend(chapter.articles)
    articles.sort(key=lambda a: article_sort_key(a.article_number))
    return articles


def list_article_numbers(
    engine: ReminderEngine,
    reviewed: ConstitutionDocument | None,
) -> list[str]:
    if reviewed is not None:
        return [a.article_number for a in iter_articles(reviewed)]
    numbers = sorted(
        {
            u.article_number
            for u in engine.units.values()
            if u.article_number
        },
        key=article_sort_key,
    )
    return numbers


def _short_article_title(title: str | None, *, limit: int = 42) -> str:
    text = (title or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _article_is_tracked(engine: ReminderEngine, article_number: str) -> bool:
    units, pending = path_units_for_article(engine, article_number)
    if pending:
        return True
    for unit in units:
        progress = engine.get_progress(unit.id)
        if progress is None:
            continue
        if progress.times_completed > 0 or progress.status in {"review", "mastered"}:
            return True
    return False


def _part_tag_roman(tag: str) -> str | None:
    match = _PART_TAG_RE.match((tag or "").strip())
    if match is None:
        return None
    return match.group(1).upper()


def _load_seed_rows(candidates: list[Path | None]) -> list[dict]:
    seed_path = next((p for p in candidates if p is not None and p.exists()), None)
    if seed_path is None:
        return []
    data = read_json(seed_path)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def load_browse_parts_seed(path: Path | None = None) -> list[dict]:
    """Load Part roman/title/article-range rows for Browse without reviewed JSON."""
    candidates = [path] if path is not None else [_PACKAGE_PARTS_SEED, _REPO_PARTS_SEED]
    return [row for row in _load_seed_rows(candidates) if row.get("roman")]


def load_browse_chapters_seed(path: Path | None = None) -> list[dict]:
    """Load Chapter roman/title/article-range rows nested under a Part."""
    candidates = [path] if path is not None else [_PACKAGE_CHAPTERS_SEED, _REPO_CHAPTERS_SEED]
    return [
        row
        for row in _load_seed_rows(candidates)
        if row.get("part") and row.get("roman")
    ]


def _suffix_in_band(suffix: str, suffix_min: str | None, suffix_max: str | None) -> bool:
    s = (suffix or "").upper()
    lo = (suffix_min or "").upper()
    hi = (suffix_max or "").upper()
    if suffix_min is not None and s < lo:
        return False
    if suffix_max is not None and s > hi:
        return False
    return True


def _roman_from_seed(article_number: str, seed: list[dict]) -> str | None:
    parts = parse_article_number(article_number)
    if parts is None:
        return None
    num = parts.numeric_component
    suffix = parts.suffix
    for row in seed:
        if row.get("repealed"):
            continue
        start = row.get("from")
        end = row.get("to")
        if start is None or end is None:
            continue
        if not (int(start) <= num <= int(end)):
            continue
        if start == end == 243 or row.get("suffix_min") is not None or row.get(
            "suffix_max"
        ) is not None:
            if not _suffix_in_band(
                suffix, row.get("suffix_min"), row.get("suffix_max")
            ):
                continue
        return str(row["roman"]).upper()
    return None


def _chapter_row_for_article(
    article_number: str,
    part_roman: str,
    seed: list[dict],
) -> dict | None:
    """Return the chapter seed row for an article inside ``part_roman``, if any."""
    parsed = parse_article_number(article_number)
    if parsed is None:
        return None
    part = part_roman.strip().upper()
    numeric_hits: list[dict] = []
    for row in seed:
        if str(row.get("part") or "").strip().upper() != part:
            continue
        start = row.get("from")
        end = row.get("to")
        if start is None or end is None:
            continue
        if not (int(start) <= parsed.numeric_component <= int(end)):
            continue
        numeric_hits.append(row)
    banded: list[dict] = []
    unbanded: list[dict] = []
    for row in numeric_hits:
        has_band = row.get("suffix_min") is not None or row.get("suffix_max") is not None
        if has_band:
            if _suffix_in_band(
                parsed.suffix, row.get("suffix_min"), row.get("suffix_max")
            ):
                banded.append(row)
        else:
            unbanded.append(row)
    if banded:
        return banded[0]
    if unbanded:
        return unbanded[0]
    return None


def _part_titles_from_units(engine: ReminderEngine) -> dict[str, str]:
    """Map Part roman → display title from PART_OVERVIEW unit tags."""
    from constitution_memorizer.web.progress_stats import (  # noqa: PLC0415
        _display_part_title,
    )

    titles: dict[str, str] = {}
    for unit in engine.units.values():
        if unit.type != LearningUnitType.PART_OVERVIEW:
            continue
        roman: str | None = None
        name: str | None = None
        for tag in unit.tags:
            maybe = _part_tag_roman(tag)
            if maybe is not None:
                roman = maybe
                continue
            if name is None and tag.strip():
                name = tag.strip()
        if roman and name and roman not in titles:
            titles[roman] = _display_part_title(name)
    return titles


def _article_labels_from_units(engine: ReminderEngine) -> dict[str, str]:
    """Bare Act heading per article. Prefer ARTICLE units; else any unit.title."""
    labels: dict[str, str] = {}
    for unit in engine.units.values():
        number = unit.article_number
        if not number:
            continue
        short = _short_article_title(unit.title or "")
        if not short:
            continue
        if unit.type == LearningUnitType.ARTICLE:
            labels[number] = short
        elif number not in labels:
            labels[number] = short
    return labels


def browse_parts_from_units(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
    news_articles: set[str] | None = None,
    parts_seed: list[dict] | None = None,
) -> list[BrowsePartSection]:
    """Group Browse cards by Part tags + seed ranges when reviewed JSON is absent."""
    from constitution_memorizer.web.progress_stats import (  # noqa: PLC0415
        _article_range_label,
        _display_part_title,
    )

    dues = article_due_summaries(engine, as_of=as_of)
    if news_articles is None:
        news_articles = parse_news_articles(engine.get_news_articles_raw())
    seed = parts_seed if parts_seed is not None else load_browse_parts_seed()
    titles = {str(row["roman"]).upper(): _display_part_title(str(row.get("title") or "")) for row in seed}
    titles.update(_part_titles_from_units(engine))
    labels = _article_labels_from_units(engine)
    seed_order = {str(row["roman"]).upper(): i for i, row in enumerate(seed)}
    chapter_seed = load_browse_chapters_seed()

    # Prefer explicit Part tags; fall back to article-number seed ranges.
    by_part: dict[str, dict[str, str]] = {}
    for number in list_article_numbers(engine, None):
        roman: str | None = None
        for unit in engine.units.values():
            if unit.article_number != number:
                continue
            for tag in unit.tags:
                roman = _part_tag_roman(tag)
                if roman is not None:
                    break
            if roman is not None:
                break
        if roman is None:
            roman = _roman_from_seed(number, seed)
        if roman is None:
            roman = "—"
        by_part.setdefault(roman, {})[number] = labels.get(number, "")

    def _card(number: str, title: str) -> BrowseArticleCard:
        summary = dues.get(number)
        flagged = number in news_articles
        return BrowseArticleCard(
            article_number=number,
            title=title,
            href=f"/browse/article/{number}",
            tracked=_article_is_tracked(engine, number),
            due_count=summary.due_count if summary else 0,
            due_kind=summary.due_kind if summary else None,
            in_news=flagged,
            marks=marks_for_article(number, in_news=flagged),
        )

    sections: list[BrowsePartSection] = []
    # Emit seed order first (includes repealed Part VII note), then any extras.
    seen: set[str] = set()
    for row in seed:
        roman = str(row["roman"]).upper()
        seen.add(roman)
        arts = by_part.get(roman, {})
        if row.get("repealed"):
            sections.append(
                BrowsePartSection(
                    part_number=roman,
                    part_title=titles.get(roman, _display_part_title(str(row.get("title") or ""))),
                    article_range="—",
                    cards=[],
                    note="Repealed — States in Part B of the First Schedule.",
                )
            )
            continue
        if not arts:
            continue
        numbers = sorted(arts.keys(), key=article_sort_key)
        loose, chapter_groups = _split_cards_by_chapter(
            roman, arts, _card, chapter_seed
        )
        sections.append(
            BrowsePartSection(
                part_number=roman,
                part_title=titles.get(roman, ""),
                article_range=_article_range_label(numbers),
                cards=loose,
                chapters=chapter_groups,
            )
        )

    extras = [r for r in by_part.keys() if r not in seen]
    for roman in sorted(
        extras,
        key=lambda r: (
            r == "—",
            seed_order.get(r, 999),
            roman_to_int(r) is None,
            roman_to_int(r) or 99,
            r,
        ),
    ):
        arts = by_part[roman]
        if not arts:
            continue
        numbers = sorted(arts.keys(), key=article_sort_key)
        title = "Other articles" if roman == "—" else titles.get(roman, "")
        loose, chapter_groups = _split_cards_by_chapter(
            roman, arts, _card, chapter_seed
        )
        sections.append(
            BrowsePartSection(
                part_number=roman,
                part_title=title,
                article_range=_article_range_label(numbers),
                cards=loose,
                chapters=chapter_groups,
            )
        )
    return sections


def _split_cards_by_chapter(
    part_roman: str,
    arts: dict[str, str],
    make_card,
    chapter_seed: list[dict],
) -> tuple[list[BrowseArticleCard], list[BrowseChapterGroup]]:
    """Split a Part's articles into ungrouped cards plus ordered chapter groups."""
    from constitution_memorizer.web.progress_stats import (  # noqa: PLC0415
        _article_range_label,
        _display_part_title,
    )

    ungrouped: dict[str, str] = {}
    by_chapter: dict[str, dict[str, str]] = {}
    meta: dict[str, dict] = {}
    for number, title in arts.items():
        row = _chapter_row_for_article(number, part_roman, chapter_seed)
        if row is None:
            ungrouped[number] = title
            continue
        roman = str(row["roman"]).upper()
        by_chapter.setdefault(roman, {})[number] = title
        meta.setdefault(roman, row)

    loose = [
        make_card(n, ungrouped[n])
        for n in sorted(ungrouped.keys(), key=article_sort_key)
    ]
    order = [
        str(row["roman"]).upper()
        for row in chapter_seed
        if str(row.get("part") or "").upper() == part_roman.upper()
    ]
    groups: list[BrowseChapterGroup] = []
    seen: set[str] = set()
    for roman in order:
        if roman in seen:
            continue
        seen.add(roman)
        grouped = by_chapter.get(roman)
        if not grouped:
            continue
        numbers = sorted(grouped.keys(), key=article_sort_key)
        row = meta.get(roman, {})
        groups.append(
            BrowseChapterGroup(
                chapter_number=roman,
                chapter_title=_display_part_title(str(row.get("title") or "")),
                article_range=_article_range_label(numbers),
                cards=[make_card(n, grouped[n]) for n in numbers],
            )
        )
    return loose, groups


def browse_parts_sections(
    engine: ReminderEngine,
    reviewed: ConstitutionDocument | None,
    *,
    as_of: date | None = None,
    news_articles: set[str] | None = None,
) -> list[BrowsePartSection]:
    """Part-grouped Browse index (Sprint 29) with due/overdue card badges."""
    from constitution_memorizer.web.progress_stats import (  # noqa: PLC0415
        _article_range_label,
        _display_part_title,
        _part_articles,
    )

    dues = article_due_summaries(engine, as_of=as_of)
    if news_articles is None:
        news_articles = parse_news_articles(engine.get_news_articles_raw())

    def _card(number: str, title: str) -> BrowseArticleCard:
        summary = dues.get(number)
        flagged = number in news_articles
        return BrowseArticleCard(
            article_number=number,
            title=title,
            href=f"/browse/article/{number}",
            tracked=_article_is_tracked(engine, number),
            due_count=summary.due_count if summary else 0,
            due_kind=summary.due_kind if summary else None,
            in_news=flagged,
            marks=marks_for_article(number, in_news=flagged),
        )

    sections: list[BrowsePartSection] = []
    if reviewed is None:
        # learning_units.json is tracked; reviewed Bare Act JSON is often local-only.
        return browse_parts_from_units(
            engine, as_of=as_of, news_articles=news_articles
        )

    for part in reviewed.parts:
        if str(part.part_number).upper() in {"UNKNOWN", "—", ""}:
            continue
        articles = _part_articles(part)
        numbers = [a.article_number for a in articles]
        title = _display_part_title(part.title)
        if not articles and "VII" in str(part.part_number).upper():
            sections.append(
                BrowsePartSection(
                    part_number=str(part.part_number),
                    part_title=title,
                    article_range="—",
                    cards=[],
                    note="Repealed — States in Part B of the First Schedule.",
                )
            )
            continue
        if not articles:
            continue
        loose = [
            _card(a.article_number, _short_article_title(a.title))
            for a in part.articles
        ]
        chapter_groups: list[BrowseChapterGroup] = []
        for chapter in part.chapters:
            if not chapter.articles:
                continue
            ch_numbers = [a.article_number for a in chapter.articles]
            chapter_groups.append(
                BrowseChapterGroup(
                    chapter_number=str(chapter.chapter_number),
                    chapter_title=_display_part_title(chapter.title),
                    article_range=_article_range_label(ch_numbers),
                    cards=[
                        _card(a.article_number, _short_article_title(a.title))
                        for a in chapter.articles
                    ],
                )
            )
        sections.append(
            BrowsePartSection(
                part_number=str(part.part_number),
                part_title=title,
                article_range=_article_range_label(numbers),
                cards=loose,
                chapters=chapter_groups,
            )
        )
    return sections


def adjacent_article_numbers(
    engine: ReminderEngine,
    reviewed: ConstitutionDocument | None,
    article_number: str,
) -> tuple[str | None, str | None]:
    """Return (previous, next) article numbers in Browse order."""
    numbers = list_article_numbers(engine, reviewed)
    if not numbers:
        return None, None
    target = article_number.lower()
    for index, number in enumerate(numbers):
        if number.lower() == target:
            prev_n = numbers[index - 1] if index > 0 else None
            next_n = numbers[index + 1] if index + 1 < len(numbers) else None
            return prev_n, next_n
    return None, None


def get_article(
    reviewed: ConstitutionDocument | None,
    article_number: str,
) -> Article | None:
    if reviewed is None:
        return None
    target = article_number.lower()
    for article in iter_articles(reviewed):
        if article.article_number.lower() == target:
            return article
    return None


def learn_units_for_article(
    engine: ReminderEngine,
    article_number: str,
) -> list[LearningUnit]:
    """Chain-level units for the article (clauses/articles; not letter children)."""
    units = [
        u
        for u in engine.units.values()
        if (u.article_number or "").lower() == article_number.lower()
        and u.type != LearningUnitType.SUBCLAUSE
        and (u.revision_order > 0 or u.type == LearningUnitType.ARTICLE)
    ]
    units.sort(key=lambda u: (u.revision_order or 10_000, u.id))
    return units


def _is_unit_memorized(engine: ReminderEngine, unit_id: str) -> bool:
    progress = engine.get_progress(unit_id)
    if progress is None:
        return False
    return progress.times_completed > 0 or progress.status in {"review", "mastered"}


def build_amendment_meta(
    engine: ReminderEngine,
    article_number: str,
    curated: ArticleAmendments | None,
) -> str | None:
    """Meta line under the article title (units · memorized · amendments)."""
    if curated is None:
        return None
    path_units, _ = path_units_for_article(engine, article_number)
    unit_n = len(path_units)
    memorized_n = sum(1 for u in path_units if _is_unit_memorized(engine, u.id))
    unit_label = "1 unit" if unit_n == 1 else f"{unit_n} units"
    mem_label = "1 memorized" if memorized_n == 1 else f"{memorized_n} memorized"
    return (
        f"{unit_label} · {mem_label} · {curated.count_label} — "
        "open any clause below in Learn"
    )


def build_article_view(
    engine: ReminderEngine,
    reviewed: ConstitutionDocument | None,
    article_number: str,
    *,
    amendments_catalog: dict[str, ArticleAmendments] | None = None,
) -> ArticleBrowseView | None:
    article = get_article(reviewed, article_number)
    learn_units = learn_units_for_article(engine, article_number)

    if article is None and not learn_units:
        return None

    curated = get_article_amendments(amendments_catalog or {}, article_number)
    amendments_list: list[Amendment] | None
    show_unamended = False
    if curated is None:
        amendments_list = None
    else:
        amendments_list = list(curated.amendments)
        show_unamended = not curated.has_amendments
    meta = build_amendment_meta(engine, article_number, curated)

    # Prefer tracked Learn units for body text so Browse matches the committed
    # corpus (reviewed JSON is often local/stale). Fall back to reviewed body.
    units_text = "\n\n".join(u.text for u in learn_units if u.text).strip()
    if units_text:
        full_text = units_text
    elif article is not None:
        full_text = _article_full_text(article)
    else:
        full_text = ""

    if article is not None:
        return ArticleBrowseView(
            article_number=article.article_number,
            title=article.title,
            part_number=article.part_number,
            status=article.status.value if hasattr(article.status, "value") else str(article.status),
            full_text=full_text,
            learn_units=learn_units,
            amendments=amendments_list,
            amendment_meta=meta,
            show_unamended=show_unamended,
        )

    return ArticleBrowseView(
        article_number=article_number,
        title=learn_units[0].title if learn_units else None,
        # No reviewed Bare Act to read the Part off — the Part seed that drives
        # Browse knows it, and the phone's back link needs it.
        part_number=_roman_from_seed(article_number, load_browse_parts_seed()),
        status="unknown",
        full_text=full_text,
        learn_units=learn_units,
        amendments=amendments_list,
        amendment_meta=meta,
        show_unamended=show_unamended,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Part drill-down (mobile designs 02 / 03 / 16). The phone browses Part-first,
# so the Parts index needs a progress summary per Part and each Part needs its
# own page; both read the same `browse_parts_sections` view-model.
# ─────────────────────────────────────────────────────────────────────────────

PART_SLUG_TRANSLATION = str.maketrans({" ": "-", ".": "", "/": "-"})


def part_slug(part_number: str) -> str:
    """URL-safe Part token — 'IV A' → 'iv-a'."""
    return str(part_number).strip().lower().translate(PART_SLUG_TRANSLATION)


def part_href(part_number: str) -> str:
    return f"/browse/part/{part_slug(part_number)}"


@dataclass(frozen=True)
class PartProgressSummary:
    learned: int
    total: int
    percent: int
    due_count: int
    label: str
    learned_numbers: tuple[str, ...] = ()


def _section_cards(section: BrowsePartSection) -> list[BrowseArticleCard]:
    cards = list(section.cards)
    for chapter in section.chapters:
        cards.extend(chapter.cards)
    return cards


def part_progress_summary(
    engine: ReminderEngine,
    section: BrowsePartSection,
    *,
    today: date | None = None,
    continue_id: str | None = None,
) -> PartProgressSummary:
    """'3 of 4 learned' + the due count shown on each Part card."""
    from constitution_memorizer.web.progress_stats import (  # noqa: PLC0415
        article_mastery_state,
    )

    today = today or date.today()
    cards = _section_cards(section)
    learned_numbers: list[str] = []
    for card in cards:
        state = article_mastery_state(
            engine, card.article_number, today=today, continue_id=continue_id
        )
        if state in ("mastered", "learning"):
            learned_numbers.append(card.article_number)
    learned = len(learned_numbers)
    total = len(cards)
    percent = int(round(100 * learned / total)) if total else 0
    due_count = sum(card.due_count for card in cards)
    if not total:
        label = "—"
    elif learned == 0:
        label = "Not started"
    else:
        label = f"{learned} of {total} learned"
    return PartProgressSummary(
        learned=learned,
        total=total,
        percent=percent,
        due_count=due_count,
        label=label,
        learned_numbers=tuple(learned_numbers),
    )


def part_title_from_seed(part_number: str | None) -> str | None:
    """Part title by roman numeral, read only from the Part seed.

    Deliberately does not go through ``browse_parts_sections``: the Article
    page must not touch bulk progress just to label its back link, and that
    builder pulls due counts for every Article in the Constitution.
    """
    if not part_number:
        return None
    wanted = str(part_number).strip().upper()
    for row in load_browse_parts_seed():
        if str(row.get("roman", "")).strip().upper() == wanted:
            title = str(row.get("title", "")).strip()
            return title or None
    return None


def find_part_section(
    sections: list[BrowsePartSection],
    slug: str,
) -> BrowsePartSection | None:
    wanted = part_slug(slug)
    for section in sections:
        if part_slug(section.part_number) == wanted:
            return section
    return None


@dataclass(frozen=True)
class ArticlePhoneMeta:
    """The meta line under an Article title on the phone (design 04).

    Reads nothing that costs a database roundtrip. The Article page is the
    busiest authenticated surface and deliberately avoids bulk progress —
    ``build_amendment_meta`` returns early for the same reason — so this line
    carries only the saved marker, the unit count and the amendment link.

    The design also shows "N of 6 modes · revision in N days" here. That needs
    per-unit progress, which on this page means one bulk read; it is left out
    rather than spent silently.
    """

    saved: bool
    unit_count: int
    amendment_count: int

    @property
    def progress_line(self) -> str:
        if not self.unit_count:
            return "Not yet mapped to clauses"
        return f"{self.unit_count} clause{'s' if self.unit_count != 1 else ''} to learn"


def article_phone_meta(
    learn_units: list[LearningUnit],
    *,
    saved: bool = False,
    amendment_count: int = 0,
) -> ArticlePhoneMeta:
    return ArticlePhoneMeta(
        saved=saved,
        unit_count=len(learn_units),
        amendment_count=amendment_count,
    )
