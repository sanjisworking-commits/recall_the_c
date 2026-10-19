#!/usr/bin/env python3
"""Capture a route matrix from a local Recall the C server with headless Chrome over CDP.

Usage:
  capture_local.py --base http://127.0.0.1:8912 --out DIR --label frozen \
      [--signin] [--widths 390x844,1280x900] [--themes light,dark] [--routes routes.json]

For every route × width × theme the script records a viewport PNG, a DOM probe
(screen key, top-nav links, visible phone tabs, active link, account slot text,
zoom meta) and the HTTP status/redirect chain, and writes manifest.json with
SHA-256 of every PNG. --signin performs the dev fake-Google sign-in with httpx
and injects the resulting cookies into Chrome (never printed or saved).
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, pathlib, shutil, subprocess, sys, time, urllib.request
import httpx, websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROBE = r"""
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const txt = e => e ? e.innerText.replace(/\s+/g, ' ').trim() : null;
  const top = document.querySelector('nav.PrimaryTabs--top');
  const bars = [...document.querySelectorAll('nav.mobile-tabbar')];
  const bar = bars.find(vis) || null;
  const links = n => n ? [...n.querySelectorAll('a,button')].map(a => ({t: txt(a), href: a.getAttribute('href'), active: a.classList.contains('is-active'), current: a.getAttribute('aria-current'), vis: vis(a)})) : [];
  const header = document.querySelector('header.site-header');
  const acct = document.querySelector('.account-menu, .nav-signin, a.nav-signin');
  const meta = document.querySelector('meta[name=viewport]');
  return {
    url: location.pathname + location.search, title: document.title,
    mscreen: document.body.dataset.mscreen || null, bodyClass: document.body.className.trim(),
    headerVisible: vis(header), topNavVisible: vis(top), topNav: links(top).filter(l => l.vis),
    phoneBarsInDom: bars.length, phoneBarVisible: !!bar, phoneBar: links(bar).filter(l => l.vis), phoneBarClass: bar ? bar.className : null,
    account: acct ? {cls: acct.className, text: txt(acct), vis: vis(acct)} : null,
    guestPill: !!document.querySelector('.guest-pill'), viewport: meta ? meta.content : null,
    hScroll: document.documentElement.scrollWidth > window.innerWidth,
    footerTools: [...document.querySelectorAll('footer .footer-tools a, footer .footer-tools button')].filter(vis).map(txt),
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
    chain = []; r = client.get(url, follow_redirects=False); chain.append((url, r.status_code))
    hops = 0
    while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
        nxt = r.headers.get("location"); nxt = nxt if nxt.startswith("http") else client.base_url.join(nxt)
        r = client.get(str(nxt), follow_redirects=False); chain.append((str(nxt), r.status_code)); hops += 1
    return chain

def signin(client: httpx.Client):
    """Dev fake-Google sign-in, the same way the test-suite does it (no host round trip)."""
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state") or client.cookies.get("rtc_oauth_state")
    assert state, "no oauth state cookie"
    authed = client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert authed.status_code == 303, authed.status_code
    probe = client.get("/dashboard", follow_redirects=True)
    body = probe.text.split("<main", 1)[-1][:600].lower()
    assert "reading as a guest" not in body, "sign-in did not take"
    host = httpx.URL(str(client.base_url)).host
    return [{"name": c.name, "value": c.value, "domain": host, "path": "/", "httpOnly": True} for c in client.cookies.jar]


async def run(args):
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    routes = json.loads(pathlib.Path(args.routes).read_text()) if args.routes else DEFAULT_ROUTES
    widths = [tuple(map(int, w.split("x"))) for w in args.widths.split(",")]
    themes = args.themes.split(",")
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = signin(client) if args.signin else []
    viewer = "signedin-free" if args.signin else "guest"
    prof = pathlib.Path(args.out) / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True)
    port = args.debug_port
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                             f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception: time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        manifest = {"label": args.label, "base": args.base, "viewer": viewer, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "chrome": subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.strip(), "rows": []}
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            st = {"id": 0, "events": []}
            await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Network.enable"); await cdp(ws, st, "Runtime.enable")
            for c in cookies:
                await cdp(ws, st, "Network.setCookie", c)
            for route in routes:
                key, path = route["key"], route["path"]
                chain = status_chain(client, path)
                for (w, h) in widths:
                    for theme in themes:
                        await cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 561})
                        await cdp(ws, st, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": theme}]})
                        st["events"].clear()
                        await cdp(ws, st, "Page.navigate", {"url": args.base + path})
                        try: await wait_event(ws, st, "Page.loadEventFired")
                        except TimeoutError: pass
                        await asyncio.sleep(0.6)
                        await cdp(ws, st, "Runtime.evaluate", {"expression": "document.fonts && document.fonts.ready", "awaitPromise": True})
                        probe = (await cdp(ws, st, "Runtime.evaluate", {"expression": PROBE, "returnByValue": True}))["result"]["value"]
                        shot = await cdp(ws, st, "Page.captureScreenshot", {"format": "png"})
                        name = f"{args.label}_{viewer}_{key}_{w}x{h}_{theme}.png"
                        data = __import__("base64").b64decode(shot["data"]); (out / name).write_bytes(data)
                        manifest["rows"].append({"key": key, "route": path, "width": w, "height": h, "theme": theme, "file": name,
                                                 "sha256": hashlib.sha256(data).hexdigest(), "status_chain": chain, "probe": probe})
                        print(f"{name:70s} {chain[-1][1]} {probe['mscreen']} bar={probe['phoneBarVisible']} nav={probe['topNavVisible']}", flush=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0

DEFAULT_ROUTES = [
  {"key": "landing", "path": "/"}, {"key": "browse", "path": "/browse"}, {"key": "browse-part-iii", "path": "/browse/part/iii"},
  {"key": "article-14", "path": "/browse/article/14"}, {"key": "laws", "path": "/laws"}, {"key": "laws-ndps", "path": "/laws/ndps"},
  {"key": "laws-uapa", "path": "/laws/uapa"}, {"key": "laws-bns", "path": "/laws/bns"}, {"key": "laws-mtp", "path": "/laws/mtp"},
  {"key": "ndps-section-8", "path": "/laws/ndps/section/8"}, {"key": "playground", "path": "/playground"},
  {"key": "playground-plans", "path": "/playground?stage=plans"}, {"key": "playground-plans-plus", "path": "/playground?stage=plans&tier=plus"},
  {"key": "playground-add-uapa", "path": "/playground/laws/uapa/add"}, {"key": "dashboard", "path": "/dashboard"},
  {"key": "calendar", "path": "/calendar"}, {"key": "profile", "path": "/profile"}, {"key": "settings", "path": "/settings"},
  {"key": "devices", "path": "/profile/security/devices"}, {"key": "tables", "path": "/tables"}, {"key": "search", "path": "/search"},
  {"key": "terms", "path": "/terms"}, {"key": "privacy", "path": "/privacy"}, {"key": "grievance", "path": "/grievance"},
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--signin", action="store_true"); ap.add_argument("--widths", default="390x844,1280x900"); ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--routes"); ap.add_argument("--debug-port", type=int, default=9333)
    sys.exit(asyncio.run(run(ap.parse_args())))
