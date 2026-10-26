#!/usr/bin/env python3
"""Markdown tables for the M2 evidence from the capture manifests (frozen vs candidate, per §3 row)."""
import json, pathlib, sys
S = pathlib.Path(sys.argv[1]); out = []
TIERS = [("guest", "guest"), ("free", "Free"), ("plus", "Plus"), ("pro", "Pro"), ("max", "Max"), ("expired", "expired"), ("halted", "halted")]
ROUTES = ["laws-ndps", "laws-uapa", "laws-bns", "laws-bnss", "laws-pss", "laws-mtp", "add-ndps-direct", "add-uapa-direct", "ndps-section-8", "ndps-schedule", "laws-unknown"]
def load(kind, tier):
    p = S / f"m2_{'baseline' if kind == 'frozen' else 'cand'}" / tier / "manifest.json"
    return {(r["key"], r["width"], r["theme"]): r for r in json.load(open(p))["rows"]} if p.exists() else {}
def cta(p):
    return "; ".join(f"{c['t']}→{c['href'] or '–'}{' (sheet)' if c['sheet'] else ''}" for c in p["cta"]) or "–"
def rows(p):
    ch = sum(1 for r in p["rows"] if r["tag"] == "summary"); sc = sum(1 for r in p["rows"] if "schedule-row" in r["cls"]); sec = sum(1 for r in p["rows"] if "section-row" in r["cls"])
    return f"{ch} ch / {sc} sch / {sec} sec" if (ch or sc or sec) else f"{p['rowCount']} (legacy)"
def sheet(r):
    s = r.get("sheet");
    if not s: return "–"
    d = s["probe"]["dialog"]; return f"{'open' if d and d.get('open') else 'closed'} {d.get('panelKind') if d else ''} {d['box']['w'] if d and d.get('box') else ''}px".strip()
out.append("| Route | Viewer | Width | Frozen meta / CTA / rows | Candidate meta / CTA / rows | Sheet (cand) | Status | Files (frozen → candidate) |\n|---|---|---|---|---|---|---|---|")
for tier, label in TIERS:
    F, C = load("frozen", tier), load("cand", tier)
    for key in ROUTES:
        for w in (390, 1280):
            f, c = F.get((key, w, "light")), C.get((key, w, "light"))
            if not c: continue
            fp, cp = (f or {}).get("probe", {}), c["probe"]
            fs = f"{fp.get('meta') or '–'} / {cta(fp) if fp else '–'} / {rows(fp) if fp else '–'}" if f else "–"
            cs = f"{cp.get('meta') or '–'} / {cta(cp)} / {rows(cp)}"
            out.append(f"| `{c['route']}` | {label} | {w} | {fs} | {cs} | {sheet(c)} | {c['status_chain'][-1][1]} | `{(f or {}).get('file','–')}` → `{c['file']}` |")
print("\n".join(out))
