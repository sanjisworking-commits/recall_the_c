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

# ── Cluster-level relations ────────────────────────────────────────────────
#
# CURRICULUM JUDGEMENT, NOT MIGRATION. Nothing below comes from the legacy
# seed; these are decisions about which parts of the Constitution sit next to
# each other pedagogically, and they should be reviewed as such.
#
# Two principles, applied consistently:
#
#   RELATED  a direct structural or doctrinal link — the same organ at Union
#            and State level, a right and its remedy, an institution and the
#            function it performs, or two provisions of one Part that are
#            habitually read together.
#
#   EXPLORE  deliberately further away but still coherent: a different organ,
#            or the same subject seen from another Part. Explore is curated
#            novelty, not "anything unrelated" — the point is to widen the
#            lens, not to randomise it.
#
# Declared one way and closed symmetrically below, because the selector only
# consults the *anchor's* lists: an asymmetric declaration would make Article
# 14 -> 21 Related while 21 -> 14 fell through to the legacy scorer.
RELATED_CLUSTERS: dict[str, list[str]] = {
    # Part III reads as one fabric: rights, their remedy, and the groups they
    # protect.
    "equality": ["liberty", "rights_against_exploitation", "cultural_rights"],
    "liberty": ["constitutional_remedies", "rights_against_exploitation"],
    "rights_against_exploitation": ["directive_principles"],
    "religion": ["cultural_rights", "equality", "liberty"],
    "cultural_rights": ["liberty"],
    "constitutional_remedies": ["high_courts", "union_judiciary"],
    # Part IV and IVA are the companion aspirations to Part III.
    "directive_principles": ["fundamental_duties", "equality"],
    "fundamental_duties": ["citizenship", "cultural_rights"],
    # Who belongs, and to what territory.
    "citizenship": ["equality", "union_territory"],
    "union_territory": ["centre_state", "state_executive"],
    # The executive, its advisers, and the powers it exercises alone.
    "executive_union": ["council_of_ministers", "pardoning", "parliament"],
    "council_of_ministers": ["state_executive", "parliament"],
    "pardoning": ["state_executive", "union_judiciary"],
    "state_executive": ["state_legislature", "executive_union"],
    # Legislatures, and the power to legislate when they are not sitting.
    "parliament": ["state_legislature", "ordinance"],
    "ordinance": ["state_legislature", "executive_union"],
    "state_legislature": ["centre_state"],
    # Courts, and the bodies that displace them.
    "union_judiciary": ["high_courts", "tribunals"],
    "high_courts": ["tribunals"],
    "tribunals": ["services"],
    # Money, audit, and the machinery that spends it.
    "cag": ["finance", "parliament", "services"],
    "finance": ["centre_state", "trade", "property"],
    "property": ["trade"],
    "trade": ["centre_state"],
    "services": ["equality"],
    # Local government is the third tier of the same federal idea.
    "panchayats": ["municipalities", "state_legislature", "elections"],
    "municipalities": ["state_legislature", "elections"],
    "elections": ["parliament", "state_legislature"],
    # Federal stress, and the power to change the text itself.
    "centre_state": ["parliament", "emergency"],
    "emergency": ["executive_union", "state_executive"],
    "amendment": ["parliament", "union_judiciary", "centre_state"],
    "official_language": ["cultural_rights", "union_judiciary"],
}

EXPLORE_CLUSTERS: dict[str, list[str]] = {
    # From a right, out to the machinery that delivers or suspends it.
    "equality": ["services", "panchayats"],
    "liberty": ["emergency", "union_judiciary"],
    "rights_against_exploitation": ["services", "municipalities"],
    "religion": ["official_language", "citizenship"],
    "cultural_rights": ["official_language", "union_territory"],
    "constitutional_remedies": ["emergency", "tribunals"],
    "directive_principles": ["panchayats", "finance"],
    "fundamental_duties": ["elections", "official_language"],
    "citizenship": ["elections", "liberty"],
    "union_territory": ["parliament", "finance"],
    # From an organ, out to a different organ or the money behind it.
    "executive_union": ["union_judiciary", "cag"],
    "council_of_ministers": ["elections", "ordinance"],
    "pardoning": ["liberty", "high_courts"],
    "parliament": ["finance", "constitutional_remedies"],
    "ordinance": ["emergency", "centre_state"],
    "state_executive": ["panchayats", "high_courts"],
    "state_legislature": ["cag", "trade"],
    "union_judiciary": ["services", "amendment"],
    "high_courts": ["services", "municipalities"],
    "tribunals": ["centre_state", "trade"],
    "cag": ["property", "municipalities"],
    "finance": ["municipalities", "directive_principles"],
    "property": ["liberty", "panchayats"],
    "trade": ["directive_principles", "municipalities"],
    "services": ["union_judiciary", "elections"],
    "panchayats": ["directive_principles", "finance"],
    "municipalities": ["property", "trade"],
    "elections": ["citizenship", "high_courts"],
    "centre_state": ["union_judiciary", "trade"],
    "emergency": ["liberty", "finance"],
    "amendment": ["equality", "emergency"],
    "official_language": ["citizenship", "high_courts"],
}


def _symmetric(declared: dict[str, list[str]]) -> dict[str, list[str]]:
    """Close a declaration both ways, preserving declaration order."""
    out: dict[str, list[str]] = {key: list(values) for key, values in declared.items()}
    for source, targets in declared.items():
        for target in targets:
            peers = out.setdefault(target, [])
            if source not in peers:
                peers.append(source)
    return {key: sorted(set(values)) for key, values in out.items()}


def main() -> int:
    seed = json.loads(SEED.read_text(encoding="utf-8"))

    related = _symmetric(RELATED_CLUSTERS)
    explore = _symmetric(EXPLORE_CLUSTERS)

    # A pair cannot be both. Related is the more familiar reading, so it wins,
    # and the Explore side is dropped rather than left to resolve by accident.
    for cid, peers in explore.items():
        explore[cid] = [p for p in peers if p not in set(related.get(cid, []))]

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
            "related_clusters": related.get(cid, []),
            "explore_clusters": explore.get(cid, []),
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
            "related_clusters / explore_clusters are curriculum judgement, "
            "not migration: no cluster-level relations existed in the legacy "
            "data. Related means a direct structural or doctrinal link "
            "(Union/State counterpart, right and remedy, institution and "
            "function); Explore means deliberate distance that still widens "
            "the lens. Declared one way and closed symmetrically, because the "
            "selector consults only the anchor's lists.",
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

    def _shown(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT))
        except ValueError:  # regenerated elsewhere, e.g. by the drift test
            return str(path)

    families_null = sum(1 for c in clusters.values() if c["family"] is None)
    print(f"wrote {_shown(OUT)}")
    print(f"wrote {_shown(PACKAGED)}")
    print(f"  families        : {len(FAMILIES)}")
    print(f"  clusters        : {len(clusters)} ({families_null} with family: null)")
    print(f"  articles        : {len(article_meta)}")
    print(f"  article_edges   : {len(article_edges)}")
    multi = {a: m['clusters'] for a, m in article_meta.items() if len(m['clusters']) > 1}
    print(f"  multi-cluster   : {len(multi)} -> {sorted(multi)}")
    print(f"  related links   : {sum(len(v) for v in related.values()) // 2} pairs")
    print(f"  explore links   : {sum(len(v) for v in explore.values()) // 2} pairs")
    bare = [c for c in clusters if not related.get(c) and not explore.get(c)]
    print(f"  clusters with no relations: {len(bare)} {bare}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
