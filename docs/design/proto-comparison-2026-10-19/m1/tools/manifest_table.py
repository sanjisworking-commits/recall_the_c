#!/usr/bin/env python3
"""Render a capture manifest.json (from capture_local.py) as a Markdown evidence table."""
import json, sys, pathlib
m = json.load(open(sys.argv[1]))
rows = m["rows"]
print(f"Label `{m['label']}` · viewer `{m['viewer']}` · base `{m['base']}` · captured {m['captured_at']} · {m['chrome']}\n")
print("| Route | W×H | Theme | Status chain | Screen key | Top nav | Phone bar | Current | Account slot | Zoom meta | File | SHA-256 (12) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    p = r["probe"]; chain = " → ".join(f"{u.split(m['base'],1)[-1] or '/'} {s}" for u, s in r["status_chain"])
    cur = [l["href"] for l in (p["phoneBar"] if r["width"] < 561 else p["topNav"]) if l["current"]]
    bar = "none" if not p["phoneBarVisible"] else ("legacy 4-tab" if "is-guest" in (p["phoneBarClass"] or "") else f"{len(p['phoneBar'])}-tab")
    nav = "visible" if p["topNavVisible"] else "hidden"
    acct = (p["account"] or {}).get("text") or "—"
    zoom = "locked" if p["viewport"] and "user-scalable=no" in p["viewport"] else ("free" if p["viewport"] else "—")
    print(f"| `{r['route']}` | {r['width']}×{r['height']} | {r['theme']} | {chain} | {p['mscreen'] or '—'} | {nav} | {bar} | {', '.join(cur) or '—'} | {acct[:40]} | {zoom} | `{r['file']}` | `{r['sha256'][:12]}` |")
