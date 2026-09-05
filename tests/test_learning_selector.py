"""LearningMixSelector is a pure function over an injected candidate set."""

from __future__ import annotations

import random

import pytest
from datetime import date
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.eligibility import article_slot_policy, eligible_candidates
from constitution_memorizer.planner.models import MixCandidate
from constitution_memorizer.planner.selector import LearningMixSelector
from constitution_memorizer.progress.scheduler import ReminderEngine


def _unit(unit_id: str, article: str, order: int, *, part: str = "III") -> LearningUnit:
    return LearningUnit(
        id=unit_id,
        type=LearningUnitType.CLAUSE,
        article_number=article,
        display_title=f"Article {article}",
        text=f"Text for {unit_id}",
        estimated_learning_time=60,
        revision_order=order,
        tags=[f"Part {part}"],
    )


def _candidate(unit: LearningUnit, *themes: str) -> MixCandidate:
    numeric = None
    if unit.article_number and unit.article_number.isdigit():
        numeric = int(unit.article_number)
    return MixCandidate(
        unit=unit,
        article_number=unit.article_number,
        part="III",
        chapter=None,
        themes=themes,
        article_numeric=numeric,
    )


def test_selector_is_seeded_and_fills_the_target():
    units = [_unit(f"u{i}", str(14 + i), i) for i in range(8)]
    candidates = [_candidate(unit, "equality") for unit in units]
    first = LearningMixSelector().select(candidates, 5, rng=random.Random(7))
    second = LearningMixSelector().select(candidates, 5, rng=random.Random(7))
    assert [item.id for item in first] == [item.id for item in second]
    assert len(first) == 5
    other = LearningMixSelector().select(candidates, 5, rng=random.Random(99))
    assert {item.id for item in first} != {item.id for item in other} or first[0].id != other[0].id


def test_free_plan_my_day_respects_remaining_article_claim_slots(tmp_path: Path):
    units = [
        _unit("claimed-a", "14", 1),
        _unit("claimed-b", "14", 2),
        _unit("open-15", "15", 3),
        _unit("open-15b", "15", 4),
        _unit("open-16", "16", 5),
        _unit("open-19", "19", 6),
        _unit("open-21", "21", 7),
    ]
    engine = ReminderEngine.from_units(tmp_path / "progress.db", units)
    today = date(2026, 8, 1)
    candidates = eligible_candidates(
        engine,
        as_of=today,
        claimed={"14"},
        remaining_slots=1,
        entitlements_on=True,
    )
    allow = article_slot_policy(
        claimed={"14"}, remaining_slots=1, entitlements_on=True
    )
    mix = LearningMixSelector().select(candidates, 5, rng=random.Random(3), allow=allow)
    introduced = {
        item.article_number
        for item in mix
        if item.article_number and item.article_number not in {"14"}
    }
    assert len(introduced) <= 1
    assert mix
    at_cap = article_slot_policy(
        claimed={"14"}, remaining_slots=0, entitlements_on=True
    )
    capped = LearningMixSelector().select(
        candidates, 5, rng=random.Random(3), allow=at_cap
    )
    assert capped
    assert all(item.article_number == "14" for item in capped)


def test_selector_has_no_request_parameter():
    import inspect

    params = inspect.signature(LearningMixSelector.select).parameters
    assert "request" not in params
    assert "candidates" in params


def test_full_access_mix_ignores_free_article_slot_cap(tmp_path: Path):
    units = [
        _unit("claimed-a", "14", 1),
        _unit("open-15", "15", 2),
        _unit("open-16", "16", 3),
        _unit("open-19", "19", 4),
        _unit("open-21", "21", 5),
        _unit("open-32", "32", 6),
    ]
    engine = ReminderEngine.from_units(tmp_path / "progress.db", units)
    today = date(2026, 8, 1)
    capped = eligible_candidates(
        engine,
        as_of=today,
        claimed={"14", "15", "16"},
        remaining_slots=0,
        entitlements_on=True,
    )
    assert {item.article_number for item in capped} <= {"14", "15", "16"}
    open_pool = eligible_candidates(
        engine,
        as_of=today,
        claimed=set(),
        remaining_slots=None,
        entitlements_on=False,
    )
    assert {item.article_number for item in open_pool} >= {"14", "15", "16", "19", "21", "32"}


