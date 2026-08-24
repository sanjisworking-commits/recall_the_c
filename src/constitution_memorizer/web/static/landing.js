/* Recall the C — landing page motion.
 *
 * Vanilla port of the Claude Design `DCLogic` prototype. Three scrolling
 * regimes share one engine:
 *
 *   hero + §01 (600vh scrubbed Part animation) ── free scroll
 *   §02 ↕ §03 ↕ §05 ──────────────────────────── snap corridor (CSS)
 *   closing 165vh block ───────────────────────── free scroll
 *
 * Nothing here ever writes the scroll position except an explicit nav-anchor
 * smooth scroll: CSS scroll-snap owns every landing, the letter field only
 * moves pixels, and the mobile mode-intro reads scroll but never touches it.
 *
 * Frame budget (especially on coarse-pointer / narrow phones):
 *   cache DOM at boot → measure geometry rarely → apply scroll from cache →
 *   requestAnimationFrame only while something is dirty or still easing.
 * Android Chrome toolbar height changes do not rebuild animation geometry.
 */
(function () {
  'use strict';

  var reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  // Baked prototype props (the design's defaults). Each landmark carries ONE
  // number: how far the letters have closed in (0 = scattered hero field,
  // 1 = sphere fully formed).
  var FIELD = { hero: 0, s01: 0.5, s02: 0.8, s03: 1, s05: 1, close: 1 };

  // Desktop keeps the original 1250-glyph field. Coarse/narrow phones use a
  // denser-looking ~62% budget — same contours, fewer offscreen samples.
  var FIELD_BUDGET_DESKTOP = 1250;
  var FIELD_BUDGET_MOBILE = 780;
  var WIDTH_SLACK = 8;
  var FOLLOW = 0.07;

  // The only mutable page state that outlives a frame: how many closing lines
  // are lit. (`stage` drove the removed running-head marker and is gone.)
  var state = { lit: 0 };

  // Letter-field working set.
  var parts = null, groups = null, canvas = null, ctx = null;
  var gatherP = 0, morphP = 0, gatherT, morphT;
  var introPlaying = false;            // set by setupModeIntro on ≤640
  var introMs = 0, t0 = Date.now();

  // Cached nodes — never querySelector inside the hot frame.
  var els = {
    bar: null,
    canvas: null,
    probe: null,
    pin: null,
    pinStmt: null,
    cards: [],
    method: null,
    learn: null,
    stage5: null,
    close: null,
    circlesWrap: null,
    circles: [],
    litLines: [],
    reveals: [],
    scrims: [],
    cardGeom: []
  };

  // Geometry in document coordinates. Rebuilt on load / fonts / orientation /
  // meaningful width change — not on Android toolbar height flicker.
  var geo = {
    ready: false,
    vw: 0,
    vh: 800,
    canvasW: 0,
    canvasH: 0,
    pinDocTop: 0,
    pinHeight: 0,
    stmtDocTop: 0,
    stmtHeight: 0,
    methodDocTop: 0,
    methodHeight: 0,
    learnDocTop: 0,
    learnHeight: 0,
    stage5DocTop: 0,
    stage5Height: 0,
    closeDocTop: 0,
    closeHeight: 0,
    circlesDocTop: 0,
    circlesHeight: 0,
    revealTops: [],
    keys: [],
    spherePos: null,
    closePos: null,
    pinEnd: null
  };

  var lastY = -1;
  var lastWidth = 0;
  var lastInnerH = 0;
  var raf = 0;
  var idleTo = 0;
  var resizeTo = 0;
  var fieldDirty = true;
  var lastBar = '';
  var lastCnvOp = '';
  var modeIntroResize = null;
  var modeIntroKick = null;

  var clamp = function (v) { return v < 0 ? 0 : v > 1 ? 1 : v; };

  function pageY() {
    return window.pageYOffset || document.documentElement.scrollTop || 0;
  }

  // Capability profile — viewport + pointer, never UA sniffing.
  function coarseLayout() {
    var w = window.innerWidth || 0;
    var coarse = false;
    try {
      coarse = !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
    } catch (e) { /* ignore */ }
    return w <= 900 || (coarse && w <= 1100);
  }

  function fieldDpr() {
    var raw = window.devicePixelRatio || 1;
    // Phone: 1.5 is sharp enough for 8–12px glyphs without 3× backing stores.
    // Desktop retina may go to 2.
    return Math.min(raw, coarseLayout() ? 1.5 : 2);
  }

  function fieldBudget() {
    return coarseLayout() ? FIELD_BUDGET_MOBILE : FIELD_BUDGET_DESKTOP;
  }

  function readStableVh() {
    var probe = els.probe;
    if (!probe || !probe.isConnected) {
      probe = document.querySelector('[data-vh-probe]');
      els.probe = probe;
    }
    var svh = probe && probe.offsetHeight;
    if (svh > 0) return svh;
    if (coarseLayout()) {
      return document.documentElement.clientHeight || window.innerHeight || 800;
    }
    return window.innerHeight || 800;
  }

  function setStyle(el, prop, value) {
    if (!el) return;
    if (el.style[prop] !== value) el.style[prop] = value;
  }

  function docTop(rect, y) {
    return rect.top + y;
  }

  function cacheDom() {
    els.bar = document.querySelector('[data-progress-bar]');
    els.canvas = document.querySelector('[data-brain]');
    els.probe = document.querySelector('[data-vh-probe]');
    els.pin = document.querySelector('[data-pin-src]');
    els.pinStmt = els.pin ? els.pin.querySelector('[data-pin] [data-reveal]') : null;
    els.cards = els.pin
      ? Array.prototype.slice.call(els.pin.querySelectorAll('[data-pcard]'))
      : [];
    els.method = document.getElementById('method');
    els.learn = document.getElementById('learn');
    els.stage5 = document.querySelector('[data-stage="5"]');
    els.close = document.querySelector('[data-lit-src]');
    els.circlesWrap = document.querySelector('[data-circles]');
    els.circles = els.circlesWrap
      ? Array.prototype.slice.call(els.circlesWrap.querySelectorAll('[data-circ]'))
      : [];
    els.litLines = els.close
      ? Array.prototype.slice.call(els.close.querySelectorAll('[data-l]'))
      : [];
    els.reveals = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
    els.scrims = Array.prototype.slice.call(document.querySelectorAll('[data-scrim]'));
    if (els.canvas) {
      canvas = els.canvas;
      if (!ctx) ctx = canvas.getContext('2d');
    }
  }

  // ── Letter field → sphere → brain ─────────────────────────────
  function setupField() {
    if (parts) return;
    try { buildField(); } catch (e) { parts = null; }
  }

  function buildField() {
    var D = window.BRAIN_PATHS;
    if (!D) throw new Error('brain path data not loaded');

    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('style', 'position:absolute;width:0;height:0;overflow:hidden;opacity:0');
    document.body.appendChild(svg);

    // Measure every subpath first, then hand out a fixed particle budget in
    // proportion to length, so long contours read and hairline folds survive.
    var elsP = [], lens = [], total = 0, i;
    for (i = 0; i < D.length; i++) {
      var path = document.createElementNS(ns, 'path');
      path.setAttribute('d', D[i]);
      svg.appendChild(path);
      var L = path.getTotalLength();
      elsP.push(path);
      lens.push(L);
      total += L;
    }

    var step = total / fieldBudget();
    var CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789§';
    parts = [];
    groups = [];

    for (i = 0; i < elsP.length; i++) {
      var Li = lens[i];
      var n = Math.max(2, Math.round(Li / step));
      var idx = [];
      for (var k = 0; k < n; k++) {
        var pt = elsP[i].getPointAtLength((k / (n - 1)) * Li);
        idx.push(parts.length);
        parts.push({ bx: pt.x, by: pt.y, ch: CHARS[(Math.random() * CHARS.length) | 0] });
      }
      groups.push({ idx: idx, closed: /z\s*$/i.test(D[i]), major: Li > 360 });
    }
    svg.remove();

    // Sphere seats (fibonacci) + scattered origins out in space.
    var N = parts.length;
    var golden = Math.PI * (3 - Math.sqrt(5));
    parts.forEach(function (p, i) {
      var yv = 1 - (i / (N - 1)) * 2;
      var r = Math.sqrt(Math.max(0, 1 - yv * yv));
      var th = golden * i;
      p.sx = Math.cos(th) * r;
      p.sy = yv;
      p.sz = Math.sin(th) * r;
      var a = Math.random() * Math.PI * 2;
      var d = 0.55 + Math.random() * 0.95;
      p.ox = Math.cos(a) * d;
      p.oy = Math.sin(a) * d * 0.9;
      p.delay = Math.random() * 0.42;
      p.accent = Math.random() < 0.09;
      p.size = 8 + Math.random() * 4;
    });
  }

  function drawField() {
    if (!canvas || !canvas.isConnected) {
      if (!els.canvas || !els.canvas.isConnected) cacheDom();
      canvas = els.canvas;
      if (canvas && !ctx) ctx = canvas.getContext('2d');
    }
    if (!parts) setupField();
    var c = canvas;
    if (!c || !parts) return false;

    var w = geo.canvasW, hgt = geo.canvasH;
    if (!w || !hgt) return false;

    var dpr = fieldDpr();
    var bw = Math.round(w * dpr), bh = Math.round(hgt * dpr);
    if (c.width !== bw || c.height !== bh) {
      c.width = bw;
      c.height = bh;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, hgt);

    // Follow the scroll-derived targets rather than jumping to them. This is the
    // ONLY smoothing in the page and it moves pixels, never the scroll position.
    if (typeof gatherT === 'number') {
      var dg = gatherT - gatherP;
      gatherP = Math.abs(dg) < 0.0005 ? gatherT : gatherP + dg * FOLLOW;
    }
    if (typeof morphT === 'number') {
      var dm = morphT - morphP;
      morphP = Math.abs(dm) < 0.0005 ? morphT : morphP + dm * FOLLOW;
    }
    var gp = gatherP || 0;
    var mp = morphP || 0;

    var easeOut = function (v) { return 1 - Math.pow(1 - v, 3); };
    var easeInOut = function (v) { return v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2; };

    var gEase = easeInOut;
    var morph = easeInOut(clamp(mp));
    var t = Date.now();
    var spin = (reduced ? 0 : t * 0.00007) + gp * 0.3 + morph * 0.5;

    var cx = w * 0.5, cy = hgt * 0.5;
    var R = Math.min(w * 0.3, hgt * 0.4);
    // Glyphs scale with the viewport — at full size on a phone the field reads
    // as a crowd rather than a haze.
    var gScale = Math.max(0.52, Math.min(1, Math.min(w, hgt * 1.4) / 1280)) * 0.72;
    var box = window.BRAIN_BOX || [940, 670];
    var bScale = Math.min(w * 0.00066, hgt * 0.00116);
    var bwBox = box[0] * bScale, bhBox = box[1] * bScale;

    var cosR = Math.cos(spin), sinR = Math.sin(spin);

    // Arrival progress, independent of scroll: 0 = far out in space and unlit,
    // 1 = the resting field.
    var intro = introMs > 0 ? clamp((Date.now() - t0) / introMs) : 1;

    // Scatter spread. The vertical spread is height-based, so on a portrait
    // phone the gathered field stretches into an upright oval void; cap the
    // vertical spread to the horizontal there so it stays circular.
    var spreadX = w * 0.5;
    var spreadY = hgt * 0.5;
    if (spreadY > spreadX) spreadY = spreadX;

    var pad = 24;
    var xMin = -pad, xMax = w + pad, yMin = -pad, yMax = hgt + pad;

    for (var i = 0; i < parts.length; i++) {
      var q = parts[i];
      var g = gEase(clamp((gp - q.delay) / (1 - q.delay)));

      var rx = q.sx * cosR - q.sz * sinR;
      var rz = q.sx * sinR + q.sz * cosR;
      var persp = 1 / (1 + rz * 0.42);

      var sphX = cx + rx * R * persp;
      var sphY = cy + q.sy * R * persp;
      var ai = intro >= 1 ? 1 : easeOut(clamp((intro - q.delay * 0.42) / (1 - q.delay * 0.42)));
      var push = 1 + (1 - ai) * 2.4;
      q.introA = ai;

      var spaceX = cx + q.ox * spreadX * push;
      var spaceY = cy + q.oy * spreadY * push;

      var x = spaceX + (sphX - spaceX) * g;
      var y = spaceY + (sphY - spaceY) * g;

      if (!reduced && g < 1) {
        var amp = Math.min(w, hgt) * 0.016 * (1 - g) * ai;
        x += Math.sin(t * 0.00034 + q.ox * 5.1) * amp;
        y += Math.cos(t * 0.00027 + q.oy * 6.3) * amp * 1.15;
      }

      if (morph > 0) {
        var bob = reduced ? 0 : morph * bScale * 9;
        var bX = cx - bwBox / 2 + q.bx * bScale + Math.sin(t * 0.00021 + q.by * 0.006) * bob;
        var bY = cy - bhBox / 2 + q.by * bScale + Math.sin(t * 0.00027 + q.bx * 0.005) * bob * 0.7;
        x += (bX - x) * morph;
        y += (bY - y) * morph;
      }
      q.x = x;
      q.y = y;
      q.depth = persp;
      q.on = x >= xMin && x <= xMax && y >= yMin && y <= yMax;
    }

    // Lines take over from the letters as the brain resolves. Accent contours
    // are indigo (#6E82C8 → rgb(110,130,200)) to match the page.
    if (morph > 0.86) {
      var la = clamp((morph - 0.86) / 0.14);
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      for (var gi = 0; gi < groups.length; gi++) {
        var grp = groups[gi];
        ctx.lineWidth = gi === 0 ? 1.5 : grp.major ? 1.2 : 0.9;
        ctx.strokeStyle = gi === 0 ? 'rgba(110,130,200,' + la.toFixed(3) + ')'
          : grp.major ? 'rgba(110,130,200,' + (la * 0.8).toFixed(3) + ')'
          : 'rgba(244,241,234,' + (la * 0.72).toFixed(3) + ')';
        ctx.beginPath();
        var ix = grp.idx;
        for (var k2 = 0; k2 < ix.length; k2++) {
          var qq = parts[ix[k2]];
          if (k2 === 0) ctx.moveTo(qq.x, qq.y); else ctx.lineTo(qq.x, qq.y);
        }
        if (grp.closed) ctx.closePath();
        ctx.stroke();
      }
    }

    // Letters fade out as the lines arrive. Skip offscreen / faded glyphs.
    var glyphA = 1 - clamp((morph - 0.8) / 0.2);
    if (glyphA > 0.02) {
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      var lastFont = '';
      for (var j = 0; j < parts.length; j++) {
        var p = parts[j];
        if (!p.on) continue;
        var a = glyphA * (0.3 + p.depth * 0.5) * (p.introA == null ? 1 : p.introA);
        if (a < 0.02) continue;
        var f = Math.max(3, Math.round(p.size * gScale * (0.75 + p.depth * 0.4))) + 'px "Source Sans 3", system-ui, sans-serif';
        if (f !== lastFont) { ctx.font = f; lastFont = f; }
        ctx.fillStyle = p.accent
          ? 'rgba(110,130,200,' + Math.min(1, a * 1.2).toFixed(3) + ')'
          : 'rgba(244,241,234,' + a.toFixed(3) + ')';
        ctx.fillText(p.ch, p.x, p.y);
      }
    }
    return true;
  }

  function fieldStillMoving() {
    if (introMs > 0 && (Date.now() - t0) < introMs + 80) return true;
    if (typeof gatherT === 'number' && Math.abs(gatherT - gatherP) > 0.0005) return true;
    if (typeof morphT === 'number' && Math.abs(morphT - morphP) > 0.0005) return true;
    return false;
  }

  // ── Reveals ───────────────────────────────────────────────────
  function reveal(el) {
    if (el.getAttribute('data-shown') || el.getAttribute('data-pending')) return;
    var d = reduced ? 0 : parseInt(el.getAttribute('data-delay') || '0', 10);
    if (!d) { el.setAttribute('data-shown', '1'); return; }
    el.setAttribute('data-pending', '1');
    setTimeout(function () { el.setAttribute('data-shown', '1'); }, d);
  }

  function revealAll() {
    if (!els.reveals.length) cacheDom();
    els.reveals.forEach(reveal);
  }

  function centreOfStored(docTopVal, height) {
    return docTopVal + height / 2 - geo.vh / 2;
  }

  // Expensive layout read. Not called from the hot scroll/idle path.
  function measureGeometry() {
    cacheDom();
    var vh = readStableVh();
    var y = pageY();
    var vw = window.innerWidth || 0;
    if (document.documentElement.scrollHeight < vh * 1.4) return;

    geo.vw = vw;
    geo.vh = vh;

    if (els.canvas) {
      var cr = els.canvas.getBoundingClientRect();
      geo.canvasW = cr.width;
      geo.canvasH = cr.height;
    }

    var pinR = els.pin ? els.pin.getBoundingClientRect() : null;
    geo.pinDocTop = pinR ? docTop(pinR, y) : 0;
    geo.pinHeight = pinR ? pinR.height : 0;
    geo.pinEnd = pinR ? geo.pinDocTop + Math.max(0, pinR.height - vh) : null;

    var stmtR = els.pinStmt ? els.pinStmt.getBoundingClientRect() : null;
    geo.stmtDocTop = stmtR ? docTop(stmtR, y) : 0;
    geo.stmtHeight = stmtR ? stmtR.height : 0;

    var methodR = els.method ? els.method.getBoundingClientRect() : null;
    geo.methodDocTop = methodR ? docTop(methodR, y) : 0;
    geo.methodHeight = methodR ? methodR.height : 0;

    var learnR = els.learn ? els.learn.getBoundingClientRect() : null;
    geo.learnDocTop = learnR ? docTop(learnR, y) : 0;
    geo.learnHeight = learnR ? learnR.height : 0;

    var s5R = els.stage5 ? els.stage5.getBoundingClientRect() : null;
    geo.stage5DocTop = s5R ? docTop(s5R, y) : 0;
    geo.stage5Height = s5R ? s5R.height : 0;

    var closeR = els.close ? els.close.getBoundingClientRect() : null;
    geo.closeDocTop = closeR ? docTop(closeR, y) : 0;
    geo.closeHeight = closeR ? closeR.height : 0;
    geo.closePos = closeR ? geo.closeDocTop : null;

    var circR = els.circlesWrap ? els.circlesWrap.getBoundingClientRect() : null;
    geo.circlesDocTop = circR ? docTop(circR, y) : 0;
    geo.circlesHeight = circR ? circR.height : 0;

    els.cardGeom = els.cards.map(function (el) {
      return { top: el.offsetTop, height: el.offsetHeight };
    });

    geo.revealTops = els.reveals.map(function (el) {
      return docTop(el.getBoundingClientRect(), y);
    });

    geo.keys = [
      { name: 'Hero', pos: 0, k: FIELD.hero },
      { name: '§01', pos: geo.pinEnd, k: FIELD.s01 },
      { name: '§02', pos: methodR ? centreOfStored(geo.methodDocTop, geo.methodHeight) : null, k: FIELD.s02 },
      { name: '§03', pos: learnR ? centreOfStored(geo.learnDocTop, geo.learnHeight) : null, k: FIELD.s03 },
      { name: '§05', pos: s5R ? centreOfStored(geo.stage5DocTop, geo.stage5Height) : null, k: FIELD.s05 },
      { name: 'Close', pos: geo.closePos, k: FIELD.close }
    ].filter(function (kf) { return kf.pos !== null && isFinite(kf.pos); });
    geo.keys.sort(function (a, b) { return a.pos - b.pos; });

    geo.spherePos = null;
    for (var ki = 0; ki < geo.keys.length; ki++) {
      if (geo.keys[ki].k >= 0.999) { geo.spherePos = geo.keys[ki].pos; break; }
    }
    geo.ready = true;
  }

  function gatherAt(pos) {
    var keys = geo.keys;
    if (!keys.length) return 0;
    if (pos <= keys[0].pos) return keys[0].k;
    for (var i = 0; i < keys.length - 1; i++) {
      var a = keys[i], b = keys[i + 1];
      if (pos <= b.pos) {
        var t = Math.max(0, Math.min(1, (pos - a.pos) / Math.max(1, b.pos - a.pos)));
        var easeK = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        return a.k + (b.k - a.k) * easeK;
      }
    }
    return keys[keys.length - 1].k;
  }

  function morphAt(pos) {
    if (geo.spherePos === null || geo.closePos === null || geo.closePos <= geo.spherePos) return 0;
    return Math.max(0, Math.min(1, (pos - geo.spherePos) / (geo.closePos - geo.spherePos)));
  }

  // Scroll apply: uses cached geometry. No querySelector / getBoundingClientRect
  // / offsetTop in this path.
  function applyScroll(y) {
    if (!geo.ready) return;
    var vh = geo.vh;
    var max = document.documentElement.scrollHeight - vh;
    var trueP = max > 0 ? Math.min(1, y / max) : 0;
    var barVal = (trueP * 100).toFixed(2) + '%';
    if (els.bar && barVal !== lastBar) {
      lastBar = barVal;
      els.bar.style.width = barVal;
    }

    gatherT = gatherAt(y);
    morphT = morphAt(y);

    var i, el;
    // No scrims ship on this page; keep the hook without layout reads.

    for (i = 0; i < els.reveals.length; i++) {
      el = els.reveals[i];
      if ((geo.revealTops[i] - y) < vh * 0.9) reveal(el);
      if (el.getAttribute('data-shown') && el.style.opacity !== '1') {
        el.style.opacity = '1';
        el.style.transform = 'none';
      }
    }

    if (els.pin) {
      var pinTop = geo.pinDocTop - y;
      var span = geo.pinHeight - vh;
      var p = span > 40 ? Math.max(0, Math.min(1, -pinTop / span)) : 1;
      if (els.canvas) {
        var enterP = Math.min(1, p / 0.12);
        var hold = 1;
        if (els.pinStmt) {
          var stmtBottom = geo.stmtDocTop + geo.stmtHeight - y;
          hold = Math.max(0, Math.min(1, stmtBottom / Math.max(1, vh * 0.3)));
        }
        var dim = Math.max(0, Math.min(enterP, hold));
        var op = (1 - 0.75 * dim).toFixed(3);
        if (op !== lastCnvOp) {
          lastCnvOp = op;
          els.canvas.style.opacity = op;
        }
      }

      var cards = els.cards;
      var n = cards.length;
      var narrow = geo.vw <= 900;
      for (i = 0; i < n; i++) {
        el = cards[i];
        if (narrow && !reduced) {
          var kk = Math.max(0, Math.min(1, (p - (i / n) * 0.7) / 0.3));
          setStyle(el, 'opacity', '1');
          setStyle(el, 'transform', 'translate3d(0,' + ((110 - 160 * kk) * vh / 100).toFixed(1) + 'px,0)');
          continue;
        }
        var start = 0.16 + (i / n) * 0.62;
        var kCard = reduced ? 1 : Math.max(0, Math.min(1, (p - start) / 0.22));
        var e = 1 - Math.pow(1 - kCard, 3);
        var cg = els.cardGeom[i] || { top: 0, height: 0 };
        var frameH = geo.pinHeight > vh ? vh : geo.pinHeight;
        var lift = Math.max(0, cg.top + cg.height - frameH + 10);
        var travel = Math.max(0, frameH - cg.top + lift);
        setStyle(el, 'opacity', kCard > 0 ? '1' : '0');
        setStyle(el, 'transform', 'translate3d(0,' + ((1 - e) * travel - lift).toFixed(1) + 'px,0)');
      }
    }

    var wrap = introPlaying ? null : els.circlesWrap;
    if (wrap) {
      var wide = geo.vw > 820;
      var wrTop = geo.circlesDocTop - y;
      var pc = Math.max(0, Math.min(1, (vh * 0.92 - wrTop) / (vh * 0.72)));
      var ml = (-24 + 27 * pc).toFixed(2) + '%';
      var gml = (-30 + 26 * pc).toFixed(2) + '%';
      var circles = els.circles;
      for (i = 0; i < circles.length; i++) {
        el = circles[i];
        if (wide) {
          if (i > 0) setStyle(el, 'marginLeft', ml);
          setStyle(el, 'marginTop', '');
        } else {
          setStyle(el, 'marginLeft', i % 3 === 0 ? '0%' : gml);
          setStyle(el, 'marginTop', i > 2 ? gml : '');
        }
        var on = pc * 6.4 > i + 0.15;
        setStyle(el, 'color', on ? '#f4f1ea' : 'rgba(244,241,234,0.62)');
        setStyle(el, 'borderColor', on ? 'rgba(244,241,234,0.34)' : 'rgba(244,241,234,0.14)');
      }
    }

    var lit = state.lit;
    if (els.close) {
      var srTop = geo.closeDocTop - y;
      var span2 = geo.closeHeight - vh;
      var pp = span2 > 0 ? Math.max(0, Math.min(1, -srTop / span2)) : 0;
      var pinned = srTop <= 1;
      var nLines = els.litLines.length || 1;
      lit = !pinned ? 0 : Math.max(1, Math.min(nLines, 1 + Math.floor(pp * nLines * 1.15)));
      var spans = els.litLines;
      for (i = 0; i < spans.length; i++) {
        el = spans[i];
        var lineOn = reduced || (pinned && i < lit);
        var boxed = el.hasAttribute('data-lbox');
        setStyle(el, 'color', lineOn
          ? ((!boxed && i === spans.length - 1 && lit >= spans.length) ? '#6E82C8' : '#ffffff')
          : 'rgba(244,241,234,0.26)');
      }
    }

    state.lit = lit;
  }

  function cancelIdle() {
    if (idleTo) { clearTimeout(idleTo); idleTo = 0; }
  }

  function requestTick() {
    if (document.hidden) return;
    if (!raf) raf = requestAnimationFrame(tick);
  }

  function tick() {
    raf = 0;
    if (document.hidden) return;
    if (!geo.ready) measureGeometry();
    var y = pageY();
    var scrolled = y !== lastY;
    if (scrolled) {
      lastY = y;
      applyScroll(y);
    }
    var moving = fieldStillMoving();
    if (fieldDirty || scrolled || moving) {
      drawField();
      fieldDirty = false;
    }
    var introMoving = modeIntroKick ? modeIntroKick() : false;
    if (moving || introMoving) {
      requestTick();
      return;
    }
    // Time-driven idle spin: full frame rate on desktop; ~12fps on coarse/narrow
    // so parked phones are not filling 780 glyphs sixty times a second.
    if (!reduced && parts) {
      if (coarseLayout()) {
        if (!idleTo) {
          idleTo = setTimeout(function () {
            idleTo = 0;
            fieldDirty = true;
            requestTick();
          }, 80);
        }
      } else {
        fieldDirty = true;
        requestTick();
      }
    }
  }

  function rebuildAndTick() {
    cacheDom();
    measureGeometry();
    fieldDirty = true;
    lastY = -1;
    if (modeIntroResize) modeIntroResize();
    requestTick();
  }

  function onResize() {
    var w = window.innerWidth || 0;
    var h = window.innerHeight || 0;
    var widthChanged = Math.abs(w - lastWidth) >= WIDTH_SLACK;
    var oriented = lastWidth > 0 && lastInnerH > 0 && ((lastWidth > lastInnerH) !== (w > h));
    if (coarseLayout() && !widthChanged && !oriented) {
      // Android Chrome toolbar: height-only. Do not rebuild field geometry.
      return;
    }
    var delay = (widthChanged || oriented) ? 40 : 120;
    clearTimeout(resizeTo);
    resizeTo = setTimeout(function () {
      lastWidth = window.innerWidth || 0;
      lastInnerH = window.innerHeight || 0;
      rebuildAndTick();
    }, delay);
  }

  /* Three scrolling regimes, one scroll engine. This state machine only
     switches `html.snap-active` on and off at the two gateways. It never sets
     scrollTop (except an explicit nav-anchor smooth scroll), never suppresses
     wheel input, and never corrects a landing. Direction is read from real
     scroll-position change, not wheel deltaY. */
  function setupSnapCorridor() {
    var ok = window.matchMedia('(min-width:901px)').matches &&
      !window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    if (!ok) return;
    var root = document.documentElement;
    var posY = function () { return window.pageYOffset || root.scrollTop || 0; };
    var topOf = function (node) {
      if (!node) return null;
      return Math.round(node.getBoundingClientRect().top + posY());
    };
    var prevY = posY(), active = false, suspended = false;
    // Set when the reader has been released at a boundary; cleared once they are
    // clearly away from it (mandatory snapping never lets the boundary persist).
    var released = null;
    var navT = null;
    var release = function (dir) {
      root.classList.remove('snap-active');
      active = false;
      released = dir;
    };

    var snapCheck = function () {
      if (suspended) { prevY = posY(); return; }
      var y = posY(), vh = window.innerHeight;
      var first = topOf(els.method);
      var last = topOf(els.stage5);
      if (first === null || last === null) return;
      var down = y > prevY;
      if (released === 'up' && (y < first - vh * 0.45 || y > first + vh * 0.3)) released = null;
      if (released === 'down' && (y > last + vh * 0.45 || y < last - vh * 0.3)) released = null;
      if (released) { prevY = y; return; }
      if (!active) {
        // Engage snapping only right at the gateway being entered — §02 coming
        // down, §05 coming up — so the browser settles onto that screen. The
        // window must NOT reach across the whole corridor: a fast flick (or a
        // browser that coalesces scroll events through momentum, e.g. Safari)
        // can make the first handled position already deep inside, and turning
        // mandatory snapping on there grabs the NEAREST snap point — which read
        // as §01 jumping straight to §05. Overshoot past the gateway simply
        // free-scrolls this pass instead of yanking to a far section.
        var enterDown = down && y >= first - vh * 0.25 && y < first + vh * 0.5;
        var enterUp = !down && y <= last + vh * 0.25 && y > last - vh * 0.5;
        if (enterDown || enterUp) { root.classList.add('snap-active'); active = true; }
      } else if (y < first - 24) release('up');
      else if (y > last + vh * 0.6) release('down');
      prevY = y;
    };

    // Leaving the corridor is decided from input INTENT, not an observed scroll
    // position: mandatory snapping never rests outside the three screens.
    var onIntent = function (e) {
      if (!active || suspended) return;
      var up = null;
      if (e.type === 'wheel') up = e.deltaY < 0;
      else if (e.type === 'keydown') {
        if (e.key === 'ArrowUp' || e.key === 'PageUp' || e.key === 'Home') up = true;
        else if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === 'End' || e.key === ' ') up = false;
        else return;
      } else return;
      var y = posY();
      var first = topOf(els.method);
      var last = topOf(els.stage5);
      if (up === true && first !== null && Math.abs(y - first) < 48) release('up');
      else if (up === false && last !== null && Math.abs(y - last) < 48) release('down');
    };

    // Anchor clicks: smooth is requested explicitly, and snapping steps aside
    // for the duration so it cannot hijack the destination.
    var onNavClick = function (e) {
      var a = e.target.closest && e.target.closest('a[href^="#"]');
      if (!a) return;
      var id = a.getAttribute('href').slice(1);
      var el = id ? document.getElementById(id) : null;
      if (!el) return;
      e.preventDefault();
      suspended = true;
      root.classList.remove('snap-active');
      active = false;
      window.scrollTo({ top: Math.round(el.getBoundingClientRect().top + posY()), behavior: 'smooth' });
      clearTimeout(navT);
      navT = setTimeout(function () { suspended = false; prevY = posY(); snapCheck(); }, 900);
    };

    window.addEventListener('scroll', snapCheck, { passive: true });
    window.addEventListener('scrollend', snapCheck);
    window.addEventListener('resize', snapCheck);
    window.addEventListener('wheel', onIntent, { passive: true });
    window.addEventListener('keydown', onIntent);
    document.addEventListener('click', onNavClick);
    snapCheck();
  }

  /* Mobile only (≤640px): the six mode circles arrive as one compact,
     overlapped memory cluster with letter fragments orbiting it, then resolve
     into the layout the CSS already describes — as a continuous, reversible,
     scroll-linked morph. One normalized progress (down 0→1, up 1→0 the exact
     same paths), driven by §03's travel through the viewport, smoothed only in
     the visual value. Read-only w.r.t. scroll — never scrollTo/preventDefault/
     lock. Reduced motion renders progress 1 immediately. */
  function setupModeIntro() {
    if (window.innerWidth > 640) return;
    if (!els.circlesWrap) cacheDom();
    var wrap = els.circlesWrap;
    if (!wrap) { setTimeout(setupModeIntro, 200); return; }
    var circles = els.circles.length >= 6
      ? els.circles
      : Array.prototype.slice.call(wrap.querySelectorAll('[data-circ]'));
    if (circles.length < 6) { setTimeout(setupModeIntro, 200); return; }

    var CLUSTER = 0.09, SCALE = 0.34, STAG = 0.035;
    // Extra angular travel each circle carries at progress 0, unwound to zero by
    // progress 1. Mixed directions so the knot uncoils rather than spins.
    var ARC = [40, 95, -80, 60, -100, -45].map(function (d) { return (d * Math.PI) / 180; });
    var seed = [], curP = 0, introDone = false;
    var measureSeed = function () {
      seed.forEach(function (s) { s.el.style.transform = ''; });
      var wr = wrap.getBoundingClientRect();
      var cx = wr.width / 2, cy = wr.height / 2;
      seed = circles.map(function (el, i) {
        var r = el.getBoundingClientRect();
        var rx = r.left - wr.left + r.width / 2;
        var ry = r.top - wr.top + r.height / 2;
        var base = window.getComputedStyle(el).transform;
        var vx = rx - cx, vy = ry - cy;
        return {
          el: el,
          base: base && base !== 'none' ? base : '',
          ox: cx - rx,
          oy: cy - ry,
          R: Math.max(1, Math.hypot(vx, vy)),
          th: Math.atan2(vy, vx),
          arc: ARC[i % ARC.length],
          r0: Math.min(Math.hypot(vx, vy), Math.max(wr.width, wr.height) * CLUSTER),
          label: el.querySelector('span:not([data-fill])'),
          lead: i === 5
        };
      });
    };
    measureSeed();

    // Letter fragments — a local layer, unrelated to the sphere/brain canvas.
    var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789§';
    var field = document.createElement('div');
    field.setAttribute('data-mfield', '1');
    field.setAttribute('aria-hidden', 'true');
    field.style.cssText = 'position:absolute;inset:-16%;pointer-events:none;overflow:hidden;z-index:0';
    var bits = [];
    var bitN = 36;
    for (var i = 0; i < bitN; i++) {
      var s = document.createElement('span');
      var ang = Math.random() * Math.PI * 2;
      var rad = 0.18 + Math.random() * 0.34;
      s.textContent = chars[(Math.random() * chars.length) | 0];
      s.style.cssText = 'position:absolute;font-family:Fraunces,Georgia,serif;line-height:1;' +
        'left:' + (50 + Math.cos(ang) * rad * 100).toFixed(1) + '%;' +
        'top:' + (50 + Math.sin(ang) * rad * 100).toFixed(1) + '%;' +
        'font-size:' + (8 + Math.random() * 6).toFixed(1) + 'px;' +
        'color:' + (Math.random() < 0.12 ? '#6E82C8' : '#f4f1ea') + ';';
      field.appendChild(s);
      bits.push({ el: s, ox: Math.cos(ang), oy: Math.sin(ang), o: 0.06 + Math.random() * 0.16, d: Math.random() * 0.3 });
    }
    wrap.insertBefore(field, wrap.firstChild);

    var ease = function (p) { return p < 0.5 ? 8 * p * p * p * p : 1 - Math.pow(-2 * p + 2, 4) / 2; };
    var paint = function (p) {
      curP = p;
      seed.forEach(function (s, i) {
        var sp = Math.max(0, Math.min(1, (p - i * STAG) / (1 - 5 * STAG)));
        // Radius opens across the whole span; rotation is spent by ~80%, so the
        // last fifth is pure settling with no residual spin.
        var eRad = ease(sp);
        var eRot = ease(Math.min(1, sp / 0.8));
        var r = s.r0 + (s.R - s.r0) * eRad;
        var th = s.th + s.arc * (1 - eRot);
        var back = 1 - eRad;
        s.el.style.transform = (s.base ? s.base + ' ' : '') +
          'translate(' + (s.ox + r * Math.cos(th)).toFixed(2) + 'px,' + (s.oy + r * Math.sin(th)).toFixed(2) + 'px)' +
          ' scale(' + (1 + SCALE * back).toFixed(3) + ')';
        var lp = Math.max(0, Math.min(1, (sp - 0.45) / 0.4));
        s.el.style.borderColor = 'rgba(' + (110 + 134 * lp).toFixed(0) + ',' + (130 + 111 * lp).toFixed(0) + ',' + (200 + 34 * lp).toFixed(0) + ',' + (0.4 - 0.26 * lp).toFixed(3) + ')';
        if (s.label) s.label.style.opacity = ((s.lead ? 0.9 : 0.26) + (1 - (s.lead ? 0.9 : 0.26)) * lp).toFixed(3);
      });
      var fp = Math.max(0, Math.min(1, (p - 0.3) / 0.5));
      bits.forEach(function (b) {
        var k = Math.max(0, Math.min(1, (fp - b.d) / 0.7));
        b.el.style.opacity = (b.o * (1 - k)).toFixed(3);
        b.el.style.transform = 'translate(' + (b.ox * 16 * k).toFixed(1) + 'px,' + (b.oy * 16 * k).toFixed(1) + 'px)';
      });
    };

    var resolved = false;
    var strip = function () {
      seed.forEach(function (s) {
        s.el.style.transform = '';
        s.el.style.borderColor = '';
        if (s.label) s.label.style.opacity = '';
      });
      field.style.display = 'none';
      resolved = true;
      introPlaying = false;
    };
    var clear = function () {
      strip();
      if (field.parentNode) field.parentNode.removeChild(field);
      introDone = true;
      modeIntroKick = null;
      modeIntroResize = null;
    };
    var render = function (p) {
      if (p > 0.9995) { if (!resolved) strip(); curP = 1; return; }
      if (resolved) { field.style.display = ''; resolved = false; }
      introPlaying = true;   // applyScroll leaves the circles alone meanwhile
      paint(p);
    };

    if (reduced) { render(1); return; }

    // One progress variable, derived from the section's travel through the
    // viewport — read only, never written. ~78% of a viewport of real scroll.
    var visual = 0, target = 0, painted = -1;
    var readTarget = function () {
      var vh = geo.vh || window.innerHeight || 800;
      var top = geo.circlesDocTop ? (geo.circlesDocTop - pageY()) : 0;
      if (!geo.circlesDocTop && wrap) {
        top = wrap.getBoundingClientRect().top;
      }
      return Math.max(0, Math.min(1, (vh * 0.92 - top) / (vh * 0.78)));
    };
    target = readTarget();
    visual = target;
    render(visual);
    var introNeedsFrame = false;
    modeIntroKick = function () {
      if (introDone || document.hidden) {
        introNeedsFrame = false;
        return false;
      }
      var rTop, vh;
      if (geo.ready) {
        rTop = geo.circlesDocTop - pageY();
        vh = geo.vh;
      } else {
        rTop = wrap.getBoundingClientRect().top;
        vh = window.innerHeight || 800;
      }
      if (rTop + (geo.circlesHeight || 0) < -vh * 0.5 || rTop > vh * 2) {
        introNeedsFrame = false;
        return false;
      }
      target = Math.max(0, Math.min(1, (vh * 0.92 - rTop) / (vh * 0.78)));
      var d = target - visual;
      visual = Math.abs(d) < 0.0008 ? target : visual + d * 0.12;
      introNeedsFrame = Math.abs(target - visual) >= 0.0008;
      if (Math.abs(visual - painted) >= 0.0008) {
        painted = visual;
        render(visual);
      }
      return introNeedsFrame;
    };

    modeIntroResize = function () {
      if (introDone) return;
      if (window.innerWidth > 640) {
        clear();
        return;
      }
      measureSeed();
      render(curP);
    };
  }

  // ── §02 cloze: tap a blank to reveal its word ─────────────────
  function setupCloze() {
    var words = ['deprived', 'life', 'liberty', 'procedure', 'law'];
    Array.prototype.forEach.call(document.querySelectorAll('[data-cloze]'), function (el) {
      var i = parseInt(el.getAttribute('data-cloze'), 10);
      el.addEventListener('click', function () {
        if (el.getAttribute('data-on')) {
          el.removeAttribute('data-on');
          el.innerHTML = '&nbsp;';
        } else {
          el.setAttribute('data-on', '1');
          el.textContent = words[i];
        }
      });
    });
  }

  // ── Boot ──────────────────────────────────────────────────────
  function boot() {
    cacheDom();
    lastWidth = window.innerWidth || 0;
    lastInnerH = window.innerHeight || 0;

    // Arrival: on a fresh load the letters fly in from deep space. Skipped for
    // reduced motion, and skipped when the browser restores scroll down the page.
    introMs = reduced ? 0 : 2400;
    t0 = Date.now();
    if ((window.pageYOffset || 0) > (window.innerHeight || 800) * 0.4) introMs = 0;

    measureGeometry();
    applyScroll(pageY());
    fieldDirty = true;
    requestTick();

    setTimeout(rebuildAndTick, 160);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { rebuildAndTick(); });
    }

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        if (raf) { cancelAnimationFrame(raf); raf = 0; }
        cancelIdle();
        return;
      }
      fieldDirty = true;
      lastY = -1;
      requestTick();
    });
    window.addEventListener('scroll', function () {
      cancelIdle();
      requestTick();
    }, { passive: true });
    window.addEventListener('resize', onResize);
    window.addEventListener('orientationchange', function () {
      clearTimeout(resizeTo);
      resizeTo = setTimeout(rebuildAndTick, 80);
    });

    // Content must never stay permanently invisible.
    setTimeout(revealAll, 1400);

    setupSnapCorridor();
    setupModeIntro();
    setupCloze();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
