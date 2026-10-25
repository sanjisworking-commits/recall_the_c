#!/usr/bin/env python3
"""PF-2: busy state on the sheet trigger under throttled network. Usage: verify_busy.py BASE OUT"""
import asyncio, base64, json, pathlib, shutil, subprocess, sys, time, urllib.request, websockets, httpx
sys.path.insert(0, str(pathlib.Path(__file__).parent)); from capture_m2 import cdp, wait_event, CHROME, signin
BASE, OUT = sys.argv[1], pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
GUEST = "--guest" in sys.argv
ATTACH = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--attach-port=")), 0))
TRIG = "(() => { const t = document.querySelector('.ActHead-btn'); const d = document.querySelector('dialog.pg-sheet'); return {text: t.textContent.trim(), busy: t.getAttribute('aria-busy'), cls: t.className, href: t.getAttribute('href'), pe: getComputedStyle(t).pointerEvents, cursor: getComputedStyle(t).cursor, opacity: getComputedStyle(t).opacity, open: d && d.open, active: document.activeElement.tagName + '.' + document.activeElement.className}; })()"
async def wait_open(ws, st, limit=20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        o = (await cdp(ws, st, "Runtime.evaluate", {"expression": "!!(document.querySelector('dialog.pg-sheet') && document.querySelector('dialog.pg-sheet').open)", "returnByValue": True}))["result"]["value"]
        if o: return round(time.monotonic() - t0, 2)
        await asyncio.sleep(0.25)
    return None
async def main():
    prof = OUT / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True); port = ATTACH or 9451
    client = httpx.Client(base_url=BASE, timeout=20); cookies = [] if (GUEST or ATTACH) else signin(client)
    if ATTACH:
        port = ATTACH; proc = None
    else:
        proc = None if ATTACH else subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = {}
    try:
        for _ in range(50):
            try: targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"))) if ATTACH else next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies: await cdp(ws, st, "Network.setCookie", c)
            for (w, h) in ((1280, 900), (390, 844)):
                await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561}); L = log[str(w)] = {}
                st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": BASE + "/laws/uapa"})
                try: await wait_event(ws, st, "Page.loadEventFired")
                except TimeoutError: pass
                await asyncio.sleep(0.8)
                # throttle: 2.5 s latency so the busy state is observable
                await cdp(ws, st, "Network.emulateNetworkConditions", {"offline": False, "latency": 2500, "downloadThroughput": -1, "uploadThroughput": -1})
                st["events"].clear()
                L["before"] = (await cdp(ws, st, "Runtime.evaluate", {"expression": TRIG, "returnByValue": True}))["result"]["value"]
                await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('.ActHead-btn').click(); document.querySelector('.ActHead-btn').click(); document.querySelector('.ActHead-btn').click();"})
                await asyncio.sleep(0.3)
                L["during"] = (await cdp(ws, st, "Runtime.evaluate", {"expression": TRIG, "returnByValue": True}))["result"]["value"]
                data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"]); (OUT / f"busy_during_{w}.png").write_bytes(data)
                L["open_after_s"] = await wait_open(ws, st); await asyncio.sleep(0.4)
                reqs = [e for e in st["events"] if e.get("method") == "Network.requestWillBeSent" and "/add" in e["params"]["request"]["url"]]
                L["add_requests_sent"] = len(reqs)
                L["after_open"] = (await cdp(ws, st, "Runtime.evaluate", {"expression": TRIG, "returnByValue": True}))["result"]["value"]
                await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('dialog.pg-sheet .pg-sheet-close').click()"}); await asyncio.sleep(0.6)
                L["after_close"] = (await cdp(ws, st, "Runtime.evaluate", {"expression": TRIG, "returnByValue": True}))["result"]["value"]
                await cdp(ws, st, "Network.emulateNetworkConditions", {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
                for k, v in L.items(): print(w, k, v if not isinstance(v, dict) else {x: v[x] for x in ('text', 'busy', 'cls', 'pe', 'cursor', 'opacity', 'open', 'active', 'href') if x in v})
            (OUT / "busy_verification.json").write_text(json.dumps(log, indent=1))
    finally:
        if proc: proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
        elif ATTACH:
            try: urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{page['id']}")
            except Exception: pass
asyncio.run(main())
