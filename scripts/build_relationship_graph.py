#!/usr/bin/env python
"""Generate data/reference/learning_relationships.json from the legacy seed.

One-off migration, kept in the repo so the curated graph's provenance is
reproducible and reviewable rather than hand-typed.

What it does NOT do: invent relationships. Every cluster, membership and edge
here comes from learning_relationships.seed.json. Articles the seed never
mentions stay out of the graph entirely, and clusters the starter taxonomy
does not clearly cover get ``family: null`` rather than a guess.

Two deliberate semantic changes, both recorded in the emitted file's
``migration_notes``:

* the four legacy "medium" pairs become ``related``. They score 65 today and
  65 >= CLOSE_THRESHOLD (60), so production currently treats them as Close.
* groups of more than two Articles expand pairwise, matching what
  ``_pair_strengths()`` already does (14/15/16 -> three edges, not two).
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "reference" / "learning_relationships.seed.json"
OUT = ROOT / "data" / "reference" / "learning_relationships.json"
# Packaged copy, mirroring how browse_parts/browse_chapters ship. Written from
# the same run so the two cannot drift; a test asserts they are identical.
PACKAGED = ROOT / "src" / "constitution_memorizer" / "web" / "learning_relationships.json"

# The seven starter families (spec §6). A cluster is mapped only where the
# taxonomy clearly covers it; everything else is null until curriculum review.
FAMILIES: dict[str, str] = {
    "fundamental_rights": "Fundamental Rights",
    "union_executive": "Union Executive",
    "state_executive": "State Executive",
    "legislature": "Legislature",
    "judiciary": "Judiciary",
    "federalism": "Federalism",
    "emergency": "Emergency",
}

CLUSTER_FAMILY: dict[str, str] = {
    "equality": "fundamental_rights",
    "liberty": "fundamental_rights",
    "rights_against_exploitation": "fundamental_rights",
    "religion": "fundamental_rights",
    "cultural_rights": "fundamental_rights",
    "constitutional_remedies": "fundamental_rights",
    "executive_union": "union_executive",
    "state_executive": "state_executive",
    "parliament": "legislature",
    "state_legislature": "legislature",
    "union_judiciary": "judiciary",
    "high_courts": "judiciary",
    "centre_state": "federalism",
    "emergency": "emergency",
}

# Clusters that span two starter families (union<->state counterparts). A single
# family would be wrong here, not merely unknown, so they stay null on purpose.
SPANNING = {"pardoning", "council_of_ministers", "ordinance"}

# Relationship type per legacy group, read off the seed's own labels.
EDGE_TYPES: dict[str, str] = {
    "Equality cluster": "same_doctrine",
    "Liberty cluster": "same_doctrine",
    "Constitutional remedies": "parallel_remedy",
    "Pardoning powers": "union_state_counterpart",
    "Council of Ministers": "union_state_counterpart",
    "Ministerial advice and tenure": "union_state_counterpart",
    "Ordinance powers": "union_state_counterpart",
    "Emergency provisions": "same_doctrine",
    "Fundamental rights and their remedy": "right_remedy",
    "Life and education": "general_specific",
    "Legislative competence": "same_doctrine",
    "Elections and adult suffrage": "institution_function",
}

STRENGTH_BUCKET = {"strong": "close", "medium": "related"}


def main() -> int:
    seed = json.loads(SEED.read_text(encoding="utf-8"))

    clusters: dict[str, dict] = {}
    for theme in seed["themes"]:
        cid = theme["id"]
        clusters[cid] = {
            "label": theme["label"],
            # null where the starter taxonomy does not clearly cover it.
            "family": CLUSTER_FAMILY.get(cid),
            # Explicit, never defaulted: co-membership scores 65 today, which
            # is >= CLOSE_THRESHOLD, so Close preserves current behaviour.
            "same_cluster_bucket": "close",
            # Nothing curated yet — inventing cluster relations is out of scope.
            "related_clusters": [],
            "explore_clusters": [],
        }

    # Article metadata: every membership preserved, primary = FIRST seen.
    article_meta: dict[str, dict] = {}
    for theme in seed["themes"]:
        for article in theme["articles"]:
            key = str(article)
            entry = article_meta.setdefault(
                key, {"primary_cluster": theme["id"], "clusters": []}
            )
            if theme["id"] not in entry["clusters"]:
                entry["clusters"].append(theme["id"])

    # Edges: pairwise expansion of every legacy group.
    article_edges: list[dict] = []
    for pair in seed["pairs"]:
        label = pair["label"]
        bucket = STRENGTH_BUCKET[pair["strength"]]
        for a, b in combinations([str(x) for x in pair["articles"]], 2):
            article_edges.append(
                {
                    "a": a,
                    "b": b,
                    "bucket": bucket,
                    "type": EDGE_TYPES[label],
                    "direction": "both",
                    "reason": label,
                }
            )

    graph = {
        "schema_version": "1.0",
        "migration_notes": [
            "Generated by scripts/build_relationship_graph.py from "
            "learning_relationships.seed.json. Do not hand-edit wholesale; "
            "curate additively.",
            "The four legacy 'medium' pairs (13-32, 21-21A, 245-246, 324-326) "
            "are 'related' here. They score 65 in the legacy scorer and "
            "65 >= CLOSE_THRESHOLD (60), so production treats them as Close "
            "today. This is an intentional normalisation, not parity.",
            "Legacy groups of more than two Articles are expanded pairwise, "
            "matching _pair_strengths(): 14/15/16, 19/21/22 and 352/356/360 "
            "each contribute three edges.",
            "cluster.family is null where the seven starter families do not "
            "clearly cover the cluster. pardoning, council_of_ministers and "
            "ordinance span union and state families, so a single family "
            "would be wrong rather than merely unknown.",
            "related_clusters / explore_clusters are intentionally empty: no "
            "cluster-level relations existed in the legacy data, and this "
            "migration invents none.",
        ],
        "families": {fid: {"label": label} for fid, label in FAMILIES.items()},
        "clusters": clusters,
        "article_metadata": article_meta,
        "unit_metadata": {},
        "article_edges": article_edges,
        "unit_edges": [],
    }

    payload = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(payload, encoding="utf-8")
    PACKAGED.write_text(payload, encoding="utf-8")

    families_null = sum(1 for c in clusters.values() if c["family"] is None)
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"wrote {PACKAGED.relative_to(ROOT)}")
    print(f"  families        : {len(FAMILIES)}")
    print(f"  clusters        : {len(clusters)} ({families_null} with family: null)")
    print(f"  articles        : {len(article_meta)}")
    print(f"  article_edges   : {len(article_edges)}")
    multi = {a: m['clusters'] for a, m in article_meta.items() if len(m['clusters']) > 1}
    print(f"  multi-cluster   : {len(multi)} -> {sorted(multi)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
