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
  targets          every visible shell control (top-nav links, phone tabs, account
                   button / Sign in) with its CSS-px box and whether it meets 44×44
  contrast         computed text colour vs. the composited background behind each
                   shell label, as a WCAG ratio (M1-R close: A02 for everyone)

Optional per-row extras (M1-R close, 2026-11-06):
  --focus KEYS     on the named route keys, press Tab repeatedly and record the
                   focused shell control plus its :focus-visible outline each time
  --tap-profile    at phone widths (< 561), click the Profile tab after the probe,
                   wait for the load and record the URL and the identity shown

Usage:
  capture_m1r.py --base http://127.0.0.1:8914 --out DIR --label candidate-free --tier free \
      [--signin] [--widths 320x568,390x844,561x900,640x900,720x900,1280x900] [--themes light,dark] [--routes routes.json]
      [--focus browse,settings] [--tap-profile]
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
  // ── M1-R close: targets + contrast ────────────────────────────────────────
  const parseColor = s => {
    if (!s) return null;
    let m = s.match(/^rgba?\(([^)]+)\)$/);
    if (m) { const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; }
    m = s.match(/^color\(srgb ([^)]+)\)$/);
    if (m) { const p = m[1].split(/[\s\/]+/).filter(Boolean).map(Number); return {r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1}; }
    return null;
  };
  const over = (fg, bg) => ({r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1});
  const bgBehind = el => {
    // composite the ancestors' background-colors (innermost first) over opaque paper
    const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parseColor(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = {r: 255, g: 255, b: 255, a: 1};
    const html = parseColor(getComputedStyle(document.documentElement).backgroundColor); if (html && html.a > 0) acc = over(html, acc);
    for (let i = layers.length - 1; i >= 0; i--) acc = over(layers[i], acc);
    return acc;
  };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100; };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const controls = [];
  const push = (kind, el) => { if (!el || !vis(el)) return; const b = box(el); const fg = parseColor(getComputedStyle(el).color); const bg = bgBehind(el);
    const fgc = fg ? (fg.a < 1 ? over(fg, bg) : fg) : null;
    controls.push({kind, t: txt(el), href: el.getAttribute('href'), current: !!(el.getAttribute('aria-current') || el.classList.contains('is-active')), box: b, meets44: b.w >= 44 && b.h >= 44,
                   fg: fgc ? hex(fgc) : null, bg: hex(bg), ratio: fgc ? ratio(fgc, bg) : null}); };
  if (vis(top)) [...top.querySelectorAll('a,button')].forEach(a => push('topnav', a));
  visibleBars.forEach(bar => [...bar.querySelectorAll('a,button')].forEach(a => push('phonetab', a)));
  push('account', acctBtn); push('signin', signin); push('chip', chip);
  const smallTargets = controls.filter(c => c.kind !== 'chip' && !c.meets44).map(c => `${c.kind}:${c.t}:${c.box.w}x${c.box.h}`);
  const lowContrast = controls.filter(c => c.ratio !== null && c.ratio < 4.5).map(c => `${c.kind}:${c.t}:${c.fg}/${c.bg}=${c.ratio}`);
  return {
    targets: controls, smallTargets, lowContrast,
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

FOCUS_PROBE = r"""
(() => {
  const el = document.activeElement; if (!el || el === document.body) return {el: 'body'};
  const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
  const shell = el.closest('header.site-header') ? 'header' : (el.closest('nav.mobile-tabbar') ? 'phonebar' : (el.closest('.mobile-topbar') ? 'topbar' : 'page'));
  return {el: el.tagName + '.' + (el.className || '').toString().trim().split(/\s+/).slice(0, 3).join('.'), text: (el.innerText || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 40),
          href: el.getAttribute('href'), shell, focusVisible: el.matches(':focus-visible'),
          outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 ? `${cs.outlineWidth} ${cs.outlineStyle} ${cs.outlineColor}` : null,
          boxShadow: cs.boxShadow !== 'none' ? cs.boxShadow : null, box: {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)},
          inViewport: r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth};
})()
"""

PROFILE_PROBE = r"""
(() => {
  const t = s => { const e = document.querySelector(s); return e ? e.innerText.replace(/\s+/g, ' ').trim() : null; };
  const bar = [...document.querySelectorAll('nav.mobile-tabbar')].find(b => getComputedStyle(b).display !== 'none');
  const current = bar ? [...bar.querySelectorAll('a')].filter(a => a.getAttribute('aria-current') || a.classList.contains('is-active')).map(a => a.innerText.trim()) : null;
  return {url: location.pathname, title: document.title, mscreen: document.body.dataset.mscreen || null,
          name: t('.profile-name'), email: ([...document.querySelectorAll('p.muted, .muted')].map(e => e.innerText.trim()).find(x => /@/.test(x)) || null), bodyHasEmail: /@/.test(document.body.innerText),
          currentTab: current, signoutPresent: !!document.querySelector('form[action*="logout"], form[action*="signout"], [data-signout], .settings-signout-form')};
})()
"""

async def press_tab(ws, st, shift=False):
    for t in ("keyDown", "keyUp"):
        await cdp(ws, st, "Input.dispatchKeyEvent", {"type": t, "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9, "nativeVirtualKeyCode": 9, "modifiers": 8 if shift else 0})

async def phone_bar_trail(ws, st):
    """The fixed bar sits last in the DOM, after the page content, so a plain Tab walk
    rarely reaches it within a short trail. Put focus on the first tab programmatically,
    then drive Tab / Shift+Tab with real key events so every tab is recorded in its
    keyboard (:focus-visible) state."""
    ok = (await cdp(ws, st, "Runtime.evaluate", {"expression": "(() => { const b = [...document.querySelectorAll('nav.mobile-tabbar')].find(n => getComputedStyle(n).display !== 'none'); const a = b && b.querySelector('a,button'); if (!a) return false; a.focus(); return true; })()", "returnByValue": True}))["result"]["value"]
    if not ok: return []
    trail = []
    for _ in range(4):
        await press_tab(ws, st)
        trail.append((await cdp(ws, st, "Runtime.evaluate", {"expression": FOCUS_PROBE, "returnByValue": True}))["result"]["value"])
    for _ in range(4):
        await press_tab(ws, st, shift=True)
        trail.append((await cdp(ws, st, "Runtime.evaluate", {"expression": FOCUS_PROBE, "returnByValue": True}))["result"]["value"])
    return trail

async def focus_trail(ws, st, limit=14):
    trail = []
    await cdp(ws, st, "Runtime.evaluate", {"expression": "document.activeElement && document.activeElement.blur(); window.scrollTo(0,0)"})
    for _ in range(limit):
        await press_tab(ws, st)
        f = (await cdp(ws, st, "Runtime.evaluate", {"expression": FOCUS_PROBE, "returnByValue": True}))["result"]["value"]
        trail.append(f)
        if f.get("shell") == "page" and len(trail) > 1 and trail[-2].get("shell") != "page":
            break  # left the shell: the header/phone bar trail is complete
    return trail

async def tap_profile(ws, st, probe):
    tab = next((t for t in probe.get("phoneBar") or [] if (t.get("t") or "").strip().lower().startswith("profile")), None)
    if not tab: return {"error": "no visible Profile tab"}
    cx, cy = tab["box"]["x"] + tab["box"]["w"] / 2, tab["box"]["y"] + tab["box"]["h"] / 2
    st["events"].clear()
    for t in ("mousePressed", "mouseReleased"):
        await cdp(ws, st, "Input.dispatchMouseEvent", {"type": t, "x": cx, "y": cy, "button": "left", "clickCount": 1})
    try: await wait_event(ws, st, "Page.loadEventFired")
    except TimeoutError: pass
    await asyncio.sleep(0.4)
    res = (await cdp(ws, st, "Runtime.evaluate", {"expression": PROFILE_PROBE, "returnByValue": True}))["result"]["value"]
    res["tappedAt"] = [round(cx), round(cy)]; res["tabHref"] = tab.get("href")
    shot = await cdp(ws, st, "Page.captureScreenshot", {"format": "png"})
    return res, base64.b64decode(shot["data"])

async def run(args):
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    routes = json.loads(pathlib.Path(args.routes).read_text()) if args.routes else DEFAULT_ROUTES
    widths = [tuple(map(int, w.split("x"))) for w in args.widths.split(",")]
    themes = args.themes.split(",")
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = signin(client) if args.signin else []
    focus_keys = set(args.focus.split(",")) if args.focus else set()
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
                        row = manifest["rows"][-1]
                        if key in focus_keys and theme == "light":
                            row["focusTrail"] = await focus_trail(ws, st)
                            if probe.get("phoneBarsVisible"):
                                row["phoneBarTrail"] = await phone_bar_trail(ws, st)
                        if args.tap_profile and w < 561 and theme == "light" and (probe.get("phoneBar") or []):
                            tapped = await tap_profile(ws, st, probe)
                            if isinstance(tapped, tuple):
                                res, png = tapped; tname = f"{args.label}_{viewer}_{key}_{w}x{h}_{theme}_tap-profile.png"
                                (out / tname).write_bytes(png); res["file"] = tname; res["sha256"] = hashlib.sha256(png).hexdigest(); row["profileTap"] = res
                            else:
                                row["profileTap"] = tapped
                        av = probe.get("avatar") or {}
                        extra = ""
                        if probe.get("smallTargets"): extra += f" SMALL={len(probe['smallTargets'])}"
                        if probe.get("lowContrast"): extra += f" LOWC={probe['lowContrast'][:2]}"
                        if row.get("focusTrail"): extra += f" focus={len(row['focusTrail'])}/{sum(1 for f in row['focusTrail'] if f.get('outline'))}"
                        if row.get("phoneBarTrail"): extra += f" bar={len(row['phoneBarTrail'])}/{sum(1 for f in row['phoneBarTrail'] if f.get('outline') and f.get('shell') == 'phonebar')}"
                        if row.get("profileTap"): extra += f" tap→{row['profileTap'].get('url')}:{row['profileTap'].get('name')}"
                        print(f"{name:66s} {chain[-1][1]} surfaces={probe['navSurfaces']} tabs={len(probe['phoneBar'])} "
                              f"avatar={'ok' if av.get('vis') and av.get('hitOnButton') else ('none' if not av else ('hidden' if not probe.get('headerVisible') else 'BAD'))} "
                              f"overlaps={len(probe['headerOverlaps'])} chip={probe['chip']['text'] if probe.get('chip') else '-'}{extra}", flush=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--tier", default="free"); ap.add_argument("--signin", action="store_true")
    ap.add_argument("--widths", default="390x844,561x900,640x900,720x900,1280x900"); ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--routes"); ap.add_argument("--debug-port", type=int, default=9335)
    ap.add_argument("--focus", help="comma-separated route keys on which to record a keyboard Tab trail (light theme)")
    ap.add_argument("--tap-profile", action="store_true", help="at phone widths, tap the Profile tab after the probe and record where it lands")
    raise SystemExit(asyncio.run(run(ap.parse_args())))
