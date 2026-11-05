"""M1-R shell capture: route × width × theme PNGs plus a shell probe.

Based on m1/tools/capture_local.py (same CDP driver, same dev fake-Google
sign-in that never writes a cookie to disk). The probe answers the M1-R
acceptance questions per row:

  navSurfaces      how many primary navigation surfaces are visible
                   (top PrimaryTabs + visible phone bars) — must be exactly 1
  phoneTabs        visible phone tabs (label, href, current) — 5 usable on phone
  avatar           account button: visible, size, and whether a hit-test at its
                   centre lands on it (clickable, not covered)
  headerOverlaps   pairs of visible header children whose boxes intersect
  chip             the account-slot status text (tier label)
  hScroll          page wider than viewport

Usage:
  capture_m1r.py --base http://127.0.0.1:8914 --out DIR --label candidate-free --tier free \
      [--signin] [--widths 390x844,561x900,640x900,720x900,1280x900] [--themes light,dark] [--routes routes.json]
"""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, json, pathlib, shutil, subprocess, time, urllib.request
import httpx, websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROBE = r"""
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const txt = e => e ? e.innerText.replace(/\s+/g, ' ').trim() : null;
  const box = e => { const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; };
  const top = document.querySelector('nav.PrimaryTabs--top');
  const bars = [...document.querySelectorAll('nav.mobile-tabbar')];
  const visibleBars = bars.filter(vis);
  const links = n => n ? [...n.querySelectorAll('a,button')].filter(vis).map(a => ({t: txt(a), href: a.getAttribute('href'), current: a.getAttribute('aria-current') || (a.classList.contains('is-active') ? 'class' : null), box: box(a)})) : [];
  const header = document.querySelector('header.site-header');
  const acctBtn = document.querySelector('.account-menu-btn');
  const signin = document.querySelector('a.nav-signin');
  let avatar = null;
  if (acctBtn) {
    const b = box(acctBtn); const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
    const hit = document.elementFromPoint(cx, cy);
    avatar = {vis: vis(acctBtn), box: b, hitOnButton: !!(hit && (hit === acctBtn || acctBtn.contains(hit))), hitTag: hit ? hit.tagName + '.' + (hit.className || '') : null,
              img: !!acctBtn.querySelector('.account-avatar'), label: acctBtn.getAttribute('aria-label')};
  }
  const chip = document.querySelector('.account-menu-btn-status');
  const kids = header ? [...header.querySelectorAll(':scope > *')].filter(vis) : [];
  const overlaps = [];
  for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++) {
    const a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
    const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left), iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ix > 2 && iy > 2) overlaps.push([kids[i].className || kids[i].tagName, kids[j].className || kids[j].tagName, Math.round(ix) + 'x' + Math.round(iy)]);
  }
  const meta = document.querySelector('meta[name=viewport]');
  return {
    url: location.pathname + location.search, title: document.title,
    mscreen: document.body.dataset.mscreen || null, bodyClass: document.body.className.trim(),
    headerVisible: vis(header), topNavVisible: vis(top), topNav: links(top),
    phoneBarsInDom: bars.length, phoneBarsVisible: visibleBars.length, phoneBar: links(visibleBars[0] || null), phoneBarAttrs: visibleBars.map(b => [...b.attributes].map(a => a.name).filter(n => n.startsWith('data-')).join(' ')),
    navSurfaces: (vis(top) ? 1 : 0) + visibleBars.length,
    avatar, signin: signin ? {vis: vis(signin), text: txt(signin), box: box(signin)} : null,
    chip: chip ? {text: txt(chip), vis: vis(chip)} : null,
    headerOverlaps: overlaps, viewport: meta ? meta.content : null,
    hScroll: document.documentElement.scrollWidth > window.innerWidth,
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

def status_chain(client, url):
    chain = []; r = client.get(url, follow_redirects=False); chain.append((url, r.status_code)); hops = 0
    while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
        nxt = r.headers.get("location"); nxt = nxt if nxt.startswith("http") else client.base_url.join(nxt)
        r = client.get(str(nxt), follow_redirects=False); chain.append((str(nxt), r.status_code)); hops += 1
    return chain

def signin(client):
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state") or client.cookies.get("rtc_oauth_state")
    assert state, "no oauth state cookie"
    authed = client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert authed.status_code == 303, authed.status_code
    host = httpx.URL(str(client.base_url)).host
    return [{"name": c.name, "value": c.value, "domain": host, "path": "/", "httpOnly": True} for c in client.cookies.jar]

DEFAULT_ROUTES = [
  {"key": "dashboard", "path": "/dashboard"}, {"key": "browse", "path": "/browse"}, {"key": "browse-part-iii", "path": "/browse/part/iii"},
  {"key": "article-14", "path": "/browse/article/14"}, {"key": "laws", "path": "/laws"}, {"key": "laws-ndps", "path": "/laws/ndps"},
  {"key": "laws-uapa", "path": "/laws/uapa"}, {"key": "ndps-section-8", "path": "/laws/ndps/section/8"},
  {"key": "playground", "path": "/playground"}, {"key": "playground-plans", "path": "/playground?stage=plans"},
  {"key": "calendar", "path": "/calendar"}, {"key": "profile", "path": "/profile"}, {"key": "settings", "path": "/settings"},
  {"key": "billing", "path": "/billing/subscriptions"}, {"key": "tables", "path": "/tables"}, {"key": "search", "path": "/search"},
  {"key": "terms", "path": "/terms"}, {"key": "landing", "path": "/"},
]

async def run(args):
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    routes = json.loads(pathlib.Path(args.routes).read_text()) if args.routes else DEFAULT_ROUTES
    widths = [tuple(map(int, w.split("x"))) for w in args.widths.split(",")]
    themes = args.themes.split(",")
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = signin(client) if args.signin else []
    viewer = args.tier if args.signin else "guest"
    prof = out / ".chrome-profile"; shutil.rmtree(prof, ignore_errors=True)
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
                        data = base64.b64decode(shot["data"]); (out / name).write_bytes(data)
                        manifest["rows"].append({"key": key, "route": path, "width": w, "height": h, "theme": theme, "file": name,
                                                 "sha256": hashlib.sha256(data).hexdigest(), "status_chain": chain, "probe": probe})
                        av = probe.get("avatar") or {}
                        print(f"{name:66s} {chain[-1][1]} surfaces={probe['navSurfaces']} tabs={len(probe['phoneBar'])} "
                              f"avatar={'ok' if av.get('vis') and av.get('hitOnButton') else ('none' if not av else 'BAD')} "
                              f"overlaps={len(probe['headerOverlaps'])} chip={probe['chip']['text'] if probe.get('chip') else '-'}", flush=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--tier", default="free"); ap.add_argument("--signin", action="store_true")
    ap.add_argument("--widths", default="390x844,561x900,640x900,720x900,1280x900"); ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--routes"); ap.add_argument("--debug-port", type=int, default=9335)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
