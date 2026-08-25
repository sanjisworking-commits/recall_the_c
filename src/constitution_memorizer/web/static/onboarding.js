/* First-login onboarding tour (design: First-Login Onboarding.dc.html +
   Onboarding Guide.dc.html; motion spec: ONBOARDING-MOTION-HANDOFF.md).

   A guidance layer over the real pages: one travelling guide card that glides
   between live targets, a fixed Getting-started checklist, and a spotlight
   ring on the current target. Loaded only while onboarding_status == "active";
   Skip/Finish post the new status to /onboarding/state.

   The tutorial is restricted to Article 1(1): first login shows a full-screen
   prompt (start the tutorial, or skip straight to the dashboard); the guided
   path is Browse → Article 1 → Article 1(1) → Calendar → Settings, and the
   finish lands on Browse. Goals (4): find Article 1(1) → complete it → see
   the revision schedule → set up calendar sync. Progress across page loads
   lives in localStorage; the server stores the coarse status
   (active/skipped/completed). */
(function () {
  "use strict";

  var body = document.body;
  if ((body.getAttribute("data-onboarding") || "") !== "active") return;
  if (!body.classList.contains("is-authed")) return;

  var path = window.location.pathname;
  if (path.indexOf("/admin") === 0) return;

  // Desktop-only for now — the phone UI changes and gets its own tour design
  // later. Not skipped server-side: the tour waits for a desktop visit.
  if (window.matchMedia && window.matchMedia("(max-width: 820px)").matches) {
    return;
  }

  // Captured before app.js listeners can strip ?done= from the URL.
  var params = new URLSearchParams(window.location.search);

  var STORE_KEY = "cm-onboarding-v1";
  // The one unit the tutorial teaches with — everything else stays quiet.
  var TOUR_UNIT_ID = "article-1-clause-1";
  var TOUR_UNIT = "/learn/" + TOUR_UNIT_ID;
  var TOUR_ARTICLE = "/browse/article/1";
  var EASE = "cubic-bezier(0.22,1,0.36,1)";
  var GOAL_LABELS = [
    "Find Article 1(1)",
    "Complete Article 1(1)",
    "See your revision schedule",
    "Set up calendar sync",
  ];

  // Once the tour ends in this browser it must never restart from a cached
  // page (back button, bfcache) whose HTML still says "active". The flag
  // outlives the state store; a Settings replay clears it after the server
  // confirms the status really is active again.
  var DONE_FLAG = "cm-onboarding-finished";
  function hasFinishedFlag() {
    try {
      return localStorage.getItem(DONE_FLAG) === "1";
    } catch (e) {
      return false;
    }
  }
  function setFinishedFlag() {
    try {
      localStorage.setItem(DONE_FLAG, "1");
    } catch (e) {
      /* ignore */
    }
  }
  function clearFinishedFlag() {
    try {
      localStorage.removeItem(DONE_FLAG);
    } catch (e) {
      /* ignore */
    }
  }

  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {};
    } catch (e) {
      return {};
    }
  }
  var state = loadState();
  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch (e) {
      /* ignore */
    }
  }

  function reduced() {
    return (
      !document.documentElement.classList.contains("rtc-anim") ||
      (window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    );
  }
  function isMobile() {
    return window.matchMedia && window.matchMedia("(max-width: 820px)").matches;
  }

  /* ── audio cues ────────────────────────────────────────────────────
     Two voices cut from the same source, so they read as siblings:
       tick — 250ms, -9 dBFS: an onboarding action landed.
       move — 200ms, -15 dBFS: just moving through the learning modes.
     Silent until the learner's first click, because browsers block audio
     before a gesture and an unprompted noise on load is startling. */
  var CUES = {
    tick: "/static/onboarding-tick.m4a",
    move: "/static/onboarding-move.m4a",
  };
  var cueEls = {};
  var cueAt = 0;
  var gestured = false;

  function cue(name) {
    if (!gestured) return;
    // One cue per beat: a single action can trip several observers at once.
    var now = Date.now();
    if (now - cueAt < 150) return;
    cueAt = now;
    var src = CUES[name] || CUES.tick;
    try {
      if (!cueEls[name]) {
        cueEls[name] = new Audio(src);
        cueEls[name].preload = "auto";
      }
      cueEls[name].currentTime = 0;
      var p = cueEls[name].play();
      if (p && p.catch) p.catch(function () {});
    } catch (e) {
      /* a missing or blocked cue must never break the tour */
    }
  }

  // Any click inside the tour counts as the unlocking gesture.
  document.addEventListener(
    "click",
    function () {
      gestured = true;
    },
    true
  );

  function postState(status) {
    var fd = new FormData();
    fd.append("status", status);
    fetch("/onboarding/state", {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: fd,
    }).catch(function () {});
  }

  /* ── page-derived goal updates ─────────────────────────────────── */
  var onBrowseIndex = path === "/browse" || path === "/browse/";
  var onTourUnit = path === TOUR_UNIT;
  var onTourArticle = path === TOUR_ARTICLE;
  var onCalendar = path.indexOf("/calendar") === 0 && path.indexOf("/calendar/google") !== 0;
  var onSettings = path.indexOf("/settings") === 0;

  // Following the guided path counts as having started the tutorial.
  if (onBrowseIndex || onTourArticle || onTourUnit) state.started = true;
  if (onTourUnit) state.unit = true;
  // ?done=<unit_id> only ever appears on the redirect after a real Done —
  // only the tutorial unit advances the tour.
  if (params.get("done") === TOUR_UNIT_ID) state.done = true;
  if (onCalendar && state.done) state.cal = true;
  save();

  /* ── tiny DOM helper ───────────────────────────────────────────── */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function checkSvg(size) {
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", size);
    svg.setAttribute("height", size);
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    var p = document.createElementNS(svgNS, "path");
    p.setAttribute("d", "M3 8.5l3.2 3.2L13 5");
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", "currentColor");
    p.setAttribute("stroke-width", "2.2");
    p.setAttribute("stroke-linecap", "square");
    p.setAttribute("stroke-dasharray", "14");
    svg.appendChild(p);
    return svg;
  }

  /* ── the guide card ────────────────────────────────────────────── */
  var guide = el("div", "ob-guide");
  guide.setAttribute("role", "dialog");
  var card = el("div", "ob-card");
  var connector = el("div", "ob-connector");
  connector.setAttribute("aria-hidden", "true");
  connector.appendChild(el("span", "ob-connector-line"));
  connector.appendChild(el("span", "ob-connector-dot"));
  connector.hidden = true;
  var progress = el("div", "ob-progress");
  var progressFill = el("div", "ob-progress-fill");
  progress.appendChild(progressFill);
  var content = el("div", "ob-content");
  card.appendChild(progress);
  card.appendChild(content);
  guide.appendChild(connector);
  guide.appendChild(card);

  var currentTarget = null;
  var quieted = [];
  var placeSide = false;

  function clearTarget() {
    if (currentTarget) currentTarget.classList.remove("ob-target");
    currentTarget = null;
    quieted.forEach(function (n) {
      n.classList.remove("ob-quiet");
    });
    quieted = [];
  }

  var booted = false;

  function setTarget(node, opts) {
    opts = opts || {};
    if (currentTarget === node) return;
    clearTarget();
    currentTarget = node || null;
    placeSide = !!opts.side;
    if (currentTarget) {
      currentTarget.classList.add("ob-target");
      if (opts.quietSiblings && currentTarget.parentElement) {
        var siblings = currentTarget.parentElement.children;
        for (var i = 0; i < siblings.length; i++) {
          var sib = siblings[i];
          if (sib !== currentTarget && !sib.contains(currentTarget)) {
            sib.classList.add("ob-quiet");
            quieted.push(sib);
          }
        }
      }
      // Move, settle, explain: when the highlight jumps to something outside
      // the comfortable band mid-page (e.g. Done unlocking below the fold),
      // bring it to the reader instead of leaving the card at the edge.
      // Boot has its own lead after first paint.
      if (booted) {
        var r = currentTarget.getBoundingClientRect();
        if (r.top < 0 || r.bottom > window.innerHeight * 0.9) {
          window.setTimeout(leadTo, 80);
        }
      }
    }
  }

  // "Lead them there": settle the target near 42% of the viewport.
  function leadTo() {
    if (!currentTarget) return;
    var box = currentTarget.getBoundingClientRect();
    var top = box.top + window.scrollY - window.innerHeight * 0.42;
    // Hidden tabs freeze smooth scrolling (it runs on rAF) — jump instead.
    if (reduced() || document.hidden) {
      window.scrollTo(0, Math.max(0, top));
    } else {
      window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }
  }

  /* ── content model ─────────────────────────────────────────────── */
  function goalsDone() {
    return [!!state.unit, !!state.done, !!state.cal, !!state.sync];
  }
  function doneCount() {
    return goalsDone().filter(Boolean).length;
  }
  function stepLabel() {
    return "Step " + Math.min(doneCount() + 1, 4) + " of 4";
  }

  // Sound the cue as the action fires, before any navigation it triggers.
  function withCue(fn) {
    return function (ev) {
      gestured = true;
      cue("tick");
      fn(ev);
    };
  }

  function renderContent(g) {
    content.textContent = "";
    var head = el("div", "ob-head");
    var eyebrow = el("p", "ob-eyebrow" + (g.check ? " is-check" : ""));
    if (g.check) eyebrow.appendChild(checkSvg(12));
    eyebrow.appendChild(document.createTextNode(g.eyebrow || ""));
    var meta = el("span", "ob-head-meta");
    meta.appendChild(el("span", "ob-step", g.step || stepLabel()));
    var close = el("button", "ob-close", "✕");
    close.type = "button";
    close.setAttribute("aria-label", "Skip tour");
    close.addEventListener("click", skipTour);
    meta.appendChild(close);
    head.appendChild(eyebrow);
    head.appendChild(meta);
    content.appendChild(head);
    content.appendChild(el("h3", "ob-title", g.title || ""));
    content.appendChild(el("p", "ob-body", g.body || ""));
    if (g.note) content.appendChild(el("p", "ob-note", g.note));
    if (g.ladder) content.appendChild(buildLadder());
    if (g.back || g.primary || g.secondary) {
      var actions = el("div", "ob-actions");
      if (g.back) {
        var back = el("button", "ob-btn-back", "Back");
        back.type = "button";
        back.addEventListener("click", withCue(g.back));
        actions.appendChild(back);
      }
      if (g.primary) {
        var primary = el("button", "ob-btn-primary", g.primaryLabel);
        primary.type = "button";
        primary.addEventListener("click", withCue(g.primary));
        actions.appendChild(primary);
      }
      if (g.secondary) {
        var secondary = el("button", "ob-btn-secondary", g.secondaryLabel);
        secondary.type = "button";
        secondary.addEventListener("click", withCue(g.secondary));
        actions.appendChild(secondary);
      }
      content.appendChild(actions);
    }
    guide.setAttribute("aria-label", g.title || "Getting started");
    progressFill.style.width = doneCount() * 25 + "%";
    guide.classList.toggle("is-wide", !!g.ladder);
  }

  var lastContentKey = "";
  function setContent(g) {
    var key = JSON.stringify([g.eyebrow, g.title, g.body, g.step, g.primaryLabel]);
    if (key === lastContentKey) return;
    var first = !lastContentKey;
    lastContentKey = key;
    if (first || reduced()) {
      renderContent(g);
      return;
    }
    // crossfade: out (x −8px), swap, in (x 8px → 0)
    content.style.opacity = "0";
    content.style.transform = "translateX(-8px)";
    window.setTimeout(function () {
      renderContent(g);
      content.style.transition = "none";
      content.style.transform = "translateX(8px)";
      // timer, not rAF — the swap-in must complete even in a hidden tab
      window.setTimeout(function () {
        content.style.transition = "";
        content.style.opacity = "1";
        content.style.transform = "translateX(0)";
      }, 30);
    }, 150);
  }

  // Revision ladder — Day 1 → 3 → 7 → 15 → 30 → 60 (shipped INTERVAL_LADDER).
  function buildLadder() {
    var wrap = el("div", "ob-ladder");
    wrap.appendChild(el("div", "ob-ladder-rule"));
    var row = el("div", "ob-ladder-row");
    ["Day 1", "3", "7", "15", "30", "60"].forEach(function (label, i) {
      var rung = el("span", "ob-rung" + (i === 0 ? " is-first" : ""));
      rung.style.animationDelay = 160 + i * 100 + "ms";
      rung.appendChild(el("span", "ob-rung-dot"));
      rung.appendChild(el("span", "ob-rung-label", label));
      row.appendChild(rung);
    });
    wrap.appendChild(row);
    wrap.appendChild(
      el(
        "p",
        "ob-ladder-note",
        "Recall schedules every revision for you, through Day 60."
      )
    );
    return wrap;
  }

  /* ── travelling placement (desktop) ────────────────────────────── */
  var pos = null;
  var tweenRaf = null;
  var tweenTo = null;
  var snapMode = false;

  function applyPos(x, y) {
    guide.style.transform = "translate3d(" + x + "px," + y + "px,0)";
  }

  function setPos(x, y, showConnector) {
    if (
      pos &&
      Math.abs(pos.x - x) <= 1.5 &&
      Math.abs(pos.y - y) <= 1.5 &&
      pos.connector === showConnector
    ) {
      return;
    }
    if (
      tweenRaf &&
      tweenTo &&
      Math.abs(tweenTo.x - x) <= 1.5 &&
      Math.abs(tweenTo.y - y) <= 1.5
    ) {
      return;
    }
    connector.hidden = !showConnector;
    tweenTo = { x: x, y: y };
    if (!pos || reduced() || snapMode || document.hidden) {
      if (tweenRaf) cancelAnimationFrame(tweenRaf);
      tweenRaf = null;
      pos = { x: x, y: y, connector: showConnector };
      applyPos(x, y);
      return;
    }
    var from = { x: pos.x, y: pos.y };
    var dur = 320;
    var t0 = performance.now();
    if (tweenRaf) cancelAnimationFrame(tweenRaf);
    var step = function () {
      var k = Math.min(1, (performance.now() - t0) / dur);
      var e = 1 - Math.pow(1 - k, 3);
      pos = {
        x: from.x + (x - from.x) * e,
        y: from.y + (y - from.y) * e,
        connector: showConnector,
      };
      applyPos(pos.x, pos.y);
      tweenRaf = k < 1 ? requestAnimationFrame(step) : null;
    };
    tweenRaf = requestAnimationFrame(step);
  }

  function place() {
    if (!guide.isConnected || guide.classList.contains("is-centered")) {
      return;
    }
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var cardBox = guide.getBoundingClientRect();
    var w = cardBox.width || 352;
    var h = cardBox.height || 240;
    if (!currentTarget || !currentTarget.isConnected) {
      // no target: dock bottom-left, clear of the checklist on the right
      setPos(24, Math.max(16, vh - h - 24), false);
      return;
    }
    var r = currentTarget.getBoundingClientRect();
    if (!r.width && !r.height) return;
    var clamp = function (x, y, conn) {
      return {
        x: Math.max(16, Math.min(x, vw - w - 16)),
        y: Math.max(16, Math.min(y, vh - h - 16)),
        connector: conn,
      };
    };
    var below = clamp(r.left - 26, r.bottom + 12, true);
    var right = clamp(r.right + 24, r.top + r.height / 2 - h / 2, false);
    var left = clamp(r.left - 24 - w, r.top + r.height / 2 - h / 2, false);
    var above = clamp(r.left - 26, r.top - 12 - h, false);
    var dockBR = clamp(vw, vh - h - 64, false);
    var dockBL = clamp(24, vh - h - 64, false);
    var fits = h + 32 <= vh;
    var belowFree = {
      x: Math.max(16, vw - w - 16),
      y: fits ? Math.min(r.bottom + 16, vh - h - 16) : 16,
      connector: false,
    };
    var cands = placeSide
      ? [right, left, dockBR, dockBL, belowFree]
      : [below, right, left, above, dockBR, dockBL, belowFree, clamp(24, 0, false)];
    var boxes = [];
    var listEl = document.querySelector(".ob-list, .ob-pill");
    if (listEl) boxes.push({ box: listEl.getBoundingClientRect(), weight: 0.5 });
    var headEl = document.querySelector("header.site-header");
    if (headEl) boxes.push({ box: headEl.getBoundingClientRect(), weight: 0.6 });
    var panelEl = document.querySelector("[data-account-panel]:not([hidden])");
    if (panelEl) boxes.push({ box: panelEl.getBoundingClientRect(), weight: 1.5 });
    var colEl = document.querySelector("main .panel");
    if (colEl) boxes.push({ box: colEl.getBoundingClientRect(), weight: 0.12 });
    var over = function (c, b) {
      if (!b || !b.width) return 0;
      var ox = Math.max(0, Math.min(c.x + w, b.right) - Math.max(c.x, b.left));
      var oy = Math.max(0, Math.min(c.y + h, b.bottom) - Math.max(c.y, b.top));
      return ox * oy;
    };
    // Stay close to the highlight: a candidate pays for every pixel it sits
    // away from the target, so the far docks only win when nothing adjacent
    // works. Covering the target itself is still the dominant penalty.
    var tcx = r.left + r.width / 2;
    var tcy = r.top + r.height / 2;
    var distPenalty = function (c) {
      var dx = c.x + w / 2 - tcx;
      var dy = c.y + h / 2 - tcy;
      return 12 * Math.sqrt(dx * dx + dy * dy);
    };
    var best = cands[0];
    var bestScore = Infinity;
    for (var i = 0; i < cands.length; i++) {
      var score = 3 * over(cands[i], r) + distPenalty(cands[i]);
      for (var j = 0; j < boxes.length; j++) {
        score += boxes[j].weight * over(cands[i], boxes[j].box);
      }
      if (score < bestScore) {
        bestScore = score;
        best = cands[i];
      }
    }
    setPos(best.x, best.y, best.connector && over(best, r) === 0);
  }

  /* ── Getting-started checklist ─────────────────────────────────── */
  var list = null;
  var pill = null;
  var listOpen = false;
  var goalEls = [];
  var marker = null;

  var listSig = "";
  function buildChecklist() {
    var sig = [doneCount(), listOpen, isMobile(), window.innerWidth >= 1280].join("|");
    if (sig === listSig && (list || pill || isMobile())) return;
    listSig = sig;
    if (list) list.remove();
    if (pill) pill.remove();
    list = null;
    pill = null;
    if (isMobile()) return;
    var wide = window.innerWidth >= 1280;
    if (!wide && !listOpen) {
      pill = el("button", "ob-pill");
      pill.type = "button";
      pill.setAttribute("aria-expanded", "false");
      pill.setAttribute("aria-label", "Getting started — expand");
      pill.appendChild(el("span", "ob-pill-dot"));
      pill.appendChild(document.createTextNode("Getting started"));
      pill.appendChild(el("span", "ob-pill-count", doneCount() + " of 4"));
      pill.addEventListener("click", function () {
        listOpen = true;
        buildChecklist();
      });
      body.appendChild(pill);
      return;
    }
    list = el("aside", "ob-list");
    list.setAttribute("aria-label", "Getting started");
    var head = el("div", "ob-list-head");
    head.appendChild(el("span", "ob-list-eyebrow", "Getting started"));
    var meta = el("span", "ob-list-meta");
    meta.appendChild(el("span", "ob-list-count", doneCount() + " of 4"));
    if (!wide) {
      var collapse = el("button", "ob-list-collapse", "✕");
      collapse.type = "button";
      collapse.setAttribute("aria-label", "Collapse getting started");
      collapse.addEventListener("click", function () {
        listOpen = false;
        buildChecklist();
      });
      meta.appendChild(collapse);
    }
    head.appendChild(meta);
    list.appendChild(head);
    var ul = el("ul", "ob-goals");
    marker = el("span", "ob-goal-marker");
    marker.setAttribute("aria-hidden", "true");
    marker.style.opacity = "0";
    ul.appendChild(marker);
    var flags = goalsDone();
    var active = flags.indexOf(false);
    goalEls = [];
    GOAL_LABELS.forEach(function (label, i) {
      var li = el(
        "li",
        "ob-goal" + (flags[i] ? " is-done" : i === active ? " is-active" : "")
      );
      if (flags[i]) {
        li.appendChild(checkSvg(12));
        li.firstChild.style.color = "var(--browse-due)";
      } else {
        li.appendChild(
          el("span", "ob-goal-mark", i === active ? "●" : "○")
        );
      }
      li.appendChild(el("span", "", label));
      ul.appendChild(li);
      goalEls.push(li);
    });
    list.appendChild(ul);
    var foot = el("div", "ob-list-foot");
    var skip = el("button", "ob-skip-link", "Skip tour");
    skip.type = "button";
    skip.addEventListener("click", skipTour);
    foot.appendChild(skip);
    list.appendChild(foot);
    body.appendChild(list);
    // accent marker slides to the active row
    if (active !== -1 && goalEls[active]) {
      var target = goalEls[active];
      requestAnimationFrame(function () {
        marker.style.top = target.offsetTop + "px";
        marker.style.height = target.offsetHeight + "px";
        marker.style.opacity = "1";
      });
    }
  }

  /* ── teardown / skip / finish ──────────────────────────────────── */
  function removeChecklist() {
    if (list) list.remove();
    if (pill) pill.remove();
    list = null;
    pill = null;
    listSig = "";
  }

  function teardown() {
    clearTarget();
    guide.remove();
    removeChecklist();
    setIntroBackdrop(false);
    var success = document.querySelector(".ob-success");
    if (success) success.remove();
    if (tick) clearInterval(tick);
    try {
      localStorage.removeItem(STORE_KEY);
    } catch (e) {
      /* ignore */
    }
    body.removeAttribute("data-onboarding");
  }

  function skipTour() {
    postState("skipped");
    setFinishedFlag();
    teardown();
  }

  var finished = false;
  function finishTour() {
    if (finished) return;
    finished = true;
    state.sync = true;
    save();
    postState("completed");
    setFinishedFlag();
    cue("tick");
    clearTarget();
    guide.remove();
    removeChecklist();
    setIntroBackdrop(false);
    showSuccess();
  }

  function showSuccess() {
    var wrap = el("div", "ob-success");
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-label", "You're ready");
    var sCard = el("div", "ob-card");
    var sProgress = el("div", "ob-progress");
    var sFill = el("div", "ob-progress-fill");
    sFill.style.width = "100%";
    sProgress.appendChild(sFill);
    sCard.appendChild(sProgress);
    var sContent = el("div", "ob-content");
    var head = el("div", "ob-head ob-stagger-1");
    var eyebrow = el("p", "ob-eyebrow");
    var badge = el("span", "ob-success-badge");
    badge.style.color = "var(--browse-due)";
    badge.appendChild(checkSvg(11));
    eyebrow.appendChild(badge);
    eyebrow.appendChild(document.createTextNode("You're ready"));
    head.appendChild(eyebrow);
    head.appendChild(el("span", "ob-step", "Step 4 of 4"));
    sContent.appendChild(head);
    var title = el("h3", "ob-title ob-stagger-2", "Your first unit is in memory.");
    sContent.appendChild(title);
    sContent.appendChild(
      el(
        "p",
        "ob-body ob-stagger-3",
        "Recall will bring it back when it's time to revise."
      )
    );
    sContent.appendChild(
      el(
        "p",
        "ob-note ob-stagger-5",
        "Keep going — every unit you finish today joins the same schedule."
      )
    );
    var actions = el("div", "ob-actions ob-stagger-4");
    var cta = el("button", "ob-btn-primary", "Continue learning");
    cta.type = "button";
    cta.addEventListener("click", function () {
      teardown();
      window.location.href = "/onboarding/plan";
    });
    actions.appendChild(cta);
    sContent.appendChild(actions);
    sCard.appendChild(sContent);
    wrap.appendChild(sCard);
    body.appendChild(wrap);
  }

  /* ── learn-page model (modes / completion beats) ───────────────── */
  var learn = document.querySelector(".learn");
  var learnTabs = learn
    ? Array.prototype.slice.call(learn.querySelectorAll(".mode-tabs [data-learn-mode]"))
    : [];
  var justDone = null;

  var MODE_GUIDE = {
    read: [
      "READ",
      "Read it once carefully.",
      "Don't try to memorize it yet. First understand the shape of the sentence.",
    ],
    cloze: [
      "CLOZE",
      "Recall the missing word before you reveal it.",
      "Tap each blank one by one. “Reveal all” is there to help, but it doesn't count as completing the exercise.",
    ],
    letters: [
      "LETTERS",
      "Now remove almost all the help.",
      "Use the first letters to say the clause from memory. Reveal the full text only when you want to check yourself.",
    ],
    type: [
      "TYPE",
      "Write it from memory.",
      "It doesn't need to be perfect. Finish your attempt, then choose “Check my attempt”.",
    ],
    recite: [
      "RECITE",
      "Say it aloud from memory.",
      "Recall will compare your attempt with the Bare Act wording.",
    ],
    test: [
      "TEST",
      "One final check.",
      "Answer without looking back at the text.",
    ],
  };
  var DONE_COPY = {
    read: ["Now hide some of it.", "Cloze blanks out the words that carry the meaning.", "cloze"],
    cloze: ["Try the same clause with fewer clues.", "Letters keeps only the first letter of every word.", "letters"],
    letters: ["Now write it out.", "Type checks your wording against the Bare Act.", "type"],
    type: ["Say it out loud.", "Recite compares what you say with the Bare Act wording.", "recite"],
    recite: ["One last check.", "Test asks three short questions on this clause.", "test"],
    test: ["That's every method.", "Mark it Done and Recall schedules the rest.", ""],
  };
  var MODE_LABELS = {
    read: "Read",
    cloze: "Cloze",
    letters: "Letters",
    type: "Type",
    recite: "Recite",
    test: "Test",
  };

  function tabMode(tab) {
    return tab.getAttribute("data-learn-mode");
  }
  function tabSeen(tab) {
    return (tab.textContent || "").indexOf("✓") !== -1;
  }
  function tabLocked(tab) {
    return tab.classList.contains("is-locked");
  }
  function seenModes() {
    var seen = {};
    learnTabs.forEach(function (tab) {
      if (tabSeen(tab)) seen[tabMode(tab)] = true;
    });
    return seen;
  }
  function openModes() {
    return learnTabs.filter(function (tab) {
      return !tabLocked(tab);
    });
  }
  function unseenModes() {
    return openModes().filter(function (tab) {
      return !tabSeen(tab);
    });
  }
  function doneUnlocked() {
    var btn = document.getElementById("learn-done-btn");
    return !!btn && !btn.disabled;
  }
  function goToMode(mode) {
    var tab = learnTabs.filter(function (t) {
      return tabMode(t) === mode;
    })[0];
    if (tab) tab.click();
  }

  function learnGuide() {
    var seen = seenModes();
    var open = openModes();
    var left = unseenModes();
    var seenN = open.length - left.length;
    var g = { step: seenN + " of " + open.length + " methods" };
    if (doneUnlocked()) {
      g.eyebrow = "THE RECALL LOOP";
      g.title = "That's the whole Recall loop.";
      g.body =
        "Mark it Done and we'll take care of when you need to see it again.";
      setTarget(document.querySelector(".learn-actions"));
      return g;
    }
    var mode = learn.getAttribute("data-mode") || "read";
    if (justDone && DONE_COPY[justDone]) {
      var d = DONE_COPY[justDone];
      g.eyebrow = (MODE_LABELS[justDone] || justDone).toUpperCase() + " COMPLETE";
      g.check = true;
      g.title = d[0];
      g.body = d[1];
      // point at what's actually left, never at a locked or finished tab
      var next = d[2] && !seen[d[2]] ? d[2] : left.length ? tabMode(left[0]) : null;
      if (next && seen[next]) next = left.length ? tabMode(left[0]) : null;
      if (!d[2] && left.length) {
        g.title = left.length === 1 ? "One method left." : left.length + " methods left.";
        g.body =
          "Done unlocks once you've been through all " +
          open.length +
          ". " +
          MODE_LABELS[tabMode(left[0])] +
          " is next.";
      }
      if (next) {
        g.primaryLabel = "Continue to " + MODE_LABELS[next] + " →";
        g.primary = function () {
          justDone = null;
          goToMode(next);
        };
      }
    } else if (MODE_GUIDE[mode]) {
      var c = MODE_GUIDE[mode];
      g.eyebrow = c[0];
      g.title = c[1];
      g.body = c[2];
      if (seen[mode] && left.length) {
        var nxt = tabMode(left[0]);
        g.primaryLabel = "Continue to " + MODE_LABELS[nxt] + " →";
        g.primary = function () {
          goToMode(nxt);
        };
      }
    } else {
      g.eyebrow = "KEEP GOING";
      g.title = left.length === 1 ? "One method left." : left.length + " methods left.";
      g.body = "Done unlocks once you've been through every open method.";
      if (left.length) {
        var m = tabMode(left[0]);
        g.primaryLabel = "Continue to " + MODE_LABELS[m] + " →";
        g.primary = function () {
          goToMode(m);
        };
      }
    }
    setTarget(document.querySelector(".mode-tabs"), { side: true });
    return g;
  }

  /* ── stage machine ─────────────────────────────────────────────── */
  function articleTarget() {
    return (
      document.querySelector(
        '.browse-article-grid a[href="/browse/article/1"], .browse-article-grid .browse-article-card[href="/browse/article/1"]'
      ) ||
      document.querySelector('a.browse-card-link[href="/browse/article/1"]') ||
      document.querySelector(".browse-article-grid a")
    );
  }

  var lastGoalCount = null;

  function gcalConnected() {
    return !!(
      document.querySelector(".gcal-connected-head") ||
      document.querySelector(".gcal-notice.is-ok")
    );
  }

  function update() {
    // The JS-enhanced Done flow strips ?done= from the next URL, but it
    // flips the button to its "Saved" state before navigating — catch that.
    if (onTourUnit && !state.done && document.querySelector("#learn-done-btn.is-rtc-saved")) {
      state.done = true;
      save();
    }
    // A checklist goal ticking over is an onboarding action too — it is how
    // Done, the Calendar visit and calendar sync each register.
    if (lastGoalCount !== null && doneCount() > lastGoalCount) cue("tick");
    lastGoalCount = doneCount();

    guide.classList.remove("is-centered");
    var wantIntro = false;
    var g = null;

    if (!state.done) {
      if (onTourUnit) {
        g = learnGuide();
      } else if (onTourArticle) {
        var unitLink = document.querySelector(".checklist .checklist-item");
        setTarget(unitLink, { quietSiblings: false });
        g = {
          eyebrow: "ARTICLE 1",
          title: "Begin with clause (1).",
          body: "Short enough to learn quickly — long enough to show you how Recall works.",
          back: function () {
            window.location.href = "/browse";
          },
        };
      } else if (onBrowseIndex) {
        setTarget(articleTarget(), { quietSiblings: true });
        g = {
          eyebrow: "YOUR FIRST UNIT",
          title: "Start with Article 1.",
          body: "It begins with a short clause, which makes it a good place to learn how Recall works.",
        };
      } else if (!state.started) {
        // First login: a full-screen prompt — start the tutorial, or skip
        // straight to the dashboard. Nothing else shows behind it.
        setTarget(null);
        guide.classList.add("is-centered");
        wantIntro = true;
        g = {
          eyebrow: "YOUR FIRST RECALL",
          title: "Let's memorize one clause.",
          body: "A short tutorial shows you how Recall works using Article 1(1). It only takes a few minutes.",
          primaryLabel: "Start the tutorial",
          primary: function () {
            state.started = true;
            save();
            window.location.href = "/browse";
          },
          secondaryLabel: "Skip for now",
          secondary: declineIntro,
        };
      } else {
        // Wandered off the guided path mid-tutorial — point back to it.
        setTarget(null);
        g = {
          eyebrow: "YOUR FIRST RECALL",
          title: "Pick up where you left off.",
          body: "Article 1(1) is your tutorial unit — finish all its methods to mark it Done.",
          primaryLabel: state.unit ? "Back to Article 1(1)" : "Go to Article 1",
          primary: function () {
            window.location.href = state.unit ? TOUR_UNIT : TOUR_ARTICLE;
          },
          secondaryLabel: "Skip for now",
          secondary: skipTour,
        };
      }
    } else if (!state.cal) {
      var panel = document.querySelector("[data-account-panel]");
      var menuOpen = panel && !panel.hidden;
      if (menuOpen) {
        setTarget(panel.querySelector('a[href="/calendar"]'));
        g = {
          eyebrow: "ACCOUNT MENU",
          title: "Open Calendar.",
          body: "Your revision days live here. Recall already knows when your unit comes back.",
        };
      } else {
        setTarget(document.querySelector(".account-menu-btn"));
        g = {
          eyebrow: "SCHEDULED",
          check: true,
          title: "Now see when it comes back.",
          body: "Your first unit is saved. Open your account menu — top right — to find your Calendar.",
        };
      }
    } else if (!state.sync) {
      if (onSettings) {
        var connectRow = document.querySelector(".gcal-connect-row");
        // Connected already, or calendar sync not offered on this install —
        // either way there is nothing left to set up.
        if (gcalConnected() || !connectRow) {
          finishTour();
          return;
        }
        setTarget(connectRow);
        g = {
          eyebrow: "OPTIONAL",
          title: "Put your Recall schedule on Google Calendar.",
          body: "Recall already manages your revisions here. Connect Google Calendar if you also want those revision days to appear in your calendar.",
          note: "Recall creates a separate “Recall the C — Revision Schedule” calendar. It doesn't need access to your unrelated personal calendars.",
          secondaryLabel: "Maybe later",
          secondary: finishTour,
        };
      } else if (onCalendar) {
        setTarget(document.querySelector(".calendar-cell.is-today"));
        g = {
          eyebrow: "REVISION SCHEDULED",
          title: "You don't need to remember when to revise.",
          body: "Your unit is now in your Recall schedule. Every time you complete a revision, Recall moves it to the next interval.",
          ladder: true,
          primaryLabel: "Got it — show me calendar sync",
          primary: function () {
            window.location.href = "/settings";
          },
          secondaryLabel: "Skip calendar setup",
          secondary: finishTour,
        };
      } else {
        setTarget(null);
        g = {
          eyebrow: "OPTIONAL",
          title: "Put your Recall schedule on Google Calendar.",
          body: "One last step — connect Google Calendar in Settings if you want revision days on your own calendar.",
          primaryLabel: "Open Settings",
          primary: function () {
            window.location.href = "/settings";
          },
          secondaryLabel: "Maybe later",
          secondary: finishTour,
        };
      }
    } else {
      finishTour();
      return;
    }

    setContent(g);
    setIntroBackdrop(wantIntro);
    if (wantIntro) {
      removeChecklist();
    } else {
      buildChecklist();
    }
    place();
  }

  // Full-screen blank backdrop behind the first-login prompt.
  var introBackdrop = null;
  function setIntroBackdrop(on) {
    if (on && !introBackdrop) {
      introBackdrop = el("div", "ob-intro-backdrop");
      introBackdrop.setAttribute("aria-hidden", "true");
      body.insertBefore(introBackdrop, guide);
    } else if (!on && introBackdrop) {
      introBackdrop.remove();
      introBackdrop = null;
    }
  }

  // Declining the first-login prompt skips the tour and lands on the dashboard.
  function declineIntro() {
    postState("skipped");
    setFinishedFlag();
    teardown();
    if (path.indexOf("/dashboard") !== 0) {
      window.location.href = "/dashboard";
    }
  }

  /* ── boot + observers ──────────────────────────────────────────── */
  // setTimeout, not rAF: rAF freezes in hidden tabs, and completion beats
  // must not be lost when the page is backgrounded mid-attempt.
  var updateTimer = null;
  function scheduleUpdate() {
    if (updateTimer) return;
    updateTimer = window.setTimeout(function () {
      updateTimer = null;
      update();
    }, 40);
  }

  var tick = null;

  function boot() {
    body.appendChild(guide);
    update();
    booted = true;
    if (currentTarget) {
      window.setTimeout(leadTo, 60);
    }

    // learn page: watch mode switches and ✓ marks for completion beats
    if (learn) {
    var lastSeen = seenModes();
    var lastMode = learn.getAttribute("data-mode") || "read";
    var mo = new MutationObserver(function () {
      // Capture the Done "Saved" state synchronously — the tour-mode Done
      // flow navigates away quickly, before the coalesced update timer fires.
      if (!state.done && document.querySelector("#learn-done-btn.is-rtc-saved")) {
        state.done = true;
        save();
      }
      var nowSeen = seenModes();
      var newlyDone = null;
      Object.keys(nowSeen).forEach(function (m) {
        if (!lastSeen[m]) newlyDone = m;
      });
      var nowMode = learn.getAttribute("data-mode") || "read";
      if (newlyDone && newlyDone !== "read") {
        justDone = newlyDone;
        cue("tick");
      } else if (nowMode !== lastMode) {
        // Moving between modes is travel, not an achievement — softer voice.
        justDone = null;
        cue("move");
      }
      lastSeen = nowSeen;
      lastMode = nowMode;
      scheduleUpdate();
    });
    // No attributeFilter: the Done button unlocks via a disabled-attribute
    // change deep in the subtree, and mode switches via data-mode on .learn.
    mo.observe(learn, {
      attributes: true,
      subtree: true,
      childList: true,
      characterData: true,
    });
  }

  // account menu open/close (menu stage)
  var accountPanel = document.querySelector("[data-account-panel]");
  if (accountPanel) {
    new MutationObserver(scheduleUpdate).observe(accountPanel, {
      attributes: true,
      attributeFilter: ["hidden"],
    });
  }

  // while scrolling the card tracks immediately; then eases home
  var scrollT = null;
  window.addEventListener(
    "scroll",
    function () {
      snapMode = true;
      if (scrollT) clearTimeout(scrollT);
      scrollT = window.setTimeout(function () {
        snapMode = false;
        place();
      }, 130);
      place();
    },
    { passive: true }
  );
  window.addEventListener("resize", function () {
    buildChecklist();
    place();
  });
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      place();
    }).observe(card);
  }
  // self-healing anchor: cheap rect read, writes only when the target moved.
  // Also a fallback for state observers: re-derive the guide when the Done
  // button unlocks or ✓ marks change without a caught mutation.
  var lastTickSig = "";
  tick = window.setInterval(function () {
    place();
    if (learn) {
      var sig = doneUnlocked() + "|" + Object.keys(seenModes()).sort().join(",");
      if (sig !== lastTickSig) {
        lastTickSig = sig;
        scheduleUpdate();
      }
    }
  }, 500);
  }

  // A bfcache restore can bring back a page whose tour layer was live when
  // the user finished — tear it down instead of resuming.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted && hasFinishedFlag()) teardown();
  });

  if (hasFinishedFlag()) {
    // The tour already ended in this browser, but this page's HTML says
    // "active" — usually the back button serving a stale cached page. Ask
    // the server; only a genuine replay (status active again) may boot.
    fetch("/onboarding/state", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (p) {
        if (p && p.status === "active") {
          clearFinishedFlag();
          boot();
        } else {
          body.removeAttribute("data-onboarding");
        }
      })
      .catch(function () {
        body.removeAttribute("data-onboarding");
      });
  } else {
    boot();
  }
})();
