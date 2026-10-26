import asyncio, json, sys, urllib.request, pathlib, websockets
sys.path.insert(0, sys.argv[2]); from capture_m2 import cdp, wait_event
PORT, BASE = int(sys.argv[1]), "https://recallthec-production.up.railway.app"
JS = """(() => {
  const main = document.querySelector('main') || document.body;
  const rows = [...document.querySelectorAll('[data-device], .device, li, tr, article, section')].filter(e => /device|this|revoke|remove|registered|last/i.test(e.textContent) && e.children.length && e.textContent.trim().length < 600);
  const per = [...document.querySelectorAll('form[action*="/remove"]')].map(f => { let e = f; for (let i=0;i<6 && e && !/Registered/.test(e.innerText||''); i++) e = e.parentElement; return {action: f.getAttribute('action'), block: (e ? e.innerText : '').replace(/\s+/g,' ').slice(0,160)}; });
  return {per, url: location.href, title: document.title, text: main.innerText.slice(0, 4000),
          forms: [...document.querySelectorAll('form')].map(f => ({action: f.getAttribute('action'), method: f.method, inputs: [...f.querySelectorAll('input')].map(i => i.name + '=' + (i.type==='hidden' && /token|csrf/i.test(i.name) ? '<hidden>' : i.value)), button: (f.querySelector('button')||{}).textContent}))};
})()"""
async def main():
    page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")))
    try:
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Runtime.enable")
            await cdp(ws, st, "Page.navigate", {"url": BASE + "/profile/security/devices"})
            try: await wait_event(ws, st, "Page.loadEventFired")
            except TimeoutError: pass
            await asyncio.sleep(0.8)
            r = (await cdp(ws, st, "Runtime.evaluate", {"expression": JS, "returnByValue": True}))["result"]["value"]
            print(json.dumps(r, indent=1, ensure_ascii=False))
    finally:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{page['id']}")
asyncio.run(main())