def test_unresolved_split_capable_units_are_excluded_from_mixes(tmp_path: Path):
    from constitution_memorizer.web.service import select_today_mix

    units = [
        _unit("plain", "14", 1),
        LearningUnit(
            id="split-parent",
            type=LearningUnitType.CLAUSE,
            article_number="15",
            display_title="Article 15",
            text="Split parent",
            estimated_learning_time=60,
            revision_order=2,
            tags=["Part III"],
            allows_letter_split=True,
            child_unit_ids=["split-a", "split-b"],
        ),
        LearningUnit(
            id="split-a",
            type=LearningUnitType.SUBCLAUSE,
            article_number="15",
            display_title="Article 15(a)",
            text="(a)",
            estimated_learning_time=30,
            revision_order=0,
            tags=["Part III"],
            parent_clause_id="split-parent",
        ),
        _unit("plain-2", "16", 3),
    ]
    engine = ReminderEngine.from_units(tmp_path / "progress.db", units)
    today = date(2026, 8, 1)
    assert "split-parent" not in select_today_mix(engine, target=5, as_of=today)
    engine.set_split_preference("split-parent", "whole")
    assert "split-parent" in select_today_mix(engine, target=5, as_of=today)


# ── Recall Mix composition, from the curated graph ──────────────────────────
#
# Composition is the product promise: Steady stays cohesive, Intensive widens
# without becoming a scattergun. These build their own graph so the bucket of
# every candidate is visible in the test source rather than inferred from the
# shipped curriculum.

from constitution_memorizer.planner.graph import CuratedRelationshipGraph  # noqa: E402
from constitution_memorizer.planner.selector import recency_key  # noqa: E402

_ANCHOR = "100"
_CLOSE = ["101", "102", "103", "104"]
_RELATED = ["201", "202", "203"]
_EXPLORE = ["301", "302", "303"]
_STRANGER = ["401", "402", "403"]


def _test_graph() -> CuratedRelationshipGraph:
    meta = {_ANCHOR: {"primary_cluster": "equality", "clusters": ["equality"]}}
    for article in _CLOSE:
        meta[article] = {"primary_cluster": "equality", "clusters": ["equality"]}
    for article in _RELATED:
        meta[article] = {"primary_cluster": "liberty", "clusters": ["liberty"]}
    for article in _EXPLORE:
        meta[article] = {"primary_cluster": "money", "clusters": ["money"]}
    for article in _STRANGER:
        meta[article] = {"primary_cluster": "orphan", "clusters": ["orphan"]}
    return CuratedRelationshipGraph(
        {
            "families": {"rights": {"label": "Rights"}},
            "clusters": {
                "equality": {
                    "family": "rights",
                    "same_cluster_bucket": "close",
                    "related_clusters": ["liberty"],
                    "explore_clusters": ["money"],
                },
                "liberty": {"family": "rights"},
                "money": {"family": None},
                "orphan": {"family": None},
            },
            "article_metadata": meta,
            "unit_metadata": {},
            "article_edges": [],
            "unit_edges": [],
        }
    )


def _c(article: str) -> MixCandidate:
    return _candidate(_unit(f"article-{article}", article, int(article)))


def _buckets(selection) -> dict[str, int]:
    return selection.bucket_counts()


def _select(candidates, target, seed=1, **kwargs):
    kwargs.setdefault("graph", _test_graph())
    return LearningMixSelector().select_detailed(
        candidates, target, rng=random.Random(seed), **kwargs
    )


def _pool(articles=None):
    articles = articles or (_CLOSE + _RELATED + _EXPLORE)
    return [_c(_ANCHOR), *[_c(a) for a in articles]]


@pytest.mark.parametrize(
    "target, expected",
    [
        (3, {"close": 1, "related": 1}),
        (5, {"close": 2, "related": 1, "explore": 1}),
        (7, {"close": 3, "related": 2, "explore": 1}),
    ],
)
def test_composition_is_exact_for_each_target(target, expected):
    """Steady 3 deliberately has no Explore; Intensive 7 has exactly one."""
    selection = _select(_pool(), target, committed=[_c(_ANCHOR)])
    assert len(selection.picks) == target
    assert selection.anchor.id == f"article-{_ANCHOR}"
    assert _buckets(selection) == expected


def test_close_slot_reaches_for_related_before_explore():
    """The gradient is the point: a missing Close falls to Related, not novelty.

    Swept across seeds because the bug this replaces was a shuffle — a single
    seed would have passed against it.
    """
    pool = [_c(_ANCHOR), *[_c(a) for a in _RELATED], *[_c(a) for a in _EXPLORE]]
    for seed in range(60):
        selection = _select(pool, 5, seed=seed, committed=[_c(_ANCHOR)])
        counts = _buckets(selection)
        # Wants 2 close + 1 related + 1 explore; no close exists, so the two
        # close slots draw Related first and only then Explore.
        assert counts.get("related", 0) == 3, (seed, counts)
        assert counts.get("explore", 0) == 1, (seed, counts)


