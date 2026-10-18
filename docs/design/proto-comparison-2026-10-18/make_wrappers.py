import sys, pathlib
src_dir = pathlib.Path(sys.argv[1])
hook = r'''
<script>
(function(){
  var q = new URLSearchParams(location.search);
  function findLogic(){
    var root = document.getElementById('dc-root'); if(!root) return null;
    var key = Object.keys(root).find(function(k){return k.indexOf('__reactContainer')===0}); if(!key) return null;
    var stack=[root[key]], seen=new Set();
    while(stack.length){ var x=stack.pop(); if(!x||seen.has(x)) continue; seen.add(x);
      if(x.stateNode && x.stateNode.logic) return x.stateNode;
      if(x.child) stack.push(x.child); if(x.sibling) stack.push(x.sibling); }
    return null;
  }
  var tries=0;
  var t = setInterval(function(){
    tries++; var inst = findLogic();
    if(!inst){ if(tries>200) clearInterval(t); return; }
    clearInterval(t);
    var L = inst.logic; window.__L = L;
    var name = inst.__name;
    var props = {};
    ['viewer','notice','endState','defaultLaw','calDesign','gcalSyncState'].forEach(function(k){ if(q.get(k)) props[k]=q.get(k); });
    ['atLimit','showSourceStamp','simulateUploadFailure','sessionExpired'].forEach(function(k){ if(q.get(k)!==null) props[k]=q.get(k)==='1'||q.get(k)==='true'; });
    if(Object.keys(props).length && window.__dcSetProps) window.__dcSetProps(name, props);
    if(q.get('pin')==='1'){ var s=document.createElement('style'); s.textContent='[data-screen-label="Prototype phone"],[data-screen-label="Desktop app"]{position:fixed !important;left:0;top:0;z-index:9999;margin:0 !important;} body{overflow:hidden;background:#e8e8e5}'; document.head.appendChild(s); }
    var patch = {};
    if(q.get('screen')) patch.screen = q.get('screen');
    if(q.get('law')) { patch.law = q.get('law'); L._lawTouched = true; }
    patch.sheet = q.get('sheet')==='1';
    if(q.get('calMonth')) patch.calMonth = parseInt(q.get('calMonth'),10);
    if(q.get('seed')==='1' && L.seedDemo && L.state && L.state.added && !Object.keys(L.state.added).length) Object.assign(patch, L.seedDemo());
    if(q.get('empty')==='1') patch.added = {};
    if(q.get('screen')==='learn' && L.lnInit) patch.ln = L.lnInit();
    if(q.get('screen')==='calendar') { if(patch.calMonth===undefined) patch.calMonth = 9; patch.calDay = null; }
    setTimeout(function(){ L.setState(patch); window.__hooked = true; }, 50);
  }, 100);
})();
</script>
'''
for name, out in (("Recall the C - Playground.dc.html","phone.html"),("Recall the C - Playground Desktop.dc.html","desktop.html")):
    html = (src_dir/name).read_text(encoding="utf-8")
    assert "</body>" in html
    html = html.replace("</body>", hook + "</body>", 1)
    (src_dir/out).write_text(html, encoding="utf-8")
    print("wrote", out, len(html))
