"""M3-F02 / M3-A01 keyboard check for the collapsible Part headers.

Headless Chrome over CDP (same plumbing as ../../m1r/tools/capture_m1r.py):
Tab from the top of /browse until a Part toggle is focused with a visible
:focus-visible outline, press Enter (collapse: aria-expanded flips, only that
Part's body hides), press Space (expand), then toggle a legend filter and
clear it. One JSON row per width; nothing is persisted on the server.

    PYTHONPATH=src .venv/bin/python docs/design/proto-comparison-2026-10-19/m3/tools/keyboard_m3.py --base http://127.0.0.1:8918 --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import shutil
import subprocess
import time
import urllib.request

import websockets

HERE = pathlib.Path(__file__).resolve()
TOOL = HERE.parents[2] / "m1r" / "tools" / "capture_m1r.py"
spec = importlib.util.spec_from_file_location("capture_m1r", TOOL)
m1r = importlib.util.module_from_spec(spec); spec.loader.exec_module(m1r)

STATE = """(() => {
  const ts = [...document.querySelectorAll('[data-browse-part-toggle]')];
  const a = document.activeElement;
  const idx = ts.indexOf(a);
  const row = (t) => { const b = document.getElementById(t.getAttribute('aria-controls')); const cs = getComputedStyle(t);
    return {expanded: t.getAttribute('aria-expanded'), bodyHidden: b ? b.hidden : null, bodyDisplay: b ? getComputedStyle(b).display : null,
            outline: cs.outlineStyle + ' ' + cs.outlineWidth, focusVisible: t.matches(':focus-visible'), box: (() => { const r = t.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })()}; };
  return {focusedIsToggle: idx >= 0, focusedIndex: idx, active: a ? (a.tagName + (a.className ? '.' + String(a.className).split(' ')[0] : '')) : null,
          first: ts.length ? row(ts[0]) : null, second: ts.length > 1 ? row(ts[1]) : null, toggles: ts.length};
})()"""

async def key(ws, st, name, code, vk):
    for t in ("keyDown", "keyUp"):
        await m1r.cdp(ws, st, "Input.dispatchKeyEvent", {"type": t, "key": name, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk, "text": "\r" if name == "Enter" else (" " if name == " " else "")})

async def evaluate(ws, st, expr):
    return (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}))["result"].get("value")

async def run(args):
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    prof = out / ".chrome-profile-kb"; shutil.rmtree(prof, ignore_errors=True)
    proc = subprocess.Popen([m1r.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={args.debug_port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{args.debug_port}/json")); break
            except Exception: time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            st = {"id": 0, "events": []}
            await m1r.cdp(ws, st, "Page.enable"); await m1r.cdp(ws, st, "Runtime.enable")
            for w, h in [tuple(map(int, x.split("x"))) for x in args.widths.split(",")]:
                await m1r.cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                await m1r.cdp(ws, st, "Page.navigate", {"url": args.base + "/browse"})
                try: await m1r.wait_event(ws, st, "Page.loadEventFired")
                except TimeoutError: pass
                await asyncio.sleep(0.5)
                await evaluate(ws, st, "document.activeElement && document.activeElement.blur(); window.scrollTo(0,0); true")
                reached = None
                for n in range(1, 40):
                    await m1r.press_tab(ws, st)
                    s = await evaluate(ws, st, STATE)
                    if s["focusedIsToggle"]:
                        reached = {"tabs": n, **s}; break
                row = {"width": w, "height": h, "reached_toggle": reached}
                if reached:
                    await key(ws, st, "Enter", "Enter", 13); await asyncio.sleep(0.15)
                    row["after_enter"] = await evaluate(ws, st, STATE)
                    await key(ws, st, " ", "Space", 32); await asyncio.sleep(0.15)
                    row["after_space"] = await evaluate(ws, st, STATE)
                row["legend"] = await evaluate(ws, st, """(() => { const i = document.querySelector('[data-browse-filter]'); if (!i) return 'no legend';
                    i.click(); const pressed = i.getAttribute('aria-pressed'); const hidden = document.querySelectorAll('.browse-article-card.is-mark-hidden').length;
                    i.click(); return {pressed, hiddenWhileFiltered: hidden, afterClear: document.querySelectorAll('.browse-article-card.is-mark-hidden').length, cleared: i.getAttribute('aria-pressed')}; })()""")
                rows.append(row)
    finally:
        proc.terminate()
    (out / "keyboard.json").write_text(json.dumps({"base": args.base, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": rows}, indent=1))
    for r in rows:
        rt = r["reached_toggle"]; ae = r.get("after_enter") or {}; sp = r.get("after_space") or {}
        print(f"{r['width']}x{r['height']}: toggle focused after {rt and rt['tabs']} Tabs, focus-visible={rt and rt['first']['focusVisible']}, outline={rt and rt['first']['outline']}, box={rt and rt['first']['box']}; "
              f"Enter→ expanded={ae.get('first',{}).get('expanded')} bodyDisplay={ae.get('first',{}).get('bodyDisplay')} secondStill={ae.get('second',{}).get('expanded')}; "
              f"Space→ expanded={sp.get('first',{}).get('expanded')} bodyDisplay={sp.get('first',{}).get('bodyDisplay')}; legend={r['legend']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--widths", default="390x844,1280x900"); ap.add_argument("--debug-port", type=int, default=9391)
    asyncio.run(run(ap.parse_args()))
