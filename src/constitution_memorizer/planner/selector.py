"""One day's NEW mix: an anchor, then units of decreasing familiarity.

Composition is fixed by TARGET_COMPOSITION — Steady 3 is anchor + close +
related, Balanced 5 adds a second close and one explore, Intensive 7 adds a
third close and a second related. The point of the gradient is
familiarity -> association -> novelty, so a short day stays cohesive and a long
one never becomes a scattergun.

Which bucket a unit falls in is *curated data*, read from the relationship
graph. This module does not decide whether two provisions are conceptually
close; it only composes a day out of buckets the curriculum already assigned.
Where the graph has nothing to say, a clearly-tagged legacy heuristic fills in
until curation catches up — but a curated candidate is always preferred to a
legacy one, so "graph-first" means the curated pools are drained first, not
merely that curated classifications win for the same pair.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from constitution_memorizer.planner.graph import (
    CuratedRelationshipGraph,
    curated_graph,
)
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

BUCKET_ORDER = ("close", "related", "explore")

# Which buckets may stand in for a slot, most familiar substitute first. An
# unfilled Close slot reaches for Related before it ever reaches for Explore.
# Each rung is tried curated-then-legacy, so the bucket the slot asked for
# always outranks where the classification came from.
FALLBACK_LADDER: dict[str, tuple[str, ...]] = {
    "close": ("close", "related", "explore"),
    "related": ("related", "close", "explore"),
    "explore": ("explore", "related", "close"),
}


@dataclass(frozen=True)
class MixPick:
    """One chosen unit, and an honest account of why it is here.

    ``requested_bucket`` is the slot being filled; ``effective_bucket`` is what
    the unit actually is. They differ whenever a ladder rung was descended, and
    the difference is never papered over — a Related unit filling a Close slot
    is reported as Related.
    """

    candidate: MixCandidate
    requested_bucket: str | None
    curated_bucket: str | None = None
    effective_bucket: str | None = None
    relation_type: str | None = None
    relation_source: str | None = None

    @property
    def id(self) -> str:
        return self.candidate.id

    @property
    def is_legacy(self) -> bool:
        return self.relation_source == "legacy_fallback"


@dataclass(frozen=True)
class MixSelection:
    picks: tuple[MixPick, ...]

    @property
    def units(self) -> list[MixCandidate]:
        return [pick.candidate for pick in self.picks]

    @property
    def ids(self) -> list[str]:
        return [pick.candidate.id for pick in self.picks]

    @property
    def anchor(self) -> MixCandidate | None:
        return self.picks[0].candidate if self.picks else None

    @property
    def legacy_count(self) -> int:
        """How far this day had to lean on uncurated relationships."""
        return sum(1 for pick in self.picks if pick.is_legacy)

    def bucket_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for pick in self.picks[1:]:
            counts[pick.effective_bucket or "unclassified"] += 1
        return dict(counts)


def recency_key(
    candidate: MixCandidate, graph: CuratedRelationshipGraph | None = None
) -> str:
    """The identity anchor-recency is measured against.

    Curated cluster first. The remaining rungs matter: without them every
    uncurated unit would share one "unclassified" key, and downweighting that
    key would suppress a third of the corpus at once.
    """
    graph = graph or curated_graph()
    unit_id, article = candidate.id, candidate.article_number
    return (
        graph.primary_cluster_for(unit_id, article)
        or graph.primary_family_for(unit_id, article)
        or candidate.primary_theme
        or article
        or unit_id
    )


def _pick(rng: random.Random, pool: list[MixCandidate]) -> MixCandidate | None:
    if not pool:
        return None
    return pool[rng.randrange(len(pool))]


def _anchor_groups(
    candidates: Sequence[MixCandidate], graph: CuratedRelationshipGraph
) -> dict[str, list[MixCandidate]]:
    groups: dict[str, list[MixCandidate]] = defaultdict(list)
    for candidate in candidates:
        meta = graph.metadata_for(candidate.id, candidate.article_number)
        if not meta.anchor_eligible:
            continue
        groups[recency_key(candidate, graph)].append(candidate)
    return groups


def _choose_anchor(
    candidates: Sequence[MixCandidate],
    rng: random.Random,
    *,
    recent_theme: str | None,
    graph: CuratedRelationshipGraph,
) -> MixCandidate | None:
    """Weighted-random anchor: recent cluster downweighted, never banned.

    Groups are chosen uniformly (bar the recency downweight) so a 146-unit
    cluster does not crowd out a 2-unit one; anchor_weight then decides within
    the chosen group.
    """
    groups = _anchor_groups(candidates, graph)
    if not groups:
        # Every candidate opted out of anchoring: fall back to the whole pool
        # rather than returning no day at all.
        groups = defaultdict(list)
        for candidate in candidates:
            groups[recency_key(candidate, graph)].append(candidate)
    if not groups:
        return None
    keys = list(groups)
    weights = [
        RECENT_THEME_WEIGHT if key == recent_theme else 1.0 for key in keys
    ]
    key = rng.choices(keys, weights=weights, k=1)[0]
    pool = groups[key]
    unit_weights = [
        max(
            0.0,
            graph.metadata_for(c.id, c.article_number).anchor_weight,
        )
        for c in pool
    ]
    if any(weight > 0 for weight in unit_weights):
        return rng.choices(pool, weights=unit_weights, k=1)[0]
    return _pick(rng, pool)


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


def classify(
    anchor: MixCandidate,
    other: MixCandidate,
    *,
    graph: CuratedRelationshipGraph,
    use_legacy_fallback: bool = True,
) -> MixPick:
    """Where ``other`` stands relative to ``anchor``, and on whose authority."""
    relation = graph.bucket_for(
        anchor.id, other.id, anchor.article_number, other.article_number
    )
    if relation.is_classified:
        return MixPick(
            candidate=other,
            requested_bucket=None,
            curated_bucket=relation.bucket,
            effective_bucket=relation.bucket,
            relation_type=relation.relation_type,
            relation_source=relation.source,
        )
    if not use_legacy_fallback:
        return MixPick(
            candidate=other,
            requested_bucket=None,
            curated_bucket=None,
            effective_bucket=None,
            relation_source="unclassified",
        )
    # No curated relationship. The legacy scorer always answers — even for a
    # pair with nothing in common, which it calls Explore — so this is kept in
    # its own pools and drained only after every curated pool is empty.
    return MixPick(
        candidate=other,
        requested_bucket=None,
        curated_bucket=None,
        effective_bucket=band_for_score(relationship_score(anchor, other)),
        relation_source="legacy_fallback",
    )


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
        committed: Sequence[MixCandidate] = (),
        graph: CuratedRelationshipGraph | None = None,
        use_legacy_fallback: bool = True,
    ) -> list[MixCandidate]:
        return self.select_detailed(
            candidates,
            target,
            rng=rng,
            allow=allow,
            recent_theme=recent_theme,
            committed=committed,
            graph=graph,
            use_legacy_fallback=use_legacy_fallback,
        ).units

    def select_detailed(
        self,
        candidates: Sequence[MixCandidate],
        target: int,
        *,
        rng: random.Random | None = None,
        allow: AllowFn | None = None,
        recent_theme: str | None = None,
        committed: Sequence[MixCandidate] = (),
        graph: CuratedRelationshipGraph | None = None,
        use_legacy_fallback: bool = True,
    ) -> MixSelection:
        """Compose one day.

        ``committed`` is work already owed to the learner, in commitment order.
        Its first item anchors the day — no recency roll, because the day is
        not free to choose. Every committed unit counts against the bucket
        quotas by its *actual* relationship to that anchor, so a carryover that
        already supplies the Related and Explore slots leaves only Close to
        fill. Committed units are assumed pre-validated: the caller checks them
        against eligibility and the entitlement policy before handing them over,
        because dropping owed work at this point would silently lose it.
        """
        quota = normalize_target(target) or 0
        if quota <= 0:
            return MixSelection(picks=())
        rng = rng or random.Random()
        graph = graph or curated_graph()

        picks: list[MixPick] = []
        selected: list[MixCandidate] = []

        for item in committed:
            if len(selected) >= quota:
                break
            if any(existing.id == item.id for existing in selected):
                continue
            selected.append(item)
            picks.append(MixPick(candidate=item, requested_bucket=None))

        if selected:
            anchor = selected[0]
        else:
            if not candidates:
                return MixSelection(picks=())
            anchor = _choose_anchor(
                list(candidates), rng, recent_theme=recent_theme, graph=graph
            )
            if anchor is None:
                return MixSelection(picks=())
            if not _allowed(anchor, selected, allow):
                fallback = [
                    item for item in candidates if _allowed(item, selected, allow)
                ]
                rng.shuffle(fallback)
                if not fallback:
                    return MixSelection(picks=())
                anchor = fallback[0]
            selected.append(anchor)
            picks.append(MixPick(candidate=anchor, requested_bucket=None))

        picks[0] = MixPick(
            candidate=anchor, requested_bucket="anchor", relation_source="anchor"
        )

        close_n, related_n, explore_n = TARGET_COMPOSITION.get(quota, (1, 1, 0))
        need = {"close": close_n, "related": related_n, "explore": explore_n}

        # Carryover after the anchor already supplies some of the composition.
        for index, item in enumerate(selected[1:], start=1):
            pick = classify(
                anchor,
                item,
                graph=graph,
                use_legacy_fallback=use_legacy_fallback,
            )
            picks[index] = MixPick(
                candidate=item,
                requested_bucket="committed",
                curated_bucket=pick.curated_bucket,
                effective_bucket=pick.effective_bucket,
                relation_type=pick.relation_type,
                relation_source=pick.relation_source,
            )
            bucket = pick.effective_bucket
            if bucket in need:
                need[bucket] = max(0, need[bucket] - 1)

        # Two pools, kept apart on purpose: a curated Related beats a legacy
        # Close, because the whole point is to prefer curated candidates rather
        # than merely to prefer curated labels for the same pair.
        curated: dict[str, list[MixCandidate]] = {b: [] for b in BUCKET_ORDER}
        legacy: dict[str, list[MixCandidate]] = {b: [] for b in BUCKET_ORDER}
        unclassified: list[MixCandidate] = []
        detail: dict[str, MixPick] = {}
        for item in candidates:
            if item.id == anchor.id:
                continue
            pick = classify(
                anchor,
                item,
                graph=graph,
                use_legacy_fallback=use_legacy_fallback,
            )
            detail[item.id] = pick
            if pick.curated_bucket:
                curated[pick.curated_bucket].append(item)
            elif pick.effective_bucket:
                legacy[pick.effective_bucket].append(item)
            else:
                unclassified.append(item)

        def draw(slot: str, count: int) -> None:
            # Bucket first, source second. The requested bucket is the product
            # invariant — a Related slot filled by a legacy Related is closer
            # to what was asked for than one filled by a curated Close. Source
            # only breaks ties *within* a bucket. Ordering these the other way
            # round collapsed a curated anchor's whole day into Close, because
            # curated Close outranked every legacy Related and Explore.
            for rung in FALLBACK_LADDER[slot]:
                for pool in (curated[rung], legacy[rung]):
                    if count <= 0 or len(selected) >= quota:
                        return
                    taken = _take_from_band(pool, count, selected, rng, allow)
                    for item in taken:
                        picks.append(_record(detail[item.id], slot))
                        selected.append(item)
                    count -= len(taken)
            if count > 0 and len(selected) < quota:
                taken = _take_from_band(unclassified, count, selected, rng, allow)
                for item in taken:
                    picks.append(_record(detail[item.id], slot))
                    selected.append(item)

        for slot in BUCKET_ORDER:
            draw(slot, need[slot])

        # Short of quota with quotas satisfied: top up rather than hand back a
        # thin day, still preferring curated candidates.
        if len(selected) < quota:
            draw("close", quota - len(selected))

        picks = picks[:quota]
        # The anchor holds position 0 — the session opens there, and Auto's
        # persisted day records it as the day's anchor. The committed prefix
        # keeps its commitment order; only freshly chosen units are shuffled,
        # so the day does not always read close, close, related, explore.
        head = max(1, len(committed))
        tail = picks[head:]
        rng.shuffle(tail)
        return MixSelection(picks=tuple([*picks[:head], *tail]))


def _record(pick: MixPick, slot: str) -> MixPick:
    return MixPick(
        candidate=pick.candidate,
        requested_bucket=slot,
        curated_bucket=pick.curated_bucket,
        effective_bucket=pick.effective_bucket,
        relation_type=pick.relation_type,
        relation_source=pick.relation_source,
    )
