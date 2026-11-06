"""M2-R capture: Act-head CTA states and Add-dialog variants, scenario-driven.

Same CDP driver and dev fake-Google sign-in as m1r/tools/capture_m1r.py (the
cookie is injected into headless Chrome and never written to disk). A scenario
file lists ordered steps; each step may first change the account's state through
the app's own endpoints (``setup``: add a law Entire-Act, remove a law), then
captures one route per width × theme:

  head      Act-head CTA probe (kind, label, href, badge, note, box, contrast)
  sheet     click the [data-pg-sheet] trigger, wait for the open <dialog>, probe
            the panel (kind, step, title, texts, every control with its box and
            contrast, focus inside the dialog) and screenshot it
  keyboard  Tab through the open dialog (containment), Escape (closes, focus
            returns to the opener)
  scope     press the confirm button → the scope step, screenshot
  fail      intercept the scope POST with CDP Fetch and answer with the server's
            own JSON shape {ok:false,error:"save_failed",outcome:...} so the
            in-dialog banner (M2R-F03) renders without touching the account;
            then press Retry (the real GET re-read) and probe what replaces it

Nothing in ``fail`` reaches the server; every other state change is a real
POST through the signed-in session, exactly as a user would make it.
"""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, json, pathlib, shutil, subprocess, time, urllib.request
import httpx, websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

COLOR_LIB = r"""
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const txt = e => e ? (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim() : null;
  const box = e => { if (!e) return null; const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; };
  const parseColor = s => { if (!s) return null; let m = s.match(/^rgba?\(([^)]+)\)$/); if (m) { const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; } m = s.match(/^color\(srgb ([^)]+)\)$/); if (m) { const p = m[1].split(/[\s\/]+/).filter(Boolean).map(Number); return {r: p[0]*255, g: p[1]*255, b: p[2]*255, a: p.length > 3 ? p[3] : 1}; } return null; };
  const over = (f, b) => ({r: f.r*f.a + b.r*(1-f.a), g: f.g*f.a + b.g*(1-f.a), b: f.b*f.a + b.b*(1-f.a), a: 1});
  const bgBehind = el => { const layers = []; for (let n = el; n; n = n.parentElement) { const c = parseColor(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } } let acc = {r:255,g:255,b:255,a:1}; const html = parseColor(getComputedStyle(document.documentElement).backgroundColor); if (html && html.a > 0) acc = over(html, acc); for (let i = layers.length-1; i >= 0; i--) acc = over(layers[i], acc); return acc; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); }; return 0.2126*f(c.r) + 0.7152*f(c.g) + 0.0722*f(c.b); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return Math.round(((Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05))*100)/100; };
  const hex = c => '#' + [c.r,c.g,c.b].map(v => Math.round(v).toString(16).padStart(2,'0')).join('');
  const control = (kind, el) => { if (!el || !vis(el)) return null; const b = box(el); const fg = parseColor(getComputedStyle(el).color); const bg = bgBehind(el); const fgc = fg ? (fg.a < 1 ? over(fg, bg) : fg) : null; return {kind, t: txt(el), tag: el.tagName, href: el.getAttribute('href'), box: b, meets44: b.w >= 44 && b.h >= 44, fg: fgc ? hex(fgc) : null, bg: hex(bg), ratio: fgc ? ratio(fgc, bg) : null, focusable: el.tabIndex >= 0}; };
"""

