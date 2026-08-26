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
        // Rebuild from the live query so the revision session survives the
        // round-trip; only `mode` is dropped, because the deck IS no mode.
        var params = new URLSearchParams(window.location.search);
        params.delete("mode");
        var query = params.toString();
        history.replaceState(
          {},
          "",
          "/learn/" + encodeURIComponent(unitId) + (query ? "?" + query : "")
        );
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

    /* ── The action bar ──────────────────────────────────────────────────
       One primary button at a time.

       A mode that needs a deliberate act to complete (Type, Test, Recite)
       shows that act as the primary until it passes; then the same slot
       becomes "Next →". Cloze completes by tapping blanks and Letters by
       speech, so their controls stay secondary and Next leads from the start.

       Next walks only the modes still outstanding — completed ones drop out
       of the rotation — and turns into Done once nothing is left, handing off
       to the real Done button so the POST and the quote are unchanged.

       Controls are moved into the bar, never rebuilt, so every handler
       app.js bound to them survives. */

    var MODE_CONTROLS = {
      cloze: ".learn-cloze-controls",
      // Only the speak button, not the whole row: "Full text" is a view aid
      // that belongs beside the letters it reveals, and in the bar it read as
      // a third CTA next to Speak and Next.
      letters: ".learn-letters-speak",
      type: ".learn-type-check",
      // Record button only: "Hold to peek" is an aid, not a CTA.
      recite: ".learn-recite-toggle",
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

    // Entitlement-aware: locked modes are not required, so they must not keep
    // the deck from ever finishing.
    var requiredModes = (learn.getAttribute("data-required-modes") || "")
      .split(",")
      .map(function (mode) {
        return mode.trim();
      })
      .filter(Boolean);
    var universe = requiredModes.length
      ? order.filter(function (mode) {
          return requiredModes.indexOf(mode) !== -1;
        })
      : order.slice();

    function isModeDone(mode) {
      var tab = learn.querySelector('.mode-tab[data-learn-mode="' + mode + '"]');
      return Boolean(tab) && tab.textContent.indexOf("✓") !== -1;
    }

    function pendingModes(exclude) {
      return universe.filter(function (mode) {
        return mode !== exclude && !isModeDone(mode);
      });
    }

    // Next after the current mode, wrapping to the start; null when the deck
    // has nothing outstanding left.
    function nextTarget(current) {
      var pending = pendingModes(current);
      if (!pending.length) return null;
      var here = order.indexOf(current);
      for (var i = 0; i < pending.length; i += 1) {
        if (order.indexOf(pending[i]) > here) return pending[i];
      }
      return pending[0];
    }

    function syncNextButton(mode) {
      if (!nextBtn) return;
      // Next is constant on the right (design 3b), with two exceptions: a live
      // mic (owned by the record handlers via `is-recording`), and Type, whose
      // own check button morphs into the advance so the bar never shows two
      // CTAs. The design draws no bar for Type — frame 10 shows a single ink
      // CTA — so it is the one mode that carries Next on another button.
      var typeCheck = nav && nav.querySelector("[data-type-check]");
      var typeSolo = mode === "type" && Boolean(typeCheck);
      // Letters is the same shape once its mic is in the bar: the speak button
      // is Speak, then Stop, then the advance — never a CTA beside Next.
      // In the "Just read" view there is no speak button, so Next leads.
      var lettersSpeak = nav && nav.querySelector("[data-letters-speak]");
      var lettersSolo =
        mode === "letters" && Boolean(lettersSpeak) && !lettersSpeak.hidden;
      // Recite and Test are the same one-slot shape: the mode's own act, then
      // the advance. Every mode that owns a CTA now behaves alike, so the bar
      // never shows two.
      var reciteToggle = nav && nav.querySelector("[data-recite-toggle]");
      var reciteSolo =
        mode === "recite" && Boolean(reciteToggle) && !reciteToggle.hidden;
      var quizSubmit = nav && nav.querySelector("[data-quiz-submit]");
      var quizSolo = mode === "test" && Boolean(quizSubmit) && !quizSubmit.hidden;
      if (nav) {
        nav.classList.toggle(
          "is-solo-cta",
          typeSolo || lettersSolo || reciteSolo || quizSolo
        );
      }

      var target = nextTarget(mode);

      // Shared tail for every solo mode: while the mode's act is outstanding
      // the button keeps its own label; once done it becomes Next, or Done
      // when nothing is left outstanding.
      function paintAdvance(btn, armed) {
        if (!armed) return;
        if (target === null) {
          var locked = !doneBtn || doneBtn.disabled;
          btn.textContent = doneBtn ? doneBtn.textContent.trim() : "Done";
          btn.disabled = locked;
        } else {
          btn.textContent = "Next →";
          btn.disabled = false;
        }
      }

      if (lettersSolo) {
        paintAdvance(lettersSpeak, lettersSpeak.dataset.lettersAdvance);
        return;
      }

      if (reciteSolo) {
        paintAdvance(reciteToggle, reciteToggle.dataset.reciteAdvance);
        return;
      }

      if (quizSolo) {
        // Test keeps its score in the label until the very last mode, where
        // the button has to read as Done rather than a score.
        if (quizSubmit.dataset.quizAdvance && target === null) {
          paintAdvance(quizSubmit, true);
        }
        return;
      }

      if (typeSolo) {
        if (typeCheck.dataset.typeAdvance) {
          if (target === null) {
            var doneLocked = !doneBtn || doneBtn.disabled;
            typeCheck.textContent = doneBtn ? doneBtn.textContent.trim() : "Done";
            typeCheck.disabled = doneLocked;
          } else {
            typeCheck.textContent = "Next →";
            typeCheck.disabled = false;
          }
        } else {
          typeCheck.disabled = false;
        }
        return;
      }

      if (target === null) {
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

    function goToMode(mode) {
      // Route through the desktop tab so app.js owns the panel swap, the
      // seen-marking and the history entry exactly as it does elsewhere.
      var tab = learn.querySelector('.mode-tab[data-learn-mode="' + mode + '"]');
      if (tab) tab.click();
      showMode(mode);
    }

    // Test's scored submit advances the deck through this same path (design
    // 3a #6). app.js owns the button's label; the deck owns where it goes.
    // Type's check button re-labels itself through these; the deck decides
    // whether it should read Next or Done.
    learn.addEventListener("learn:type-checked", function () {
      syncNextButton(currentMode());
    });
    learn.addEventListener("learn:type-reset", function () {
      syncNextButton(currentMode());
    });

    // Type's morphed CTA is the only way to Done in that mode — there is no
    // second button beside it, unlike Test (frame 3e).
    learn.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-type-check]");
      if (!btn || !btn.dataset.typeAdvance) return;
      // app.js set the flag while handling this very click; that tap ran the
      // check and must not also advance.
      if (event.rtcTypeChecked) return;
      event.preventDefault();
      event.stopPropagation();
      var target = nextTarget(currentMode());
      if (target === null) {
        if (doneBtn && !doneBtn.disabled) doneBtn.click();
        return;
      }
      goToMode(target);
    });

    learn.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-letters-speak]");
      if (!btn || !btn.dataset.lettersAdvance) return;
      // Swallow the tap before app.js's own speak handler reopens the mic.
      event.preventDefault();
      event.stopPropagation();
      var target = nextTarget(currentMode());
      if (target === null) {
        if (doneBtn && !doneBtn.disabled) doneBtn.click();
        return;
      }
      goToMode(target);
    }, true);

    learn.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-recite-toggle]");
      if (!btn || !btn.dataset.reciteAdvance) return;
      // Swallow before app.js's toggle handler restarts the recorder.
      event.preventDefault();
      event.stopPropagation();
      var target = nextTarget(currentMode());
      if (target === null) {
        if (doneBtn && !doneBtn.disabled) doneBtn.click();
        return;
      }
      goToMode(target);
    }, true);

    // On the last outstanding mode Test's submit reads "Done", so its tap has
    // to fire Done rather than fall through to app.js's advance-then-retry.
    learn.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-quiz-submit]");
      if (!btn || !btn.dataset.quizAdvance) return;
      if (nextTarget(currentMode()) !== null) return;
      event.preventDefault();
      event.stopPropagation();
      if (doneBtn && !doneBtn.disabled) doneBtn.click();
    }, true);

    learn.addEventListener("learn:recite-advance", function () {
      syncNextButton(currentMode());
    });

    // maybeComplete fires this once the clause is fully recalled, so the
    // button repaints as the advance without waiting for another sync.
    learn.addEventListener("learn:letters-advance", function () {
      syncNextButton(currentMode());
    });

    // "Just read" hides the speak button, which takes the bar's only CTA away
    // — without re-syncing, is-solo-cta kept Next hidden too and the bar was
    // left empty. Watching the attribute rather than the toggle catches every
    // path that hides it, including the localStorage-restored view on load.
    var lettersSpeakBtn = learn.querySelector("[data-letters-speak]");
    if (lettersSpeakBtn && window.MutationObserver) {
      new MutationObserver(function () {
        if (currentMode() === "letters") syncNextButton("letters");
      }).observe(lettersSpeakBtn, {
        attributes: true,
        attributeFilter: ["hidden"],
      });
    }

    learn.addEventListener("learn:advance", function () {
      var mode = currentMode();
      var target = nextTarget(mode);
      if (target === null) {
        // Nothing outstanding — the session CTA is already the Done state.
        syncNextButton(mode);
        return;
      }
      goToMode(target);
    });

    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        var mode = currentMode();
        var target = nextTarget(mode);
        if (target === null) {
          if (doneBtn && !doneBtn.disabled) doneBtn.click();
          return;
        }
        goToMode(target);
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

    // app.js owns mode switching and can be reached by paths this file does not
    // originate (a desktop tab, history restore). Watch the attribute it sets
    // so the bar re-syncs however the mode changed, rather than only when the
    // deck drove it.
    if (window.MutationObserver) {
      new MutationObserver(function () {
        if (learn.getAttribute("data-mobile-view") !== "mode") return;
        placeControls(currentMode());
        syncNextButton(currentMode());
      }).observe(learn, { attributes: true, attributeFilter: ["data-mode"] });
    }

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

    // showDeck rewrites the URL, so a bfcache restore can hand back a page
    // whose DOM says "deck" on a ?mode= entry (or the reverse). Trust the URL.
    window.addEventListener("pageshow", function (event) {
      if (!event.persisted || !isPhone()) return;
      var wanted = new URLSearchParams(window.location.search).get("mode");
      if (wanted && learn.getAttribute("data-mobile-view") !== "mode") {
        showMode(currentMode());
      } else if (!wanted && learn.getAttribute("data-mobile-view") === "mode") {
        showDeck();
      }
    });

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

  // Live state only — counts, listening, accuracy. The standing instruction
  // lines moved into the "?" dialog, so they are no longer lifted here.
  var MODE_STATUS_LINES = {
    cloze: ["[data-cloze-status]"],
    letters: ["[data-letters-status]"],
    recite: ["[data-recite-status]"],
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

  /* ── Article CTA (design 3a #8) ─────────────────────────────────────────
     Progressive enhancement. The server ships "Learn this Article" so the
     Article page keeps rendering without a per-Article progress read; this
     personalises it after first paint. Signed-out visitors never ask, and a
     failed or slow reply simply leaves the neutral label — no spinner, no
     layout shift. */

  function initArticleCta() {
    if (!isPhone()) return;
    if (!document.body.classList.contains("is-authed")) return;
    var cta = document.querySelector("[data-article-cta]");
    var label = cta && cta.querySelector("[data-article-cta-label]");
    if (!cta || !label) return;
    var number = cta.getAttribute("data-article-cta");
    if (!number) return;

    fetch("/api/articles/" + encodeURIComponent(number) + "/progress", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error("no-progress");
        return response.json();
      })
      .then(function (data) {
        if (!data || data.ok !== true) return;
        if (data.state === "due") {
          cta.classList.add("is-due");
          label.replaceChildren(
            Object.assign(document.createElement("span"), {
              className: "cta-dot",
            }),
            document.createTextNode("Revise — due today")
          );
          return;
        }
        if (data.state === "started") {
          label.textContent =
            "Continue · " + data.modes_done + " of " + data.modes_total + " modes";
        }
        // "not_started" keeps the server-rendered label.
      })
      .catch(function () {
        /* Non-blocking: the neutral label stands. */
      });
  }

  /* ── Calendar: open a day ───────────────────────────────────────────────
     Tapping a cell swaps the list below for that day's units. All the data is
     already on the page (the same calendar.days the grid is built from), so
     this costs no request. Tapping the open day again returns to Today. */

  function initCalendarDays() {
    var grid = document.querySelector(".cal-m-grid");
    if (!grid) return;
    var todayList = document.querySelector("[data-today-list]");
    var emptyList = document.querySelector("[data-day-empty]");
    var emptyLabel = document.querySelector("[data-day-empty-label]");
    var lists = Array.prototype.slice.call(
      document.querySelectorAll("[data-day-list]")
    );
    var open = null;

    function show(iso) {
      lists.forEach(function (list) {
        list.hidden = list.getAttribute("data-day-list") !== iso;
      });
      var matched = lists.some(function (list) {
        return list.getAttribute("data-day-list") === iso;
      });
      if (emptyList) emptyList.hidden = Boolean(iso) && matched;
      if (todayList) todayList.hidden = Boolean(iso);
      Array.prototype.forEach.call(grid.querySelectorAll(".cal-m-cell"), function (cell) {
        cell.classList.toggle("is-selected", Boolean(iso) && cell.getAttribute("data-date") === iso);
      });
    }

    function clear() {
      open = null;
      lists.forEach(function (list) {
        list.hidden = true;
      });
      if (emptyList) emptyList.hidden = true;
      if (todayList) todayList.hidden = false;
      Array.prototype.forEach.call(grid.querySelectorAll(".cal-m-cell"), function (cell) {
        cell.classList.remove("is-selected");
      });
    }

    grid.addEventListener("click", function (event) {
      var cell = event.target.closest(".cal-m-cell");
      if (!cell || cell.classList.contains("is-blank")) return;
      var iso = cell.getAttribute("data-date");
      if (!iso) return;
      if (open === iso) {
        clear();
        return;
      }
      open = iso;
      if (emptyLabel) {
        emptyLabel.textContent = cell.getAttribute("aria-label") || "Nothing scheduled";
      }
      show(iso);
    });
  }

  // iOS Safari does NOT shrink the layout viewport when the keyboard opens —
  // only the visual viewport shrinks. So `position: fixed; bottom: 0` pins the
  // action bar to the bottom of the full-height page, which is now behind the
  // keyboard: in Type mode "Check my attempt" simply vanished while typing.
  //
  // visualViewport gives the real visible box. The obscured strip is the gap
  // between the bottom of the visual viewport and the bottom of the layout
  // viewport; lifting the bar by exactly that much puts it on the keyboard.
  function initKeyboardInset() {
    var learn = document.querySelector(".learn[data-mobile-view]");
    var nav = learn && learn.querySelector("[data-mode-nav]");
    var vv = window.visualViewport;
    if (!nav || !vv) return;

    function sync() {
      if (!isPhone() || learn.getAttribute("data-mobile-view") !== "mode") {
        nav.style.transform = "";
        document.body.classList.remove("is-keyboard-open");
        return;
      }
      // offsetTop matters because iOS scrolls the visual viewport within the
      // layout viewport once the keyboard is up.
      var covered = window.innerHeight - (vv.height + vv.offsetTop);
      // Sub-pixel noise and the URL bar collapsing both produce small values
      // that are not a keyboard; a real keyboard is far taller.
      if (covered < 80) {
        nav.style.transform = "";
        document.body.classList.remove("is-keyboard-open");
        return;
      }
      nav.style.transform = "translateY(" + -Math.round(covered) + "px)";
      // The home indicator is behind the keyboard now, so its safe-area
      // padding is dead space between the bar and the keys.
      document.body.classList.add("is-keyboard-open");
    }

    vv.addEventListener("resize", sync);
    vv.addEventListener("scroll", sync);
    // Mode switches and deck round-trips change whether the bar is shown.
    if (window.MutationObserver) {
      new MutationObserver(sync).observe(learn, {
        attributes: true,
        attributeFilter: ["data-mobile-view", "data-mode"],
      });
    }
    sync();
  }

  // Zoom, on phones only.
  //
  // The viewport meta covers Android and older iOS, but Safari has ignored
  // `user-scalable=no` and `maximum-scale` for pinch since iOS 10 — Apple
  // treats page zoom as an accessibility guarantee. The only lever left on
  // iPhone is WebKit's non-standard gesture events, so pinch is cancelled
  // here and double-tap is handled in CSS with touch-action: manipulation.
  //
  // Deliberately phone-scoped: desktop browsers ignore the viewport meta
  // entirely, and browser/OS zoom (ctrl+scroll, Display Zoom, Reader) is
  // untouched on every platform, so text can still be enlarged.
  function initNoZoom() {
    ["gesturestart", "gesturechange", "gestureend"].forEach(function (name) {
      document.addEventListener(
        name,
        function (event) {
          if (isPhone()) event.preventDefault();
        },
        { passive: false }
      );
    });
  }

  /* ── Mode help (the "?" in the mode bar) ────────────────────────────────
     The per-mode hint line used to sit above every panel — read once, then
     scrolled past on every later visit. Same guidance, on demand instead. */

  function initModeHelp() {
    var learn = document.querySelector(".learn[data-mobile-view]");
    var modal = document.querySelector("[data-mode-help-modal]");
    var copyEl = document.getElementById("mode-help-copy");
    if (!learn || !modal || !copyEl || typeof modal.showModal !== "function") {
      return;
    }
    var copy = {};
    try {
      copy = JSON.parse(copyEl.textContent || "{}");
    } catch (_e) {
      return;
    }
    var titleEl = modal.querySelector("[data-mode-help-title]");
    var bodyEl = modal.querySelector("[data-mode-help-body]");

    document.addEventListener("click", function (event) {
      if (event.target.closest("[data-mode-help-close]")) {
        modal.close();
        return;
      }
      if (!event.target.closest("[data-mode-help]")) return;
      var entry = copy[learn.dataset.mode || "read"];
      if (!entry) return;
      if (titleEl) titleEl.textContent = entry.title;
      if (bodyEl) bodyEl.textContent = entry.body;
      if (!modal.open) modal.showModal();
    });

    // Clicking the backdrop closes it, like the sheets elsewhere.
    modal.addEventListener("click", function (event) {
      if (event.target === modal) modal.close();
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
    initArticleCta();
    initCalendarDays();
    // After initLearnDeck: the bar only exists in its final form once the
    // deck has moved the active mode's controls into it.
    initKeyboardInset();
    initNoZoom();
    initModeHelp();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
