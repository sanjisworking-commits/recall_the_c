"""Structural validation for the curated relationship graph.

The graph is curriculum data edited by hand, so the failure mode to guard
against is a typo that silently removes a relationship rather than one that
crashes. A cluster id misspelt in ``related_clusters`` would simply never
match, and the planner would look like it was working.

Errors are things that make the data wrong; warnings are things worth a
curator's attention but valid to ship. ``cluster.family: null`` is neither —
the starter taxonomy is deliberately partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from constitution_memorizer.planner.graph import BUCKETS, CuratedRelationshipGraph


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_invalid(self) -> None:
        if self.errors:
            joined = "\n  - ".join(self.errors)
            raise ValueError(
                f"curated relationship graph is invalid:\n  - {joined}"
            )


def validate_graph(
    graph: CuratedRelationshipGraph,
    *,
    known_units: set[str] | None = None,
    known_articles: set[str] | None = None,
) -> ValidationResult:
    """Check the graph's internal consistency, and its fit to a corpus.

    ``known_units`` / ``known_articles`` are optional: pass them to catch ids
    that no longer exist in the corpus.
    """
    result = ValidationResult()
    families = graph.families
    clusters = graph.clusters

    # -- clusters ---------------------------------------------------------
    referenced_families: set[str] = set()
    for cid, spec in clusters.items():
        family = spec.get("family")
        if family:
            referenced_families.add(str(family))
            if str(family) not in families:
                result.errors.append(
                    f"cluster {cid!r} points at missing family {family!r}"
                )
        bucket = spec.get("same_cluster_bucket")
        if bucket is not None and bucket not in BUCKETS:
            result.errors.append(
                f"cluster {cid!r} has invalid same_cluster_bucket {bucket!r}"
            )
        for key in ("related_clusters", "explore_clusters"):
            for ref in spec.get(key) or []:
                if str(ref) not in clusters:
                    result.errors.append(
                        f"cluster {cid!r} {key} references unknown cluster {ref!r}"
                    )
                if str(ref) == cid:
                    result.errors.append(
                        f"cluster {cid!r} {key} references itself"
                    )

    for fid in families:
        if fid not in referenced_families:
            result.warnings.append(f"family {fid!r} has no clusters")

    # -- metadata ---------------------------------------------------------
    _check_metadata(
        result, graph.article_metadata, clusters, "article", known_articles
    )
    _check_metadata(result, graph.unit_metadata, clusters, "unit", known_units)

    # A unit that overrides primary_cluster must own a clusters list containing
    # it. Checked against what was *written*, not what resolved: the validator
    # cannot see which Article a unit belongs to, so it requires the membership
    # to be stated rather than inferring it. Explicit beats convenient here —
    # a silently widened membership is a relationship nobody wrote down.
    for unit_id, raw in graph.raw_unit_metadata.items():
        if not raw.primary_cluster:
            continue
        if raw.clusters is None or raw.primary_cluster not in raw.clusters:
            result.errors.append(
                f"unit {unit_id!r} sets primary_cluster "
                f"{raw.primary_cluster!r} without a clusters list containing "
                "it; supply the replacement clusters explicitly"
            )

    # -- edges ------------------------------------------------------------
    # Contradictions are caught during indexing: the index is last-wins, so by
    # the time it is readable the losing edge is already gone.
    result.errors.extend(graph.edge_conflicts)
    _check_edges(result, graph.article_edges, "article_edge", known_articles)
    _check_edges(result, graph.unit_edges, "unit_edge", known_units)

    # -- reachability -----------------------------------------------------
    for cid in clusters:
        if not graph.articles_in_cluster(cid) and not graph.units_in_cluster(cid):
            result.warnings.append(f"cluster {cid!r} has no members")

    return result


def _check_metadata(result, metadata, clusters, label, known) -> None:
    for key, node in metadata.items():
        if known is not None and key not in known:
            result.warnings.append(
                f"{label} {key!r} is curated but absent from the corpus"
            )
        for cid in node.clusters:
            if cid not in clusters:
                result.errors.append(
                    f"{label} {key!r} references unknown cluster {cid!r}"
                )
        if node.primary_cluster and node.primary_cluster not in clusters:
            result.errors.append(
                f"{label} {key!r} primary_cluster {node.primary_cluster!r} "
                "is not a known cluster"
            )
        if node.clusters and node.primary_cluster not in node.clusters:
            result.errors.append(
                f"{label} {key!r} primary_cluster {node.primary_cluster!r} "
                f"is not among its clusters {list(node.clusters)}"
            )
        if not isinstance(node.anchor_weight, float) or node.anchor_weight <= 0:
            result.errors.append(
                f"{label} {key!r} has invalid anchor_weight {node.anchor_weight!r}"
            )
        if len(set(node.clusters)) != len(node.clusters):
            result.warnings.append(f"{label} {key!r} lists a cluster twice")


def _check_edges(result, edges, label, known) -> None:
    seen: dict[frozenset[str], tuple[str, str | None]] = {}
    for (a, b), edge in edges.items():
        if a == b:
            result.errors.append(f"{label} {a!r} points at itself")
            continue
        if edge.bucket not in BUCKETS:
            result.errors.append(
                f"{label} {a!r}->{b!r} has invalid bucket {edge.bucket!r}"
            )
        if known is not None:
            for side in (a, b):
                if side not in known:
                    result.warnings.append(
                        f"{label} references {side!r}, absent from the corpus"
                    )
        # Contradiction, not duplication: the same pair asserted two ways.
        key = frozenset((a, b))
        prior = seen.get(key)
        current = (edge.bucket, edge.relation_type)
        if prior is not None and prior != current:
            result.errors.append(
                f"{label} {sorted(key)} declared twice with different "
                f"meanings: {prior} vs {current}"
            )
        seen[key] = current