HEAD_PROBE = "(() => {" + COLOR_LIB + r"""
  const cta = document.querySelector('.ActHead-cta');
  const btn = cta ? cta.querySelector('.ActHead-btn, .ActHead-inpg-continue') : null;
  const controls = cta ? [...cta.querySelectorAll('a,button')].map(a => control('cta', a)).filter(Boolean) : [];
  return {url: location.pathname, kind: cta ? cta.getAttribute('data-pg-kind') : null, membership: cta ? cta.getAttribute('data-membership') : null,
          primary: btn ? {t: txt(btn), href: btn.getAttribute('href'), sheet: btn.hasAttribute('data-pg-sheet'), box: box(btn)} : null,
          badge: txt(cta && cta.querySelector('.LawStatusBadge, .ActHead-inpg-badge')), note: txt(cta && cta.querySelector('.ActHead-note')),
          controls, small: controls.filter(c => !c.meets44).map(c => c.t + ':' + c.box.w + 'x' + c.box.h), low: controls.filter(c => c.ratio !== null && c.ratio < 4.5).map(c => c.t + '=' + c.ratio),
          flatList: !!document.querySelector('[data-act-list] .bareact-section-row') && !document.querySelector('[data-act-list] details.bareact-chapter'),
          hScroll: document.documentElement.scrollWidth > innerWidth};
})()"""

PANEL_PROBE = "(() => {" + COLOR_LIB + r"""
  const dialog = document.querySelector('dialog.pg-sheet');
  const panel = dialog ? dialog.querySelector('.pg-sheet-panel') : document.querySelector('.pg-sheet-panel');
  if (!panel) return {open: false};
  const step = panel.getAttribute('data-step');
  const visibleStep = [...panel.querySelectorAll('[data-add-step]')].find(vis);
  const scopeEl = visibleStep || panel;
  const headings = [...panel.querySelectorAll('h1,h2')].filter(vis).map(txt);
  const texts = [...scopeEl.querySelectorAll('p')].filter(vis).map(txt);
  const controls = [...scopeEl.querySelectorAll('a,button,input:not([type=hidden])')].map(a => control('panel', a)).filter(Boolean);
  const alert = panel.querySelector('[data-pg-add-alert]');
  const active = document.activeElement;
  return {open: !!(dialog && dialog.open), dialogOpenAttr: dialog ? dialog.hasAttribute('open') : null, kind: panel.getAttribute('data-pg-kind'), step, headings, texts, controls,
          small: controls.filter(c => !c.meets44).map(c => c.t + ':' + c.box.w + 'x' + c.box.h), low: controls.filter(c => c.ratio !== null && c.ratio < 4.5).map(c => c.t + '=' + c.ratio),
          labelledBy: dialog ? dialog.getAttribute('aria-labelledby') : panel.getAttribute('aria-labelledby'), ariaModal: dialog ? dialog.getAttribute('aria-modal') : panel.getAttribute('aria-modal'),
          focusInside: !!(dialog && active && dialog.contains(active)), focusOn: active ? (active.tagName + '.' + (active.className||'').toString().split(/\s+/)[0] + ':' + (txt(active)||'').slice(0,30)) : null,
          alert: alert && !alert.hidden ? {outcome: alert.getAttribute('data-outcome'), role: alert.getAttribute('role'), text: txt(alert.querySelector('.pg-add-alert-text')), controls: [...alert.querySelectorAll('a,button')].map(a => control('alert', a)).filter(Boolean)} : null,
          panelBox: box(panel), warning: txt(panel.querySelector('[data-pg-free-warning]')), hasMonthEyebrow: /^[A-Z][a-z]+ \d{4}$/.test(txt(panel.querySelector('.pg-eyebrow')) || ''), eyebrow: txt(panel.querySelector('.pg-eyebrow')),
          hasPrice: /₹/.test(txt(panel) || ''), hScroll: document.documentElement.scrollWidth > innerWidth};
})()"""

FOCUS_PROBE = r"""
(() => { const d = document.querySelector('dialog.pg-sheet'); const el = document.activeElement; const cs = el ? getComputedStyle(el) : null;
  return {inDialog: !!(d && el && d.contains(el)), el: el ? el.tagName + '.' + (el.className||'').toString().split(/\s+/).slice(0,2).join('.') : null, text: el ? (el.innerText||el.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim().slice(0,30) : null,
          focusVisible: el ? el.matches(':focus-visible') : false, outline: cs && cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 ? cs.outlineWidth + ' ' + cs.outlineStyle : null, dialogOpen: !!(d && d.open)}; })()
"""

async def cdp(ws, state, method, params=None):
    state["id"] += 1; mid = state["id"]
    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == mid:
            if "error" in msg: raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})
        state["events"].append(msg)

