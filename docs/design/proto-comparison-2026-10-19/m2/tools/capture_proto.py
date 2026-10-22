#!/usr/bin/env python3
"""Capture prototype Act-head references from the local wrapper server (8911) with headless Chrome."""
import asyncio, base64, hashlib, json, pathlib, shutil, subprocess, sys, time, urllib.request, websockets
sys.path.insert(0, str(pathlib.Path(__file__).parent)); from capture_m2 import cdp, wait_event, CHROME
BASE = "http://127.0.0.1:8911"
VIEWERS = ["guest", "signedIn", "plus", "pro", "max", "expired", "halted"]
CASES = []
for v in VIEWERS:
    for law in ("ndps", "uapa", "bns"):
        CASES.append((f"act-{law}-{v}", f"screen=act&law={law}&viewer={v}&pin=1"))
    CASES.append((f"act-uapa-{v}-sheet", f"screen=act&law=uapa&viewer={v}&sheet=1&pin=1"))
    CASES.append((f"act-ndps-{v}-sheet", f"screen=act&law=ndps&viewer={v}&sheet=1&pin=1"))
PROBE = r"""(() => { const t = e => e ? (e.innerText||'').replace(/\s+/g,' ').trim() : null; const head = document.querySelector('[data-screen-label="Bare Act head"]');
 const rows = head ? [...head.querySelectorAll('[role=button], div[style*="min-height:56px"], div[style*="min-height:48px"]')].map(t) : [];
 const h2 = head ? head.querySelector('h2') : null; const dlg = document.querySelector('[role=dialog]');
 return {h2: t(h2), h2Font: h2 ? getComputedStyle(h2).fontSize : null, kicker: head ? t(head.querySelector('p')) : null, meta: head ? t([...head.querySelectorAll('p')][1]) : null,
   buttons: head ? [...head.querySelectorAll('button')].map(t) : [], rows, dialog: dlg ? {text: t(dlg).slice(0,300), w: Math.round(dlg.getBoundingClientRect().width)} : null, text: document.body.innerText.slice(0, 1200)}; })()"""
async def main():
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True); prof = out / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True); port = 9361
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try: targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page"); man = {"base": BASE, "rows": []}
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Runtime.enable")
            for key, q in CASES:
                for surface, (w, h) in (("phone", (390, 844)), ("desktop", (1280, 900))):
                    await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
                    st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": f"{BASE}/{surface}.html?{q}"})
                    try: await wait_event(ws, st, "Page.loadEventFired")
                    except TimeoutError: pass
                    await asyncio.sleep(1.2); await cdp(ws, st, "Runtime.evaluate", {"expression": "document.fonts && document.fonts.ready", "awaitPromise": True})
                    probe = (await cdp(ws, st, "Runtime.evaluate", {"expression": PROBE, "returnByValue": True}))["result"]["value"]
                    data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"]); name = f"proto_{key}_{surface}.png"; (out / name).write_bytes(data)
                    man["rows"].append({"key": key, "surface": surface, "query": q, "file": name, "sha256": hashlib.sha256(data).hexdigest(), "probe": probe})
                    print(f"{name:48s} h2={probe['h2'][:40] if probe['h2'] else None} meta={probe['meta']} btn={probe['buttons'][:3]} rows={len(probe['rows'])} dlg={bool(probe['dialog'])}", flush=True)
        (out / "manifest.json").write_text(json.dumps(man, indent=1))
    finally: proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
asyncio.run(main())
