#!/usr/bin/env python3
"""Diff two capture manifests (baseline vs candidate) by route/width/theme: probe deltas + pixel identity."""
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
key = lambda r: (r["route"], r["width"], r["theme"])
A = {key(r): r for r in a["rows"]}; B = {key(r): r for r in b["rows"]}
print("| Route | W | Theme | Status chain | Screen key | Top nav | Phone bar | Current | Account slot | Zoom | PNG identical |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
def bar(p): return "none" if not p["phoneBarVisible"] else ("legacy 4-tab" if "is-guest" in (p["phoneBarClass"] or "") else f"{len(p['phoneBar'])}-tab")
def cur(r, p): return ",".join(l["href"] for l in (p["phoneBar"] if r["width"] < 561 else p["topNav"]) if l["current"]) or "—"
def acct(p): return ((p["account"] or {}).get("text") or "—")[:32]
def zoom(p): return "locked" if p["viewport"] and "user-scalable=no" in p["viewport"] else "free"
def d(x, y): return f"{x}" if x == y else f"{x} → **{y}**"
for k in sorted(B, key=lambda k: (a["rows"].index(A[k]) if k in A else 999)):
    ra, rb = A.get(k), B[k]; pa, pb = (ra or rb)["probe"], rb["probe"]
    chain_a = " → ".join(f"{u.split(a['base'],1)[-1] or '/'} {s}" for u, s in (ra or rb)["status_chain"]); chain_b = " → ".join(f"{u.split(b['base'],1)[-1] or '/'} {s}" for u, s in rb["status_chain"])
    same = ra is not None and ra["sha256"] == rb["sha256"]
    print(f"| `{k[0]}` | {k[1]} | {k[2]} | {d(chain_a, chain_b)} | {d(pa['mscreen'], pb['mscreen'])} | {d('visible' if pa['topNavVisible'] else 'hidden', 'visible' if pb['topNavVisible'] else 'hidden')} | {d(bar(pa), bar(pb))} | {d(cur(ra or rb, pa), cur(rb, pb))} | {d(acct(pa), acct(pb))} | {d(zoom(pa), zoom(pb))} | {'yes' if same else 'no'} |")