async def wait_event(ws, state, name, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for i, ev in enumerate(state["events"]):
            if ev.get("method") == name:
                del state["events"][i]; return ev
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
            if msg.get("method") == name: return msg
            state["events"].append(msg)
        except asyncio.TimeoutError:
            pass
    raise TimeoutError(name)

async def evaluate(ws, st, expr):
    return (await cdp(ws, st, "Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}))["result"].get("value")

async def wait_for(ws, st, expr, timeout=8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if await evaluate(ws, st, expr): return True
        await asyncio.sleep(0.1)
    return False

async def click_box(ws, st, b):
    cx, cy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    await cdp(ws, st, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx, "y": cy})
    for t in ("mousePressed", "mouseReleased"):
        await cdp(ws, st, "Input.dispatchMouseEvent", {"type": t, "x": cx, "y": cy, "button": "left", "clickCount": 1})

async def press(ws, st, key, code=None, vk=None, shift=False):
    for t in ("keyDown", "keyUp"):
        await cdp(ws, st, "Input.dispatchKeyEvent", {"type": t, "key": key, "code": code or key, "windowsVirtualKeyCode": vk or 0, "nativeVirtualKeyCode": vk or 0, "modifiers": 8 if shift else 0})

async def click_text(ws, st, selector, text):
    b = await evaluate(ws, st, f"(() => {{ const el = [...document.querySelectorAll({json.dumps(selector)})].find(e => (e.innerText||'').trim() === {json.dumps(text)} && e.getBoundingClientRect().width > 0); if (!el) return null; el.scrollIntoView({{block:'center'}}); const r = el.getBoundingClientRect(); return {{x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}}; }})()")
    if not b: return False
    await click_box(ws, st, b); return True

def signin(client):
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state") or client.cookies.get("rtc_oauth_state")
    assert state, "no oauth state cookie"
    authed = client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert authed.status_code == 303, authed.status_code
    client.get("/playground")  # csrf cookie
    host = httpx.URL(str(client.base_url)).host
    return [{"name": c.name, "value": c.value, "domain": host, "path": "/", "httpOnly": True} for c in client.cookies.jar]

def run_setup(client, actions):
    done = []
    csrf = {"csrf_token": client.cookies.get("rtc_csrf") or ""}
    for a in actions or []:
        if "add" in a:
            r = client.post(f"/playground/laws/{a['add']}/add", data={**csrf, "confirm": "add", "scope": "entire"}, follow_redirects=False)
            done.append({"add": a["add"], "status": r.status_code, "location": r.headers.get("location")})
        elif "remove" in a:
            r = client.post(f"/playground/roster/{a['remove']}/remove", data=csrf, follow_redirects=False)
            done.append({"remove": a["remove"], "status": r.status_code, "location": r.headers.get("location")})
    return done

async def shot(ws, st, out, name):
    data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", {"format": "png"}))["data"])
    (out / name).write_bytes(data); return {"file": name, "sha256": hashlib.sha256(data).hexdigest()}

async def keyboard_trace(ws, st, limit=10):
    trail = []
    for _ in range(limit):
        await press(ws, st, "Tab", vk=9)
        trail.append(await evaluate(ws, st, FOCUS_PROBE))
    await press(ws, st, "Escape", vk=27)
    await asyncio.sleep(0.2)
    after = await evaluate(ws, st, FOCUS_PROBE)
    opener = await evaluate(ws, st, "(() => { const el = document.activeElement; return el ? {isTrigger: el.hasAttribute('data-pg-sheet'), text: (el.innerText||'').trim().slice(0,40)} : null; })()")
    return {"tabs": trail, "containment": all(f.get("inDialog") for f in trail), "outlined": sum(1 for f in trail if f.get("outline")), "afterEscape": after, "focusReturned": opener}

async def open_sheet(ws, st):
    b = await evaluate(ws, st, "(() => { const el = document.querySelector('.ActHead-cta [data-pg-sheet]'); if (!el) return null; el.scrollIntoView({block:'center'}); const r = el.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; })()")
    if not b: return False
    await click_box(ws, st, b)
    return await wait_for(ws, st, "!!(document.querySelector('dialog.pg-sheet') && document.querySelector('dialog.pg-sheet').open && document.querySelector('dialog.pg-sheet .pg-sheet-panel'))")

async def inject_failure(ws, st, outcome):
    await cdp(ws, st, "Fetch.enable", {"patterns": [{"urlPattern": "*/playground/laws/*/add*", "requestStage": "Request"}]})
    body = base64.b64encode(json.dumps({"ok": False, "error": "save_failed", "outcome": outcome}).encode()).decode()
    return body

async def serve_paused(ws, st, body, timeout=8):
    """Answer the next paused POST with the injected JSON; let GETs through."""
    t0 = time.time(); fulfilled = None
    while time.time() - t0 < timeout:
        try:
            ev = await wait_event(ws, st, "Fetch.requestPaused", timeout=1)
        except TimeoutError:
            if fulfilled: break
            continue
        p = ev["params"]
        if p["request"]["method"].upper() == "POST" and fulfilled is None:
            await cdp(ws, st, "Fetch.fulfillRequest", {"requestId": p["requestId"], "responseCode": 500, "responseHeaders": [{"name": "Content-Type", "value": "application/json"}], "body": body})
            fulfilled = {"url": p["request"]["url"], "method": "POST", "hadAcceptJson": "application/json" in (p["request"]["headers"].get("Accept") or p["request"]["headers"].get("accept") or "")}
        else:
            await cdp(ws, st, "Fetch.continueRequest", {"requestId": p["requestId"]})
    return fulfilled

async def run(args):
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    scenarios = json.loads(pathlib.Path(args.scenarios).read_text())
    widths = [tuple(map(int, w.split("x"))) for w in args.widths.split(",")]
    themes = args.themes.split(",")
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = signin(client) if args.signin else []
    viewer = args.tier if args.signin else "guest"
    prof = out / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True)
    port = args.debug_port
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        manifest = {"label": args.label, "base": args.base, "viewer": viewer, "tier_model": args.tier_model, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "chrome": subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.strip(), "rows": []}
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            st = {"id": 0, "events": []}
            await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies: await cdp(ws, st, "Network.setCookie", c)
            for sc in scenarios:
                setup = run_setup(client, sc.get("setup")) if args.signin else []
                for (w, h) in widths:
                    for theme in themes:
                        if sc.get("only_light") and theme != "light": continue
                        if sc.get("only_widths") and w not in sc["only_widths"]: continue
                        await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                        await cdp(ws, st, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": theme}]})
                        st["events"].clear()
                        await cdp(ws, st, "Page.navigate", {"url": args.base + sc["path"]})
                        try: await wait_event(ws, st, "Page.loadEventFired")
                        except TimeoutError: pass
                        await asyncio.sleep(0.5)
                        await evaluate(ws, st, "document.fonts && document.fonts.ready")
                        stem = f"{args.label}_{viewer}_{sc['key']}_{w}x{h}_{theme}"
                        row = {"key": sc["key"], "path": sc["path"], "width": w, "height": h, "theme": theme, "setup": setup, "head": await evaluate(ws, st, HEAD_PROBE)}
                        row["shots"] = {"head": await shot(ws, st, out, stem + "_head.png")}
                        if sc.get("sheet"):
                            opened = await open_sheet(ws, st)
                            row["sheet_opened"] = opened
                            if opened:
                                await asyncio.sleep(0.25)
                                row["sheet"] = await evaluate(ws, st, PANEL_PROBE)
                                row["shots"]["sheet"] = await shot(ws, st, out, stem + "_sheet.png")
                                if sc.get("keyboard"):
                                    row["keyboard"] = await keyboard_trace(ws, st)
                                    # Escape closed it: re-open for the next steps
                                    if sc.get("scope") or sc.get("fail"):
                                        await open_sheet(ws, st); await asyncio.sleep(0.2)
                                if sc.get("scope") or sc.get("fail"):
                                    if await click_text(ws, st, "dialog.pg-sheet button.pg-add-primary", (row.get("sheet") or {}).get("controls", [{}])[0].get("t") if False else None) is False:
                                        pass
                                    confirmed = await evaluate(ws, st, "(() => { const b = document.querySelector(\"dialog.pg-sheet [data-add-step='confirm'] button.pg-add-primary\"); if (!b) return false; b.click(); return true; })()")
                                    await asyncio.sleep(0.25)
                                    row["scope"] = await evaluate(ws, st, PANEL_PROBE)
                                    row["scope"]["confirmClicked"] = confirmed
                                    row["shots"]["scope"] = await shot(ws, st, out, stem + "_scope.png")
                                if sc.get("fail"):
                                    outcome = sc["fail"]
                                    body = await inject_failure(ws, st, outcome)
                                    clicked = await evaluate(ws, st, "(() => { const b = [...document.querySelectorAll(\"dialog.pg-sheet [data-add-step='scope'] button.pg-add-choice\")].find(x => /Entire Act/.test(x.innerText)); if (!b) return false; b.click(); return true; })()")
                                    served = await serve_paused(ws, st, body)
                                    await cdp(ws, st, "Fetch.disable")
                                    await wait_for(ws, st, "!!(document.querySelector('[data-pg-add-alert]') && !document.querySelector('[data-pg-add-alert]').hidden)")
                                    await asyncio.sleep(0.2)
                                    row["fail"] = {"outcome": outcome, "entireClicked": clicked, "intercepted": served, "panel": await evaluate(ws, st, PANEL_PROBE), "focus": await evaluate(ws, st, FOCUS_PROBE)}
                                    row["shots"]["fail"] = await shot(ws, st, out, f"{stem}_fail-{outcome}.png")
                                    # Retry: the real re-read (GET ?step=scope) swaps the panel
                                    retried = await evaluate(ws, st, "(() => { const b = document.querySelector('[data-pg-add-retry]'); if (!b) return false; b.click(); return true; })()")
                                    await asyncio.sleep(0.8)
                                    row["fail"]["retry"] = {"clicked": retried, "panel": await evaluate(ws, st, PANEL_PROBE)}
                                    row["shots"]["retry"] = await shot(ws, st, out, f"{stem}_retry-{outcome}.png")
                                await evaluate(ws, st, "(() => { const d = document.querySelector('dialog.pg-sheet'); if (d && d.open) d.close(); return true; })()")
                        manifest["rows"].append(row)
                        hd = row["head"] or {}; sh = row.get("sheet") or {}
                        flags = ""
                        for part, label in ((hd, "head"), (sh, "sheet"), ((row.get("scope") or {}), "scope"), (((row.get("fail") or {}).get("panel") or {}), "fail")):
                            if part.get("small"): flags += f" {label}:SMALL{len(part['small'])}"
                            if part.get("low"): flags += f" {label}:LOWC{len(part['low'])}"
                        kb = row.get("keyboard")
                        print(f"{stem:60s} head={hd.get('kind')}:{(hd.get('primary') or {}).get('t')!s:42s} sheet={sh.get('kind')}/{sh.get('step')} focusIn={sh.get('focusInside')}"
                              + (f" kb={'ok' if kb['containment'] else 'LEAK'}/{kb['outlined']} esc={'closed' if not kb['afterEscape'].get('dialogOpen') else 'OPEN'} ret={(kb['focusReturned'] or {}).get('isTrigger')}" if kb else "")
                              + (f" fail={(row['fail']['panel'].get('alert') or {}).get('outcome')}→retry={((row['fail']['retry'] or {}).get('panel') or {}).get('step')}" if row.get("fail") else "") + flags, flush=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--tier", default="free"); ap.add_argument("--tier-model", default="choices"); ap.add_argument("--signin", action="store_true")
    ap.add_argument("--widths", default="390x844,1280x900"); ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--scenarios", required=True); ap.add_argument("--debug-port", type=int, default=9361)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
