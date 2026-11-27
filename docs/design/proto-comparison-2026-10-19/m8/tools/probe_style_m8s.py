"""M8-S shared-style probe — the page probe of `m7/tools/probe_page_m7.py`
(same contrast and target arithmetic) with what the shared-style batch needs:

  * every low-contrast reading carries what it is, so an exclusion is never
    taken on trust: a selector path, the colour pair, and whether the text is
      disabled   inside a control that is `:disabled` or `aria-disabled="true"`
                 (genuinely inert — exempt from the contrast requirement)
      hidden     not visible to a sighted reader: visually-hidden (clipped to
                 1 px) or drawn in its own background colour (an unrevealed
                 cloze word)
    anything else is an ordinary failure;
  * named controls are measured wherever they appear (`--measure`, default the
    back link and the two sheet close controls);
  * a route may carry its own `scope` (a sheet opened by its URL is measured
    inside `dialog[open]`) and `open` (a selector clicked before measuring);
  * `--guest` skips the dev sign-in.

Headless Chrome over CDP with the dev fake Google sign-in of
`m1r/tools/capture_m1r.py`; the browser profile lives in a temporary directory
outside the repository and is removed. With `--shots <dir>` a PNG is written
for each route marked `"shot": [..]` at the listed `<width>-<theme>` pairs.

    .venv/bin/python …/m8/tools/probe_style_m8s.py --base http://127.0.0.1:8931 --out <dir> --label plus-monthly --routes routes.json [--guest] [--shots <dir>]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websockets

HERE = pathlib.Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("capture_m1r", HERE.parents[2] / "m1r" / "tools" / "capture_m1r.py")
m1r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m1r)

PROBE = r"""
(() => {
  const lum = c => { const a = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]; };
  const parse = s => { const m = (s || '').match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(parseFloat); return {rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1}; };
  const bgOf = el => { let e = el; while (e) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0.99) return c.rgb; e = e.parentElement; } return [255, 255, 255]; };
  const hex = c => '#' + c.map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const pair = el => { const fg = parse(getComputedStyle(el).color); const bg = bgOf(el); if (!fg) return {r: 21, fg: null, bg: hex(bg)}; const l1 = lum(fg.rgb), l2 = lum(bg); return {r: Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100, fg: hex(fg.rgb), bg: hex(bg)}; };
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || r.width <= 0 || r.height <= 0) return false; let p = e; while (p) { const s = getComputedStyle(p); if (s.display === 'none' || s.visibility === 'hidden') return false; p = p.parentElement; } return true; };
  const scope = __SCOPE__;
  const main = document.querySelector(scope) || document.querySelector('main') || document.body;
  const label = e => (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 48);
  const path = e => { const parts = []; let n = e; for (let i = 0; n && n.nodeType === 1 && i < 3; i++, n = n.parentElement) { parts.unshift(n.tagName.toLowerCase() + (n.classList.length ? '.' + [...n.classList].slice(0, 3).join('.') : '')); } return parts.join(' > '); };
  // genuinely inert: the text sits inside a control the browser or ARIA marks disabled
  const disabled = e => { const c = e.closest('button, input, select, textarea, a, [role="button"], fieldset'); if (!c) return false; return c.matches(':disabled') || c.getAttribute('aria-disabled') === 'true'; };
  // not visible to a sighted reader: clipped to a pixel, or drawn in its own background colour
  const hidden = (e, p) => { let n = e; while (n && n !== document.body) { const cs = getComputedStyle(n); const r = n.getBoundingClientRect(); if ((r.width <= 1 && r.height <= 1) || cs.clip === 'rect(0px, 0px, 0px, 0px)' || cs.clipPath === 'inset(50%)') return 'visually-hidden'; n = n.parentElement; } if (p.r <= 1.15) return 'same-as-background'; return ''; };
  const ctrls = [...main.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary')].filter(vis);
  const target = e => { if (e.tagName === 'INPUT' && (e.type === 'radio' || e.type === 'checkbox')) { const l = e.closest('label') || (e.id && document.querySelector('label[for="' + e.id + '"]')); if (l && vis(l)) return l; } return e; };
  const small = ctrls.map(e => { const t = target(e); const r = t.getBoundingClientRect(); return {t: label(t) || label(e), sel: path(e), w: Math.round(r.width), h: Math.round(r.height), viaLabel: t !== e}; }).filter(c => c.w < 44 || c.h < 44);
  const texts = [...main.querySelectorAll('*')].filter(e => vis(e) && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
  const readings = texts.map(e => { const p = pair(e); return {t: label(e), sel: path(e), r: p.r, fg: p.fg, bg: p.bg, disabled: disabled(e), hidden: p.r < 4.5 ? hidden(e, p) : ''}; });
  const low = readings.filter(x => x.r < 4.5);
  const measured = __MEASURE__.flatMap(sel => [...document.querySelectorAll(sel)].filter(vis).map(e => { const r = e.getBoundingClientRect(); return {sel, t: label(e), w: Math.round(r.width), h: Math.round(r.height), inert: e.matches(':disabled') || e.getAttribute('aria-disabled') === 'true'}; }));
  const fails = low.filter(x => !x.disabled && !x.hidden);
  return {
    title: document.title, scope: document.querySelector(scope) ? scope : 'main', hScroll: document.documentElement.scrollWidth > window.innerWidth,
    stylesheets: [...document.querySelectorAll('link[rel=stylesheet]')].map(l => (l.getAttribute('href') || '').split('/').pop()),
    controls: ctrls.length, smallTargets: small, texts: readings.length,
    minRatio: readings.length ? Math.min(...readings.map(x => x.r)) : null,
    minRatioOrdinary: readings.filter(x => !x.disabled && !(x.r < 4.5 && x.hidden)).reduce((m, x) => Math.min(m, x.r), 21),
    failing: fails, failingCount: fails.length,
    exemptDisabled: low.filter(x => x.disabled), exemptHidden: low.filter(x => !x.disabled && x.hidden),
    measured,
  };
})()
"""


async def run(args) -> int:
    import httpx

    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    shots = pathlib.Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    routes = json.loads(pathlib.Path(args.routes).read_text())
    cookies = []
    if not args.guest:
        cookies = m1r.signin(httpx.Client(base_url=args.base, timeout=20))
    prof = pathlib.Path(tempfile.mkdtemp(prefix="m8s-probe-profile-"))
    proc = subprocess.Popen([m1r.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                             f"--remote-debugging-port={args.debug_port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    measure = [s.strip() for s in args.measure.split(",") if s.strip()]
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{args.debug_port}/json")); break
            except Exception:
                time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            st = {"id": 0, "events": []}
            for method in ("Page.enable", "Network.enable", "Runtime.enable"):
                await m1r.cdp(ws, st, method)
            for c in cookies:
                await m1r.cdp(ws, st, "Network.setCookie", c)

            async def ev(expr, await_promise=False):
                return (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": await_promise}))["result"].get("value")

            for route in routes:
                scope = route.get("scope", args.scope)
                for size in args.widths.split(","):
                    w, h = (int(x) for x in size.split("x"))
                    for theme in args.themes.split(","):
                        await m1r.cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                        await m1r.cdp(ws, st, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": theme}]})
                        st["events"].clear()
                        await m1r.cdp(ws, st, "Page.navigate", {"url": args.base + route["path"]})
                        try:
                            await m1r.wait_event(ws, st, "Page.loadEventFired")
                        except TimeoutError:
                            pass
                        await asyncio.sleep(0.5)
                        await ev("document.fonts && document.fonts.ready.then(() => true)", True)
                        if route.get("open"):
                            # click each match in turn until a dialog is open (a page may carry a
                            # desktop and a phone entry point; only the visible one opens anything)
                            await ev(f"(() => {{ for (const e of document.querySelectorAll({json.dumps(route['open'])})) {{ e.click(); if (document.querySelector('dialog[open]')) return true; }} return false; }})()")
                            await asyncio.sleep(0.6)
                        probe = await ev(PROBE.replace("__SCOPE__", json.dumps(scope)).replace("__MEASURE__", json.dumps(measure)))
                        exceptions = [e["params"]["exceptionDetails"].get("text") for e in st["events"] if e.get("method") == "Runtime.exceptionThrown"]
                        row = {"key": route["key"], "path": route["path"], "width": w, "height": h, "theme": theme, **probe, "exceptions": exceptions}
                        rows.append(row)
                        if shots and f"{w}-{theme}" in route.get("shot", []):
                            metrics = await m1r.cdp(ws, st, "Page.getLayoutMetrics")
                            size_css = metrics.get("cssContentSize") or metrics["contentSize"]
                            clip = {"x": 0, "y": 0, "width": w, "height": min(int(size_css["height"]) + 1, 6000), "scale": 1}
                            png = await m1r.cdp(ws, st, "Page.captureScreenshot", {"format": "png", "clip": clip, "captureBeyondViewport": True})
                            (shots / f'{args.label}-{route["key"]}-{w}-{theme}.png').write_bytes(base64.b64decode(png["data"]))
                        print(f'{route["key"]:14} {w:4} {theme:5} hScroll={probe["hScroll"]} small={len(probe["smallTargets"])} '
                              f'FAIL={probe["failingCount"]} minOrdinary={probe["minRatioOrdinary"]} exemptDisabled={len(probe["exemptDisabled"])} '
                              f'exemptHidden={len(probe["exemptHidden"])} measured={[(m["sel"], m["w"], m["h"]) for m in probe["measured"]]} exc={len(exceptions)}', flush=True)
        (out / f"style-probe-{args.label}.json").write_text(json.dumps(
            {"label": args.label, "base": args.base, "guest": bool(args.guest), "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": rows}, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--routes", required=True); ap.add_argument("--widths", default="390x844,1280x900")
    ap.add_argument("--themes", default="light,dark"); ap.add_argument("--debug-port", type=int, default=9343)
    ap.add_argument("--scope", default="main"); ap.add_argument("--guest", action="store_true"); ap.add_argument("--shots", default="")
    ap.add_argument("--measure", default=".pg-back,.pg-sheet-close,.cal-si-dialog-head button")
    raise SystemExit(asyncio.run(run(ap.parse_args())))
