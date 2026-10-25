#!/usr/bin/env python3
"""Interaction states for the M2 head: first chapter expanded, About open, keyboard focus on a row. Usage: capture_states.py BASE OUT [--signin]"""
import asyncio, base64, hashlib, json, pathlib, shutil, subprocess, sys, time, urllib.request, websockets, httpx
sys.path.insert(0, str(pathlib.Path(__file__).parent)); from capture_m2 import cdp, wait_event, CHROME, signin
BASE, OUT = sys.argv[1], pathlib.Path(sys.argv[2]); SIGNIN = "--signin" in sys.argv
ATTACH = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--attach-port=")), 0))
STATES = [
  ("chapter-open", "(() => { const d = document.querySelector('details.bareact-chapter'); d.open = true; d.querySelector('summary').focus(); return d.querySelector('summary').getAttribute('aria-expanded'); })()"),
  ("about-open", "(() => { document.querySelector('[data-bareact-info-toggle]').click(); return document.querySelector('[data-bareact-info-toggle]').getAttribute('aria-expanded'); })()"),
  ("row-focus", "(() => { const s = document.querySelectorAll('summary.bareact-chapter-row')[2]; s.focus(); return document.activeElement === s; })()"),
  ("schedule-focus", "(() => { const a = document.querySelector('a.bareact-schedule-row-link'); if (!a) return 'none'; a.focus(); return document.activeElement === a; })()"),
]
async def main():
    OUT.mkdir(parents=True, exist_ok=True); prof = OUT / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True); port = 9381
    client = httpx.Client(base_url=BASE, timeout=20); cookies = signin(client) if (SIGNIN and not ATTACH) else []
    if ATTACH:
        port = ATTACH; proc = None
    else:
        proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try: targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"))) if ATTACH else next(t for t in targets if t["type"] == "page"); man = []
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies: await cdp(ws, st, "Network.setCookie", c)
            for (w, h) in ((390, 844), (1280, 900)):
                for key, js in STATES:
                    await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                    st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": BASE + "/laws/ndps"})
                    try: await wait_event(ws, st, "Page.loadEventFired")
                    except TimeoutError: pass
                    await asyncio.sleep(0.6)
                    res = (await cdp(ws, st, "Runtime.evaluate", {"expression": js, "returnByValue": True}))["result"].get("value")
                    await asyncio.sleep(0.4)
                    focus = (await cdp(ws, st, "Runtime.evaluate", {"expression": "(() => { const e = document.activeElement; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return {tag: e.tagName, cls: e.className, outline: cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor, box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]}; })()", "returnByValue": True}))["result"]["value"]
                    data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"]); name = f"state_{key}_{w}x{h}.png"; (OUT / name).write_bytes(data)
                    man.append({"state": key, "width": w, "result": res, "focus": focus, "file": name, "sha256": hashlib.sha256(data).hexdigest()})
                    print(name, "->", res, "| focus:", focus, flush=True)
        (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    finally:
        if proc: proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
        elif ATTACH:
            try: urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{page['id']}")
            except Exception: pass
asyncio.run(main())
