"""Compare two `readback_m8.py` outputs row by row.

For every (state, tier model, page) it reports whether the page body is
byte-identical (after whitespace and CSRF-token normalisation, as recorded in
`main_sha`) and, where it is not, which recorded fields differ. This is the
guard that a presentation batch changed only the pages it meant to.

    python …/m8/tools/diff_readback_m8.py <baseline>/readback.json <candidate>/readback.json [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FIELDS = ("status", "location", "header", "title", "h1", "add_title", "gate", "pg_kind", "plan_form", "links", "forms",
          "law_item_links", "mentions_bns", "device_lede")


def load(path: str) -> tuple[dict, dict]:
    data = json.loads(Path(path).read_text())
    return data, {(r["state"], r["tier_model"], r["page"]): r for r in data["rows"] if r["state"] != "device_log"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline"); ap.add_argument("candidate"); ap.add_argument("--out", default="")
    args = ap.parse_args()
    base_doc, base = load(args.baseline)
    cand_doc, cand = load(args.candidate)
    same, changed, only = [], [], []
    for key in sorted(set(base) | set(cand)):
        b, c = base.get(key), cand.get(key)
        if b is None or c is None:
            only.append({"row": key, "in": "baseline" if c is None else "candidate"})
            continue
        # link order is compared as a set: the order of law cards on a read-only home is not
        # stable between two renders of the same state (a tie the page does not break)
        norm = lambda v: sorted(v) if isinstance(v, list) else v
        diffs = {f: {"baseline": b.get(f), "candidate": c.get(f)} for f in FIELDS if norm(b.get(f)) != norm(c.get(f))}
        if b.get("main_sha") == c.get("main_sha") and not diffs:
            same.append(key)
        else:
            changed.append({"row": key, "reach": c.get("reach", ""), "body_identical": b.get("main_sha") == c.get("main_sha"), "fields": diffs})
    report = {"baseline_sha": base_doc.get("sha"), "candidate_sha": cand_doc.get("sha"), "identical_rows": len(same),
              "changed_rows": len(changed), "rows_in_one_only": only, "changed": changed,
              "identical": [list(k) for k in same]}
    if args.out:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        (out / "readback-diff.json").write_text(json.dumps(report, indent=1, default=str))
    print(f'baseline {report["baseline_sha"]} → candidate {report["candidate_sha"]}: {len(same)} rows identical, {len(changed)} changed, {len(only)} in one only')
    by_state: dict = {}
    for ch in changed:
        state, model, page = ch["row"]
        by_state.setdefault((state, model), []).append(page + ("" if ch["fields"] else "*"))
    for (state, model), pages in sorted(by_state.items()):
        print(f"  {state:20} {model:8} {', '.join(pages)}")
    print("  (* = body differs but no recorded field does)")


if __name__ == "__main__":
    main()
