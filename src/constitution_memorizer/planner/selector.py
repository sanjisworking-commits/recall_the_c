"""Guided-random mix of related learning units for one day's NEW session."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Sequence

from constitution_memorizer.planner.models import (
    TARGET_COMPOSITION,
    MixCandidate,
    normalize_target,
)
from constitution_memorizer.planner.relationships import (
    RECENT_THEME_WEIGHT,
    band_for_score,
    relationship_score,
)

AllowFn = Callable[[MixCandidate, Sequence[MixCandidate]], bool]


def _pick(rng: random.Random, pool: list[MixCandidate]) -> MixCandidate | None:
    if not pool:
        return None
    return pool[rng.randrange(len(pool))]


def _theme_groups(candidates: Sequence[MixCandidate]) -> dict[str, list[MixCandidate]]:
    groups: dict[str, list[MixCandidate]] = defaultdict(list)
    for candidate in candidates:
        groups[candidate.primary_theme].append(candidate)
    return groups


def _choose_anchor(
    candidates: Sequence[MixCandidate],
    rng: random.Random,
    *,
    recent_theme: str | None,
) -> MixCandidate | None:
    groups = _theme_groups(candidates)
    if not groups:
        return None
    themes = list(groups)
    weights = [
        RECENT_THEME_WEIGHT if theme == recent_theme else 1.0
        for theme in themes
    ]
    theme = rng.choices(themes, weights=weights, k=1)[0]
    return _pick(rng, groups[theme])


def _allowed(
    candidate: MixCandidate,
    selected: Sequence[MixCandidate],
    allow: AllowFn | None,
) -> bool:
    if any(item.id == candidate.id for item in selected):
        return False
    if allow is None:
        return True
    return allow(candidate, selected)


def _take_from_band(
    pool: list[MixCandidate],
    count: int,
    selected: list[MixCandidate],
    rng: random.Random,
    allow: AllowFn | None,
) -> list[MixCandidate]:
    chosen: list[MixCandidate] = []
    remaining = [item for item in pool if _allowed(item, selected + chosen, allow)]
    rng.shuffle(remaining)
    for item in remaining:
        if len(chosen) >= count:
            break
        if not _allowed(item, selected + chosen, allow):
            continue
        chosen.append(item)
    return chosen


class LearningMixSelector:
    """Pure mix builder. Callers inject candidates, RNG, and an allow policy."""

    def select(
        self,
        candidates: Sequence[MixCandidate],
        target: int,
        *,
        rng: random.Random | None = None,
        allow: AllowFn | None = None,
        recent_theme: str | None = None,
    ) -> list[MixCandidate]:
        quota = normalize_target(target) or 0
        if quota <= 0 or not candidates:
            return []
        rng = rng or random.Random()
        pool = list(candidates)
        selected: list[MixCandidate] = []

        anchor = _choose_anchor(pool, rng, recent_theme=recent_theme)
        if anchor is None:
            return []
        if _allowed(anchor, selected, allow):
            selected.append(anchor)
        else:
            fallback = [
                item for item in pool if _allowed(item, selected, allow)
            ]
            rng.shuffle(fallback)
            if not fallback:
                return []
            selected.append(fallback[0])
            anchor = selected[0]

        close_n, related_n, explore_n = TARGET_COMPOSITION.get(quota, (1, 1, 0))
        others = [item for item in pool if item.id != anchor.id]
        bands: dict[str, list[MixCandidate]] = {
            "close": [],
            "related": [],
            "explore": [],
        }
        for item in others:
            bands[band_for_score(relationship_score(anchor, item))].append(item)

        selected.extend(_take_from_band(bands["close"], close_n, selected, rng, allow))
        selected.extend(_take_from_band(bands["related"], related_n, selected, rng, allow))
        selected.extend(_take_from_band(bands["explore"], explore_n, selected, rng, allow))

        # Fallback down the bands until the quota is filled or the pool is empty.
        leftovers = [
            item
            for band in ("close", "related", "explore")
            for item in bands[band]
            if _allowed(item, selected, allow)
        ]
        rng.shuffle(leftovers)
        for item in leftovers:
            if len(selected) >= quota:
                break
            if _allowed(item, selected, allow):
                selected.append(item)

        mix = selected[:quota]
        if len(mix) > 1:
            tail = mix[1:]
            rng.shuffle(tail)
            mix = [mix[0], *tail]
        return mix
