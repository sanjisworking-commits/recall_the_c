"""M7 page-level probe: what `capture_m1r.py` measures for the shell, measured
for the page content inside <main>.

Per route × width × theme (headless Chrome over CDP, the dev fake Google
sign-in of `m1r/tools/capture_m1r.py`; the browser profile lives in a
temporary directory outside the repository and is removed):

  hScroll        the document is wider than the viewport
  smallTargets   visible links and buttons in <main> narrower or shorter than 44 px
  lowContrast    visible leaf text in <main> whose colour against the first opaque
                 background behind it is under 4.5:1 (WCAG ratio)
  minRatio       the lowest such ratio on the page
  tabTrail       the first Tab stops inside <main>: label and whether the focused
                 control shows an outline or a box-shadow ring
  exceptions     script exceptions raised while the page loaded

    .venv/bin/python …/m7/tools/probe_page_m7.py --base http://127.0.0.1:8927 --out <dir> --label free-choices --routes routes.json
"""
from __future__ import annotations

import argparse
import asyncio
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
  const ratio = el => { const fg = parse(getComputedStyle(el).color); if (!fg) return 21; const l1 = lum(fg.rgb), l2 = lum(bgOf(el)); return Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100; };
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || r.width <= 0 || r.height <= 0) return false; let p = e; while (p) { const s = getComputedStyle(p); if (s.display === 'none' || s.visibility === 'hidden') return false; p = p.parentElement; } return true; };
  const main = document.querySelector('main') || document.body;
  const label = e => (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  const ctrls = [...main.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary')].filter(vis);
  const small = ctrls.map(e => { const r = e.getBoundingClientRect(); return {t: label(e), w: Math.round(r.width), h: Math.round(r.height)}; }).filter(c => c.w < 44 || c.h < 44);
  const texts = [...main.querySelectorAll('*')].filter(e => vis(e) && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
  const ratios = texts.map(e => ({t: label(e), r: ratio(e)}));
  return {
    title: document.title, hScroll: document.documentElement.scrollWidth > window.innerWidth,
    controls: ctrls.length, smallTargets: small,
    lowContrast: ratios.filter(x => x.r < 4.5), minRatio: ratios.length ? Math.min(...ratios.map(x => x.r)) : null, texts: ratios.length,
  };
})()
"""
FOCUS = r"""
(() => { const a = document.activeElement; if (!a || a === document.body) return null; const cs = getComputedStyle(a);
  const main = document.querySelector('main');
  return {inMain: !!(main && main.contains(a)), t: (a.innerText || a.getAttribute('aria-label') || a.tagName).replace(/\s+/g, ' ').trim().slice(0, 40),
          ring: (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== 'none')}; })()
"""


async def run(args) -> int:
    import httpx

    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    routes = json.loads(pathlib.Path(args.routes).read_text())
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = m1r.signin(client)
    prof = pathlib.Path(tempfile.mkdtemp(prefix="m7-probe-profile-"))
    proc = subprocess.Popen([m1r.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                             f"--remote-debugging-port={args.debug_port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
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
            for route in routes:
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
                        await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": "document.fonts && document.fonts.ready", "awaitPromise": True})
                        probe = (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": PROBE, "returnByValue": True}))["result"]["value"]
                        trail = []
                        if theme == "light":
                            for _ in range(args.tabs):
                                await m1r.press_tab(ws, st)
                                stop = (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": FOCUS, "returnByValue": True}))["result"].get("value")
                                if stop and stop["inMain"]:
                                    trail.append({"t": stop["t"], "ring": bool(stop["ring"])})
                        exceptions = [e["params"]["exceptionDetails"].get("text") for e in st["events"] if e.get("method") == "Runtime.exceptionThrown"]
                        row = {"key": route["key"], "path": route["path"], "width": w, "height": h, "theme": theme, **probe,
                               "tabTrail": trail, "exceptions": exceptions}
                        rows.append(row)
                        print(f'{route["key"]:12} {w}x{h} {theme:5} hScroll={probe["hScroll"]} small={len(probe["smallTargets"])} '
                              f'low={len(probe["lowContrast"])} min={probe["minRatio"]} tabs={len(trail)} noRing={sum(1 for t in trail if not t["ring"])} exc={len(exceptions)}', flush=True)
        (out / "page-probe.json").write_text(json.dumps({"label": args.label, "base": args.base, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": rows}, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--routes", required=True); ap.add_argument("--widths", default="390x844,1280x900")
    ap.add_argument("--themes", default="light,dark"); ap.add_argument("--tabs", type=int, default=24)
    ap.add_argument("--debug-port", type=int, default=9337)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
