"""M7b: browser checks of the Learn page after the deck was removed and the
primary action became a bar — headless Chrome over CDP, the driver and dev fake
Google sign-in of `m1r/tools/capture_m1r.py`; the browser profile lives in a
temporary directory outside the repository.

  bar        where the action bar sits at four window sizes (a wide, tall
             window; a wide, short one; 640 x 450, a reduced-viewport reflow
             check; a phone): sticky to the window bottom, or ordinary flow.
             Browser zoom is not exercised
  focus      on the test mode in the wide, tall window: Tab through the page
             and count focus stops that end up underneath the bar
  tabs       the six mode tabs: links, which is current, which carry the
             completed mark
  fallback   the typed fallback, exercised: letters — type the opening words,
             "Check typed words", read the result; recite — type the passage,
             "Check accuracy", read the score, the accuracy map and whether the
             completion action appeared

Live speech is not exercised (no speech provider is configured locally).

    .venv/bin/python …/m7b/tools/check_learn_m7b.py --base http://127.0.0.1:8929 --out <dir> --stem /playground/laws/bns/sections/1/learn
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

BAR = r"""
(() => {
  const bars = [...document.querySelectorAll('.pg-learn-actionbar')];
  const bar = bars.find(b => getComputedStyle(b).display !== 'none') || bars[0];
  if (!bar) return null;
  const cs = getComputedStyle(bar); const r = bar.getBoundingClientRect();
  return {position: cs.position, display: cs.display, top: Math.round(r.top), bottom: Math.round(r.bottom),
          windowHeight: innerHeight, pageHeight: document.documentElement.scrollHeight,
          stuck: cs.position === 'sticky' && Math.round(r.bottom) === innerHeight && document.documentElement.scrollHeight > innerHeight,
          hScroll: document.documentElement.scrollWidth > innerWidth};
})()
"""
FOCUS = r"""
(() => {
  const a = document.activeElement; const stage = document.querySelector('[data-pg-learn]');
  if (!a || a === document.body || !stage || !stage.contains(a)) return null;
  const bar = [...document.querySelectorAll('.pg-learn-actionbar')].find(b => getComputedStyle(b).display !== 'none');
  const r = a.getBoundingClientRect(); const b = bar ? bar.getBoundingClientRect() : null;
  const inBar = !!(bar && bar.contains(a));
  const under = !!(b && !inBar && getComputedStyle(bar).position === 'sticky' && r.bottom > b.top + 1 && r.top < b.bottom - 1);
  return {t: (a.innerText || a.getAttribute('aria-label') || a.value || a.tagName).replace(/\s+/g, ' ').trim().slice(0, 32),
          top: Math.round(r.top), bottom: Math.round(r.bottom), inBar, underBar: under, offscreen: r.bottom < 0 || r.top > innerHeight, scrollY: Math.round(scrollY)};
})()
"""
TABS = r"""
(() => [...document.querySelectorAll('.pg-mode-tabs .mode-tab')].map(a => {
  const cs = getComputedStyle(a); const r = a.getBoundingClientRect();
  return {label: a.textContent.replace(/\s+/g, ' ').trim(), href: a.getAttribute('href'), link: a.tagName === 'A' && !!a.getAttribute('href'),
          current: a.getAttribute('aria-current') === 'page', done: a.classList.contains('is-done'),
          visible: cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 1 && r.height > 1, w: Math.round(r.width), h: Math.round(r.height)};
}))()
"""


async def run(args) -> int:
    import httpx

    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = m1r.signin(client)
    prof = pathlib.Path(tempfile.mkdtemp(prefix="m7b-learn-profile-"))
    proc = subprocess.Popen([m1r.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                             f"--remote-debugging-port={args.debug_port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rec: dict = {"base": args.base, "stem": args.stem, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "live_speech": "NOT RUN", "browser_zoom": "NOT RUN"}
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

            async def ev(expr):
                return (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))["result"].get("value")

            async def go(mode, w, h):
                await m1r.cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                await m1r.cdp(ws, st, "Page.navigate", {"url": f"{args.base}{args.stem}/{mode}"})
                try:
                    await m1r.wait_event(ws, st, "Page.loadEventFired")
                except TimeoutError:
                    pass
                await asyncio.sleep(0.6)

            async def type_into(selector, text):
                await ev(f"document.querySelector({json.dumps(selector)}).focus()")
                await m1r.cdp(ws, st, "Input.insertText", {"text": text})

            # bar ----------------------------------------------------------------
            rec["bar"] = []
            for label, w, h in (("wide, tall", 1280, 900), ("wide, short", 1280, 500), ("reduced viewport (reflow check)", 640, 450), ("phone", 390, 844)):
                await go("read", w, h)
                rec["bar"].append({"window": f"{w}x{h}", "case": label, **(await ev(BAR) or {"missing": True})})

            # focus --------------------------------------------------------------
            await go("test", 1280, 900)
            stops = []
            for _ in range(args.tabs):
                await m1r.press_tab(ws, st)
                # the page scrolls smoothly to the focused control: let it settle
                # (two equal readings) before measuring
                last = None
                for _ in range(20):
                    await asyncio.sleep(0.12)
                    y = await ev("Math.round(scrollY)")
                    if y == last:
                        break
                    last = y
                stop = await ev(FOCUS)
                if stop:
                    stops.append(stop)
            rec["focus"] = {"mode": "test", "window": "1280x900", "bar": await ev(BAR), "stops": len(stops),
                            "underBar": [s for s in stops if s["underBar"]], "offscreen": [s for s in stops if s["offscreen"]],
                            "reachedBarAction": any(s["inBar"] for s in stops), "trail": [s["t"] for s in stops][:40],
                            "scrolledTo": max((s["scrollY"] for s in stops), default=0),
                            "note": "each reading is taken after the browser's own focus scroll has settled"}

            # tabs ---------------------------------------------------------------
            await go("cloze", 1280, 900)
            rec["tabs"] = {"window": "1280x900", "mode": "cloze", "tabs": await ev(TABS),
                           "deck": await ev("document.querySelectorAll('.pg-learn-deck, .learn-deck-card').length")}

            # typed fallback -----------------------------------------------------
            await go("letters", 1280, 900)
            words = await ev("(document.querySelector('[data-letters-text]').getAttribute('data-letters-text') || '').split(/\\s+/).slice(0, 5).join(' ')")
            await type_into("[data-letters-manual]", words)
            await ev("document.querySelector('[data-letters-check-text]').click()")
            await asyncio.sleep(1.2)
            rec["fallback_letters"] = {
                "typedWords": len(words.split()),
                "fallbackVisible": await ev("(() => { const f = document.querySelector('[data-letters-fallback]'); return !!f && !f.hidden && f.getBoundingClientRect().height > 0; })()"),
                "status": await ev("(document.querySelector('[data-letters-status]') || {}).textContent"),
                "bar": await ev(BAR),
            }
            await go("recite", 1280, 900)
            before = await ev("(() => { const b = document.querySelector('[data-pg-complete]'); return {completeHidden: b.hidden, bar: getComputedStyle(document.querySelector('.pg-learn-actionbar')).display}; })()")
            passage = await ev("document.querySelector('[data-recite-text]').getAttribute('data-recite-text')")
            await type_into("[data-recite-manual]", passage)
            await ev("document.querySelector('[data-recite-check]').click()")
            await asyncio.sleep(1.5)
            rec["fallback_recite"] = {
                "before": before, "typedWords": len(passage.split()),
                "stats": await ev("(() => { const s = document.querySelector('[data-recite-stats]'); return s.hidden ? null : s.textContent; })()"),
                "mapWords": await ev("(() => { const m = document.querySelector('[data-recite-map]'); return m.hidden ? 0 : m.children.length; })()"),
                "mapHits": await ev("document.querySelectorAll('[data-recite-map] .is-hit').length"),
                "completeHidden": await ev("document.querySelector('[data-pg-complete]').hidden"),
                "bar": await ev(BAR),
            }
            rec["exceptions"] = [e["params"]["exceptionDetails"].get("text") for e in st["events"] if e.get("method") == "Runtime.exceptionThrown"]
        (out / "learn-check.json").write_text(json.dumps(rec, indent=1))
        for b in rec["bar"]:
            print(f'bar   {b["window"]:9} {b["case"]:24} position={b.get("position")} stuck={b.get("stuck")} hScroll={b.get("hScroll")}')
        f = rec["focus"]
        print(f'focus {f["stops"]} stops (page scrolled to {f["scrolledTo"]}px), under the bar: {len(f["underBar"])}, off screen: {len(f["offscreen"])}, reached the bar action: {f["reachedBarAction"]}')
        print("tabs ", [(t["label"], "current" if t["current"] else "", "done" if t["done"] else "", f'{t["w"]}x{t["h"]}') for t in rec["tabs"]["tabs"]], "deck elements:", rec["tabs"]["deck"])
        print("letters", rec["fallback_letters"]["status"], "| recite", rec["fallback_recite"]["stats"], "map", rec["fallback_recite"]["mapWords"], "hits", rec["fallback_recite"]["mapHits"],
              "complete hidden before/after:", rec["fallback_recite"]["before"]["completeHidden"], rec["fallback_recite"]["completeHidden"])
        print("exceptions", rec["exceptions"])
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--stem", default="/playground/laws/bns/sections/1/learn"); ap.add_argument("--tabs", type=int, default=44)
    ap.add_argument("--debug-port", type=int, default=9341)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
