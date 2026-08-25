"""Guided-random selection of today's new learning units."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.utils.identifiers import parse_article_number
from constitution_memorizer.web.browse import load_browse_chapters_seed
from constitution_memorizer.web.service import unit_visible_for_preference

SCORE_SAME_ARTICLE = 100
SCORE_CURATED_PAIR = 90
SCORE_SAME_CHAPTER = 70
SCORE_SAME_THEME = 70
SCORE_SAME_PART = 40
SCORE_NEARBY_ARTICLE = 20
NEARBY_ARTICLE_SPAN = 3

QUOTAS = {
    3: {"close": 1, "related": 1, "explore": 0},
    5: {"close": 2, "related": 1, "explore": 1},
    7: {"close": 3, "related": 2, "explore": 1},
}

_REL_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "learning_relationships.json"
)

ArticleAllowed = Callable[[str | None], bool]


def _default_allowed(_article: str | None) -> bool:
    return True


def load_relationships(path: Path | None = None) -> dict:
    target = path or _REL_PATH
    if not target.is_file():
        return {"themes": [], "pairs": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _article_key(unit: LearningUnit) -> str:
    raw = (unit.article_number or "").strip()
    parts = parse_article_number(raw) if raw else None
    return parts.article_number if parts is not None else raw


def _article_numeric(unit: LearningUnit) -> int | None:
    parts = parse_article_number(unit.article_number or "") if unit.article_number else None
    return parts.numeric_component if parts is not None else None


def _part_label(unit: LearningUnit) -> str:
    for tag in unit.tags:
        if str(tag).startswith("Part "):
            return str(tag)
    return ""


def _chapter_key(
    unit: LearningUnit, chapters: list[dict]
) -> str:
    numeric = _article_numeric(unit)
    if numeric is None:
        return ""
    suffix = ""
    parts = parse_article_number(unit.article_number or "") if unit.article_number else None
    if parts is not None:
        suffix = parts.suffix
    for row in chapters:
        low = int(row.get("from") or 0)
        high = int(row.get("to") or 0)
        if not (low <= numeric <= high):
            continue
        suffix_min = str(row.get("suffix_min") or "")
        suffix_max = str(row.get("suffix_max") or "")
        if suffix_min or suffix_max:
            if not suffix or suffix < suffix_min or suffix > suffix_max:
                continue
        return f"{row.get('part')}-{row.get('roman')}"
    return ""


def _theme_ids_for_article(article: str, relationships: dict) -> set[str]:
    found: set[str] = set()
    for theme in relationships.get("themes") or []:
        numbers = {str(n).upper() for n in theme.get("article_numbers") or []}
        if article.upper() in numbers:
            found.add(str(theme.get("id") or theme.get("label") or ""))
    return {item for item in found if item}


def _paired_articles(article: str, relationships: dict) -> set[str]:
    found: set[str] = set()
    needle = article.upper()
    for pair in relationships.get("pairs") or []:
        numbers = [str(n).upper() for n in pair.get("articles") or []]
        if needle in numbers:
            found.update(numbers)
    found.discard(needle)
    return found


def eligible_new_units(
    engine: ReminderEngine,
    *,
    article_allowed: ArticleAllowed | None = None,
    exclude_unit_ids: set[str] | None = None,
) -> list[LearningUnit]:
    allowed = article_allowed or _default_allowed
    excluded = exclude_unit_ids or set()
    out: list[LearningUnit] = []
    for unit in engine.units.values():
        if unit.id in excluded:
            continue
        if unit.type == LearningUnitType.PART_OVERVIEW:
            continue
        if not unit_visible_for_preference(engine, unit):
            continue
        if not allowed(unit.article_number):
            continue
        row = engine.get_progress(unit.id)
        if row is not None and (
            row.times_completed > 0 or row.status in ("review", "mastered")
        ):
            continue
        out.append(unit)
    out.sort(key=lambda u: (u.revision_order, u.id))
    return out


def _score(
    candidate: LearningUnit,
    anchor: LearningUnit,
    *,
    relationships: dict,
    chapters: list[dict],
) -> int:
    a_key = _article_key(anchor)
    c_key = _article_key(candidate)
    best = 0
    if a_key and c_key and a_key == c_key:
        best = max(best, SCORE_SAME_ARTICLE)
    if c_key and c_key.upper() in _paired_articles(a_key, relationships):
        best = max(best, SCORE_CURATED_PAIR)
    if _chapter_key(candidate, chapters) and _chapter_key(
        candidate, chapters
    ) == _chapter_key(anchor, chapters):
        best = max(best, SCORE_SAME_CHAPTER)
    a_themes = _theme_ids_for_article(a_key, relationships)
    c_themes = _theme_ids_for_article(c_key, relationships)
    if a_themes and c_themes & a_themes:
        best = max(best, SCORE_SAME_THEME)
    if _part_label(candidate) and _part_label(candidate) == _part_label(anchor):
        best = max(best, SCORE_SAME_PART)
    a_num = _article_numeric(anchor)
    c_num = _article_numeric(candidate)
    if a_num is not None and c_num is not None:
        if 0 < abs(a_num - c_num) <= NEARBY_ARTICLE_SPAN:
            best = max(best, SCORE_NEARBY_ARTICLE)
    return best


def _band(score: int) -> str:
    if score >= SCORE_SAME_CHAPTER:
        return "close"
    if score >= SCORE_NEARBY_ARTICLE:
        return "related"
    return "explore"


def _theme_bucket(unit: LearningUnit, relationships: dict) -> str:
    themes = _theme_ids_for_article(_article_key(unit), relationships)
    if themes:
        return sorted(themes)[0]
    part = _part_label(unit)
    return part or "other"


def select_learning_mix(
    engine: ReminderEngine,
    count: int,
    *,
    rng: random.Random | None = None,
    article_allowed: ArticleAllowed | None = None,
    exclude_unit_ids: Iterable[str] | None = None,
    recent_theme: str | None = None,
    relationships: dict | None = None,
) -> list[LearningUnit]:
    """Pick up to ``count`` eligible units. Same ``rng`` seed is reproducible."""
    rng = rng or random.Random()
    relationships = relationships if relationships is not None else load_relationships()
    chapters = load_browse_chapters_seed()
    pool = eligible_new_units(
        engine,
        article_allowed=article_allowed,
        exclude_unit_ids=set(exclude_unit_ids or ()),
    )
    if not pool or count <= 0:
        return []
    wanted = min(int(count), len(pool))
    quotas = QUOTAS.get(wanted) or QUOTAS.get(min(QUOTAS, key=lambda k: abs(k - wanted)))
    close_n = int((quotas or {}).get("close", 1))
    related_n = int((quotas or {}).get("related", 1))
    explore_n = int((quotas or {}).get("explore", 0))

    by_theme: dict[str, list[LearningUnit]] = defaultdict(list)
    for unit in pool:
        by_theme[_theme_bucket(unit, relationships)].append(unit)
    weights: list[float] = []
    themes = list(by_theme.keys())
    for theme in themes:
        weight = 1.0 / max(1, len(by_theme[theme]) ** 0.25)
        if recent_theme and theme == recent_theme:
            weight *= 0.55
        weights.append(weight)
    theme = rng.choices(themes, weights=weights, k=1)[0]
    anchor = rng.choice(by_theme[theme])

    selected: list[LearningUnit] = [anchor]
    selected_ids = {anchor.id}
    rest = [unit for unit in pool if unit.id != anchor.id]
    scored = [
        (unit, _score(unit, anchor, relationships=relationships, chapters=chapters))
        for unit in rest
    ]

    def take(band: str, n: int) -> None:
        nonlocal scored
        if n <= 0 or len(selected) >= wanted:
            return
        candidates = [pair for pair in scored if _band(pair[1]) == band]
        rng.shuffle(candidates)
        for unit, _score_val in candidates:
            if len(selected) >= wanted:
                break
            if unit.id in selected_ids:
                continue
            selected.append(unit)
            selected_ids.add(unit.id)
            n -= 1
            if n <= 0:
                break
        scored = [pair for pair in scored if pair[0].id not in selected_ids]

    take("close", close_n)
    take("related", related_n)
    take("explore", explore_n)
    # Fallback: fill remaining from whatever is left.
    leftovers = [unit for unit, _s in scored if unit.id not in selected_ids]
    rng.shuffle(leftovers)
    for unit in leftovers:
        if len(selected) >= wanted:
            break
        selected.append(unit)
        selected_ids.add(unit.id)

    tail = selected[1:]
    rng.shuffle(tail)
    ordered = [selected[0], *tail]
    return ordered[:wanted]
