"""Static constitutional relationships plus structural scoring constants."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit
from constitution_memorizer.planner.models import MixCandidate
from constitution_memorizer.utils.identifiers import parse_article_number
from constitution_memorizer.utils.json_io import read_json

SCORE_SAME_ARTICLE = 100
SCORE_CURATED_PAIR = 90
SCORE_SAME_CHAPTER = 70
SCORE_SAME_THEME = 65
SCORE_SAME_PART = 40
SCORE_NEARBY_ARTICLE = 15

CLOSE_THRESHOLD = 60
RELATED_THRESHOLD = 30
NEARBY_ARTICLE_WINDOW = 3
RECENT_THEME_WEIGHT = 0.35

_PART_TAG_RE = re.compile(r"^Part\s+([IVXLCDM]+)$", re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SEED = _REPO_ROOT / "data" / "reference" / "learning_relationships.seed.json"
_PARTS_SEED = _REPO_ROOT / "data" / "reference" / "browse_parts.seed.json"
_CHAPTERS_SEED = _REPO_ROOT / "data" / "reference" / "browse_chapters.seed.json"
_PACKAGE_PARTS = Path(__file__).resolve().parents[1] / "web" / "browse_parts.seed.json"
_PACKAGE_CHAPTERS = Path(__file__).resolve().parents[1] / "web" / "browse_chapters.seed.json"


def _load_json_list(paths: list[Path]) -> list[dict]:
    for path in paths:
        if not path.exists():
            continue
        data = read_json(path)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


@lru_cache(maxsize=1)
def load_relationship_data(path: str | None = None) -> dict:
    candidate = Path(path) if path else _SEED
    if candidate.exists():
        data = read_json(candidate)
        if isinstance(data, dict):
            return data
    return {"version": 1, "themes": [], "pairs": []}


@lru_cache(maxsize=1)
def _article_themes(path: str | None = None) -> dict[str, tuple[str, ...]]:
    data = load_relationship_data(path)
    out: dict[str, list[str]] = {}
    for theme in data.get("themes") or []:
        theme_id = str(theme.get("id") or "").strip()
        if not theme_id:
            continue
        for raw in theme.get("articles") or []:
            key = str(raw).strip()
            if not key:
                continue
            out.setdefault(key, []).append(theme_id)
    return {key: tuple(values) for key, values in out.items()}


@lru_cache(maxsize=1)
def _pair_strengths(path: str | None = None) -> dict[frozenset[str], str]:
    data = load_relationship_data(path)
    out: dict[frozenset[str], str] = {}
    for pair in data.get("pairs") or []:
        articles = [str(a).strip() for a in (pair.get("articles") or []) if str(a).strip()]
        if len(articles) < 2:
            continue
        strength = str(pair.get("strength") or "medium")
        for i, left in enumerate(articles):
            for right in articles[i + 1 :]:
                out[frozenset((left, right))] = strength
    return out


def _part_tag_roman(tag: str) -> str | None:
    match = _PART_TAG_RE.match((tag or "").strip())
    if match is None:
        return None
    return match.group(1).upper()


def _suffix_in_band(suffix: str, suffix_min: str | None, suffix_max: str | None) -> bool:
    value = (suffix or "").upper()
    low = (suffix_min or "").upper()
    high = (suffix_max or "").upper()
    if suffix_min is not None and value < low:
        return False
    if suffix_max is not None and value > high:
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
            if not _suffix_in_band(suffix, row.get("suffix_min"), row.get("suffix_max")):
                continue
        return str(row["roman"]).upper()
    return None


def _chapter_key(article_number: str | None) -> str | None:
    if not article_number:
        return None
    parts_seed = _load_json_list([_PARTS_SEED, _PACKAGE_PARTS])
    part_roman = _roman_from_seed(article_number, parts_seed)
    if not part_roman:
        return None
    parsed = parse_article_number(article_number)
    if parsed is None:
        return None
    chapters = _load_json_list([_CHAPTERS_SEED, _PACKAGE_CHAPTERS])
    numeric_hits: list[dict] = []
    for row in chapters:
        if str(row.get("part") or "").strip().upper() != part_roman:
            continue
        start = row.get("from")
        end = row.get("to")
        if start is None or end is None:
            continue
        if int(start) <= parsed.numeric_component <= int(end):
            numeric_hits.append(row)
    banded = [
        row
        for row in numeric_hits
        if (row.get("suffix_min") is not None or row.get("suffix_max") is not None)
        and _suffix_in_band(parsed.suffix, row.get("suffix_min"), row.get("suffix_max"))
    ]
    if banded:
        row = banded[0]
        return f"{row.get('part')}-{row.get('roman')}"
    unbanded = [
        row
        for row in numeric_hits
        if row.get("suffix_min") is None and row.get("suffix_max") is None
    ]
    if unbanded:
        row = unbanded[0]
        return f"{row.get('part')}-{row.get('roman')}"
    return None


def _part_for_unit(unit: LearningUnit) -> str | None:
    for tag in unit.tags:
        roman = _part_tag_roman(tag)
        if roman:
            return roman
    if unit.article_number:
        return _roman_from_seed(
            unit.article_number, _load_json_list([_PARTS_SEED, _PACKAGE_PARTS])
        )
    return None


def build_candidate(unit: LearningUnit) -> MixCandidate:
    article = unit.article_number
    parsed = parse_article_number(article) if article else None
    themes = _article_themes().get(article or "", ())
    return MixCandidate(
        unit=unit,
        article_number=article,
        part=_part_for_unit(unit),
        chapter=_chapter_key(article),
        themes=themes,
        article_numeric=parsed.numeric_component if parsed else None,
    )


def relationship_score(anchor: MixCandidate, other: MixCandidate) -> int:
    if anchor.id == other.id:
        return 0
    score = 0
    if (
        anchor.article_number
        and other.article_number
        and anchor.article_number == other.article_number
    ):
        score = max(score, SCORE_SAME_ARTICLE)
    if anchor.article_number and other.article_number:
        pair = frozenset((anchor.article_number, other.article_number))
        strength = _pair_strengths().get(pair)
        if strength == "strong":
            score = max(score, SCORE_CURATED_PAIR)
        elif strength == "medium":
            score = max(score, SCORE_SAME_THEME)
    if anchor.chapter and other.chapter and anchor.chapter == other.chapter:
        score = max(score, SCORE_SAME_CHAPTER)
    if set(anchor.themes) & set(other.themes):
        score = max(score, SCORE_SAME_THEME)
    if anchor.part and other.part and anchor.part == other.part:
        score = max(score, SCORE_SAME_PART)
    if (
        anchor.article_numeric is not None
        and other.article_numeric is not None
        and abs(anchor.article_numeric - other.article_numeric) <= NEARBY_ARTICLE_WINDOW
    ):
        score = max(score, SCORE_NEARBY_ARTICLE)
    return score


def band_for_score(score: int) -> str:
    if score >= CLOSE_THRESHOLD:
        return "close"
    if score >= RELATED_THRESHOLD:
        return "related"
    return "explore"


def candidates_from_units(units) -> list[MixCandidate]:
    return [build_candidate(unit) for unit in units]
