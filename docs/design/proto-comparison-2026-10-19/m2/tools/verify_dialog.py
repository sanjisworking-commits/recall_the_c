#!/usr/bin/env python3
"""Verify the Add dialog corrections in a real (headless) browser: direct open, in-page open, dismissal, focus return, scope-step name, phone Close. Usage: verify_dialog.py BASE OUT"""
import asyncio, base64, json, pathlib, shutil, subprocess, sys, time, urllib.request, websockets, httpx
sys.path.insert(0, str(pathlib.Path(__file__).parent)); from capture_m2 import cdp, wait_event, CHROME, signin
BASE, OUT = sys.argv[1], pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
STATE = """(() => { const d = document.querySelector('dialog.pg-sheet'); const p = d && d.querySelector('.pg-sheet-panel'); const a = document.activeElement;
 const lab = d && d.getAttribute('aria-labelledby'); const labEl = lab && document.getElementById(lab);
 return {url: location.pathname, dialogOpen: !!(d && d.open), dialogRole: d && d.getAttribute('role'), dialogModal: d && d.getAttribute('aria-modal'), labelledby: lab, labelText: labEl && labEl.innerText.trim(), labelVisible: !!(labEl && labEl.offsetParent !== null),
   panelRole: p && p.getAttribute('role'), panelModal: p && p.getAttribute('aria-modal'), dialogsInPage: document.querySelectorAll('[role=dialog], dialog[open]').length, roleDialogsInsideHost: d ? d.querySelectorAll('[role=dialog]').length : null,
   active: a ? a.tagName + '.' + (a.className||'').toString().slice(0,30) + ' ' + (a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,30) : null,
   closeBtn: (() => { const b = d && d.querySelector('.pg-sheet-close'); if (!b) return null; const r = b.getBoundingClientRect(); const cs = getComputedStyle(b); return {display: cs.display, w: Math.round(r.width), h: Math.round(r.height), label: b.getAttribute('aria-label')}; })(),
   returnAttr: d && d.getAttribute('data-pg-sheet-return')}; })()"""
async def key(ws, st, k, text=None):
    text = text or {"Enter": "\r", "Escape": None}.get(k)
    base = {"key": k, "code": k, "windowsVirtualKeyCode": {"Enter": 13, "Escape": 27, "Tab": 9}.get(k, 0)}
    await cdp(ws, st, "Input.dispatchKeyEvent", {"type": "keyDown", **base, **({"text": text} if text else {})}); await cdp(ws, st, "Input.dispatchKeyEvent", {"type": "keyUp", **base}); await asyncio.sleep(0.25)
async def state(ws, st): return (await cdp(ws, st, "Runtime.evaluate", {"expression": STATE, "returnByValue": True}))["result"]["value"]
async def shot(ws, st, name):
    data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"]); (OUT / name).write_bytes(data)
async def main():
    prof = OUT / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True); port = 9431
    client = httpx.Client(base_url=BASE, timeout=20); cookies = signin(client)
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = {}
    try:
        for _ in range(50):
            try: targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies: await cdp(ws, st, "Network.setCookie", c)
            for (w, h) in ((1280, 900), (390, 844)):
                await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561}); L = log[f"{w}"] = {}
                async def nav(path):
                    st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": BASE + path})
                    try: await wait_event(ws, st, "Page.loadEventFired")
                    except TimeoutError: pass
                    await asyncio.sleep(0.8)
                # 1. direct URL (Plus, UAPA addable): opened as modal, label kept, URL unchanged while open
                await nav("/playground/laws/uapa/add"); L["direct_open"] = await state(ws, st); await shot(ws, st, f"direct_open_{w}.png")
                # 2. scope step via the confirm button (Enter on the focused primary)
                await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('dialog.pg-sheet .pg-add-primary').focus()"}); await key(ws, st, "Enter"); await asyncio.sleep(0.4)
                L["direct_scope_step"] = await state(ws, st); await shot(ws, st, f"direct_scope_{w}.png")
                # 3. Escape → closed, URL back to the Act, focus somewhere sensible
                await key(ws, st, "Escape"); await asyncio.sleep(0.5); L["direct_after_escape"] = await state(ws, st)
                # 4. in-page open from the Act head (Enter on the CTA), label, then ✕ click, focus returns to the CTA
                await nav("/laws/uapa"); await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('.ActHead-btn').focus()"}); await key(ws, st, "Enter"); await asyncio.sleep(1.0)
                L["inpage_open"] = await state(ws, st); await shot(ws, st, f"inpage_open_{w}.png")
                await cdp(ws, st, "Runtime.evaluate", {"expression": "document.querySelector('dialog.pg-sheet .pg-sheet-close').click()"}); await asyncio.sleep(0.5); L["inpage_after_close_click"] = await state(ws, st)
                # 5. Free-style sheet with no Cancel: guest-free check happens on a Free server; here confirm the ✕ is the explicit control on phone
            (OUT / "dialog_verification.json").write_text(json.dumps(log, indent=1))
            for w, L in log.items():
                print(f"=== {w}px")
                for k, v in L.items(): print(f"  {k}: url={v['url']} open={v['dialogOpen']} label={v['labelledby']}→{v['labelText']!r} vis={v['labelVisible']} panelRole={v['panelRole']} roleDialogsInHost={v['roleDialogsInsideHost']} active={v['active']!r} close={v['closeBtn']}")
    finally: proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
asyncio.run(main())
