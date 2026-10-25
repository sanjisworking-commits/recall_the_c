#!/usr/bin/env python3
"""Keyboard trace on the M2 head: Tab through the band and the first rows, Enter on a chapter row, Escape on the sheet. Usage: capture_keyboard.py BASE OUT [--signin]"""
import asyncio, time, base64, hashlib, json, pathlib, shutil, subprocess, sys, time, urllib.request, websockets, httpx
sys.path.insert(0, str(pathlib.Path(__file__).parent)); from capture_m2 import cdp, wait_event, CHROME, signin
BASE, OUT = sys.argv[1], pathlib.Path(sys.argv[2]); SIGNIN = "--signin" in sys.argv
ATTACH = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--attach-port=")), 0))
ACTIVE = "(() => { const e = document.activeElement; if (!e || e === document.body) return {tag:'BODY'}; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return {tag: e.tagName, cls: (e.className||'').toString().slice(0,40), text: (e.innerText||e.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().slice(0,50), outline: cs.outlineStyle + ' ' + cs.outlineWidth, box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)], expanded: e.getAttribute('aria-expanded'), inDialog: !!e.closest('dialog')}; })()"
async def key(ws, st, k, code=None, text=None):
    text = text or {"Enter": "\r", " ": " "}.get(k)
    base = {"key": k, "code": code or k, "windowsVirtualKeyCode": {"Tab": 9, "Enter": 13, "Escape": 27, " ": 32}.get(k, 0)}
    await cdp(ws, st, "Input.dispatchKeyEvent", {"type": "keyDown", **base, **({"text": text} if text else {})})
    await cdp(ws, st, "Input.dispatchKeyEvent", {"type": "keyUp", **base})
    await asyncio.sleep(0.15)
async def wait_open(ws, st, limit=20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        o = (await cdp(ws, st, "Runtime.evaluate", {"expression": "!!(document.querySelector('dialog.pg-sheet') && document.querySelector('dialog.pg-sheet').open)", "returnByValue": True}))["result"]["value"]
        if o: return round(time.monotonic() - t0, 2)
        await asyncio.sleep(0.25)
    return None
async def main():
    OUT.mkdir(parents=True, exist_ok=True); prof = OUT / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True); port = 9382
    client = httpx.Client(base_url=BASE, timeout=20); cookies = signin(client) if (SIGNIN and not ATTACH) else []
    if ATTACH:
        port = ATTACH; proc = None
    else:
        proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try: targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"))) if ATTACH else next(t for t in targets if t["type"] == "page"); trace = []
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies: await cdp(ws, st, "Network.setCookie", c)
            for (w, h) in ((1280, 900), (390, 844)):
                await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": BASE + "/laws/uapa"})
                try: await wait_event(ws, st, "Page.loadEventFired")
                except TimeoutError: pass
                await asyncio.sleep(0.6)
                # Start tabbing from the back link so the trace is the head's own order.
                await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('.ActHead-back').focus()"})
                steps = []
                for i in range(7):
                    a = (await cdp(ws, st, "Runtime.evaluate", {"expression": ACTIVE, "returnByValue": True}))["result"]["value"]; steps.append(a)
                    if a.get("tag") == "SUMMARY" and a.get("expanded") == "false":
                        await key(ws, st, "Enter"); await asyncio.sleep(0.3)
                        b = (await cdp(ws, st, "Runtime.evaluate", {"expression": ACTIVE, "returnByValue": True}))["result"]["value"]; steps.append({"after": "Enter", **b})
                        data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"]); name = f"kbd_enter-opens-chapter_{w}x{h}.png"; (OUT / name).write_bytes(data)
                        await key(ws, st, "Enter")  # close again
                    await key(ws, st, "Tab")
                # Open the sheet from the CTA with Enter, then Escape
                await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('.ActHead-btn').focus()"})
                await key(ws, st, "Enter"); opened_s = await wait_open(ws, st); await asyncio.sleep(0.4)
                inside = (await cdp(ws, st, "Runtime.evaluate", {"expression": ACTIVE, "returnByValue": True}))["result"]["value"]
                data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"]); name = f"kbd_sheet-open_{w}x{h}.png"; (OUT / name).write_bytes(data)
                tabs = []
                for i in range(5):
                    await key(ws, st, "Tab"); tabs.append((await cdp(ws, st, "Runtime.evaluate", {"expression": ACTIVE, "returnByValue": True}))["result"]["value"])
                await key(ws, st, "Escape"); await asyncio.sleep(0.4)
                back = (await cdp(ws, st, "Runtime.evaluate", {"expression": ACTIVE, "returnByValue": True}))["result"]["value"]
                dlg = (await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('dialog.pg-sheet').open", "returnByValue": True}))["result"]["value"]
                trace.append({"width": w, "tab_order": steps, "sheet_focus_on_open": inside, "sheet_tab_cycle": tabs, "after_escape": {"dialog_open": dlg, "focus": back}, "sheet_open_after_s": opened_s})
                print(f"--- {w}px"); [print("  ", s.get("after", "tab"), s.get("tag"), s.get("cls"), repr(s.get("text")), s.get("outline"), s.get("box"), "expanded=", s.get("expanded")) for s in steps]
                print("   sheet opened after s:", opened_s); print("   sheet open → focus:", inside.get("tag"), inside.get("cls"), inside.get("text"), "| tab cycle:", [(t.get("tag"), t.get("cls"), t.get("inDialog")) for t in tabs]); print("   escape → dialog open:", dlg, "focus:", back.get("tag"), back.get("cls"), back.get("text"))
        (OUT / "keyboard_trace.json").write_text(json.dumps(trace, indent=1))
    finally:
        if proc: proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
        elif ATTACH:
            try: urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{page['id']}")
            except Exception: pass
asyncio.run(main())