def test_curated_beats_legacy_within_the_same_bucket():
    """Source breaks ties inside a bucket; it never outranks the bucket itself.

    A Close slot offered a curated Close and a legacy Close takes the curated
    one. What it must NOT do is take a curated *Related* over a legacy Close —
    that is the ordering fixed in test_requested_bucket_outranks_curation.
    """
    curated_close = _c(_CLOSE[0])
    anchor = _candidate(_unit(f"article-{_ANCHOR}", _ANCHOR, 100), "equality")
    legacy_close = _candidate(_unit("article-900", "900", 900), "equality")
    pool = [anchor, legacy_close, curated_close]
    for seed in range(40):
        selection = _select(pool, 3, seed=seed, committed=[anchor])
        # By slot, not by position: the tail is shuffled on purpose so a day
        # does not always read close, close, related, explore.
        close_pick = next(
            p for p in selection.picks[1:] if p.requested_bucket == "close"
        )
        assert close_pick.candidate.id == curated_close.id, seed
        assert close_pick.relation_source == "same_cluster", seed


def test_requested_bucket_outranks_curation():
    """The 3/5/7 gradient is the product invariant, not the data's provenance.

    Ordering source before bucket collapsed a curated anchor's whole day into
    Close: with no curated Related or Explore pool, both of those slots
    preferred a curated Close to any legacy candidate, and Balanced lost its
    association and novelty entirely. A legacy Related is closer to what a
    Related slot asked for than a curated Close is.
    """
    # Article 900 is absent from the curated graph but shares a legacy theme
    # with the anchor, which the old scorer reads as 65 — i.e. Close.
    anchor = _candidate(_unit(f"article-{_ANCHOR}", _ANCHOR, 100), "equality")
    legacy_close = _candidate(_unit("article-900", "900", 900), "equality")
    pool = [anchor, legacy_close, *[_c(a) for a in _RELATED]]

    graph = _test_graph()
    assert graph.bucket_for("article-900", "article-900", "900", "900").bucket is None
    from constitution_memorizer.planner.relationships import (
        band_for_score,
        relationship_score,
    )

    assert band_for_score(relationship_score(anchor, legacy_close)) == "close"

    for seed in range(40):
        # Steady wants 1 Close + 1 Related. The Close slot takes the legacy
        # Close; the Related slot takes a curated Related. Neither slot is
        # filled by the other bucket.
        selection = _select(pool, 3, seed=seed, committed=[anchor])
        by_slot = {p.requested_bucket: p for p in selection.picks[1:]}
        assert by_slot["close"].candidate.id == legacy_close.id, seed
        assert by_slot["close"].effective_bucket == "close", seed
        assert by_slot["related"].effective_bucket == "related", seed
        assert by_slot["related"].relation_source == "cluster_relation", seed


def test_legacy_picks_are_tagged_and_counted():
    pool = [_c(_ANCHOR), *[_c(a) for a in _STRANGER]]
    selection = _select(pool, 3, committed=[_c(_ANCHOR)])
    used = [p for p in selection.picks[1:]]
    assert used, "expected the day to be filled from somewhere"
    assert all(p.relation_source == "legacy_fallback" for p in used)
    assert all(p.curated_bucket is None for p in used)
    assert selection.legacy_count == len(used)


def test_unclassified_is_the_last_resort_once_legacy_is_retired():
    """Phase C: with the legacy path off, uncurated units are unclassified."""
    pool = [_c(_ANCHOR), *[_c(a) for a in _STRANGER]]
    selection = _select(pool, 3, committed=[_c(_ANCHOR)], use_legacy_fallback=False)
    used = selection.picks[1:]
    assert used
    assert all(p.relation_source == "unclassified" for p in used)
    assert all(p.effective_bucket is None for p in used)
    assert selection.legacy_count == 0


# ── committed carryover ─────────────────────────────────────────────────────


def test_committed_prefix_anchors_and_credits_the_quota():
    """Carryover of anchor + Related + Explore leaves only Close to fill."""
    committed = [_c(_ANCHOR), _c(_RELATED[0]), _c(_EXPLORE[0])]
    selection = _select(_pool(), 5, committed=committed)
    assert selection.ids[:3] == [p.id for p in committed]
    fresh = selection.picks[3:]
    assert len(fresh) == 2
    assert {p.effective_bucket for p in fresh} == {"close"}
    assert _buckets(selection) == {"close": 2, "related": 1, "explore": 1}


def test_committed_order_is_never_shuffled():
    committed = [_c(_ANCHOR), _c(_CLOSE[0]), _c(_RELATED[0])]
    for seed in range(50):
        selection = _select(_pool(), 5, seed=seed, committed=committed)
        assert selection.ids[:3] == [p.id for p in committed], seed


