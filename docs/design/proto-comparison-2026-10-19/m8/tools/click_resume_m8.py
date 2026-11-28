"""M8-Ra (G2): what a click on the Act head's "Resume Playground" does.

Headless Chrome over CDP with the dev fake sign-in. On the Bare Act page of a
paused account it clicks the head's action and records, from the browser's own
network events: whether the link carried the sheet-opener marker, whether the
page first fetched the target as a sheet (a request with the
`X-Requested-With: pg-sheet` header), whether the "Opening…" busy state was
set on the link, and where the browser ended up.

    .venv/bin/python …/m8/tools/click_resume_m8.py --base http://127.0.0.1:8933 --out <dir> [--path /laws/pss]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import time
import urllib.request

import httpx
import websockets

HERE = pathlib.Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("capture_m1r", HERE.parents[2] / "m1r" / "tools" / "capture_m1r.py")
m1r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m1r)

BEFORE = r"""
(() => { const a = document.querySelector('a.ActHead-btn'); if (!a) return null;
  window.__busy = false;
  new MutationObserver(() => { if (a.getAttribute('aria-busy') === 'true') window.__busy = true; }).observe(a, {attributes: true});
  return {text: a.textContent.trim(), href: a.getAttribute('href'), opener: a.hasAttribute('data-pg-sheet'), kind: a.getAttribute('data-pg-kind')}; })()
"""


async def run(args) -> int:
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cookies = m1r.signin(httpx.Client(base_url=args.base, timeout=20))
    prof = pathlib.Path(tempfile.mkdtemp(prefix="m8-click-profile-"))
    proc = subprocess.Popen([m1r.CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--remote-debugging-port={args.debug_port}",
                             f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rec: dict = {"base": args.base, "path": args.path, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{args.debug_port}/json")); break
            except Exception:
                time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            st = {"id": 0, "events": []}
            for method in ("Page.enable", "Network.enable", "Runtime.enable"):
                await m1r.cdp(ws, st, method)
            for c in cookies:
                await m1r.cdp(ws, st, "Network.setCookie", c)

            async def ev(expr):
                return (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))["result"].get("value")

            await m1r.cdp(ws, st, "Page.navigate", {"url": args.base + args.path})
            try:
                await m1r.wait_event(ws, st, "Page.loadEventFired")
            except TimeoutError:
                pass
            await asyncio.sleep(0.8)
            rec["link"] = await ev(BEFORE)
            st["events"].clear()
            await ev("document.querySelector('a.ActHead-btn').click()")
            busy = False
            for _ in range(30):
                await asyncio.sleep(0.1)
                try:
                    busy = busy or bool(await ev("window.__busy === true"))
                except Exception:
                    pass
            # drain pending events
            try:
                await m1r.wait_event(ws, st, "Page.loadEventFired", timeout=3)
            except Exception:
                pass
            requests = [e["params"]["request"] for e in st["events"] if e.get("method") == "Network.requestWillBeSent"]
            sheet_fetches = [r["url"].replace(args.base, "") for r in requests
                             if any(k.lower() == "x-requested-with" and v == "pg-sheet" for k, v in (r.get("headers") or {}).items())]
            rec["sheet_fetches_before_navigation"] = sheet_fetches
            rec["busy_state_was_set"] = busy
            rec["landed_on"] = await ev("location.pathname")
            rec["dialog_open"] = await ev("!!document.querySelector('dialog[open]')")
        (out / "resume-click.json").write_text(json.dumps(rec, indent=1))
        print(json.dumps(rec))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--path", default="/laws/pss"); ap.add_argument("--debug-port", type=int, default=9347)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
