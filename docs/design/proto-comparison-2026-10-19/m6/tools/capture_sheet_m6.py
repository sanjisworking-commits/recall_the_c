"""M6 (Q1): capture the upgrade sheet opened from the gated "Add task" entry on
the desktop Calendar, through the same headless-Chrome CDP driver as
`m1r/tools/capture_m1r.py` (imported from its path), and record what the
sheet does: it opens as a modal dialog, focus moves inside it, Esc closes it
and focus returns to the entry. Needs a server whose signed-in account lacks
`can_add_personal_calendar_tasks` (a Free account under `choices`).

    .venv/bin/python …/m6/tools/capture_sheet_m6.py --base http://127.0.0.1:8924 --out <dir> --label free-choices
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import time
import urllib.request

import websockets

HERE = pathlib.Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("capture_m1r", HERE.parents[2] / "m1r" / "tools" / "capture_m1r.py")
m1r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m1r)

STATE = """
(() => {
  const dlg = document.getElementById('cal-si-upgrade');
  const a = document.activeElement;
  const entry = document.querySelector('[data-cal-upgrade]');
  return {
    sheet: !!dlg, open: !!(dlg && dlg.open), activeInDialog: !!(dlg && dlg.contains(a)),
    active: a ? a.tagName + ' ' + (a.textContent || '').trim().slice(0, 40) : null,
    focusOnEntry: a === entry,
    title: dlg ? dlg.querySelector('h2').textContent : null,
    cta: dlg ? dlg.querySelector('a').getAttribute('href') : null,
    ctaText: dlg ? dlg.querySelector('a').textContent.trim() : null,
    price: dlg ? dlg.textContent.includes('₹') : null,
    editor: !!document.getElementById('cal-si-editor'), viewer: !!document.getElementById('cal-si-viewer'),
    gatedEntries: document.querySelectorAll('[data-cal-upgrade]').length,
    hScroll: document.documentElement.scrollWidth > window.innerWidth,
    ctaBox: dlg ? dlg.querySelector('a').getBoundingClientRect().toJSON() : null,
    closeBox: dlg ? dlg.querySelector('[data-study-close]').getBoundingClientRect().toJSON() : null,
  };
})()
"""


async def run(args) -> int:
    import httpx

    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = m1r.signin(client)
    prof = out / ".chrome-profile-sheet"; shutil.rmtree(prof, ignore_errors=True)
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
            for theme in args.themes.split(","):
                await m1r.cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False})
                await m1r.cdp(ws, st, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": theme}]})
                st["events"].clear()
                await m1r.cdp(ws, st, "Page.navigate", {"url": args.base + "/calendar"})
                try:
                    await m1r.wait_event(ws, st, "Page.loadEventFired")
                except TimeoutError:
                    pass
                await asyncio.sleep(0.6)
                await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": "document.fonts && document.fonts.ready", "awaitPromise": True})
                errors_before = [e for e in st["events"] if e.get("method") == "Runtime.exceptionThrown"]
                await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": "(() => { const b = document.querySelector('[data-cal-upgrade]'); b.focus(); b.click(); })()"})
                await asyncio.sleep(0.4)
                opened = (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": STATE, "returnByValue": True}))["result"]["value"]
                shot = await m1r.cdp(ws, st, "Page.captureScreenshot", {"format": "png"})
                name = f"{args.label}_free_calendar-sheet_1280x900_{theme}.png"
                data = base64.b64decode(shot["data"]); (out / name).write_bytes(data)
                # Tab twice: focus stays inside the modal dialog
                for _ in range(2):
                    await m1r.press_tab(ws, st)
                tabbed = (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": STATE, "returnByValue": True}))["result"]["value"]
                for ev in ("keyDown", "keyUp"):
                    await m1r.cdp(ws, st, "Input.dispatchKeyEvent", {"type": ev, "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
                await asyncio.sleep(0.3)
                closed = (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": STATE, "returnByValue": True}))["result"]["value"]
                exceptions = [e["params"]["exceptionDetails"].get("text") for e in st["events"] if e.get("method") == "Runtime.exceptionThrown"]
                rows.append({"file": name, "theme": theme, "sha256": hashlib.sha256(data).hexdigest(), "opened": opened, "afterTwoTabs": tabbed, "afterEscape": closed,
                             "exceptions": exceptions, "exceptionsBeforeOpen": len(errors_before)})
                print(name, "open", opened["open"], "focusIn", opened["activeInDialog"], "tabsStayIn", tabbed["activeInDialog"], "escClosed", not closed["open"],
                      "focusBack", closed["focusOnEntry"], "price", opened["price"], "cta", opened["cta"], "exceptions", exceptions, flush=True)
        (out / "manifest-sheet.json").write_text(json.dumps({"label": args.label, "base": args.base, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": rows}, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--themes", default="light,dark"); ap.add_argument("--debug-port", type=int, default=9336)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