def test_carryover_outranks_a_perfect_composition():
    """Preserving owed work beats manufacturing an ideal mix.

    Three Related commitments overshoot a Balanced day's single Related slot.
    Nothing is dropped or reordered to make the arithmetic tidy.
    """
    committed = [_c(_ANCHOR), *[_c(a) for a in _RELATED]]
    selection = _select(_pool(), 5, committed=committed)
    assert selection.ids[:4] == [f"article-{a}" for a in [_ANCHOR, *_RELATED]]
    assert _buckets(selection)["related"] == 3


# ── anchor selection ────────────────────────────────────────────────────────


def test_recent_cluster_is_downweighted_not_banned():
    """0.35 relative weight -> roughly a quarter of anchors, never zero."""
    pool = [*[_c(a) for a in _CLOSE], *[_c(a) for a in _RELATED]]
    recent = recency_key(_c(_CLOSE[0]), _test_graph())
    picked = 0
    runs = 400
    for seed in range(runs):
        selection = _select(pool, 3, seed=seed, recent_theme=recent)
        if recency_key(selection.anchor, _test_graph()) == recent:
            picked += 1
    share = picked / runs
    # 0.35 / 1.35 ~= 0.26. Wide enough to be seed-stable, tight enough to fail
    # both a hard ban (0.0) and a missing downweight (~0.5).
    assert 0.10 < share < 0.45, share


def test_recency_does_not_change_any_bucket():
    plain = _select(_pool(), 5, committed=[_c(_ANCHOR)])
    with_recent = _select(
        _pool(), 5, committed=[_c(_ANCHOR)], recent_theme="equality"
    )
    assert _buckets(plain) == _buckets(with_recent)


def test_anchor_ineligible_units_are_never_the_anchor():
    graph = CuratedRelationshipGraph(
        {
            "families": {},
            "clusters": {"equality": {"same_cluster_bucket": "close"}},
            "article_metadata": {
                _ANCHOR: {
                    "primary_cluster": "equality",
                    "clusters": ["equality"],
                    "anchor_eligible": False,
                },
                _CLOSE[0]: {"primary_cluster": "equality", "clusters": ["equality"]},
            },
            "unit_metadata": {},
            "article_edges": [],
            "unit_edges": [],
        }
    )
    pool = [_c(_ANCHOR), _c(_CLOSE[0])]
    for seed in range(30):
        selection = LearningMixSelector().select_detailed(
            pool, 3, rng=random.Random(seed), graph=graph
        )
        assert selection.anchor.id == f"article-{_CLOSE[0]}", seed


def test_article_14_balanced_keeps_its_related_and_explore(tmp_path: Path):
    """The real corpus case: a curated anchor must not collapse into all-Close.

    Article 14 has curated Close companions (15, 16 by edge; 17, 18 by
    cluster). Preferring curated source over the requested bucket turned
    Balanced into anchor + four Close — the whole familiarity gradient gone.

    With equality's cluster relations curated, every slot is now filled from
    the graph; before they were curated the Related and Explore slots fell to
    legacy candidates of the right bucket, which was equally acceptable. What
    is asserted here is the part that must hold either way: the composition,
    and each slot getting the bucket it asked for.
    """
    import json

    from constitution_memorizer.learning.schemas import LearningUnitsDocument
    from constitution_memorizer.planner.eligibility import eligible_candidates

    corpus = Path(__file__).resolve().parents[1] / "data" / "output" / "learning_units.json"
    doc = LearningUnitsDocument.model_validate(
        json.loads(corpus.read_text(encoding="utf-8"))
    )
    engine = ReminderEngine.from_units(tmp_path / "p.db", list(doc.units))
    pool = eligible_candidates(engine, as_of=date(2026, 9, 3))
    anchor = next(c for c in pool if c.article_number == "14")

    for seed in range(25):
        selection = LearningMixSelector().select_detailed(
            pool, 5, rng=random.Random(seed), committed=[anchor]
        )
        counts = selection.bucket_counts()
        assert counts == {"close": 2, "related": 1, "explore": 1}, (seed, counts)

        by_slot = {p.requested_bucket: p for p in selection.picks[1:] if p.requested_bucket}
        for slot in ("close", "related", "explore"):
            assert by_slot[slot].effective_bucket == slot, (seed, slot)
        # equality is fully curated — Close by edge or cluster, Related and
        # Explore through its cluster relations — so no slot needs the legacy
        # scorer. Whether a given slot is curated is data, not behaviour, so
        # only the anchor's own neighbourhood is asserted here.
        assert selection.legacy_count == 0, (seed, selection.picks)
