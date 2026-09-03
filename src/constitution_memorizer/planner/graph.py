"""The curated curriculum relationship graph.

CURRICULUM RELATIONSHIP IS PRESET DATA. THE PLANNER DOES NOT INFER SEMANTIC
CLOSENESS AT RUNTIME.

Whether two provisions are pedagogically close is a curriculum decision, not
something to derive from Article numbers being near each other. This module
loads that decision from ``data/reference/learning_relationships.json`` once
per process and answers relationship questions from memory. It reads no
database, and nothing here depends on user state — progress decides *whether*
a unit is eligible, this decides *how* eligible units relate.

Vocabulary
----------
family      the broadest grouping (Fundamental Rights, Judiciary, …). May be
            null on a cluster: the starter taxonomy is deliberately partial,
            and a wrong family is worse than none.
cluster     a curated group of Articles (equality, pardoning, …). An Article
            may belong to several; ``primary_cluster`` is the one that drives
            anchor recency and is always a member of ``clusters``.
bucket      close / related / explore — what the planner composes days from.
edge        an explicit curated relation between two Articles or two units.
            Unit edges beat Article edges; both beat cluster rules.

Precedence, highest first:

    unit edge -> article edge -> cluster relation -> family relation -> None

``None`` means *unclassified* — genuinely no curated relationship — which is a
different thing from Explore. Explore is curated novelty; unclassified is
absence of curation. Callers must keep them apart.

Where several relations apply at the same precedence, familiarity priority
decides: close > related > explore.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from constitution_memorizer.utils.json_io import read_json

BUCKETS = ("close", "related", "explore")
_BUCKET_RANK = {"close": 0, "related": 1, "explore": 2}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GRAPH = _REPO_ROOT / "data" / "reference" / "learning_relationships.json"
# Packaged copy, for installs that ship no repo `data/` directory. The graph is
# curriculum logic: if neither path exists we raise rather than degrade, because
# a silent empty graph would look like "nothing is related" instead of like the
# broken deployment it is.
_PACKAGE_GRAPH = (
    Path(__file__).resolve().parents[1] / "web" / "learning_relationships.json"
)


class CuratedGraphMissing(RuntimeError):
    """The curated graph could not be found. Never degrade — fail loudly."""


def best_bucket(buckets) -> str | None:
    """Most familiar of several applicable buckets: close > related > explore."""
    ranked = [b for b in buckets if b in _BUCKET_RANK]
    if not ranked:
        return None
    return min(ranked, key=lambda b: _BUCKET_RANK[b])


@dataclass(frozen=True)
class Relation:
    """One curated relationship, with the reason it was reached."""

    bucket: str | None
    relation_type: str | None = None
    source: str | None = None

    @property
    def is_classified(self) -> bool:
        return self.bucket is not None


UNCLASSIFIED = Relation(bucket=None)


@dataclass(frozen=True)
class NodeMetadata:
    """Resolved curated metadata for one unit (or one Article)."""

    clusters: tuple[str, ...] = ()
    primary_cluster: str | None = None
    anchor_eligible: bool = True
    anchor_weight: float = 1.0


EMPTY_METADATA = NodeMetadata()


@dataclass(frozen=True)
class _Edge:
    bucket: str
    relation_type: str | None
    direction: str


class CuratedRelationshipGraph:
    """Immutable, in-memory view of the curated curriculum graph."""

    def __init__(self, data: dict) -> None:
        self._families: dict[str, dict] = dict(data.get("families") or {})
        self._clusters: dict[str, dict] = dict(data.get("clusters") or {})
        self._article_meta = self._read_metadata(data.get("article_metadata") or {})
        self._unit_meta = self._read_metadata(data.get("unit_metadata") or {})

        # Edge indexes: one dict hit per classification, no pairwise scan.
        # Indexing is last-wins, which would quietly swallow a pair declared
        # twice with different meanings — so conflicts are recorded as they are
        # overwritten and the validator reports them.
        self._unit_edges: dict[tuple[str, str], _Edge] = {}
        self._article_edges: dict[tuple[str, str], _Edge] = {}
        self._edge_conflicts: list[str] = []
        for row in data.get("unit_edges") or []:
            self._index_edge(self._unit_edges, row, "unit_edge")
        for row in data.get("article_edges") or []:
            self._index_edge(self._article_edges, row, "article_edge")

        # Membership indexes, for coverage reporting and diagnostics.
        self._articles_by_cluster: dict[str, tuple[str, ...]] = self._invert(
            self._article_meta
        )
        self._units_by_cluster: dict[str, tuple[str, ...]] = self._invert(
            self._unit_meta
        )

    # ---------------------------------------------------------------- load --

    @staticmethod
    def _read_metadata(raw: dict) -> dict[str, NodeMetadata]:
        out: dict[str, NodeMetadata] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            clusters = tuple(
                str(c) for c in (value.get("clusters") or []) if str(c).strip()
            )
            primary = value.get("primary_cluster")
            weight = value.get("anchor_weight", 1.0)
            out[str(key)] = NodeMetadata(
                clusters=clusters,
                primary_cluster=str(primary) if primary else None,
                anchor_eligible=bool(value.get("anchor_eligible", True)),
                anchor_weight=float(weight) if isinstance(weight, (int, float)) else 1.0,
            )
        return out

    def _index_edge(
        self, index: dict[tuple[str, str], _Edge], row: dict, label: str
    ) -> None:
        a, b = str(row.get("a") or ""), str(row.get("b") or "")
        bucket = str(row.get("bucket") or "")
        if not a or not b:
            return
        if bucket not in _BUCKET_RANK:
            self._edge_conflicts.append(
                f"{label} {a!r}->{b!r} has invalid bucket {bucket!r}"
            )
            return
        direction = str(row.get("direction") or "both")
        edge = _Edge(bucket, row.get("type"), direction)
        for key in self._edge_keys(a, b, direction):
            prior = index.get(key)
            if prior is not None and (prior.bucket, prior.relation_type) != (
                edge.bucket,
                edge.relation_type,
            ):
                self._edge_conflicts.append(
                    f"{label} {sorted((a, b))} declared twice with different "
                    f"meanings: ({prior.bucket}, {prior.relation_type}) vs "
                    f"({edge.bucket}, {edge.relation_type})"
                )
            index[key] = edge

    @staticmethod
    def _edge_keys(a: str, b: str, direction: str):
        if direction in ("both", "a_to_b"):
            yield (a, b)
        if direction in ("both", "b_to_a"):
            yield (b, a)

    @staticmethod
    def _invert(meta: dict[str, NodeMetadata]) -> dict[str, tuple[str, ...]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for key, node in meta.items():
            for cluster in node.clusters:
                groups[cluster].append(key)
        return {cluster: tuple(sorted(keys)) for cluster, keys in groups.items()}

    # ------------------------------------------------------------ metadata --

    def metadata_for(self, unit_id: str, article_number: str | None = None):
        """Unit metadata if curated, else the Article's, else empty.

        A unit entry replaces its Article's wholesale — a supplied ``clusters``
        list is the unit's full membership, never a union with the inherited
        one. Anything the unit omits falls through to the Article.
        """
        unit = self._unit_meta.get(unit_id)
        article = self._article_meta.get(article_number or "")
        if unit is None:
            return article or EMPTY_METADATA
        if article is None:
            return unit
        return NodeMetadata(
            clusters=unit.clusters or article.clusters,
            primary_cluster=unit.primary_cluster or article.primary_cluster,
            anchor_eligible=unit.anchor_eligible,
            anchor_weight=unit.anchor_weight,
        )

    def clusters_for(self, unit_id: str, article_number: str | None = None):
        return self.metadata_for(unit_id, article_number).clusters

    def primary_cluster_for(self, unit_id: str, article_number: str | None = None):
        return self.metadata_for(unit_id, article_number).primary_cluster

    def families_for(self, unit_id: str, article_number: str | None = None):
        """Every family reachable from this node's clusters (may be several)."""
        seen: list[str] = []
        for cluster in self.clusters_for(unit_id, article_number):
            family = (self._clusters.get(cluster) or {}).get("family")
            if family and family not in seen:
                seen.append(str(family))
        return tuple(seen)

    def primary_family_for(self, unit_id: str, article_number: str | None = None):
        cluster = self.primary_cluster_for(unit_id, article_number)
        if not cluster:
            return None
        family = (self._clusters.get(cluster) or {}).get("family")
        return str(family) if family else None

    # ------------------------------------------------------- relationships --

    def explicit_relationship(
        self,
        anchor_unit: str,
        other_unit: str,
        anchor_article: str | None = None,
        other_article: str | None = None,
    ) -> Relation:
        """Curated edge between two nodes: unit edge first, then Article edge."""
        edge = self._unit_edges.get((anchor_unit, other_unit))
        if edge is not None:
            return Relation(edge.bucket, edge.relation_type, "unit_edge")
        if anchor_article and other_article:
            edge = self._article_edges.get((anchor_article, other_article))
            if edge is not None:
                return Relation(edge.bucket, edge.relation_type, "article_edge")
        return UNCLASSIFIED

    def bucket_for(
        self,
        anchor_unit: str,
        other_unit: str,
        anchor_article: str | None = None,
        other_article: str | None = None,
    ) -> Relation:
        """Where ``other`` sits relative to ``anchor``, or UNCLASSIFIED.

        Unclassified is not Explore. A caller that needs a body for an Explore
        slot must ask for one; it must not read absence as novelty.
        """
        if anchor_unit == other_unit:
            return UNCLASSIFIED

        explicit = self.explicit_relationship(
            anchor_unit, other_unit, anchor_article, other_article
        )
        if explicit.is_classified:
            return explicit

        anchor_clusters = set(self.clusters_for(anchor_unit, anchor_article))
        other_clusters = set(self.clusters_for(other_unit, other_article))
        if not anchor_clusters or not other_clusters:
            return UNCLASSIFIED

        # Same cluster, but only where that cluster says so — co-membership is
        # not automatically closeness (§13).
        shared = anchor_clusters & other_clusters
        same = best_bucket(
            (self._clusters.get(cid) or {}).get("same_cluster_bucket")
            for cid in shared
        )
        if same:
            return Relation(same, "same_cluster", "same_cluster")

        # Cluster-level relations, best bucket across every applicable pairing.
        applicable: list[str] = []
        for cid in anchor_clusters:
            spec = self._clusters.get(cid) or {}
            if other_clusters & set(spec.get("related_clusters") or []):
                applicable.append("related")
            if other_clusters & set(spec.get("explore_clusters") or []):
                applicable.append("explore")
        cluster_bucket = best_bucket(applicable)
        if cluster_bucket:
            return Relation(cluster_bucket, "cluster_relation", "cluster_relation")

        # Family relations, only where a family explicitly configures one.
        family_buckets = []
        anchor_families = set(self.families_for(anchor_unit, anchor_article))
        other_families = set(self.families_for(other_unit, other_article))
        for fid in anchor_families & other_families:
            configured = (self._families.get(fid) or {}).get("same_family_bucket")
            if configured:
                family_buckets.append(str(configured))
        family_bucket = best_bucket(family_buckets)
        if family_bucket:
            return Relation(family_bucket, "same_family", "family_relation")

        return UNCLASSIFIED

    # -------------------------------------------------------- diagnostics --

    @property
    def families(self) -> dict[str, dict]:
        return dict(self._families)

    @property
    def clusters(self) -> dict[str, dict]:
        return dict(self._clusters)

    @property
    def article_metadata(self) -> dict[str, NodeMetadata]:
        return dict(self._article_meta)

    @property
    def unit_metadata(self) -> dict[str, NodeMetadata]:
        return dict(self._unit_meta)

    @property
    def article_edges(self) -> dict[tuple[str, str], _Edge]:
        return dict(self._article_edges)

    @property
    def unit_edges(self) -> dict[tuple[str, str], _Edge]:
        return dict(self._unit_edges)

    @property
    def edge_conflicts(self) -> tuple[str, ...]:
        """Contradictions found while indexing, for the validator to report."""
        return tuple(self._edge_conflicts)

    def articles_in_cluster(self, cluster_id: str) -> tuple[str, ...]:
        return self._articles_by_cluster.get(cluster_id, ())

    def units_in_cluster(self, cluster_id: str) -> tuple[str, ...]:
        return self._units_by_cluster.get(cluster_id, ())

    def coverage_report(self, article_numbers) -> dict:
        """Curated coverage against a real corpus. Never hardcode these."""
        corpus = {str(a) for a in article_numbers if a}
        curated = set(self._article_meta)
        return {
            "curated_articles": len(curated),
            "corpus_articles": len(corpus),
            "curated_present": len(curated & corpus),
            "curated_absent": sorted(curated - corpus),
            "uncovered": sorted(corpus - curated),
            "clusters": len(self._clusters),
            "clusters_without_family": sorted(
                cid for cid, spec in self._clusters.items() if not spec.get("family")
            ),
            "article_edges": len(
                {frozenset(pair) for pair in self._article_edges}
            ),
        }


def load_graph_data(path: str | None = None) -> dict:
    """Read the graph JSON, or raise. Absence is a deployment fault."""
    if path:
        candidate = Path(path)
        if not candidate.exists():
            raise CuratedGraphMissing(f"curated relationship graph not found: {path}")
        return read_json(candidate)
    for candidate in (_GRAPH, _PACKAGE_GRAPH):
        if candidate.exists():
            data = read_json(candidate)
            if isinstance(data, dict):
                return data
    raise CuratedGraphMissing(
        "curated relationship graph not found at "
        f"{_GRAPH} or {_PACKAGE_GRAPH}. The planner will not fall back to "
        "heuristics: a missing graph means curriculum data was not packaged."
    )


@lru_cache(maxsize=4)
def curated_graph(path: str | None = None) -> CuratedRelationshipGraph:
    """Process-wide graph. Parsed once; every lookup after this is in memory."""
    return CuratedRelationshipGraph(load_graph_data(path))
