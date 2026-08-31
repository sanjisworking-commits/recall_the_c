"""Article / unit progress aggregates and Progress mastery map (Sprint 5 / 20)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.scheduler import INTERVAL_LADDER, ReminderEngine
from constitution_memorizer.schemas import ConstitutionDocument, Part
from constitution_memorizer.utils.identifiers import article_sort_key
from constitution_memorizer.web.service import continue_unit_id, daily_goal_streak

MasteryState = Literal["new", "learning", "review", "mastered", "due"]

# Parser dump / unclassified buckets. Browse already skips these; the map
# must too or Profile renders one "Part —" grid of Articles 1–395.
_JUNK_PART_NUMBERS = {"", "—", "-", "UNKNOWN", "UNCLASSIFIED"}
# Phone new-user map: Parts I–IV plus any Part that already has activity.
_STARTER_PART_NUMBERS = frozenset({"I", "II", "III", "IV"})


def _is_named_part(part_number: str | None) -> bool:
    return str(part_number or "").strip().upper() not in _JUNK_PART_NUMBERS


def _is_starter_part(part_number: str | None) -> bool:
    return str(part_number or "").strip().upper() in _STARTER_PART_NUMBERS


def _part_has_activity(cells: list[MasteryCell]) -> bool:
    return any(cell.state != "new" for cell in cells)


def _make_part_row(
    *,
    part_number: str,
    part_title: str,
    article_range: str,
    cells: list[MasteryCell],
) -> PartMasteryRow:
    has_activity = _part_has_activity(cells)
    return PartMasteryRow(
        part_number=part_number,
        part_title=part_title,
        article_range=article_range,
        cells=cells,
        has_activity=has_activity,
        compact=has_activity or _is_starter_part(part_number),
    )


def _article_mastery_stamp(
    engine: ReminderEngine, article_number: str
) -> tuple[date | None, int]:
    """Latest completion date and ladder interval for a mastered Article."""
    required, _pending = path_units_for_article(engine, article_number)
    last: date | None = None
    interval = INTERVAL_LADDER[-1]
    for unit in required:
        progress = engine.get_progress(unit.id)
        if progress is None or progress.last_completed is None:
            continue
        if last is None or progress.last_completed > last:
            last = progress.last_completed
            if progress.interval_days > 0:
                interval = progress.interval_days
    return last, interval


def _format_mastered_meta(interval: int, last: date | None) -> str:
    if last is None:
        return f"Day {interval}"
    return f"Day {interval} · {last.day} {last.strftime('%b')}"


@dataclass(frozen=True)
class ArticleProgress:
    article_number: str
    required: int
    completed: int
    percent: float
    pending_choice: bool


@dataclass(frozen=True)
class ProgressStatCard:
    value: str
    label: str


@dataclass(frozen=True)
class MasteryCell:
    article_number: str
    state: MasteryState
    title: str
    href: str | None
    tracked: bool


@dataclass(frozen=True)
class PartMasteryRow:
    part_number: str
    part_title: str
    article_range: str
    cells: list[MasteryCell] = field(default_factory=list)
    has_activity: bool = False
    compact: bool = False


@dataclass(frozen=True)
class PartProgressRow:
    part_number: str
    part_title: str
    done: int
    total: int
    percent: int


@dataclass(frozen=True)
class TrackedArticleRow:
    article_number: str
    title: str
    completed: int
    required: int
    percent: float
    frac: str
    tag: str
    href: str
    pending_choice: bool
    bar_percent: float


def path_units_for_article(
    engine: ReminderEngine,
    article_number: str,
) -> tuple[list[LearningUnit], bool]:
    """
    Units that count toward Article completion under current preferences.

    Returns (units, pending_choice) where pending_choice means a split-capable
    clause still needs whole/letters selection (counted as the parent clause).
    """
    articles_units = [
        u
        for u in engine.units.values()
        if (u.article_number or "").lower() == article_number.lower()
    ]
    required: list[LearningUnit] = []
    pending_choice = False

    for unit in articles_units:
        if unit.type == LearningUnitType.ARTICLE:
            required.append(unit)
            continue
        if unit.type != LearningUnitType.CLAUSE:
            continue
        if unit.allows_letter_split:
            mode = engine.get_split_preference(unit.id)
            if mode is None:
                pending_choice = True
                required.append(unit)
            elif mode == "letters":
                for child_id in unit.child_unit_ids:
                    child = engine.get_unit(child_id)
                    if child is not None:
                        required.append(child)
            else:
                required.append(unit)
        else:
            required.append(unit)

    return required, pending_choice


def _is_completed(engine: ReminderEngine, unit_id: str) -> bool:
    progress = engine.get_progress(unit_id)
    if progress is None:
        return False
    return progress.times_completed > 0 or progress.status in {"review", "mastered"}


def article_progress(
    engine: ReminderEngine,
    article_number: str,
) -> ArticleProgress | None:
    required, pending = path_units_for_article(engine, article_number)
    if not required:
        return None
    completed = sum(1 for u in required if _is_completed(engine, u.id))
    percent = round(100.0 * completed / len(required), 1)
    return ArticleProgress(
        article_number=article_number,
        required=len(required),
        completed=completed,
        percent=percent,
        pending_choice=pending,
    )


def all_article_progress(engine: ReminderEngine) -> list[ArticleProgress]:
    numbers = sorted(
        {u.article_number for u in engine.units.values() if u.article_number},
        key=article_sort_key,
    )
    rows: list[ArticleProgress] = []
    for number in numbers:
        row = article_progress(engine, number)
        if row is not None:
            rows.append(row)
    return rows


def unit_type_totals(engine: ReminderEngine) -> dict[str, int]:
    totals: dict[str, int] = {}
    for unit in engine.units.values():
        key = unit.type.value
        totals[key] = totals.get(key, 0) + 1
    return totals


def _display_part_title(title: str | None) -> str:
    raw = (title or "").strip()
    if not raw:
        return ""
    # Reviewed titles are often ALL CAPS; present in title case.
    if raw.isupper():
        return raw.title()
    return raw


def _article_range_label(numbers: list[str]) -> str:
    if not numbers:
        return "—"
    if len(numbers) == 1:
        return numbers[0]
    return f"{numbers[0]}–{numbers[-1]}"


def _is_on_first_review_rung(engine: ReminderEngine, unit_id: str) -> bool:
    """True when the unit was memorized and is still waiting on the 1-day rung."""
    progress = engine.get_progress(unit_id)
    if progress is None:
        return False
    return (
        progress.status == "review"
        and progress.times_completed > 0
        and progress.interval_days == 1
    )


def article_mastery_state(
    engine: ReminderEngine,
    article_number: str,
    *,
    today: date,
    continue_id: str | None,
) -> MasteryState | None:
    """
    Return mastery state for an article that has learning units, else None.

    Priority (Progress handoff):
    1. mastered — every path unit complete and past the 1-day learning window
    2. learning — every path unit complete but still on the 1-day rung
    3. due — global continue pointer sits in this article
    4. review — some but not all units complete
    5. new — none complete
    """
    del today  # continue pointer is the only due signal for the map
    required, _pending = path_units_for_article(engine, article_number)
    if not required:
        return None

    completed = sum(1 for u in required if _is_completed(engine, u.id))
    cont = engine.get_unit(continue_id) if continue_id else None
    continue_here = (
        cont is not None
        and (cont.article_number or "").lower() == article_number.lower()
    )

    if completed == len(required):
        if all(_is_on_first_review_rung(engine, u.id) for u in required):
            return "learning"
        return "mastered"

    if continue_here:
        return "due"
    if completed > 0:
        return "review"
    return "new"


def article_learn_href(
    engine: ReminderEngine,
    article_number: str,
    *,
    continue_id: str | None = None,
) -> str:
    """Deep-link into Learn/Choose for this article, else Browse."""
    cont = engine.get_unit(continue_id) if continue_id else None
    if cont is not None and (cont.article_number or "").lower() == article_number.lower():
        return f"/learn/{cont.id}"

    required, pending = path_units_for_article(engine, article_number)
    if pending:
        for unit in required:
            if unit.allows_letter_split and engine.get_split_preference(unit.id) is None:
                return f"/learn/{unit.id}/choose"
    for unit in required:
        if not _is_completed(engine, unit.id):
            return f"/learn/{unit.id}"
    if required:
        return f"/learn/{required[0].id}"
    return f"/browse/article/{article_number}"


def _build_mastery_cell(
    engine: ReminderEngine,
    article_number: str,
    *,
    today: date,
    continue_id: str | None,
    article_title: str | None = None,
) -> MasteryCell:
    del article_title  # Tooltip is Article N · state only (Progress handoff)
    state = article_mastery_state(
        engine, article_number, today=today, continue_id=continue_id
    )
    tracked = state is not None
    if state is None:
        state = "new"
    tip = f"Article {article_number} · {state}"
    href = article_learn_href(engine, article_number, continue_id=continue_id) if tracked else None
    return MasteryCell(
        article_number=article_number,
        state=state,
        title=tip,
        href=href,
        tracked=tracked,
    )


def _roman_by_article(engine: ReminderEngine, seed: list[dict]) -> dict[str, str]:
    """Article number → Part roman, using unit tags then seed ranges (same as Browse)."""
    from constitution_memorizer.web.browse import _part_tag_roman, _roman_from_seed

    tagged: dict[str, str] = {}
    numbers: set[str] = set()
    for unit in engine.units.values():
        number = unit.article_number
        if not number:
            continue
        numbers.add(number)
        if number in tagged:
            continue
        for tag in unit.tags:
            roman = _part_tag_roman(tag)
            if roman:
                tagged[number] = roman
                break
    assigned: dict[str, str] = {}
    for number in numbers:
        roman = tagged.get(number) or _roman_from_seed(number, seed)
        if roman and _is_named_part(roman):
            assigned[number] = roman
    return assigned


def _is_unsplit_dump(rows: list[PartMasteryRow], engine: ReminderEngine) -> bool:
    """True when the map is one parser bucket (live 'PART — / Arts 1–395')."""
    named = [row for row in rows if _is_named_part(row.part_number)]
    if not named:
        return True
    if len(named) >= 2:
        return False
    from constitution_memorizer.web.browse import load_browse_parts_seed

    assigned = _roman_by_article(engine, load_browse_parts_seed())
    romans = {
        assigned[cell.article_number]
        for cell in named[0].cells
        if cell.article_number in assigned
    }
    return len(romans) >= 2


def _rows_from_reviewed(
    engine: ReminderEngine,
    reviewed: ConstitutionDocument,
    *,
    today: date,
    continue_id: str | None,
) -> list[PartMasteryRow]:
    rows: list[PartMasteryRow] = []
    for part in reviewed.parts:
        if not _is_named_part(part.part_number):
            continue
        cells: list[MasteryCell] = []
        numbers: list[str] = []
        for article in _part_articles(part):
            numbers.append(article.article_number)
            cells.append(
                _build_mastery_cell(
                    engine,
                    article.article_number,
                    today=today,
                    continue_id=continue_id,
                    article_title=article.title,
                )
            )
        if not cells:
            continue
        rows.append(
            _make_part_row(
                part_number=part.part_number,
                part_title=_display_part_title(part.title),
                article_range=_article_range_label(numbers),
                cells=cells,
            )
        )
    return rows


def _rows_from_units_and_seed(
    engine: ReminderEngine,
    *,
    today: date,
    continue_id: str | None,
) -> list[PartMasteryRow]:
    """One row per Part from learning-unit tags + browse_parts.seed.json ranges."""
    from constitution_memorizer.utils.identifiers import roman_to_int
    from constitution_memorizer.web.browse import load_browse_parts_seed

    seed = load_browse_parts_seed()
    titles = {
        str(row["roman"]).upper(): _display_part_title(str(row.get("title") or ""))
        for row in seed
    }
    assigned = _roman_by_article(engine, seed)
    by_part: dict[str, list[str]] = {}
    for number, roman in assigned.items():
        by_part.setdefault(roman, []).append(number)
    for roman in by_part:
        by_part[roman].sort(key=article_sort_key)

    rows: list[PartMasteryRow] = []
    seen: set[str] = set()
    for row in seed:
        if row.get("repealed"):
            continue
        roman = str(row["roman"]).upper()
        seen.add(roman)
        numbers = by_part.get(roman, [])
        if not numbers:
            continue
        cells = [
            _build_mastery_cell(engine, n, today=today, continue_id=continue_id)
            for n in numbers
        ]
        rows.append(
            _make_part_row(
                part_number=roman,
                part_title=titles.get(roman, ""),
                article_range=_article_range_label(numbers),
                cells=cells,
            )
        )
    extras = [roman for roman in by_part if roman not in seen]
    extras.sort(
        key=lambda roman: (
            roman_to_int(roman) is None,
            roman_to_int(roman) or 99,
            roman,
        )
    )
    for roman in extras:
        numbers = by_part[roman]
        if not numbers:
            continue
        cells = [
            _build_mastery_cell(engine, n, today=today, continue_id=continue_id)
            for n in numbers
        ]
        rows.append(
            _make_part_row(
                part_number=roman,
                part_title=titles.get(roman, ""),
                article_range=_article_range_label(numbers),
                cells=cells,
            )
        )
    return rows


def build_parts_mastery_map(
    engine: ReminderEngine,
    reviewed: ConstitutionDocument | None,
    *,
    today: date,
    continue_id: str | None,
) -> list[PartMasteryRow]:
    """One mastery-map row per Part (desktop and phone share this grouping).

    Reviewed JSON is used only when it is actually split into Parts. A parser
    dump (one 'Part —' / Arts 1–395 grid) falls through to the same Part tags
    and seed ranges Browse uses. Never emit a single catch-all row.
    """
    if reviewed is not None:
        reviewed_rows = _rows_from_reviewed(
            engine, reviewed, today=today, continue_id=continue_id
        )
        if reviewed_rows and not _is_unsplit_dump(reviewed_rows, engine):
            return reviewed_rows
    return _rows_from_units_and_seed(engine, today=today, continue_id=continue_id)


def _part_articles(part: Part) -> list:
    articles = list(part.articles)
    for chapter in part.chapters:
        articles.extend(chapter.articles)
    articles.sort(key=lambda a: article_sort_key(a.article_number))
    return articles


def build_tracked_article_rows(
    engine: ReminderEngine,
    *,
    today: date,
    continue_id: str | None,
) -> list[TrackedArticleRow]:
    """Articles with any completion or a pending split choice."""
    rows: list[TrackedArticleRow] = []
    for prog in all_article_progress(engine):
        # Unset split choice is the default — not a signal the user is tracking.
        if prog.completed <= 0:
            continue
        state = article_mastery_state(
            engine, prog.article_number, today=today, continue_id=continue_id
        ) or "new"
        # Tag priority: mastered · choice pending · due · empty
        if state == "mastered":
            tag = "mastered"
        elif prog.pending_choice:
            tag = "choice pending"
        elif state == "due":
            tag = "due"
        else:
            tag = ""
        rows.append(
            TrackedArticleRow(
                article_number=prog.article_number,
                title=f"Article {prog.article_number}",
                completed=prog.completed,
                required=prog.required,
                percent=prog.percent,
                frac=f"{prog.completed}/{prog.required} · {prog.percent:g}%",
                tag=tag,
                href=article_learn_href(
                    engine, prog.article_number, continue_id=continue_id
                ),
                pending_choice=prog.pending_choice,
                bar_percent=prog.percent,
            )
        )
    return rows


def progress_dashboard(
    engine: ReminderEngine,
    *,
    reviewed: ConstitutionDocument | None = None,
    today: date | None = None,
) -> dict:
    """Bundle stats for the Progress page (Sprint 5 aggregates + Sprint 20 map)."""
    today = today or date.today()
    continue_id = continue_unit_id(engine, as_of=today)
    engine_stats = engine.stats()
    articles = all_article_progress(engine)
    started = [a for a in articles if a.completed > 0]
    complete = [a for a in articles if a.required and a.completed >= a.required]
    avg = (
        round(sum(a.percent for a in articles) / len(articles), 1) if articles else 0.0
    )

    path_units: list[LearningUnit] = []
    seen: set[str] = set()
    for art in articles:
        units, _ = path_units_for_article(engine, art.article_number)
        for unit in units:
            if unit.id not in seen:
                seen.add(unit.id)
                path_units.append(unit)
    tracked_units = len(path_units)
    completed_units = sum(1 for u in path_units if _is_completed(engine, u.id))
    remaining_units = max(0, tracked_units - completed_units)

    parts_map = build_parts_mastery_map(
        engine, reviewed, today=today, continue_id=continue_id
    )
    tracked_rows = build_tracked_article_rows(
        engine, today=today, continue_id=continue_id
    )
    mastered_articles = sum(
        1
        for row in parts_map
        for cell in row.cells
        if cell.tracked and cell.state == "mastered"
    )
    in_progress_articles = sum(
        1
        for row in parts_map
        for cell in row.cells
        if cell.tracked and cell.state in {"learning", "review", "due"}
    )
    part_progress: list[PartProgressRow] = []
    for row in parts_map:
        total = len(row.cells)
        if not total:
            continue
        done = sum(1 for cell in row.cells if cell.state != "new")
        if done <= 0:
            continue
        part_progress.append(
            PartProgressRow(
                part_number=row.part_number,
                part_title=row.part_title,
                done=done,
                total=total,
                percent=round(100 * done / total),
            )
        )

    stat_cards = [
        ProgressStatCard(value=str(tracked_units), label="Tracked units"),
        ProgressStatCard(value=str(completed_units), label="Completed"),
        ProgressStatCard(value=str(mastered_articles), label="Mastered"),
        ProgressStatCard(value=str(remaining_units), label="Remaining"),
    ]
    lede = (
        f"{completed_units} of {tracked_units} units memorized · "
        f"{mastered_articles} article{'s' if mastered_articles != 1 else ''} mastered"
    )

    recently_mastered: list[dict] = []
    for row in parts_map:
        for cell in row.cells:
            if not (cell.tracked and cell.state == "mastered"):
                continue
            last, interval = _article_mastery_stamp(engine, cell.article_number)
            recently_mastered.append(
                {
                    "article_number": cell.article_number,
                    "title": f"Article {cell.article_number}",
                    "href": cell.href,
                    "last_completed": last,
                    "interval": interval,
                    "meta": _format_mastered_meta(interval, last),
                    "subtitle": f"Day {interval} complete",
                }
            )
    recently_mastered.sort(
        key=lambda item: (
            -(item["last_completed"].toordinal() if item["last_completed"] else 0),
            article_sort_key(item["article_number"]),
        )
    )

    return {
        "engine": engine_stats,
        "by_type": unit_type_totals(engine),
        "articles": articles,
        "articles_started": len(started),
        "articles_complete": len(complete),
        "articles_total": len(articles),
        "avg_article_percent": avg,
        "lede": lede,
        "stat_cards": stat_cards,
        "mastered_count": mastered_articles,
        "in_progress_count": in_progress_articles,
        "daily_goal_streak": daily_goal_streak(engine, as_of=today),
        "parts_map": parts_map,
        "part_progress": part_progress,
        "tracked_rows": tracked_rows,
        "continue_id": continue_id,
        "recently_mastered": recently_mastered,
    }
