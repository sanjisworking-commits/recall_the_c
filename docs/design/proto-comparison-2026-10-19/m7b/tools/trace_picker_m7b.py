"""M7b (Q8): click-by-click trace of the section picker's whole-section /
clause behaviour, through headless Chrome over CDP (the driver and the dev
fake Google sign-in of `m1r/tools/capture_m1r.py`; the browser profile lives
in a temporary directory outside the repository).

On the first unselected section that offers at least three clauses:

  1  tick the section
  2  click its second clause (the user's "untick this one")
  3  click the same clause again
  4  untick the section

and after each step record: the section box (checked / indeterminate /
aria-checked), which clause boxes are ticked, the block's data-check-state,
what the form would submit for that section (`section=` and `unit=` values),
the selection counter and the submit label. A screenshot is taken after
step 2, where the defect shows.

    .venv/bin/python …/m7b/tools/trace_picker_m7b.py --base http://127.0.0.1:8929 --out <dir> --path /playground/laws/bns/sections
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websockets

HERE = pathlib.Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("capture_m1r", HERE.parents[2] / "m1r" / "tools" / "capture_m1r.py")
m1r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m1r)

SETUP = r"""
(() => {
  const blocks = [...document.querySelectorAll('.pg-pick-section')];
  const b = blocks.find(x => x.getAttribute('data-check-state') === 'none' && !x.classList.contains('is-disabled') && x.querySelectorAll('.pg-pick-clause-check').length >= 3);
  if (!b) return null;
  window.__b = b; const d = b.querySelector('details'); if (d) d.open = true;
  b.scrollIntoView({block: 'center'});
  return {section: b.getAttribute('data-section'), clauses: b.querySelectorAll('.pg-pick-clause-check').length};
})()
"""
SNAP = r"""
(() => {
  const b = window.__b; const s = b.querySelector('.pg-pick-check'); const u = [...b.querySelectorAll('.pg-pick-clause-check')];
  const form = document.querySelector('[data-pg-picker-form]'); const fd = new FormData(form); const n = b.getAttribute('data-section');
  const ownUnits = new Set(u.map(x => x.value));
  const submit = document.querySelector('[data-pg-aside-submit]') || document.querySelector('[data-pg-submit]');
  return {
    sectionChecked: s.checked, sectionIndeterminate: s.indeterminate, ariaChecked: s.getAttribute('aria-checked'),
    checkState: b.getAttribute('data-check-state'),
    clausesTicked: u.map((x, i) => x.checked ? i + 1 : null).filter(Boolean), clauseCount: u.length,
    submitsSection: fd.getAll('section').includes(n), submitsUnits: fd.getAll('unit').filter(v => ownUnits.has(v)).length,
    counter: (document.querySelector('[data-pg-aside-n]') || {}).textContent, submitLabel: submit ? submit.textContent.trim() : null,
  };
})()
"""
STEPS = [
    ("1 tick the section", "window.__b.querySelector('.pg-pick-check').click()"),
    ("2 click clause 2 (untick it)", "window.__b.querySelectorAll('.pg-pick-clause-check')[1].click()"),
    ("3 click clause 2 again", "window.__b.querySelectorAll('.pg-pick-clause-check')[1].click()"),
    ("4 untick the section", "window.__b.querySelector('.pg-pick-check').click()"),
]


async def run(args) -> int:
    import httpx

    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url=args.base, timeout=20)
    cookies = m1r.signin(client)
    prof = pathlib.Path(tempfile.mkdtemp(prefix="m7b-picker-profile-"))
    proc = subprocess.Popen([m1r.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                             f"--remote-debugging-port={args.debug_port}", f"--user-data-dir={prof}", "--window-size=1280,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    record: dict = {"label": args.label, "base": args.base, "path": args.path, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "steps": []}
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
            await m1r.cdp(ws, st, "Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await m1r.cdp(ws, st, "Page.navigate", {"url": args.base + args.path})
            try:
                await m1r.wait_event(ws, st, "Page.loadEventFired")
            except TimeoutError:
                pass
            await asyncio.sleep(0.6)

            async def ev(expr):
                return (await m1r.cdp(ws, st, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))["result"].get("value")

            record["block"] = await ev(SETUP)
            if not record["block"]:
                raise SystemExit("no unselected section with three clauses on this page")
            record["steps"].append({"step": "0 initial", **(await ev(SNAP))})
            for name, action in STEPS:
                await ev(action)
                await asyncio.sleep(0.15)
                snap = await ev(SNAP)
                record["steps"].append({"step": name, **snap})
                if name.startswith("2"):
                    shot = await m1r.cdp(ws, st, "Page.captureScreenshot", {"format": "png"})
                    data = base64.b64decode(shot["data"]); fname = f"{args.label}_picker_after-step-2_1280x900.png"
                    (out / fname).write_bytes(data); record["screenshot"] = {"file": fname, "sha256": hashlib.sha256(data).hexdigest()}
            record["exceptions"] = [e["params"]["exceptionDetails"].get("text") for e in st["events"] if e.get("method") == "Runtime.exceptionThrown"]
        (out / "picker-trace.json").write_text(json.dumps(record, indent=1))
        for s in record["steps"]:
            print(f'{s["step"]:30} section={"✓" if s["sectionChecked"] else ("–" if s["sectionIndeterminate"] else "·")} state={s["checkState"]:4} '
                  f'clauses={s["clausesTicked"]} of {s["clauseCount"]} submits section={s["submitsSection"]} units={s["submitsUnits"]} label="{s["submitLabel"]}"', flush=True)
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", default="plus")
    ap.add_argument("--path", default="/playground/laws/bns/sections"); ap.add_argument("--debug-port", type=int, default=9339)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
