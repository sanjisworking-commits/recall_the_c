/* Phone behaviours for "Recall the C - Mobile Screens".

   Three things live here, none of which exist on desktop:
     • bottom sheets (designs 15, 21)
     • the Learn mode deck ⇄ open-mode switch (designs 05–13)
     • mark filtering from the sheet, over Part cards and Article rows

   Mode switching itself still belongs to app.js: the deck cards carry
   `data-learn-mode`, so its delegated handler swaps the panel and rewrites
   history exactly as the desktop tabs do. This file only moves the phone
   between the deck and the open mode. */
(function () {
  "use strict";

  var PHONE = "(max-width: 560px)";

  function isPhone() {
    return window.matchMedia && window.matchMedia(PHONE).matches;
  }

  /* ── Bottom sheets ─────────────────────────────────────────────────────── */

  var lastSheetOpener = null;

  function openSheet(sheet, opener) {
    if (!sheet) return;
    lastSheetOpener = opener || null;
    sheet.hidden = false;
    document.body.classList.add("mobile-sheet-open");
    var focusable = sheet.querySelector("button, a[href]");
    if (focusable) focusable.focus();
  }

  function closeSheet(sheet) {
    if (!sheet) return;
    sheet.hidden = true;
    document.body.classList.remove("mobile-sheet-open");
    if (lastSheetOpener && document.contains(lastSheetOpener)) {
      lastSheetOpener.focus();
    }
    lastSheetOpener = null;
  }

  function initSheets() {
    document.addEventListener("click", function (event) {
      var opener = event.target.closest("[data-sheet-open]");
      if (opener) {
        event.preventDefault();
        openSheet(document.getElementById(opener.getAttribute("data-sheet-open")), opener);
        return;
      }
      var closer = event.target.closest("[data-sheet-close]");
      if (closer) {
        // Anchor rows still navigate to their in-page target; the sheet just
        // gets out of the way first.
        closeSheet(closer.closest("[data-sheet]"));
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      Array.prototype.forEach.call(
        document.querySelectorAll("[data-sheet]:not([hidden])"),
        closeSheet
      );
    });
  }

  /* ── Mark filtering (design 15) ────────────────────────────────────────── */

  function initMarkFilter() {
    var triggers = Array.prototype.slice.call(
      document.querySelectorAll("[data-marks-filter]")
    );
    if (!triggers.length) return;
    var targets = Array.prototype.slice.call(
      document.querySelectorAll(".part-card[data-browse-marks], .part-row[data-browse-marks]")
    );
    var active = null;

    function apply(next) {
      active = next === active || !next ? null : next;
      triggers.forEach(function (trigger) {
        var key = trigger.getAttribute("data-marks-filter");
        if (!key) return;
        trigger.setAttribute("aria-pressed", key === active ? "true" : "false");
      });
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-sheet-open="marks-sheet"]'),
        function (chip) {
          chip.setAttribute("aria-pressed", active ? "true" : "false");
        }
      );
      targets.forEach(function (el) {
        var marks = (el.getAttribute("data-browse-marks") || "").split(/\s+/);
        el.classList.toggle("is-mark-hidden", Boolean(active) && marks.indexOf(active) === -1);
      });
      // Chapter headers with nothing left under them read as dead weight.
      Array.prototype.forEach.call(
        document.querySelectorAll(".part-chapter"),
        function (chapter) {
          var visible = chapter.querySelectorAll(".part-row:not(.is-mark-hidden)");
          chapter.classList.toggle("is-mark-hidden", Boolean(active) && !visible.length);
        }
      );
    }

    triggers.forEach(function (trigger) {
      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        apply(trigger.getAttribute("data-marks-filter"));
        closeSheet(trigger.closest("[data-sheet]"));
      });
    });
  }

  /* ── Learn: deck ⇄ mode (designs 05–13) ────────────────────────────────── */

  function initLearnDeck() {
    var learn = document.querySelector(".learn[data-mobile-view]");
    if (!learn) return;

    var unitId = learn.getAttribute("data-unit-id") || "";
    var nameEl = learn.querySelector("[data-mode-name]");
    var toast = learn.querySelector("[data-deck-toast]");
    var tracker = document.getElementById("methods-tracker");
    var cards = Array.prototype.slice.call(learn.querySelectorAll(".learn-deck-card"));
    var dots = Array.prototype.slice.call(learn.querySelectorAll(".learn-deck-dot"));
    var MODE_LABELS = {
      read: "Read",
      cloze: "Cloze",
      letters: "Letters",
      type: "Type",
      recite: "Recite",
      test: "Test",
    };

    function syncBodyClass() {
      document.body.classList.toggle(
        "is-mode-view",
        learn.getAttribute("data-mobile-view") === "mode"
      );
    }

    function currentMode() {
      return learn.dataset.mode || "read";
    }

    function showMode(mode) {
      learn.setAttribute("data-mobile-view", "mode");
      syncBodyClass();
      if (nameEl) nameEl.textContent = MODE_LABELS[mode] || mode;
      dots.forEach(function (dot, index) {
        dot.classList.toggle("is-current", cards[index] === undefined
          ? false
          : cards[index].getAttribute("data-learn-mode") === mode);
      });
      placeControls(mode);
      syncNextButton(mode);
      window.scrollTo(0, 0);
    }

    function showDeck() {
      stowControls();
      learn.setAttribute("data-mobile-view", "deck");
      syncBodyClass();
      if (unitId) {
        var url = new URL(window.location.href);
        url.pathname = "/learn/" + encodeURIComponent(unitId);
        url.searchParams.delete("mode");
        var sessionId = learn.getAttribute("data-session-id");
        if (sessionId && !url.searchParams.get("session")) {
          url.searchParams.set("session", sessionId);
        }
        history.replaceState({}, "", url.pathname + url.search + url.hash);
      }
      window.scrollTo(0, 0);
    }

    // The tracker's count is app.js's own record of visited modes; watching it
    // is how the deck learns a mode finished without duplicating that logic.
    var lastCount = tracker ? Number(tracker.getAttribute("data-count") || 0) : 0;
    var justFinished = null;

    function refreshDeckState() {
      cards.forEach(function (card, index) {
        var mode = card.getAttribute("data-learn-mode");
        var tab = learn.querySelector('.mode-tab[data-learn-mode="' + mode + '"]');
        var done = Boolean(tab) && tab.textContent.indexOf("✓") !== -1;
        card.classList.toggle("is-done", done);
        var state = card.querySelector(".learn-deck-card-state");
        if (state && done) state.textContent = "Done";
        if (dots[index]) dots[index].classList.toggle("is-done", done);
      });
    }

    if (tracker && window.MutationObserver) {
      new MutationObserver(function () {
        var count = Number(tracker.getAttribute("data-count") || 0);
        if (count > lastCount) {
          justFinished = MODE_LABELS[currentMode()] || currentMode();
        }
        lastCount = count;
        refreshDeckState();
        syncNextButton(currentMode());
      }).observe(tracker, { attributes: true, attributeFilter: ["data-count"] });
    }

    /* ── The Next / Done action bar ──────────────────────────────────────
       The phone's black CTA walks the deck rather than acting on the mode:
       Next on modes 1..n-1, then Done on the last, which hands off to the
       existing Done button so the completion quote and its POST are unchanged.

       Each mode's own control row moves in beside it, so nothing is lost —
       "Reveal all", "Check my attempt" and the rest keep their handlers
       because the elements are moved, never rebuilt. */

    var MODE_CONTROLS = {
      cloze: ".learn-cloze-controls",
      letters: ".learn-letters-controls",
      type: ".learn-type-check",
      recite: ".learn-recite-controls",
      test: ".learn-test-submit",
    };
    var nav = learn.querySelector("[data-mode-nav]");
    var nextBtn = learn.querySelector("[data-mode-next]");
    var doneBtn = document.getElementById("learn-done-btn");
    var order = cards.map(function (card) {
      return card.getAttribute("data-learn-mode");
    });
    var controlHomes = {};

    function stowControls() {
      Object.keys(controlHomes).forEach(function (mode) {
        var home = controlHomes[mode];
        if (home.el.parentNode === nav) {
          home.parent.insertBefore(home.el, home.next);
        }
      });
    }

    function placeControls(mode) {
      stowControls();
      // Desktop keeps every control where the markup put it — the action bar
      // is a phone affordance and moving nodes for it would strand them.
      if (!isPhone()) return;
      var selector = MODE_CONTROLS[mode];
      if (!selector || !nav) return;
      var panel = learn.querySelector('[data-learn-panel="' + mode + '"]');
      var el = panel && panel.querySelector(selector);
      if (!el) return;
      if (!controlHomes[mode]) {
        controlHomes[mode] = {
          el: el,
          parent: el.parentNode,
          next: el.nextSibling,
        };
      }
      nav.insertBefore(el, nextBtn);
    }

    function isLastMode(mode) {
      return order.length > 0 && order[order.length - 1] === mode;
    }

    function syncNextButton(mode) {
      if (!nextBtn) return;
      if (isLastMode(mode)) {
        nextBtn.classList.add("is-done");
        // Mirror the real Done button, gate and label included.
        var locked = !doneBtn || doneBtn.disabled;
        nextBtn.textContent = doneBtn ? doneBtn.textContent.trim() : "Done";
        nextBtn.disabled = locked;
        nextBtn.setAttribute("aria-disabled", locked ? "true" : "false");
      } else {
        nextBtn.classList.remove("is-done");
        nextBtn.textContent = "Next →";
        nextBtn.disabled = false;
        nextBtn.setAttribute("aria-disabled", "false");
      }
    }

    function advanceFrom(mode) {
      var index = order.indexOf(mode);
      var next = index === -1 ? null : order[index + 1];
      if (!next) return;
      // Route through the desktop tab so app.js owns the panel swap, the
      // seen-marking and the history entry exactly as it does elsewhere.
      var tab = learn.querySelector('.mode-tab[data-learn-mode="' + next + '"]');
      if (tab) tab.click();
      showMode(next);
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        var mode = currentMode();
        if (isLastMode(mode)) {
          if (doneBtn && !doneBtn.disabled) doneBtn.click();
          return;
        }
        advanceFrom(mode);
      });
    }

    learn.addEventListener("click", function (event) {
      var back = event.target.closest("[data-deck-back]");
      if (back && isPhone()) {
        event.preventDefault();
        if (toast && justFinished) {
          toast.textContent = justFinished + " done.";
          toast.hidden = false;
          justFinished = null;
        }
        refreshDeckState();
        showDeck();
        return;
      }
      var card = event.target.closest(".learn-deck-card");
      if (card && isPhone()) {
        // app.js opens the panel off the same click; we only change the view.
        if (toast) toast.hidden = true;
        showMode(card.getAttribute("data-learn-mode"));
      }
    });

    // Crossing the breakpoint mid-session must not leave controls in the bar.
    if (window.matchMedia) {
      var phoneQuery = window.matchMedia(PHONE);
      var onBreakpoint = function () {
        if (isPhone()) {
          if (learn.getAttribute("data-mobile-view") === "mode") {
            placeControls(currentMode());
          }
        } else {
          stowControls();
        }
      };
      if (phoneQuery.addEventListener) {
        phoneQuery.addEventListener("change", onBreakpoint);
      } else if (phoneQuery.addListener) {
        phoneQuery.addListener(onBreakpoint);
      }
    }

    syncBodyClass();
    if (learn.getAttribute("data-mobile-view") === "mode") showMode(currentMode());
    refreshDeckState();
  }

  /* ── Bare Act clause columns (designs 04, 08) ──────────────────────────
     The Bare Act is stored as plain text with hard line breaks and inline
     "(1)" / "(a)" markers, rendered with white-space: pre-wrap. The phone
     design sets the marker in a grey column beside the clause, which needs
     real elements — so build them here rather than reshaping the corpus.

     Annotation spans (.bare-fn) are moved, never rebuilt, so the listeners
     app.js already bound to them survive. */

  var CLAUSE_MARKER = /^\s*(\((?:\d{1,3}[A-Za-z]?|[A-Za-z]{1,4})\))\s+/;

  function splitIntoLines(root) {
    var lines = [[]];
    Array.prototype.slice.call(root.childNodes).forEach(function (child) {
      if (child.nodeType !== 3) {
        lines[lines.length - 1].push(child);
        return;
      }
      child.nodeValue.split("\n").forEach(function (part, index) {
        if (index > 0) lines.push([]);
        if (part !== "") {
          lines[lines.length - 1].push(document.createTextNode(part));
        }
      });
    });
    return lines.filter(function (nodes) {
      return nodes.some(function (n) {
        return n.nodeType !== 3 || n.nodeValue.trim() !== "";
      });
    });
  }

  function layoutBareAct(root) {
    if (!root || root.dataset.bareLaid === "1") return;
    var lines = splitIntoLines(root);
    if (!lines.length) return;
    root.textContent = "";
    lines.forEach(function (nodes) {
      var first = nodes[0];
      var match =
        first && first.nodeType === 3 ? first.nodeValue.match(CLAUSE_MARKER) : null;
      var row = document.createElement("span");
      // A hard break inside one clause continues the body column; only a real
      // marker starts a new clause, and only those get the clause gap.
      row.className = match ? "bare-line" : "bare-line is-continuation";

      var mark = document.createElement("span");
      mark.className = "bare-line-mark";
      if (match) {
        mark.textContent = match[1];
        first.nodeValue = first.nodeValue.slice(match[0].length);
      }
      row.appendChild(mark);

      var body = document.createElement("span");
      body.className = "bare-line-body";
      nodes.forEach(function (node) {
        body.appendChild(node);
      });
      row.appendChild(body);
      root.appendChild(row);
    });
    root.dataset.bareLaid = "1";
    root.classList.add("is-bare-laid");
  }

  function initBareAct() {
    if (!isPhone()) return;
    Array.prototype.forEach.call(
      document.querySelectorAll(".browse-article-text, .learn-read-text"),
      layoutBareAct
    );
  }

  /* ── Mode status lines (designs 06, 08–12) ─────────────────────────────
     Every mode screen opens with one grey line saying where you are. In the
     desktop markup those lines sit in each mode's control row — which the
     phone pins to the bottom of the screen as the action bar — so hoist them
     out to the top of the panel. The nodes are moved, not copied, so app.js
     keeps updating the same elements. */

  var MODE_STATUS_LINES = {
    cloze: ["[data-cloze-status]"],
    letters: ["[data-letters-status]", ".learn-letters-hint"],
    recite: ["[data-recite-status]", ".learn-recite-hint"],
  };

  function initModeStatusLines() {
    if (!isPhone()) return;
    Object.keys(MODE_STATUS_LINES).forEach(function (mode) {
      var panel = document.querySelector('[data-learn-panel="' + mode + '"]');
      if (!panel) return;
      MODE_STATUS_LINES[mode]
        .slice()
        .reverse()
        .forEach(function (selector) {
          var el = panel.querySelector(selector);
          if (!el) return;
          el.classList.add("learn-mode-status");
          panel.insertBefore(el, panel.firstChild);
        });
    });
  }

  function boot() {
    initSheets();
    initMarkFilter();
    initBareAct();
    // Must precede initLearnDeck: the deck moves each mode's control row into
    // the action bar, and the status lines have to be lifted out of those rows
    // first or they travel along and get hidden.
    initModeStatusLines();
    initLearnDeck();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
