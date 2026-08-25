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
 */
(function () {
  'use strict';

  var reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  // Baked prototype props (the design's defaults). Each landmark carries ONE
  // number: how far the letters have closed in (0 = scattered hero field,
  // 1 = sphere fully formed).
  var FIELD = { hero: 0, s01: 0.5, s02: 0.8, s03: 1, s05: 1, close: 1 };

  // The only mutable page state that outlives a frame: how many closing lines
  // are lit. (`stage` drove the removed running-head marker and is gone.)
  var state = { lit: 0 };

  // Letter-field working set.
  var parts = null, groups = null, canvas = null, ctx = null;
  var gatherP = 0, morphP = 0, gatherT, morphT;
  var introPlaying = false;            // set by setupModeIntro on ≤640
  var introMs = 0, t0 = Date.now();
  var lastY = -1, lastH = -1;

  var clamp = function (v) { return v < 0 ? 0 : v > 1 ? 1 : v; };

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
    var els = [], lens = [], total = 0, i;
    for (i = 0; i < D.length; i++) {
      var path = document.createElementNS(ns, 'path');
      path.setAttribute('d', D[i]);
      svg.appendChild(path);
      var L = path.getTotalLength();
      els.push(path);
      lens.push(L);
      total += L;
    }

    var step = total / 1250;
    var CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789§';
    parts = [];
    groups = [];

    for (i = 0; i < els.length; i++) {
      var Li = lens[i];
      var n = Math.max(2, Math.round(Li / step));
      var idx = [];
      for (var k = 0; k < n; k++) {
        var pt = els[i].getPointAtLength((k / (n - 1)) * Li);
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
    // Lazy attach: the canvas may appear after first frame.
    if (!canvas || !canvas.isConnected) {
      var el = document.querySelector('[data-brain]');
      if (!el) return;
      canvas = el;
      ctx = el.getContext('2d');
    }
    if (!parts) setupField();
    var c = canvas;
    if (!c || !parts) return;
    var rect = c.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    if (c.width !== Math.round(rect.width * dpr) || c.height !== Math.round(rect.height * dpr)) {
      c.width = Math.round(rect.width * dpr);
      c.height = Math.round(rect.height * dpr);
    }
    var w = rect.width, hgt = rect.height;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, hgt);

    // Follow the scroll-derived targets rather than jumping to them. This is the
    // ONLY smoothing in the page and it moves pixels, never the scroll position.
    var FOLLOW = 0.07;
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
    var bw = box[0] * bScale, bh = box[1] * bScale;

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
        var bX = cx - bw / 2 + q.bx * bScale + Math.sin(t * 0.00021 + q.by * 0.006) * bob;
        var bY = cy - bh / 2 + q.by * bScale + Math.sin(t * 0.00027 + q.bx * 0.005) * bob * 0.7;
        x += (bX - x) * morph;
        y += (bY - y) * morph;
      }
      q.x = x;
      q.y = y;
      q.depth = persp;
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

    // Letters fade out as the lines arrive.
    var glyphA = 1 - clamp((morph - 0.8) / 0.2);
    if (glyphA > 0.02) {
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      var lastFont = '';
      for (var j = 0; j < parts.length; j++) {
        var p = parts[j];
        var a = glyphA * (0.3 + p.depth * 0.5) * (p.introA == null ? 1 : p.introA);
        var f = Math.max(3, Math.round(p.size * gScale * (0.75 + p.depth * 0.4))) + 'px "Source Sans 3", system-ui, sans-serif';
        if (f !== lastFont) { ctx.font = f; lastFont = f; }
        ctx.fillStyle = p.accent
          ? 'rgba(110,130,200,' + Math.min(1, a * 1.2).toFixed(3) + ')'
          : 'rgba(244,241,234,' + a.toFixed(3) + ')';
        ctx.fillText(p.ch, p.x, p.y);
      }
    }
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
    Array.prototype.forEach.call(document.querySelectorAll('[data-reveal]'), reveal);
  }

  // ── Scroll-driven measurement ─────────────────────────────────
  function measure() {
    var vh = window.innerHeight || 800;
    var doc = document.documentElement;
    if (doc.scrollHeight < vh * 1.4) return; // still laying out

    var y = window.pageYOffset || doc.scrollTop || 0;

    // Top progress rail — always true page scroll.
    var max = doc.scrollHeight - vh;
    var trueP = max > 0 ? Math.min(1, y / max) : 0;
    var bar = document.querySelector('[data-progress-bar]');
    if (bar) bar.style.width = (trueP * 100).toFixed(2) + '%';

    var centreOf = function (sel) {
      var el = document.querySelector(sel);
      if (!el) return null;
      var r = el.getBoundingClientRect();
      return r.top + y - (vh / 2 - r.height / 2);
    };
    var pinEl = document.querySelector('[data-pin-src]');
    var pinEnd = null;
    if (pinEl) {
      var pr = pinEl.getBoundingClientRect();
      pinEnd = pr.top + y + Math.max(0, pr.height - vh);
    }
    var closeEl = document.querySelector('[data-lit-src]');
    var closePos = closeEl ? closeEl.getBoundingClientRect().top + y : null;
    var keys = [
      { name: 'Hero', pos: 0, k: FIELD.hero },
      { name: '§01', pos: pinEnd, k: FIELD.s01 },
      { name: '§02', pos: centreOf('#method'), k: FIELD.s02 },
      { name: '§03', pos: centreOf('#learn'), k: FIELD.s03 },
      { name: '§05', pos: centreOf('[data-stage="5"]'), k: FIELD.s05 },
      { name: 'Close', pos: closePos, k: FIELD.close }
    ].filter(function (kf) { return kf.pos !== null && isFinite(kf.pos); });
    keys.sort(function (a, b) { return a.pos - b.pos; });

    var easeK = function (t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
    var gatherAt = function (pos) {
      if (!keys.length) return 0;
      if (pos <= keys[0].pos) return keys[0].k;
      for (var i = 0; i < keys.length - 1; i++) {
        var a = keys[i], b = keys[i + 1];
        if (pos <= b.pos) {
          var t = Math.max(0, Math.min(1, (pos - a.pos) / Math.max(1, b.pos - a.pos)));
          return a.k + (b.k - a.k) * easeK(t);
        }
      }
      return keys[keys.length - 1].k;
    };

    var spherePos = null;
    for (var ki = 0; ki < keys.length; ki++) {
      if (keys[ki].k >= 0.999) { spherePos = keys[ki].pos; break; }
    }
    var morphAt = function (pos) {
      if (spherePos === null || closePos === null || closePos <= spherePos) return 0;
      return Math.max(0, Math.min(1, (pos - spherePos) / (closePos - spherePos)));
    };

    // Targets, not final values: drawField eases toward them each frame.
    gatherT = gatherAt(y);
    morphT = morphAt(y);

    // Per-section scrims (none in this build, but kept for parity).
    Array.prototype.forEach.call(document.querySelectorAll('[data-scrim]'), function (el) {
      var r = el.getBoundingClientRect();
      var enter = Math.max(0, Math.min(1, (vh - r.top) / (vh * 0.22)));
      var exit = Math.max(0, Math.min(1, r.bottom / (vh * 0.16)));
      el.style.opacity = Math.min(enter, exit).toFixed(3);
    });

    // Section reveals — re-assert every pass.
    Array.prototype.forEach.call(document.querySelectorAll('[data-reveal]'), function (el) {
      if (el.getBoundingClientRect().top < vh * 0.9) reveal(el);
      if (el.getAttribute('data-shown') && el.style.opacity !== '1') {
        el.style.opacity = '1';
        el.style.transform = 'none';
      }
    });

    // Part cards arrive one at a time while the arithmetic block is pinned.
    var pin = document.querySelector('[data-pin-src]');
    if (pin) {
      var r = pin.getBoundingClientRect();
      var span = r.height - vh;
      var p = span > 40 ? Math.max(0, Math.min(1, -r.top / span)) : 1;
      // The field holds here (its clock is frozen) but dims down so the squares
      // read cleanly, then comes back up on the way out.
      var cnv = document.querySelector('[data-brain]');
      if (cnv) {
        var enter = Math.min(1, p / 0.12);
        var hold = 1;
        var stmt = pin.querySelector('[data-pin] [data-reveal]');
        if (stmt) {
          var sr = stmt.getBoundingClientRect();
          hold = Math.max(0, Math.min(1, sr.bottom / Math.max(1, vh * 0.3)));
        }
        var dim = Math.max(0, Math.min(enter, hold));
        cnv.style.opacity = (1 - 0.75 * dim).toFixed(3);
      }

      var cards = pin.querySelectorAll('[data-pcard]');
      var n = cards.length;
      var narrow = window.innerWidth <= 900;
      // Phone spotlight: light the card whose on-screen centre is nearest the
      // viewport middle. Its top is the (live) grid top + its own translateY;
      // boxH mirrors the CSS `min(340px,44vw)`.
      var pgrid = pin.querySelector('[data-pgrid]');
      var gTop = pgrid ? pgrid.getBoundingClientRect().top : 0;
      var boxH = Math.min(340, window.innerWidth * 0.44);
      var bestI = -1, bestD = Infinity;
      Array.prototype.forEach.call(cards, function (el, i) {
        if (narrow && !reduced) {
          var kk = Math.max(0, Math.min(1, (p - (i / n) * 0.7) / 0.3));
          var ty = (110 - 160 * kk) * vh / 100;
          el.style.opacity = '1';
          el.style.transform = 'translate3d(0,' + ty.toFixed(1) + 'px,0)';
          var d = Math.abs((gTop + ty + boxH / 2) - vh * 0.5);
          if (d < bestD) { bestD = d; bestI = i; }
          return;
        }
        // Desktop / reduced-motion: the scroll spotlight never applies here, so
        // make sure no lit state lingers (e.g. after a resize from mobile).
        el.classList.remove('is-lit');
        var start = 0.16 + (i / n) * 0.62;
        var k = reduced ? 1 : Math.max(0, Math.min(1, (p - start) / 0.22));
        var e = 1 - Math.pow(1 - k, 3);
        var frameH = r.height > vh ? vh : r.height;
        var lift = Math.max(0, el.offsetTop + el.offsetHeight - frameH + 10);
        var travel = Math.max(0, frameH - el.offsetTop + lift);
        el.style.opacity = k > 0 ? '1' : '0';
        el.style.transform = 'translate3d(0,' + ((1 - e) * travel - lift).toFixed(1) + 'px,0)';
      });
      if (narrow && !reduced) {
        // One travelling spotlight: only the nearest card, and only while it is
        // genuinely near the middle (band), so nothing lit at the pin's ends.
        var litI = bestD < vh * 0.45 ? bestI : -1;
        Array.prototype.forEach.call(cards, function (el, i) {
          el.classList.toggle('is-lit', i === litI);
        });
      }
    }

    // Six mode circles: overlapped when the section arrives, spaced out as it
    // passes. On ≤640 the mode-intro owns them while it is playing.
    var wrap = introPlaying ? null : document.querySelector('[data-circles]');
    if (wrap) {
      var wide = window.innerWidth > 820;
      var wr = wrap.getBoundingClientRect();
      var pc = Math.max(0, Math.min(1, (vh * 0.92 - wr.top) / (vh * 0.72)));
      var ml = (-24 + 27 * pc).toFixed(2) + '%';
      var gml = (-30 + 26 * pc).toFixed(2) + '%';
      var circles = wrap.querySelectorAll('[data-circ]');
      Array.prototype.forEach.call(circles, function (el, i) {
        if (wide) {
          if (i > 0) el.style.marginLeft = ml;
          el.style.marginTop = '';
        } else {
          el.style.marginLeft = i % 3 === 0 ? '0%' : gml;
          el.style.marginTop = i > 2 ? gml : '';
        }
        var on = pc * 6.4 > i + 0.15;
        el.style.color = on ? '#f4f1ea' : 'rgba(244,241,234,0.62)';
        el.style.borderColor = on ? 'rgba(244,241,234,0.34)' : 'rgba(244,241,234,0.14)';
      });
    }

    // Closing statement lights line by line across its pinned scroll.
    var lit = state.lit;
    var src = document.querySelector('[data-lit-src]');
    if (src) {
      var sr2 = src.getBoundingClientRect();
      var span2 = sr2.height - vh;
      var pp = span2 > 0 ? Math.max(0, Math.min(1, -sr2.top / span2)) : 0;
      var pinned = sr2.top <= 1;
      var nLines = src.querySelectorAll('[data-l]').length || 1;
      lit = !pinned ? 0 : Math.max(1, Math.min(nLines, 1 + Math.floor(pp * nLines * 1.15)));

      var spans = src.querySelectorAll('[data-l]');
      Array.prototype.forEach.call(spans, function (el, i) {
        var on = reduced || (pinned && i < lit);
        var boxed = el.hasAttribute('data-lbox');
        el.style.color = on
          ? ((!boxed && i === spans.length - 1 && lit >= spans.length) ? '#6E82C8' : '#ffffff')
          : 'rgba(244,241,234,0.26)';
      });
    }

    state.lit = lit;
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
    var topOf = function (sel) {
      var el = document.querySelector(sel);
      return el ? Math.round(el.getBoundingClientRect().top + posY()) : null;
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
      var first = topOf('#method');
      var last = topOf('[data-stage="5"]');
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
      var first = topOf('#method');
      var last = topOf('[data-stage="5"]');
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
    var wrap = document.querySelector('[data-circles]');
    if (!wrap) { setTimeout(setupModeIntro, 200); return; }
    var circles = Array.prototype.slice.call(wrap.querySelectorAll('[data-circ]'));
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
    for (var i = 0; i < 54; i++) {
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
    };
    var render = function (p) {
      if (p > 0.9995) { if (!resolved) strip(); curP = 1; return; }
      if (resolved) { field.style.display = ''; resolved = false; }
      introPlaying = true;   // measure() leaves the circles alone meanwhile
      paint(p);
    };

    if (reduced) { render(1); return; }

    // One progress variable, derived from the section's travel through the
    // viewport — read only, never written. ~78% of a viewport of real scroll.
    var visual = 0, target = 0, raf = 0, painted = -1;
    var readTarget = function () {
      var r = wrap.getBoundingClientRect();
      var vh = window.innerHeight || 800;
      return Math.max(0, Math.min(1, (vh * 0.92 - r.top) / (vh * 0.78)));
    };
    target = readTarget();
    visual = target;
    render(visual);
    var loop = function () {
      raf = requestAnimationFrame(loop);
      var r = wrap.getBoundingClientRect();
      var vh = window.innerHeight || 800;
      if (r.bottom < -vh * 0.5 || r.top > vh * 2) return;
      target = Math.max(0, Math.min(1, (vh * 0.92 - r.top) / (vh * 0.78)));
      var d = target - visual;
      // Direction reversal is continuous: the same variable travels the other way.
      visual = Math.abs(d) < 0.0008 ? target : visual + d * 0.12;
      if (Math.abs(visual - painted) < 0.0008) return;
      painted = visual;
      render(visual);
    };

    var onResize = function () {
      if (introDone) return;
      if (window.innerWidth > 640) {
        if (raf) cancelAnimationFrame(raf);
        clear();
        window.removeEventListener('resize', onResize);
        return;
      }
      measureSeed();
      render(curP);
    };
    window.addEventListener('resize', onResize);
    raf = requestAnimationFrame(loop);
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
    // Arrival: on a fresh load the letters fly in from deep space. Skipped for
    // reduced motion, and skipped when the browser restores scroll down the page.
    introMs = reduced ? 0 : 2400;
    t0 = Date.now();
    if ((window.pageYOffset || 0) > (window.innerHeight || 800) * 0.4) introMs = 0;

    // The document does not reliably emit scroll events, so read scroll off a
    // frame loop and only re-measure when it actually moved.
    var tick = function () {
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      var h = document.documentElement.scrollHeight;
      if (y !== lastY || h !== lastH) { lastY = y; lastH = h; measure(); }
      drawField();
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);

    measure();
    setTimeout(measure, 160);
    // rAF is paused while the tab is hidden; timers keep running.
    setInterval(function () { if (document.hidden) { measure(); drawField(); } }, 250);
    var onVis = function () { measure(); drawField(); };
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('scroll', onVis, { passive: true });
    window.addEventListener('resize', onVis);
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
