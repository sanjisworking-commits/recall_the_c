#!/usr/bin/env python3
"""Capture the M2 Bare Act head route matrix from a local server with headless Chrome over CDP.

Usage:
  capture_m2.py --base http://127.0.0.1:8913 --out DIR --label frozen --tier free \
      [--signin] [--widths 390x844,1280x900] [--themes light,dark] [--routes routes.json] [--full-page]

Per route × width × theme: viewport PNG (+ optional full-page PNG), the shell
probe from the M1 tool, plus a HEAD probe (kicker, title, meta, CTA label/href,
chapter/schedule rows with hrefs and whether each is a real control, About
toggle, visible panel variant) and, for routes flagged "sheet": true, a second
capture after clicking the first [data-pg-sheet] trigger (dialog open state and
presentation). Cookies from --signin are injected into Chrome and never written.
"""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, json, pathlib, shutil, subprocess, sys, time, urllib.request
import httpx, websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROBE = r"""
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const txt = e => e ? (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim() : null;
  const box = e => { if (!e) return null; const r = e.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}; };
  const top = document.querySelector('nav.PrimaryTabs--top');
  const bars = [...document.querySelectorAll('nav.mobile-tabbar')];
  const bar = bars.find(vis) || null;
  const links = n => n ? [...n.querySelectorAll('a,button')].map(a => ({t: txt(a), href: a.getAttribute('href'), active: a.classList.contains('is-active'), vis: vis(a)})) : [];
  // Head: whichever variant is painted (legacy .bareact-head or a .guest-bareact panel or the M2 head)
  const panels = [...document.querySelectorAll('section.panel')].map(p => ({attrs: [...p.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name + (a.value ? '=' + a.value : '')), cls: p.className, vis: vis(p)}));
  const headEl = [...document.querySelectorAll('.guest-bareact, .bareact-page, .ActHead, [data-act-head]')].find(vis) || null;
  const h1 = [...document.querySelectorAll('h1')].find(vis) || null;
  const kicker = [...document.querySelectorAll('.guest-bareact-kicker, .bareact-tag, .ActHead-kicker, [data-act-kicker]')].find(vis) || null;
  const meta = [...document.querySelectorAll('.guest-bareact-meta, .ActHead-meta, [data-act-meta]')].find(vis) || null;
  const cta = [...document.querySelectorAll('.guest-bareact-cta, .LawPlaygroundCta .pg-btn, .signed-bareact-continue, .signed-bareact-sections, .ActHead-btn, .ActHead-inpg-sections, .ActHead-inpg-continue, .ActHead-link')].filter(vis).map(a => ({t: txt(a), href: a.getAttribute('href'), sheet: a.hasAttribute('data-pg-sheet'), kind: a.getAttribute('data-pg-kind') || (a.closest('[data-pg-kind]') || {getAttribute(){return null}}).getAttribute('data-pg-kind'), box: box(a)}));
  const badge = [...document.querySelectorAll('.LawStatusBadge, .signed-bareact-in-pg')].filter(vis).map(txt);
  const rowSel = '.guest-bareact-row, .bareact-chapter-row, .bareact-schedule-row, .bareact-section-row';
  const rows = [...document.querySelectorAll(rowSel)].filter(r => vis(r) && !(r.closest('details') && !r.closest('details').open && r.tagName !== 'SUMMARY')).map(r => {
    const link = r.tagName === 'A' ? r : (r.querySelector('a.bareact-schedule-row-link') || null);
    return {cls: r.className, tag: r.tagName.toLowerCase(), t: txt(r).slice(0, 90), href: link ? link.getAttribute('href') : null,
            control: r.tagName === 'A' || r.tagName === 'BUTTON' || r.tagName === 'SUMMARY' || !!link || r.getAttribute('role') === 'button',
            expanded: r.hasAttribute('aria-expanded') ? r.getAttribute('aria-expanded') : (r.closest('details') ? String(r.closest('details').open) : null), h: box(r) ? box(r).h : null};
  });
  const about = document.querySelector('[data-bareact-info-toggle]');
  const tabs = document.querySelector('[data-bareact-tabs]');
  const dlg = document.querySelector('dialog.pg-sheet');
  const addPanel = document.querySelector('[data-pg-add]');
  return {
    url: location.pathname + location.search, title: document.title, mscreen: document.body.dataset.mscreen || null, bodyClass: document.body.className.trim(),
    topNavVisible: vis(top), topNav: links(top).filter(l => l.vis).map(l => l.t), phoneBarVisible: !!bar, phoneBar: links(bar).filter(l => l.vis).map(l => l.t),
    panels, head: headEl ? {cls: headEl.className, attrs: [...headEl.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name)} : null,
    h1: txt(h1), h1Font: h1 ? getComputedStyle(h1).fontSize + '/' + getComputedStyle(h1).fontFamily.split(',')[0] : null, kicker: txt(kicker), meta: txt(meta), cta, badge,
    rows, rowCount: rows.length, about: about ? {vis: vis(about), expanded: about.getAttribute('aria-expanded')} : null, tabsHidden: tabs ? tabs.hidden : null,
    dialog: dlg ? {open: dlg.open, cls: dlg.className, box: box(dlg), panelKind: (dlg.querySelector('[data-pg-add]') || {getAttribute(){return null}}).getAttribute('data-pg-kind'), title: txt(dlg.querySelector('h1,h2')), closeBtn: !!dlg.querySelector('[data-pg-sheet-close]'), active: document.activeElement ? document.activeElement.tagName + '.' + document.activeElement.className : null} : null,
    addPage: addPanel && !dlg?.contains(addPanel) ? {kind: addPanel.getAttribute('data-pg-kind'), title: txt(addPanel.querySelector('h1')), vis: vis(addPanel), role: addPanel.getAttribute('role'), box: box(addPanel), forms: [...addPanel.querySelectorAll('form')].map(f => ({action: f.getAttribute('action'), hidden: [...f.querySelectorAll('input[type=hidden]')].map(i => i.name)})), footerVisible: vis(document.querySelector('footer.site-footer'))} : null,
    hScroll: document.documentElement.scrollWidth > window.innerWidth, docH: document.documentElement.scrollHeight,
  };
})()
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

def status_chain(client: httpx.Client, url: str):
    chain = []; r = client.get(url, follow_redirects=False); chain.append((url, r.status_code)); hops = 0
    while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
        nxt = r.headers.get("location"); nxt = nxt if nxt.startswith("http") else client.base_url.join(nxt)
        r = client.get(str(nxt), follow_redirects=False); chain.append((str(nxt), r.status_code)); hops += 1
    return chain

def signin(client: httpx.Client):
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state") or client.cookies.get("rtc_oauth_state")
    assert state, "no oauth state cookie"
    authed = client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert authed.status_code == 303, authed.status_code
    probe = client.get("/dashboard", follow_redirects=True)
    assert "reading as a guest" not in probe.text.split("<main", 1)[-1][:600].lower(), "sign-in did not take"
    host = httpx.URL(str(client.base_url)).host
    return [{"name": c.name, "value": c.value, "domain": host, "path": "/", "httpOnly": True} for c in client.cookies.jar]

async def shot(ws, st, out, name, full=False):
    params = {"format": "png"}
    if full:
        m = await cdp(ws, st, "Page.getLayoutMetrics"); cs = m.get("cssContentSize") or m["contentSize"]
        params.update({"captureBeyondViewport": True, "clip": {"x": 0, "y": 0, "width": cs["width"], "height": min(cs["height"], 6000), "scale": 1}})
    data = base64.b64decode((await cdp(ws, st, "Page.captureScreenshot", params))["data"]); (out / name).write_bytes(data)
    return hashlib.sha256(data).hexdigest()

async def run(args):
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    routes = json.loads(pathlib.Path(args.routes).read_text())
    widths = [tuple(map(int, w.split("x"))) for w in args.widths.split(",")]; themes = args.themes.split(",")
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = signin(client) if args.signin else []
    if args.add_law:
        # Local throwaway DB only: the same roster add the halted test cohort performs (confirm, then scope).
        for law in args.add_law.split(","):
            csrf = {"csrf_token": client.cookies.get("rtc_csrf") or ""}
            first = client.post(f"/playground/laws/{law}/add", data=csrf, follow_redirects=False)
            second = client.post(f"/playground/laws/{law}/add", data={**csrf, "confirm": "add", "scope": "entire"}, follow_redirects=False)
            print(f"add {law}: {first.status_code} -> {second.status_code} {second.headers.get('location')}", flush=True)
    viewer = args.tier if args.signin else "guest"
    prof = out / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True); port = args.debug_port
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try: targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        manifest = {"label": args.label, "base": args.base, "viewer": viewer, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "chrome": subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.strip(), "rows": []}
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}
            await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies: await cdp(ws, st, "Network.setCookie", c)
            for route in routes:
                key, path = route["key"], route["path"]; chain = status_chain(client, path)
                for (w, h) in widths:
                    for theme in themes:
                        await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                        await cdp(ws, st, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": theme}]})
                        st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": args.base + path})
                        try: await wait_event(ws, st, "Page.loadEventFired")
                        except TimeoutError: pass
                        await asyncio.sleep(0.6)
                        await cdp(ws, st, "Runtime.evaluate", {"expression": "document.fonts && document.fonts.ready", "awaitPromise": True})
                        probe = (await cdp(ws, st, "Runtime.evaluate", {"expression": PROBE, "returnByValue": True}))["result"]["value"]
                        stem = f"{args.label}_{viewer}_{key}_{w}x{h}_{theme}"
                        sha = await shot(ws, st, out, stem + ".png")
                        row = {"key": key, "route": path, "viewer": viewer, "width": w, "height": h, "theme": theme, "file": stem + ".png", "sha256": sha, "status_chain": chain, "probe": probe}
                        if args.full_page:
                            row["full_file"] = stem + "_full.png"; row["full_sha256"] = await shot(ws, st, out, stem + "_full.png", full=True)
                        if route.get("sheet"):
                            opened = (await cdp(ws, st, "Runtime.evaluate", {"expression": "(() => { const a = [...document.querySelectorAll('[data-pg-sheet]')].find(e => e.getBoundingClientRect().width > 0); if (!a) return 'no-trigger'; a.click(); return a.getAttribute('href'); })()", "returnByValue": True}))["result"]["value"]
                            await asyncio.sleep(1.0)
                            sprobe = (await cdp(ws, st, "Runtime.evaluate", {"expression": PROBE, "returnByValue": True}))["result"]["value"]
                            row["sheet"] = {"trigger": opened, "file": stem + "_sheet.png", "sha256": await shot(ws, st, out, stem + "_sheet.png"), "probe": {k: sprobe[k] for k in ("url", "dialog", "addPage", "hScroll")}}
                        manifest["rows"].append(row)
                        print(f"{stem:60s} {chain[-1][1]} meta={probe['meta']!r} cta={[c['t'] for c in probe['cta']]} rows={probe['rowCount']} dlg={(row.get('sheet') or {}).get('probe', {}).get('dialog', {}) and (row['sheet']['probe']['dialog'] or {}).get('open')}", flush=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True); ap.add_argument("--tier", default="free")
    ap.add_argument("--signin", action="store_true"); ap.add_argument("--widths", default="390x844,1280x900"); ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--routes", required=True); ap.add_argument("--debug-port", type=int, default=9343); ap.add_argument("--full-page", action="store_true"); ap.add_argument("--add-law", default="")
    sys.exit(asyncio.run(run(ap.parse_args())))
