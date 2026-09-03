"""The curated relationship graph: schema, precedence, and the migration.

The planner reads pedagogical closeness from this data instead of inferring it,
so the tests that matter are the ones proving the data says what we think it
says — and that a typo in it fails loudly rather than quietly removing a
relationship.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from constitution_memorizer.learning.schemas import LearningUnitsDocument
from constitution_memorizer.planner.graph import (
    CuratedGraphMissing,
    CuratedRelationshipGraph,
    curated_graph,
    load_graph_data,
)
from constitution_memorizer.planner.graph_validator import validate_graph

ROOT = Path(__file__).resolve().parents[1]
GRAPH_FILE = ROOT / "data" / "reference" / "learning_relationships.json"
UNITS_FILE = ROOT / "data" / "output" / "learning_units.json"


def _graph(**overrides) -> CuratedRelationshipGraph:
    data = {
        "families": {"rights": {"label": "Rights"}},
        "clusters": {
            "equality": {"family": "rights", "same_cluster_bucket": "close"},
            "liberty": {"family": "rights", "same_cluster_bucket": "close"},
            "money": {"family": None},
        },
        "article_metadata": {},
        "unit_metadata": {},
        "article_edges": [],
        "unit_edges": [],
    }
    data.update(overrides)
    return CuratedRelationshipGraph(data)


def _corpus() -> tuple[set[str], set[str]]:
    doc = LearningUnitsDocument.model_validate(
        json.loads(UNITS_FILE.read_text(encoding="utf-8"))
    )
    return (
        {u.id for u in doc.units},
        {u.article_number for u in doc.units if u.article_number},
    )


# ── A. the shipped graph loads and validates ────────────────────────────────


def test_shipped_graph_loads_and_has_no_validation_errors():
    units, articles = _corpus()
    result = validate_graph(curated_graph(), known_units=units, known_articles=articles)
    assert result.errors == []
    # Six curated Articles no longer exist in the corpus. They are warned about
    # rather than dropped silently, so a curator can retire them deliberately.
    absent = [w for w in result.warnings if "absent from the corpus" in w]
    assert len(absent) == 6
    for article in ("85", "124A", "174", "228A", "279A", "359A"):
        assert any(f"'{article}'" in w for w in absent), article


def test_shipped_graph_coverage_is_computed_not_assumed():
    _units, articles = _corpus()
    report = curated_graph().coverage_report(articles)
    assert report["curated_articles"] == 375
    assert report["corpus_articles"] == 491
    assert report["curated_present"] == 369
    assert len(report["curated_absent"]) == 6
    assert len(report["uncovered"]) == 122
    assert report["curated_present"] + len(report["uncovered"]) == report["corpus_articles"]


# ── B/C. bad data fails validation ──────────────────────────────────────────


def test_unknown_cluster_reference_is_an_error():
    graph = _graph(article_metadata={"14": {"primary_cluster": "nope", "clusters": ["nope"]}})
    result = validate_graph(graph)
    assert not result.ok
    assert any("unknown cluster 'nope'" in e for e in result.errors)


def test_unknown_unit_id_is_reported_against_the_corpus():
    graph = _graph(
        unit_metadata={
            "article-9999-clause-1": {
                "primary_cluster": "equality",
                "clusters": ["equality"],
            }
        }
    )
    result = validate_graph(graph, known_units={"article-14"}, known_articles={"14"})
    assert any("absent from the corpus" in w for w in result.warnings)


def test_cluster_pointing_at_missing_family_is_an_error():
    graph = _graph(clusters={"equality": {"family": "ghost"}})
    assert any("missing family 'ghost'" in e for e in validate_graph(graph).errors)


def test_contradictory_duplicate_edges_are_an_error():
    graph = _graph(
        article_edges=[
            {"a": "14", "b": "15", "bucket": "close", "type": "same_doctrine"},
            {"a": "15", "b": "14", "bucket": "explore", "type": "contrast"},
        ]
    )
    assert any("different" in e for e in validate_graph(graph).errors)


def test_self_edge_is_an_error():
    graph = _graph(article_edges=[{"a": "14", "b": "14", "bucket": "close"}])
    assert any("points at itself" in e for e in validate_graph(graph).errors)


# ── D. explicit edges override cluster rules ────────────────────────────────


def test_unit_edge_beats_article_edge_beats_cluster_rule():
    graph = _graph(
        article_metadata={
            "14": {"primary_cluster": "equality", "clusters": ["equality"]},
            "15": {"primary_cluster": "equality", "clusters": ["equality"]},
        },
        article_edges=[{"a": "14", "b": "15", "bucket": "related", "type": "contrast"}],
        unit_edges=[
            {"a": "article-14", "b": "article-15", "bucket": "explore", "type": "far"}
        ],
    )
    # Same cluster would say close; the article edge says related; the unit
    # edge says explore. Most specific wins.
    assert graph.bucket_for("article-14", "article-15", "14", "15").source == "unit_edge"
    assert graph.bucket_for("article-14", "article-15", "14", "15").bucket == "explore"
    # Without the unit edge, the article edge still beats the cluster rule.
    assert graph.bucket_for("article-14-clause-1", "article-15", "14", "15").bucket == "related"


# ── E. direction ────────────────────────────────────────────────────────────


def test_directional_edge_is_asymmetric():
    graph = _graph(
        article_edges=[
            {"a": "14", "b": "15", "bucket": "close", "direction": "a_to_b"}
        ]
    )
    assert graph.bucket_for("article-14", "article-15", "14", "15").bucket == "close"
    assert graph.bucket_for("article-15", "article-14", "15", "14").bucket is None


def test_bidirectional_is_the_default_and_works_both_ways():
    graph = _graph(article_edges=[{"a": "14", "b": "15", "bucket": "close"}])
    assert graph.bucket_for("article-14", "article-15", "14", "15").bucket == "close"
    assert graph.bucket_for("article-15", "article-14", "15", "14").bucket == "close"


# ── F/G. unclassified is not Explore ────────────────────────────────────────


def test_missing_relationship_is_unclassified_not_explore():
    graph = _graph(
        article_metadata={
            "14": {"primary_cluster": "equality", "clusters": ["equality"]},
            "266": {"primary_cluster": "money", "clusters": ["money"]},
        }
    )
    relation = graph.bucket_for("article-14", "article-266", "14", "266")
    assert relation.bucket is None
    assert relation.is_classified is False


def test_same_cluster_is_close_only_where_the_cluster_says_so():
    graph = _graph(
        clusters={
            "equality": {"family": "rights", "same_cluster_bucket": "close"},
            # No same_cluster_bucket: co-membership asserts nothing on its own.
            "money": {"family": None},
        },
        article_metadata={
            "14": {"primary_cluster": "equality", "clusters": ["equality"]},
            "15": {"primary_cluster": "equality", "clusters": ["equality"]},
            "266": {"primary_cluster": "money", "clusters": ["money"]},
            "267": {"primary_cluster": "money", "clusters": ["money"]},
        },
    )
    assert graph.bucket_for("article-14", "article-15", "14", "15").bucket == "close"
    assert graph.bucket_for("article-266", "article-267", "266", "267").bucket is None


# ── H/I. cluster relations ──────────────────────────────────────────────────


def test_cluster_related_and_explore_relations_resolve():
    graph = _graph(
        clusters={
            "equality": {
                "family": "rights",
                "same_cluster_bucket": "close",
                "related_clusters": ["liberty"],
                "explore_clusters": ["money"],
            },
            "liberty": {"family": "rights"},
            "money": {"family": None},
        },
        article_metadata={
            "14": {"primary_cluster": "equality", "clusters": ["equality"]},
            "21": {"primary_cluster": "liberty", "clusters": ["liberty"]},
            "266": {"primary_cluster": "money", "clusters": ["money"]},
        },
    )
    assert graph.bucket_for("article-14", "article-21", "14", "21").bucket == "related"
    assert graph.bucket_for("article-14", "article-266", "14", "266").bucket == "explore"


def test_competing_cluster_relations_resolve_to_the_most_familiar():
    """Close beats Related when two curated paths both apply."""
    graph = _graph(
        clusters={
            "equality": {
                "family": "rights",
                "same_cluster_bucket": "close",
                "explore_clusters": ["liberty"],
            },
            "liberty": {"family": "rights", "same_cluster_bucket": "close"},
            "money": {"family": None},
        },
        article_metadata={
            # Shares 'equality' with the anchor (close) AND sits in 'liberty',
            # which equality lists as explore. Close wins.
            "14": {"primary_cluster": "equality", "clusters": ["equality"]},
            "21": {"primary_cluster": "equality", "clusters": ["equality", "liberty"]},
        },
    )
    assert graph.bucket_for("article-14", "article-21", "14", "21").bucket == "close"


def test_competing_family_relations_resolve_to_the_most_familiar():
    graph = _graph(
        families={
            "rights": {"label": "Rights", "same_family_bucket": "explore"},
            "core": {"label": "Core", "same_family_bucket": "related"},
        },
        clusters={
            "equality": {"family": "rights"},
            "liberty": {"family": "core"},
            "duties": {"family": "rights"},
            "basics": {"family": "core"},
        },
        article_metadata={
            "14": {"primary_cluster": "equality", "clusters": ["equality", "liberty"]},
            "51": {"primary_cluster": "duties", "clusters": ["duties", "basics"]},
        },
    )
    # Both families are shared; related (core) beats explore (rights).
    assert graph.bucket_for("article-14", "article-51", "14", "51").bucket == "related"


# ── D1. families are deliberately partial ───────────────────────────────────


def test_cluster_without_a_family_is_valid_and_usable():
    graph = _graph(
        article_metadata={
            "266": {"primary_cluster": "money", "clusters": ["money"]},
            "267": {"primary_cluster": "money", "clusters": ["money"]},
        },
        clusters={"money": {"family": None, "same_cluster_bucket": "close"}},
    )
    assert validate_graph(graph).errors == []
    assert graph.bucket_for("article-266", "article-267", "266", "267").bucket == "close"
    assert graph.primary_family_for("article-266", "266") is None


def test_shipped_graph_leaves_eighteen_clusters_unfamilied():
    """The starter taxonomy covers 14 of 32 clusters; nothing was guessed.

    Three of the eighteen — pardoning, council_of_ministers, ordinance — are
    union/state counterparts that span two families, where one family would be
    wrong rather than merely unknown.
    """
    _units, articles = _corpus()
    report = curated_graph().coverage_report(articles)
    without = set(report["clusters_without_family"])
    assert len(without) == 18
    assert {"pardoning", "council_of_ministers", "ordinance"} <= without
    assert "equality" not in without


# ── D2/E2. multi-membership ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "article, clusters, primary",
    [
        ("72", ("executive_union", "pardoning"), "executive_union"),
        ("74", ("executive_union", "council_of_ministers"), "executive_union"),
        ("75", ("executive_union", "council_of_ministers"), "executive_union"),
        ("161", ("pardoning", "state_executive"), "pardoning"),
        ("163", ("council_of_ministers", "state_executive"), "council_of_ministers"),
        ("164", ("council_of_ministers", "state_executive"), "council_of_ministers"),
        ("226", ("constitutional_remedies", "high_courts"), "constitutional_remedies"),
    ],
)
def test_overlapping_memberships_survive_migration(article, clusters, primary):
    """Every membership is kept, and primary is the first seed membership.

    These seven carry the strong curated pairs, so collapsing them to a single
    cluster would have damaged the most valuable data in the seed. "First seed
    membership" is deliberate: promoting 72 to `pardoning` may well be right,
    but it is a curriculum decision, not a migration side effect.
    """
    graph = curated_graph()
    unit = f"article-{article}"
    assert graph.clusters_for(unit, article) == clusters
    assert graph.primary_cluster_for(unit, article) == primary


def test_article_226_reaches_two_families():
    graph = curated_graph()
    assert set(graph.families_for("article-226", "226")) == {
        "fundamental_rights",
        "judiciary",
    }


def test_primary_cluster_must_be_among_its_clusters():
    graph = _graph(
        article_metadata={
            "14": {"primary_cluster": "liberty", "clusters": ["equality"]}
        }
    )
    assert any("not among its clusters" in e for e in validate_graph(graph).errors)


def test_unit_clusters_replace_inherited_ones():
    graph = _graph(
        article_metadata={"19": {"primary_cluster": "liberty", "clusters": ["liberty"]}},
        unit_metadata={
            "article-19-clause-1": {
                "primary_cluster": "equality",
                "clusters": ["equality"],
            }
        },
    )
    assert graph.clusters_for("article-19-clause-1", "19") == ("equality",)
    # A sibling with no override still inherits the Article's membership.
    assert graph.clusters_for("article-19-clause-2", "19") == ("liberty",)


def test_unit_override_outside_inherited_clusters_must_supply_its_own_list():
    """No silent widening: the JSON says what the unit belongs to, or it fails."""
    graph = _graph(
        article_metadata={"19": {"primary_cluster": "liberty", "clusters": ["liberty"]}},
        unit_metadata={"article-19-clause-1": {"primary_cluster": "equality"}},
    )
    errors = validate_graph(graph).errors
    assert any("without a clusters list containing it" in e for e in errors)


# ── E3. every legacy group expanded pairwise ────────────────────────────────


STRONG_PAIRS = [
    ("14", "15"), ("14", "16"), ("15", "16"),
    ("19", "21"), ("19", "22"), ("21", "22"),
    ("32", "226"), ("72", "161"), ("74", "163"), ("75", "164"), ("123", "213"),
    ("352", "356"), ("352", "360"), ("356", "360"),
]
MEDIUM_PAIRS = [("13", "32"), ("21", "21A"), ("245", "246"), ("324", "326")]


@pytest.mark.parametrize("a, b", STRONG_PAIRS)
def test_strong_pairs_are_close_in_both_directions(a, b):
    graph = curated_graph()
    assert graph.bucket_for(f"article-{a}", f"article-{b}", a, b).bucket == "close"
    assert graph.bucket_for(f"article-{b}", f"article-{a}", b, a).bucket == "close"


@pytest.mark.parametrize("a, b", MEDIUM_PAIRS)
def test_medium_pairs_are_related_by_intent(a, b):
    """An intentional normalisation, not parity.

    The legacy scorer gives a "medium" pair SCORE_SAME_THEME (65), and
    65 >= CLOSE_THRESHOLD (60), so production treats these four as *Close*
    today. The curated graph deliberately calls them Related.
    """
    graph = curated_graph()
    assert graph.bucket_for(f"article-{a}", f"article-{b}", a, b).bucket == "related"


def test_three_article_groups_became_three_edges_not_two():
    graph = curated_graph()
    edges = {frozenset(pair) for pair in graph.article_edges}
    assert len(edges) == 18
    for group in (("14", "15", "16"), ("19", "21", "22"), ("352", "356", "360")):
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                assert frozenset((left, right)) in edges, (left, right)


# ── D3. packaging ───────────────────────────────────────────────────────────


def test_missing_graph_raises_rather_than_degrading(tmp_path: Path):
    """A missing graph is a broken deployment, not an empty curriculum."""
    with pytest.raises(CuratedGraphMissing):
        load_graph_data(str(tmp_path / "absent.json"))


def test_graph_loads_from_an_explicit_path(tmp_path: Path):
    copy = tmp_path / "graph.json"
    copy.write_text(GRAPH_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    data = load_graph_data(str(copy))
    assert data["schema_version"] == "1.0"
    assert len(CuratedRelationshipGraph(data).clusters) == 32


# ── eligibility runs before relationship, never the reverse ─────────────────


def test_a_curated_close_unit_still_needs_its_prerequisite(tmp_path: Path):
    """Relationship never overrides eligibility.

    Article 315(2) may be curated Close to the anchor and still must not enter
    the pool while 315(1) is unfinished. Scheduling a sibling earlier in the
    same day does not unlock the next one either — only persisted completion
    does.
    """
    from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
    from constitution_memorizer.planner.eligibility import eligible_candidates
    from constitution_memorizer.progress.scheduler import ReminderEngine

    def _clause(unit_id: str, article: str, order: int) -> LearningUnit:
        return LearningUnit(
            id=unit_id,
            type=LearningUnitType.CLAUSE,
            article_number=article,
            display_title=f"Article {article}({order})",
            text=f"text {unit_id}",
            estimated_learning_time=60,
            revision_order=order,
            tags=["Part XIV"],
        )

    units = [
        _clause("article-315-clause-1", "315", 1),
        _clause("article-315-clause-2", "315", 2),
    ]
    engine = ReminderEngine.from_units(tmp_path / "p.db", units)
    ids = {c.id for c in eligible_candidates(engine, as_of=date(2026, 9, 3))}
    assert "article-315-clause-1" in ids
    assert "article-315-clause-2" not in ids



def test_packaged_copy_matches_the_canonical_graph():
    """Both paths must load the same curriculum.

    browse_parts/browse_chapters ship as committed copies under web/, and the
    graph follows that pattern. The generator writes both in one run, so this
    catches a hand-edit to one of them.
    """
    packaged = ROOT / "src" / "constitution_memorizer" / "web" / "learning_relationships.json"
    assert packaged.exists(), "the graph must ship as package data"
    assert packaged.read_text(encoding="utf-8") == GRAPH_FILE.read_text(encoding="utf-8")


def test_packaged_copy_is_declared_as_package_data():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "web/learning_relationships.json" in text


def test_graph_loads_from_the_packaged_path_alone(monkeypatch):
    """An installed build with no repo data/ directory still gets the graph."""
    from constitution_memorizer.planner import graph as graph_module

    monkeypatch.setattr(graph_module, "_GRAPH", ROOT / "does" / "not" / "exist.json")
    data = graph_module.load_graph_data()
    assert len(CuratedRelationshipGraph(data).clusters) == 32


def test_no_graph_anywhere_raises(monkeypatch, tmp_path: Path):
    from constitution_memorizer.planner import graph as graph_module

    monkeypatch.setattr(graph_module, "_GRAPH", tmp_path / "a.json")
    monkeypatch.setattr(graph_module, "_PACKAGE_GRAPH", tmp_path / "b.json")
    with pytest.raises(CuratedGraphMissing):
        graph_module.load_graph_data()
