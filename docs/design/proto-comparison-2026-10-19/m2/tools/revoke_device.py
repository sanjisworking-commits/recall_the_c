import asyncio, json, sys, urllib.request, websockets
sys.path.insert(0, sys.argv[2]); from capture_m2 import cdp, wait_event
PORT, DEV, BASE = int(sys.argv[1]), sys.argv[3], "https://recallthec-production.up.railway.app"
LIST = """(() => [...document.querySelectorAll('form[action*="/remove"]')].map(f => { let e = f; for (let i=0;i<6 && e && !/Registered/.test(e.innerText||''); i++) e = e.parentElement; return {id: f.getAttribute('action').split('/').slice(-2)[0], block: (e ? e.innerText : '').replace(/\\s+/g,' ').slice(0,140)}; }).concat([{id:'__removed__', block: (document.body.innerText.split('Removed devices')[1]||'').replace(/\\s+/g,' ').slice(0,300)}, {id:'__count__', block: (document.body.innerText.match(/\\d+ of \\d+ devices/)||[''])[0]}]))()"""
async def main():
    page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")))
    try:
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            st = {"id": 0, "events": []}; await cdp(ws, st, "Page.enable"); await cdp(ws, st, "Runtime.enable")
            async def go(url):
                st["events"].clear(); await cdp(ws, st, "Page.navigate", {"url": url})
                try: await wait_event(ws, st, "Page.loadEventFired")
                except TimeoutError: pass
                await asyncio.sleep(0.8)
            await go(BASE + "/profile/security/devices")
            before = (await cdp(ws, st, "Runtime.evaluate", {"expression": LIST, "returnByValue": True}))["result"]["value"]
            print("BEFORE", json.dumps(before, ensure_ascii=False))
            ids = [x["id"] for x in before]
            assert DEV in ids, "target device not listed"
            st["events"].clear()
            r = (await cdp(ws, st, "Runtime.evaluate", {"expression": f"(() => {{ const f = document.querySelector('form[action=\"/profile/security/devices/{DEV}/remove\"]'); if (!f) return 'no form'; f.querySelector('button').click(); return 'submitted ' + f.getAttribute('action'); }})()", "returnByValue": True}))["result"]["value"]
            print("ACTION", r)
            try: await wait_event(ws, st, "Page.loadEventFired")
            except TimeoutError: pass
            await asyncio.sleep(0.8)
            url = (await cdp(ws, st, "Runtime.evaluate", {"expression": "location.href", "returnByValue": True}))["result"]["value"]
            after = (await cdp(ws, st, "Runtime.evaluate", {"expression": LIST, "returnByValue": True}))["result"]["value"]
            print("AFTER", url, json.dumps(after, ensure_ascii=False))
            # let the profile register on an Act head request, then re-read
            await go(BASE + "/laws/ndps")
            kind = (await cdp(ws, st, "Runtime.evaluate", {"expression": "(() => { const h = document.querySelector('[data-act-head]'); const b = document.querySelector('.ActHead-btn'); return {kind: h && h.getAttribute('data-pg-kind'), cta: b && b.textContent.trim(), href: b && b.getAttribute('href')}; })()", "returnByValue": True}))["result"]["value"]
            print("HEAD after registration attempt", kind)
            await go(BASE + "/profile/security/devices")
            final = (await cdp(ws, st, "Runtime.evaluate", {"expression": LIST, "returnByValue": True}))["result"]["value"]
            print("ROSTER", json.dumps(final, ensure_ascii=False))
    finally:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{page['id']}")
asyncio.run(main())
