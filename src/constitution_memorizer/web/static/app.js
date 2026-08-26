/* Light progressive enhancement for the learning UI. */
(function () {
  // Mirrors the canonical partition in progress/repository.py — keep in sync.
  const LEARN_MODES = new Set(["read", "cloze", "letters", "type", "recite", "test"]);
  // Auto-seen modes check on tab visit; the rest gate on a completed attempt.
  const AUTO_SEEN_MODES = new Set(["read"]);
  const MOTION_KEY = "cm-motion";
  const SOUND_KEY = "cm-completion-sound";
  const DONE_SOUND_SRC = "/static/completion-done.mp3";
  const AFFIRMATION_HOLD_MS = 10000;
  let doneAudio = null;

  function prefersReducedMotion() {
    return Boolean(
      window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function motionEnabled() {
    try {
      return !prefersReducedMotion() && localStorage.getItem(MOTION_KEY) !== "off";
    } catch (_e) {
      return !prefersReducedMotion();
    }
  }

  function soundEnabled() {
    try {
      return localStorage.getItem(SOUND_KEY) !== "off";
    } catch (_e) {
      return true;
    }
  }

  function syncRtcAnim() {
    document.documentElement.classList.toggle("rtc-anim", motionEnabled());
  }

  function scrollToElement(el) {
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    if (rect.top >= 0 && rect.bottom <= (window.innerHeight || 0)) {
      return;
    }
    el.scrollIntoView({
      behavior: motionEnabled() ? "smooth" : "auto",
      block: "center",
    });
  }

  function rtcReveal(el, opts) {
    if (!el) {
      return;
    }
    const delay = (opts && opts.delay) || 0;
    if (!motionEnabled()) {
      el.classList.add("rtc-reveal--visible");
      return;
    }
    window.setTimeout(function () {
      el.classList.add("rtc-reveal--visible");
    }, delay);
  }

  function initHeadingReveal() {
    document.querySelectorAll("[data-rtc-reveal]").forEach(function (el) {
      rtcReveal(el, { delay: 0 });
    });
  }
  const DENSITY_THRESH = { light: 8, medium: 6, heavy: 4 };
  const EN_SPACE = "\u2002";

  function letterLen(word) {
    return word.replace(/[^A-Za-z]/g, "").length;
  }

  /** First-letter cue string matching the design prototype. */
  function toInitials(text) {
    const words = text.trim() ? text.trim().split(/\s+/) : [];
    return words
      .map((word) => {
        const match = word.match(/^[A-Za-z]/);
        if (!match) {
          return word;
        }
        const punct = word
          .replace(/[A-Za-z]+/g, "")
          .replace(/[^.,;\u2014()]/g, "");
        return match[0] + punct;
      })
      .join(EN_SPACE);
  }

  function initCloze(panel, onComplete) {
    if (!panel) {
      return null;
    }

    const textEl = panel.querySelector(".learn-cloze-text");
    const statusEl = panel.querySelector("[data-cloze-status]");
    const densityBtns = panel.querySelectorAll("[data-cloze-density]");
    const source = panel.getAttribute("data-cloze-text") || "";
    const words = source.trim() ? source.trim().split(/\s+/) : [];
    let density = panel.getAttribute("data-cloze-density") || "medium";
    if (!DENSITY_THRESH[density]) {
      density = "medium";
    }
    const revealed = new Set();
    // Completion gate: only individually tapped blanks count — "Reveal all"
    // feeds `revealed` but never `tapRevealed`, so it cannot check the mode.
    const tapRevealed = new Set();
    let completed = false;

    function checkTapComplete() {
      if (completed) {
        return;
      }
      const blanks = [];
      words.forEach((word, index) => {
        if (isBlank(word)) {
          blanks.push(index);
        }
      });
      // No zero-blank auto-fire: an impossible cloze is simply not required.
      if (blanks.length === 0) {
        return;
      }
      if (blanks.every((index) => tapRevealed.has(index))) {
        completed = true;
        if (onComplete) {
          onComplete();
        }
      }
    }

    function threshold() {
      return DENSITY_THRESH[density] || 6;
    }

    function isBlank(word) {
      return letterLen(word) >= threshold();
    }

    function updateStatus() {
      let hidden = 0;
      let shown = 0;
      words.forEach((word, index) => {
        if (!isBlank(word)) {
          return;
        }
        hidden += 1;
        if (revealed.has(index)) {
          shown += 1;
        }
      });
      if (statusEl) {
        statusEl.textContent =
          shown + " of " + hidden + " revealed — tap a blank";
      }
    }

    function render() {
      if (!textEl) {
        return;
      }
      textEl.replaceChildren();
      words.forEach((word, index) => {
        const span = document.createElement("span");
        span.className = "learn-cloze-word";
        span.textContent = word + " ";
        if (isBlank(word)) {
          span.classList.add("is-blank");
          span.setAttribute("role", "button");
          span.setAttribute("tabindex", "0");
          span.setAttribute("aria-label", "Reveal hidden word");
          if (revealed.has(index)) {
            span.classList.add("is-revealed");
            span.removeAttribute("tabindex");
            span.removeAttribute("role");
            span.removeAttribute("aria-label");
          } else {
            const reveal = () => {
              revealed.add(index);
              tapRevealed.add(index);
              render();
              checkTapComplete();
            };
            span.addEventListener("click", reveal);
            span.addEventListener("keydown", (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                reveal();
              }
            });
          }
        }
        textEl.appendChild(span);
      });
      updateStatus();
    }

    function setDensity(next) {
      if (!DENSITY_THRESH[next]) {
        return;
      }
      density = next;
      panel.setAttribute("data-cloze-density", next);
      // Changing density restarts the per-density tap attempt.
      revealed.clear();
      tapRevealed.clear();
      densityBtns.forEach((btn) => {
        const active = btn.getAttribute("data-cloze-density") === next;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
      render();
    }

    densityBtns.forEach((btn) => {
      btn.setAttribute(
        "aria-pressed",
        btn.getAttribute("data-cloze-density") === density ? "true" : "false",
      );
      btn.addEventListener("click", () => {
        setDensity(btn.getAttribute("data-cloze-density"));
      });
    });

    // One toggle replaces the old Reveal all / Hide again pair. This is a
    // LABEL merge only: it still writes `revealed`, never `tapRevealed`, so
    // revealing everything grants no completion credit — the mode is checked
    // by recalling each blank individually, and that must not become
    // skippable by pressing one button.
    const toggleAll = panel.querySelector('[data-cloze-action="toggle-all"]');
    if (toggleAll) {
      toggleAll.addEventListener("click", () => {
        const blanks = [];
        words.forEach((word, index) => {
          if (isBlank(word)) {
            blanks.push(index);
          }
        });
        const allShown = blanks.length > 0 && blanks.every((i) => revealed.has(i));
        if (allShown) {
          revealed.clear();
          toggleAll.textContent = "Reveal all";
        } else {
          blanks.forEach((i) => revealed.add(i));
          toggleAll.textContent = "Hide again";
        }
        render();
      });
    }

    setDensity(density);

    return {
      reset() {
        revealed.clear();
        tapRevealed.clear();
        if (toggleAll) {
          toggleAll.textContent = "Reveal all";
        }
        render();
      },
    };
  }

  function initLetters(panel, onComplete) {
    if (!panel) {
      return null;
    }

    const display = panel.querySelector("[data-letters-display]");
    const toggle = panel.querySelector("[data-letters-toggle]");
    const speakBtn = panel.querySelector("[data-letters-speak]");
    const checkBtn = panel.querySelector("[data-letters-check]");
    const statusEl = panel.querySelector("[data-letters-status]");
    const fallbackEl = panel.querySelector("[data-letters-fallback]");
    const manualEl = panel.querySelector("[data-letters-manual]");
    const checkTextBtn = panel.querySelector("[data-letters-check-text]");
    const source = panel.getAttribute("data-letters-text") || "";
    const words = source.trim() ? source.trim().split(/\s+/) : [];
    const learnRoot = panel.closest(".learn");
    const unitId = learnRoot ? learnRoot.getAttribute("data-unit-id") || "" : "";
    const speech = window.RecallSpeech;
    let full = panel.getAttribute("data-letters-full") === "true";
    const correctWordIndexes = new Set();
    const cueState = words.map(() => "neutral");
    let completed = false;
    let recording = null;
    let live = null;
    let inFlight = false;
    let abortController = null;


    function earliestUnresolvedIndex() {
      for (let i = 0; i < words.length; i += 1) {
        if (isStructuralToken(words[i])) {
          continue;
        }
        if (!correctWordIndexes.has(i)) {
          return i;
        }
      }
      return words.length;
    }

    function setHidden(el, hidden) {
      if (!el) {
        return;
      }
      el.hidden = hidden;
    }

    function showStatus(message, kind) {
      if (!statusEl) {
        return;
      }
      statusEl.textContent = message || "";
      statusEl.classList.toggle("is-listening", kind === "listening");
      statusEl.classList.toggle("is-error", kind === "error");
      setHidden(statusEl, !message);
    }

    function showFallback(show) {
      setHidden(fallbackEl, !show);
    }

    function cueClass(index) {
      if (isStructuralToken(words[index])) {
        return "learn-letters-cue is-structural";
      }
      if (cueState[index] === "correct") {
        return "learn-letters-cue is-correct";
      }
      if (cueState[index] === "wrong") {
        return "learn-letters-cue is-wrong";
      }
      if (cueState[index] === "listening") {
        return "learn-letters-cue is-listening";
      }
      return "learn-letters-cue";
    }

    function initialsFor(word) {
      const match = word.match(/^[A-Za-z]/);
      if (!match) {
        return word;
      }
      const punct = word.replace(/[A-Za-z]+/g, "").replace(/[^.,;\u2014()]/g, "");
      return match[0] + punct;
    }

    function renderCues() {
      if (!display) {
        return;
      }
      display.replaceChildren();
      display.classList.toggle("is-full", full);
      display.classList.toggle("is-initials", !full);
      panel.setAttribute("data-letters-full", full ? "true" : "false");
      words.forEach((word, index) => {
        const span = document.createElement("span");
        span.className = cueClass(index);
        span.setAttribute("data-index", String(index));
        span.textContent = (full ? word : initialsFor(word)) + (index < words.length - 1 ? "\u2002" : "");
        display.appendChild(span);
      });
      if (toggle) {
        toggle.textContent = full ? "Back to initials" : "Full text";
        toggle.setAttribute("aria-pressed", full ? "true" : "false");
      }
    }

    function clearListening() {
      for (let i = 0; i < cueState.length; i += 1) {
        if (cueState[i] === "listening") {
          cueState[i] = correctWordIndexes.has(i) ? "correct" : "neutral";
        }
      }
    }

    function markListeningWindow() {
      const start = earliestUnresolvedIndex();
      let marked = 0;
      for (let i = start; i < words.length && marked < 8; i += 1) {
        if (isStructuralToken(words[i])) {
          continue;
        }
        // Never clobber a red (wrong) cue — it stays red until the word
        // is finally spoken correctly and the match flips it blue.
        if (cueState[i] !== "correct" && cueState[i] !== "wrong") {
          cueState[i] = "listening";
        }
        marked += 1;
      }
    }

    function maybeComplete() {
      if (completed || !words.length) {
        return;
      }
      let speakable = 0;
      for (let i = 0; i < words.length; i += 1) {
        if (isStructuralToken(words[i])) {
          continue;
        }
        speakable += 1;
        if (!correctWordIndexes.has(i)) {
          return;
        }
      }
      if (!speakable) {
        return;
      }
      completed = true;
      if (speakBtn) {
        // mobile.js reads this to paint "Next →"/"Done" and to own the tap,
        // so the bar never shows a speak button beside a Next button.
        speakBtn.dataset.lettersAdvance = "1";
        speakBtn.disabled = false;
      }
      if (onComplete) {
        onComplete();
      }
      panel.dispatchEvent(new CustomEvent("learn:letters-advance", { bubbles: true }));
    }

    function applyAlignment(alignment) {
      if (!Array.isArray(alignment)) {
        return;
      }
      alignment.forEach((item) => {
        const index = item && typeof item.index === "number" ? item.index : -1;
        if (index < 0 || index >= words.length) {
          return;
        }
        if (isStructuralToken(words[index])) {
          return;
        }
        if (correctWordIndexes.has(index)) {
          cueState[index] = "correct";
          return;
        }
        if (item.status === "match") {
          correctWordIndexes.add(index);
          cueState[index] = "correct";
        } else if (item.status === "substitute") {
          cueState[index] = "wrong";
        }
      });
      maybeComplete();
    }

    function failInfra(message) {
      clearListening();
      showStatus(message, "error");
      showFallback(true);
      renderCues();
    }

    async function submitBlob(blob) {
      if (!speech || !unitId) {
        failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
        return;
      }
      inFlight = true;
      abortController = new AbortController();
      try {
        const payload = await speech.transcribe({
          unitId,
          mode: "letters",
          blob,
          fromIndex: earliestUnresolvedIndex(),
          signal: abortController.signal,
        });
        clearListening();
        applyAlignment(payload.alignment || []);
        showStatus("Continue from the first letter that is not yet blue.", null);
        showFallback(false);
        renderCues();
      } catch (err) {
        const code = err && err.code ? err.code : "";
        if (code === "unavailable" || code === "timeout" || code === "provider_error") {
          failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
        } else if (code === "empty") {
          failInfra("I didn't catch that — try the word again.");
        } else if (code === "rate_limited") {
          failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
        } else {
          failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
        }
      } finally {
        inFlight = false;
        abortController = null;
      }
    }

    // Speak and check are the same button (design 3c): tap to open the mic,
    // tap again to check. `listening` is what the click handler reads to know
    // which half of the cycle it is in.
    let listening = false;
    let recClock = null;

    function enterListeningUi(label, hint) {
      markListeningWindow();
      showStatus(hint, "listening");
      listening = true;
      if (speakBtn) {
        speakBtn.classList.add("is-active");
        recClock = stopRecClock(recClock);
        recClock = startRecClock(speakBtn, label || "Stop");
      }
      setHidden(checkBtn, false);
      setNavRecording(true);
      renderCues();
    }

    function exitListeningUi(nextLabel) {
      listening = false;
      recClock = stopRecClock(recClock);
      if (speakBtn) {
        speakBtn.classList.remove("is-active");
        // In the phone bar a fully recalled clause turns this button into the
        // advance (mobile.js paints it); relabelling would undo the morph.
        // Off the bar (desktop) it stays a speak control.
        if (!(speakBtn.closest("[data-mode-nav]") && speakBtn.dataset.lettersAdvance)) {
          speakBtn.textContent = nextLabel || "▸ Speak";
        }
      }
      setHidden(checkBtn, true);
      setNavRecording(false);
    }

    async function startLegacySpeak() {
      try {
        recording = await speech.startRecording();
        enterListeningUi(
          "Stop",
          "Listening… speak a short phrase, then stop.",
        );
      } catch (_err) {
        recording = null;
        failInfra("Microphone permission is needed for spoken Letters.");
      }
    }

    async function startSpeak() {
      if (!speech || !speech.isSupported()) {
        failInfra("Microphone permission is needed for spoken Letters.");
        if (speakBtn) {
          speakBtn.disabled = true;
        }
        return;
      }
      // Live word-by-word mode first: letters turn blue as you speak.
      if (typeof speech.startLive === "function" && unitId) {
        try {
          live = await speech.startLive({
            unitId,
            fromIndex: earliestUnresolvedIndex(),
            onUpdate(payload) {
              clearListening();
              applyAlignment(payload.alignment || []);
              markListeningWindow();
              renderCues();
            },
            onEnd(code) {
              live = null;
              clearListening();
              exitListeningUi();
              renderCues();
              if (code && code !== "cancelled") {
                showStatus(
                  "Live listening ended — press Start to continue, or use the fallback.",
                  "error",
                );
                showFallback(true);
              } else {
                showStatus(
                  completed
                    ? "All letters recalled."
                    : "Continue from the first letter that is not yet blue.",
                  null,
                );
              }
            },
          });
          enterListeningUi(
            "Stop",
            "Listening — correct letters turn blue as you speak.",
          );
          return;
        } catch (err) {
          live = null;
          const code = err && err.code ? err.code : "";
          if (code === "mode_locked" || code === "rate_limited") {
            failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
            return;
          }
          // Mic granted but live plumbing failed → quietly fall back to
          // the record-then-check flow (unavailable/socket/unsupported).
        }
      }
      await startLegacySpeak();
    }

    async function checkPhrase() {
      if (live) {
        // Live mode: Stop just ends the stream; alignment already painted.
        const session = live;
        try {
          session.stop();
        } catch (_err) {
          /* ignore */
        }
        return;
      }
      if (!recording || inFlight) {
        return;
      }
      const session = recording;
      recording = null;
      exitListeningUi("▸ Next phrase");
      showStatus("Checking…", "listening");
      let blob;
      try {
        blob = await session.stop();
      } catch (_err) {
        failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
        return;
      }
      if (!blob || !blob.size) {
        failInfra("I didn't catch that — try the word again.");
        return;
      }
      await submitBlob(blob);
    }

    async function submitTyped() {
      const typed = manualEl ? manualEl.value.trim() : "";
      if (!typed) {
        showStatus("Type the next words, then check.", "error");
        return;
      }
      if (!speech) {
        failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
        return;
      }
      inFlight = true;
      try {
        const payload = await speech.transcribe({
          unitId,
          mode: "letters",
          text: typed,
          fromIndex: earliestUnresolvedIndex(),
        });
        applyAlignment(payload.alignment || []);
        if (manualEl) {
          manualEl.value = "";
        }
        showStatus("Continue from the first letter that is not yet blue.", null);
        renderCues();
      } catch (_err) {
        failInfra("Speech recognition is temporarily unavailable. Try again or use the fallback.");
      } finally {
        inFlight = false;
      }
    }

    // Voice vs plain view: "Speak it" is the interactive spoken test;
    // "Just read" restores the original passive first-letter recall (no
    // mic). The choice sticks per browser and plain view still counts the
    // method (server trust model: client reports letters attempts).
    const viewButtons = Array.from(
      panel.querySelectorAll("[data-letters-view-set]"),
    );
    const hintEl = panel.querySelector(".learn-letters-hint");
    const VIEW_KEY = "cm-letters-view";
    let view = "voice";
    try {
      if (localStorage.getItem(VIEW_KEY) === "plain") {
        view = "plain";
      }
    } catch (_e) {
      /* ignore */
    }
    let plainCounted = false;

    function applyView() {
      const plain = view === "plain";
      panel.setAttribute("data-letters-view", view);
      if (plain) {
        if (live) {
          try {
            live.cancel();
          } catch (_e) {
            /* ignore */
          }
          live = null;
        }
        if (recording) {
          try {
            recording.cancel();
          } catch (_e) {
            /* ignore */
          }
          recording = null;
        }
        clearListening();
        exitListeningUi();
        showStatus("", null);
        showFallback(false);
        renderCues();
        if (!plainCounted && onComplete) {
          plainCounted = true;
          onComplete();
        }
      }
      setHidden(speakBtn, plain);
      if (plain) {
        setHidden(checkBtn, true);
      }
      if (hintEl) {
        hintEl.textContent = plain
          ? "Recall each word from its first letter. Show full text to verify."
          : "Use the first letters. Speak the words — correct letters turn blue as you go.";
      }
      viewButtons.forEach((btn) => {
        const active = btn.getAttribute("data-letters-view-set") === view;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    viewButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = btn.getAttribute("data-letters-view-set") === "plain"
          ? "plain"
          : "voice";
        if (next === view) {
          return;
        }
        view = next;
        try {
          localStorage.setItem(VIEW_KEY, view);
        } catch (_e) {
          /* ignore */
        }
        applyView();
      });
    });

    if (toggle) {
      toggle.addEventListener("click", () => {
        full = !full;
        renderCues();
        if (full) {
          scrollToElement(display);
        }
      });
    }
    if (speakBtn) {
      speakBtn.addEventListener("click", () => {
        if (listening || recording || live) {
          checkPhrase();
          return;
        }
        startSpeak();
      });
    }
    if (checkBtn) {
      checkBtn.addEventListener("click", () => {
        checkPhrase();
      });
    }
    if (checkTextBtn) {
      checkTextBtn.addEventListener("click", () => {
        submitTyped();
      });
    }

    renderCues();
    applyView();

    return {
      reset() {
        if (abortController) {
          abortController.abort();
          abortController = null;
        }
        if (recording) {
          try {
            recording.cancel();
          } catch (_err) {
            /* ignore */
          }
          recording = null;
        }
        if (live) {
          try {
            live.cancel();
          } catch (_err) {
            /* ignore */
          }
          live = null;
        }
        inFlight = false;
        full = false;
        for (let i = 0; i < cueState.length; i += 1) {
          cueState[i] = correctWordIndexes.has(i) ? "correct" : "neutral";
        }
        exitListeningUi("▸ Speak");
        if (speakBtn) {
          speakBtn.disabled = false;
        }
        showStatus("", null);
        renderCues();
      },
    };
  }

  /* ── Recording chrome shared by Letters and Recite ──────────────────────
     While a mic is open the phone bar hides Next (design 3c/3d) and the record
     button takes the primary slot. The class is read by mobile.css; on desktop
     there is no bar and this is a no-op. */

  function setNavRecording(on) {
    const nav = document.querySelector("[data-mode-nav]");
    if (nav) {
      nav.classList.toggle("is-recording", Boolean(on));
    }
  }

  function formatClock(ms) {
    const total = Math.max(0, Math.round(ms / 1000));
    return Math.floor(total / 60) + ":" + String(total % 60).padStart(2, "0");
  }

  // Paints "▪ <prefix> · m:ss" into the button once a second. Returns the
  // interval id; pass it to stopRecClock.
  function startRecClock(btn, prefix) {
    if (!btn) {
      return null;
    }
    const began = Date.now();
    const paint = () => {
      const dot = document.createElement("span");
      dot.className = "rec-dot";
      dot.setAttribute("aria-hidden", "true");
      btn.replaceChildren(
        dot,
        document.createTextNode(prefix + " · " + formatClock(Date.now() - began))
      );
    };
    paint();
    return window.setInterval(paint, 1000);
  }

  function stopRecClock(id) {
    if (id) {
      window.clearInterval(id);
    }
    return null;
  }

  /* Clause numbering — "(3)", "(a)", "(iv)", "(2)(a)" — plus punctuation-only
     runs. Not prose: Letters never scores them, and Type does not ask the user
     to type them. Shared so the two modes cannot drift apart on what counts as
     a word. */
  function isStructuralToken(word) {
    const raw = String(word || "").trim();
    if (!raw) {
      return true;
    }
    if (/^[\(\[]?\d+[A-Za-z]?[\)\]]?\.?$/.test(raw)) {
      return true;
    }
    if (/^\(\d+\)\([A-Za-z]\)$/.test(raw)) {
      return true;
    }
    if (/^\([A-Za-z]\)$/.test(raw)) {
      return true;
    }
    if (/^\([ivxlcdmIVXLCDM]+\)$/.test(raw)) {
      return true;
    }
    if (/^[-–—−•·.,;:()/\[\]]+$/.test(raw)) {
      return true;
    }
    return !/[A-Za-z]/.test(raw);
  }

  function normWord(text) {
    return text.toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  function initType(panel, onComplete) {
    if (!panel) {
      return null;
    }

    const input = panel.querySelector("[data-type-input]");
    const mirrorEl = panel.querySelector("[data-type-mirror]");
    const countEl =
      panel.querySelector("[data-type-count]") ||
      panel.querySelector("[data-type-stats]");
    const fixEl = panel.querySelector("[data-type-fix]");
    const statsEl = panel.querySelector("[data-type-stats]");
    const resultEl = panel.querySelector("[data-type-result]");
    const scorePane = panel.querySelector('[data-type-pane="score"]');
    const wordingPane = panel.querySelector('[data-type-pane="wording"]');
    const wordingTab = panel.querySelector('[data-type-tab="wording"]');
    const tabs = Array.prototype.slice.call(
      panel.querySelectorAll("[data-type-tab]")
    );
    const checkBtn = panel.querySelector("[data-type-check]");
    const source = panel.getAttribute("data-type-text") || "";
    const sourceWords = source.trim() ? source.trim().split(/\s+/) : [];
    // Clause numbering is not recall. The target is prose only, so "(3)" and
    // "(a)" never have to be typed — and if the user types them anyway they
    // are skipped rather than scored, so the alignment holds either way.
    const words = sourceWords.filter((word) => !isStructuralToken(word));

    // A word only counts once the user has finished it (typed whitespace after
    // it). The trailing token is still being written, so it is neither scored
    // nor coloured — that is the caret position in the design.
    function settledWords(value) {
      const tokens = value.trim() ? value.trim().split(/\s+/) : [];
      if (!tokens.length) {
        return [];
      }
      const settled = /\s$/.test(value) ? tokens : tokens.slice(0, -1);
      return settled.filter((token) => !isStructuralToken(token));
    }

    // Checking evaluates the whole attempt: by then the last word is finished,
    // even though no trailing space was typed. settledWords is for the live
    // counter, where the trailing token really is still being written.
    function attemptWords(value) {
      const tokens = value.trim() ? value.trim().split(/\s+/) : [];
      return tokens.filter((token) => !isStructuralToken(token));
    }

    let composing = false;

    function matches(typedWord, index) {
      return index < words.length && normWord(typedWord) === normWord(words[index]);
    }

    // Mirrors the raw value, preserving every space and newline, so the two
    // layers wrap identically. Only ever writes the user's own tokens — the
    // source text must never reach this element.
    function renderMirror(value) {
      if (!mirrorEl) {
        return;
      }
      mirrorEl.replaceChildren();
      const parts = value.split(/(\s+)/);
      const settled = /\s$/.test(value);
      let lastWordPart = -1;
      parts.forEach((part, index) => {
        if (part && !/^\s+$/.test(part)) {
          lastWordPart = index;
        }
      });

      let wordIndex = 0;
      parts.forEach((part, index) => {
        if (!part) {
          return;
        }
        if (/^\s+$/.test(part)) {
          mirrorEl.appendChild(document.createTextNode(part));
          return;
        }
        const span = document.createElement("span");
        span.textContent = part;
        if (composing || (index === lastWordPart && !settled)) {
          span.className = "learn-type-mirror-word is-typing";
        } else if (isStructuralToken(part)) {
          // Typed a marker anyway — neither right nor wrong, and it does not
          // consume a target word.
          span.className = "learn-type-mirror-word is-structural";
        } else {
          span.className =
            "learn-type-mirror-word " +
            (matches(part, wordIndex) ? "is-correct" : "is-wrong");
          wordIndex += 1;
        }
        mirrorEl.appendChild(span);
      });
      // A textarea keeps a trailing blank line; pre-wrap on a div drops it.
      mirrorEl.appendChild(document.createTextNode("\u200b"));
    }

    function renderStats(value, checked) {
      const done = settledWords(value);
      let correct = 0;
      done.forEach((word, index) => {
        if (matches(word, index)) {
          correct += 1;
        }
      });
      const wrong = done.length - correct;
      if (countEl) {
        countEl.textContent =
          done.length +
          " of " +
          words.length +
          " words · " +
          correct +
          " correct";
      }
      if (fixEl) {
        fixEl.hidden = wrong === 0;
        fixEl.textContent = wrong === 1 ? "1 to fix" : wrong + " to fix";
      }
    }

    function render(checked) {
      const value = input ? input.value : "";
      renderMirror(value);
      renderStats(value, Boolean(checked));
      // Typing again re-arms the check, which is what keeps re-checking
      // possible without a second button.
      if (!checked && checkBtn && checkBtn.dataset.typeAdvance) {
        hideResult();
        delete checkBtn.dataset.typeAdvance;
        checkBtn.textContent = "Check my attempt";
        panel.dispatchEvent(new CustomEvent("learn:type-reset", { bubbles: true }));
      }
    }

    function selectTab(name) {
      tabs.forEach((tab) => {
        const active = tab.getAttribute("data-type-tab") === name;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (scorePane) scorePane.hidden = name !== "score";
      if (wordingPane) wordingPane.hidden = name !== "wording";
    }

    function hideResult() {
      if (resultEl) resultEl.hidden = true;
      if (statsEl) statsEl.hidden = false;
      selectTab("score");
    }

    // The wording pane is the one place the Bare Act text appears, and only
    // when the attempt was imperfect — a clean run reveals nothing.
    function renderResult() {
      const done = attemptWords(input ? input.value : "");
      let right = 0;
      done.forEach((word, index) => {
        if (matches(word, index)) right += 1;
      });
      const wrong = done.length - right;
      // "Perfect" means every target word was produced correctly — not merely
      // that nothing typed so far was wrong, which would hide the wording from
      // someone who stopped halfway.
      const perfect = right === words.length && wrong === 0;

      if (scorePane) {
        // Built as elements, not a sentence, so the count can carry the same
        // weight the app gives numbers elsewhere (the Today due card, the
        // progress strip) instead of reading as a footnote.
        const line = document.createElement("p");
        line.className = "learn-type-score";
        const num = document.createElement("span");
        num.className = "learn-type-score-num";
        num.textContent = String(right);
        const of = document.createElement("span");
        of.className = "learn-type-score-of";
        of.textContent = "/" + words.length;
        num.appendChild(of);
        const label = document.createElement("span");
        label.className = "learn-type-score-label";
        label.textContent = perfect ? "All correct ✓" : "words correct";
        line.classList.toggle("is-perfect", perfect);
        line.append(num, label);

        scorePane.replaceChildren(line);
        if (!perfect) {
          const fix = document.createElement("p");
          fix.className = "learn-type-score-fix";
          fix.textContent =
            wrong > 0
              ? wrong + (wrong === 1 ? " word to fix" : " words to fix")
              : words.length - right + " still to write";
          scorePane.appendChild(fix);
        }
      }

      if (wordingTab) wordingTab.hidden = perfect;
      if (wordingPane) {
        wordingPane.replaceChildren();
        if (!perfect) {
          words.forEach((word, index) => {
            const span = document.createElement("span");
            span.className =
              index >= done.length
                ? "learn-type-answer is-unreached"
                : matches(done[index], index)
                ? "learn-type-answer"
                : "learn-type-answer is-wrong";
            span.textContent = word + " ";
            wordingPane.appendChild(span);
          });
        }
      }

      if (statsEl) statsEl.hidden = true;
      if (resultEl) resultEl.hidden = false;
      selectTab("score");
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        selectTab(tab.getAttribute("data-type-tab"));
      });
    });

    if (input) {
      input.addEventListener("input", () => render(false));
      // Predictive keyboards rewrite the value in place; hold off scoring
      // until the word is committed or it flickers amber mid-composition.
      input.addEventListener("compositionstart", () => {
        composing = true;
        render(false);
      });
      input.addEventListener("compositionupdate", () => render(false));
      input.addEventListener("compositionend", () => {
        composing = false;
        render(false);
      });
      // Browsers restore textarea values after load; without this the box
      // holds invisible text over an empty mirror.
      window.addEventListener("pageshow", () => render(false));
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => render(false));
      }
    }
    if (checkBtn) {
      checkBtn.addEventListener("click", (event) => {
        // Once checked this button is the advance, and mobile.js owns the tap.
        // Without this guard the direct listener would re-run the check before
        // the delegated one moves on.
        if (checkBtn.dataset.typeAdvance) {
          return;
        }
        // The delegated advance handler sees this same event after us, by
        // which point the flag below is set. Stamp it so the tap that ran the
        // check cannot also advance.
        event.rtcTypeChecked = true;
        // Any completed non-empty attempt counts — no accuracy threshold.
        const typed = input ? input.value.trim() : "";
        if (!typed) {
          if (countEl) {
            countEl.textContent = "Type your attempt first";
          }
          if (fixEl) {
            fixEl.hidden = true;
          }
          if (input) {
            input.focus();
          }
          return;
        }
        render(true);
        renderResult();
        // Type has one CTA: this button now becomes the advance. The counts
        // live in the stats row above (frame 10), so the label does not
        // duplicate them — mobile.js decides whether it reads Next or Done.
        checkBtn.dataset.typeAdvance = "1";
        panel.dispatchEvent(new CustomEvent("learn:type-checked", { bubbles: true }));
        if (onComplete) {
          onComplete();
        }
      });
    }
    render(false);

    return {
      reset() {
        if (input) {
          input.value = "";
        }
        hideResult();
        if (checkBtn) {
          delete checkBtn.dataset.typeAdvance;
          checkBtn.textContent = "Check my attempt";
        }
        render(false);
      },
    };
  }

  function initRecite(panel, onComplete) {
    if (!panel) {
      return null;
    }

    const textEl = panel.querySelector("[data-recite-blur]");
    const toggle = panel.querySelector("[data-recite-toggle]");
    const peekBtn = panel.querySelector("[data-recite-peek]");
    const statusEl = panel.querySelector("[data-recite-status]");
    const transcriptEl = panel.querySelector("[data-recite-transcript]");
    const fallbackEl = panel.querySelector("[data-recite-fallback]");
    const manualEl = panel.querySelector("[data-recite-manual]");
    const checkBtn = panel.querySelector("[data-recite-check]");
    const mapEl = panel.querySelector("[data-recite-map]");
    const statsEl = panel.querySelector("[data-recite-stats]");
    const extrasEl = panel.querySelector("[data-recite-extras]");
    const source = panel.getAttribute("data-recite-text") || "";
    const speech = window.RecallSpeech;
    const learnRoot = panel.closest(".learn");
    const unitId = learnRoot ? learnRoot.getAttribute("data-unit-id") || "" : "";

    let recOn = false;
    let peeking = false;
    // Drives the button's post-recording label ("Recite again") and the live
    // clock while the mic is open.
    let scored = false;
    let recClock = null;
    let recording = null;
    let abortController = null;
    let unsupported = !(speech && speech.isSupported());
    let stopping = false;

    function setHidden(el, hidden) {
      if (!el) {
        return;
      }
      el.hidden = hidden;
    }

    function showFallback(show) {
      setHidden(fallbackEl, !show);
      if (show && manualEl) {
        manualEl.focus();
      }
    }

    function clearResults() {
      scored = false;
      if (transcriptEl) {
        transcriptEl.textContent = "";
        transcriptEl.classList.remove("is-live");
      }
      if (mapEl) {
        mapEl.replaceChildren();
      }
      if (statsEl) {
        statsEl.textContent = "";
      }
      if (extrasEl) {
        extrasEl.textContent = "";
      }
      if (manualEl) {
        manualEl.value = "";
      }
      setHidden(transcriptEl, true);
      setHidden(mapEl, true);
      setHidden(statsEl, true);
      setHidden(extrasEl, true);
      showFallback(false);
    }

    function showStatus(message, kind) {
      if (!statusEl) {
        return;
      }
      statusEl.textContent = message || "";
      statusEl.classList.toggle("is-listening", kind === "listening");
      statusEl.classList.toggle("is-error", kind === "error");
      setHidden(statusEl, !message);
    }

    function renderAccuracyMap(spokenText, labelPrefix) {
      const align = window.RecallAlign;
      if (!align || !mapEl) {
        return;
      }
      // The map is the end of a take: the button becomes "Recite again".
      scored = true;
      const result = align.alignText(source, spokenText || "");
      mapEl.replaceChildren();
      result.sourceWords.forEach((word, index) => {
        const span = document.createElement("span");
        span.className = "learn-recite-map-word";
        span.classList.add(result.hitIndices.has(index) ? "is-hit" : "is-miss");
        span.textContent = word + " ";
        mapEl.appendChild(span);
      });
      setHidden(mapEl, result.sourceWords.length === 0);

      if (statsEl) {
        statsEl.textContent = result.statsLabel;
        setHidden(statsEl, false);
      }
      if (extrasEl) {
        if (result.extras.length) {
          extrasEl.textContent = "Heard (extra): " + result.extras.join(" ");
          setHidden(extrasEl, false);
        } else {
          extrasEl.textContent = "";
          setHidden(extrasEl, true);
        }
      }

      if (transcriptEl) {
        transcriptEl.classList.remove("is-live");
        const heard = (spokenText || "").trim();
        const prefix = labelPrefix || "Heard";
        if (heard) {
          transcriptEl.textContent = prefix + ": " + heard;
          setHidden(transcriptEl, false);
        } else {
          transcriptEl.textContent = "";
          setHidden(transcriptEl, true);
        }
      }
    }

    function stopRecording() {
      if (abortController) {
        abortController.abort();
        abortController = null;
      }
      if (recording) {
        try {
          recording.cancel();
        } catch (_err) {
          /* ignore */
        }
        recording = null;
      }
    }

    function abortForServiceFailure(message) {
      recOn = false;
      stopping = true;
      stopRecording();
      stopping = false;
      render();
      showStatus(message, "error");
      showFallback(true);
    }

    async function finishRecite() {
      stopping = true;
      recOn = false;
      const session = recording;
      recording = null;
      render();
      if (!session) {
        stopping = false;
        abortForServiceFailure(
          "No speech captured. Check your connection, or type what you recited below.",
        );
        return;
      }
      showStatus("Checking…", "listening");
      let blob;
      try {
        blob = await session.stop();
      } catch (_err) {
        stopping = false;
        abortForServiceFailure(
          "Speech recognition is temporarily unavailable. Type what you recited below.",
        );
        return;
      }
      if (!blob || !blob.size || !speech) {
        stopping = false;
        abortForServiceFailure(
          "No speech captured. Check your connection, or type what you recited below.",
        );
        return;
      }
      abortController = new AbortController();
      try {
        const payload = await speech.transcribe({
          unitId,
          mode: "recite",
          blob,
          signal: abortController.signal,
        });
        const spoken = (payload.transcript || "").trim();
        if (!spoken) {
          abortForServiceFailure(
            "No speech captured. Check your connection, or type what you recited below.",
          );
          return;
        }
        showStatus("Accuracy map from your recital.", null);
        showFallback(false);
        renderAccuracyMap(spoken, "Heard");
        markReciteAdvance();
        if (onComplete) {
          onComplete();
        }
      } catch (err) {
        const code = err && err.code ? err.code : "";
        if (code === "mode_locked") {
          abortForServiceFailure("Recite is part of full Recall access.");
        } else {
          abortForServiceFailure(
            "Speech recognition is temporarily unavailable. Type what you recited below.",
          );
        }
      } finally {
        abortController = null;
        stopping = false;
      }
    }

    async function startRecognition() {
      clearResults();
      if (!speech || !speech.isSupported()) {
        unsupported = true;
        recOn = false;
        showStatus(
          "Voice recite needs a browser with microphone access.",
          "error",
        );
        if (toggle) {
          toggle.disabled = true;
        }
        showFallback(true);
        render();
        return;
      }
      try {
        recording = await speech.startRecording();
        showStatus("Listening… speak the Bare Act aloud.", "listening");
      } catch (_err) {
        unsupported = true;
        recOn = false;
        recording = null;
        showStatus(
          "Voice recite needs Chrome or Edge with microphone access.",
          "error",
        );
        if (toggle) {
          toggle.disabled = true;
        }
        showFallback(true);
        render();
      }
    }

    function markReciteAdvance() {
      if (!toggle) {
        return;
      }
      // Read by mobile.js, which paints "Next →"/"Done" and owns the tap so
      // the bar never shows a record button beside a Next button.
      toggle.dataset.reciteAdvance = "1";
      toggle.disabled = false;
      panel.dispatchEvent(new CustomEvent("learn:recite-advance", { bubbles: true }));
    }

    function render() {
      panel.setAttribute("data-recite-on", recOn ? "true" : "false");
      panel.setAttribute("data-peeking", peeking ? "true" : "false");
      if (textEl) {
        textEl.classList.toggle("is-blurred", !peeking);
      }
      if (toggle) {
        toggle.classList.toggle("is-active", recOn);
        // Recording owns the bar: rec square + live clock, and Next yields
        // until the map renders (design 3d).
        if (recOn) {
          if (!recClock) {
            recClock = startRecClock(toggle, "Stop");
          }
        } else {
          recClock = stopRecClock(recClock);
          // In the phone bar this button IS the advance once scored, and
          // mobile.js paints it "Next →" — relabelling would undo the morph.
          // Off the bar (desktop) it stays a record control.
          if (!(toggle.closest("[data-mode-nav]") && toggle.dataset.reciteAdvance)) {
            toggle.textContent = scored ? "Recite again" : "▸ Start reciting";
          }
        }
        setNavRecording(recOn);
        toggle.setAttribute("aria-pressed", recOn ? "true" : "false");
        if (unsupported) {
          toggle.disabled = true;
        }
      }
    }

    function setPeek(next) {
      peeking = next;
      render();
    }

    if (unsupported) {
      showStatus(
        "Voice recite needs a browser with microphone access.",
        "error",
      );
      if (toggle) {
        toggle.disabled = true;
      }
      showFallback(true);
    }

    if (toggle) {
      toggle.addEventListener("click", () => {
        if (unsupported) {
          return;
        }
        if (recOn) {
          finishRecite();
          return;
        }
        recOn = true;
        render();
        startRecognition();
      });
    }

    if (checkBtn) {
      checkBtn.addEventListener("click", () => {
        const spoken = manualEl ? manualEl.value.trim() : "";
        if (!spoken) {
          showStatus("Type what you recited, then check accuracy.", "error");
          return;
        }
        showStatus("Accuracy map from your text.", null);
        renderAccuracyMap(spoken, "Entered");
        markReciteAdvance();
        if (onComplete) {
          onComplete();
        }
      });
    }

    if (peekBtn) {
      const startPeek = (event) => {
        event.preventDefault();
        setPeek(true);
      };
      const endPeek = (event) => {
        event.preventDefault();
        setPeek(false);
      };
      peekBtn.addEventListener("mousedown", startPeek);
      peekBtn.addEventListener("mouseup", endPeek);
      peekBtn.addEventListener("mouseleave", endPeek);
      peekBtn.addEventListener("touchstart", startPeek, { passive: false });
      peekBtn.addEventListener("touchend", endPeek);
      peekBtn.addEventListener("touchcancel", endPeek);
      peekBtn.addEventListener("keydown", (event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          setPeek(true);
        }
      });
      peekBtn.addEventListener("keyup", (event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          setPeek(false);
        }
      });
      peekBtn.addEventListener("blur", () => setPeek(false));
    }

    render();

    return {
      reset() {
        stopping = true;
        recOn = false;
        peeking = false;
        stopRecording();
        stopping = false;
        clearResults();
        if (!unsupported) {
          showStatus("", null);
        } else {
          showStatus(
            "Voice recite needs a browser with microphone access.",
            "error",
          );
          showFallback(true);
        }
        render();
      },
    };
  }


  function initTest(panel, onGraded) {
    if (!panel) {
      return null;
    }
    const form = panel.querySelector("[data-quiz-form]");
    const scoreEl = panel.querySelector("[data-quiz-score]");
    const submitBtn = panel.querySelector("[data-quiz-submit]");
    if (!form) {
      // Unit without a quiz: the fallback message renders server-side and the
      // mode is already absent from the effective required set.
      return { reset() {} };
    }
    const learnRoot = panel.closest(".learn");
    const unitId = learnRoot ? learnRoot.getAttribute("data-unit-id") || "" : "";
    const cycle = parseInt(panel.getAttribute("data-quiz-cycle") || "0", 10) || 0;
    const fieldsets = Array.from(panel.querySelectorAll("[data-quiz-q]"));
    let errorEl = null;
    let submitting = false;

    function showError(message) {
      if (!errorEl) {
        errorEl = document.createElement("p");
        errorEl.className = "learn-test-error";
        form.appendChild(errorEl);
      }
      errorEl.textContent = message;
      errorEl.hidden = !message;
    }

    function collectAnswers() {
      const answers = [];
      let firstMissing = null;
      fieldsets.forEach((fieldset) => {
        if (fieldset.getAttribute("data-kind") === "mcq") {
          const checked = fieldset.querySelector("input[type=radio]:checked");
          if (checked) {
            answers.push(parseInt(checked.value, 10));
          } else {
            answers.push(null);
            firstMissing = firstMissing || fieldset.querySelector("input[type=radio]");
          }
        } else {
          const fill = fieldset.querySelector("[data-quiz-fill]");
          const value = fill ? fill.value.trim() : "";
          if (value) {
            answers.push(value);
          } else {
            answers.push(null);
            firstMissing = firstMissing || fill;
          }
        }
      });
      return { answers: answers, firstMissing: firstMissing };
    }

    function setFormDisabled(disabled) {
      form.querySelectorAll("input").forEach((el) => {
        el.disabled = disabled;
      });
      if (submitBtn) {
        submitBtn.disabled = disabled;
      }
    }

    function paintResults(payload) {
      const results = Array.isArray(payload.results) ? payload.results : [];
      fieldsets.forEach((fieldset, index) => {
        const resultEl = fieldset.querySelector("[data-quiz-result]");
        const result = results[index];
        if (!resultEl || !result) {
          return;
        }
        resultEl.hidden = false;
        resultEl.classList.toggle("is-correct", result.correct === true);
        resultEl.classList.toggle("is-wrong", result.correct !== true);
        resultEl.textContent = result.correct
          ? "✓ Correct"
          : "✗ Correct answer: " + result.expected;
      });
      if (scoreEl && payload.score) {
        scoreEl.hidden = false;
        scoreEl.textContent =
          "You got " + payload.score.correct + " of " + payload.score.total + ".";
      }
      setFormDisabled(true);
      if (submitBtn) {
        // Scored: the submit becomes the advance, so there is no second tap
        // hunting for Next (design 3a #6). It does NOT fire Done — the
        // right-hand session CTA keeps that job and stays visible (3e).
        if (payload.score) {
          submitBtn.textContent =
            payload.score.correct + " of " + payload.score.total + " — Next →";
          submitBtn.dataset.quizAdvance = "1";
          // setFormDisabled just disabled it; the button has a new job now.
          submitBtn.disabled = false;
        } else {
          submitBtn.textContent = "Checked ✓";
        }
      }
    }

    function resetQuiz() {
      form.querySelectorAll("input[type=radio]").forEach((el) => {
        el.checked = false;
      });
      form.querySelectorAll("[data-quiz-fill]").forEach((el) => {
        el.value = "";
      });
      fieldsets.forEach((fieldset) => {
        const resultEl = fieldset.querySelector("[data-quiz-result]");
        if (resultEl) {
          resultEl.hidden = true;
          resultEl.textContent = "";
        }
      });
      if (scoreEl) {
        scoreEl.hidden = true;
        scoreEl.textContent = "";
      }
      showError("");
      setFormDisabled(false);
      if (submitBtn) {
        delete submitBtn.dataset.quizAdvance;
        submitBtn.textContent = "Check answers";
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      // Three-state morph (design 3e): Check answers → "X of Y — Next →"
      // → "Try new set". The middle tap advances the deck but must never
      // fire Done; the right-hand session CTA keeps that job.
      if (submitBtn && submitBtn.dataset.quizAdvance) {
        delete submitBtn.dataset.quizAdvance;
        submitBtn.dataset.quizRetry = "1";
        submitBtn.textContent = "Try new set";
        panel.dispatchEvent(new CustomEvent("learn:advance", { bubbles: true }));
        return;
      }
      if (submitBtn && submitBtn.dataset.quizRetry) {
        delete submitBtn.dataset.quizRetry;
        resetQuiz();
        return;
      }
      if (submitting || !unitId) {
        return;
      }
      const collected = collectAnswers();
      if (collected.answers.some((answer) => answer === null)) {
        showError("Answer all " + fieldsets.length + " to finish.");
        if (collected.firstMissing) {
          collected.firstMissing.focus();
        }
        return;
      }
      showError("");
      submitting = true;
      fetch("/learn/" + encodeURIComponent(unitId) + "/quiz", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ cycle: cycle, answers: collected.answers }),
      })
        .then((response) => {
          const type = response.headers.get("content-type") || "";
          if (!type.includes("application/json")) {
            throw new Error("quiz-failed");
          }
          return response.json().then((payload) => ({
            status: response.status,
            payload: payload,
          }));
        })
        .then((result) => {
          submitting = false;
          const payload = result.payload || {};
          if (result.status === 409 && payload.error === "stale_quiz") {
            showError("This unit moved on — reload the page for fresh questions.");
            return;
          }
          if (result.status !== 200 || payload.ok !== true) {
            showError("Couldn't check answers — try again.");
            return;
          }
          paintResults(payload);
          if (onGraded) {
            onGraded(payload);
          }
        })
        .catch(() => {
          submitting = false;
          showError("Couldn't check answers — try again.");
        });
    });


    return {
      reset: resetQuiz,
    };
  }

  function initBareFns(root) {
    const scope = root || document;
    const LEAVE_MS = 120;
    let pinnedPrimary = null;

    function closeNested(trigger) {
      if (!trigger) {
        return;
      }
      const tipId = trigger.getAttribute("aria-controls");
      const nested = tipId ? document.getElementById(tipId) : null;
      trigger.setAttribute("aria-expanded", "false");
      trigger.classList.remove("is-open");
      if (nested) {
        nested.hidden = true;
        nested.classList.remove("is-open");
      }
    }

    function openNested(trigger) {
      if (!trigger) {
        return;
      }
      const tipId = trigger.getAttribute("aria-controls");
      const nested = tipId ? document.getElementById(tipId) : null;
      trigger.setAttribute("aria-expanded", "true");
      trigger.classList.add("is-open");
      if (nested) {
        nested.hidden = false;
        nested.classList.add("is-open");
      }
    }

    function closePrimary(el, tip) {
      el.querySelectorAll(".bare-fn-nested-trigger").forEach(closeNested);
      tip.hidden = true;
      el.classList.remove("is-open", "is-pinned");
      if (pinnedPrimary === el) {
        pinnedPrimary = null;
      }
    }

    function openPrimary(el, tip, pin) {
      if (pinnedPrimary && pinnedPrimary !== el) {
        const otherTip = pinnedPrimary.querySelector(":scope > .bare-fn-tip");
        if (otherTip) {
          closePrimary(pinnedPrimary, otherTip);
        }
      }
      tip.hidden = false;
      el.classList.add("is-open");
      if (pin) {
        el.classList.add("is-pinned");
        pinnedPrimary = el;
      }
    }

    scope.querySelectorAll(".bare-fn").forEach((el) => {
      const tip = el.querySelector(":scope > .bare-fn-tip");
      if (!tip || el.dataset.bareFnBound === "1") {
        return;
      }
      el.dataset.bareFnBound = "1";
      let leaveTimer = null;

      function clearLeave() {
        if (leaveTimer) {
          window.clearTimeout(leaveTimer);
          leaveTimer = null;
        }
      }

      function scheduleLeave() {
        clearLeave();
        leaveTimer = window.setTimeout(() => {
          if (el.classList.contains("is-pinned")) {
            return;
          }
          if (el.contains(document.activeElement)) {
            return;
          }
          closePrimary(el, tip);
        }, LEAVE_MS);
      }

      el.addEventListener("mouseenter", () => {
        clearLeave();
        openPrimary(el, tip, false);
      });
      el.addEventListener("mouseleave", scheduleLeave);
      el.addEventListener("focusin", () => {
        clearLeave();
        openPrimary(el, tip, false);
      });
      el.addEventListener("focusout", (event) => {
        if (el.contains(event.relatedTarget)) {
          return;
        }
        scheduleLeave();
      });

      // Tap/click on the marked word toggles pin (nested triggers stopPropagation).
      el.addEventListener("click", (event) => {
        if (event.target.closest(".bare-fn-nested-trigger")) {
          return;
        }
        event.preventDefault();
        if (el.classList.contains("is-pinned")) {
          closePrimary(el, tip);
        } else {
          openPrimary(el, tip, true);
        }
      });

      tip.querySelectorAll(".bare-fn-nested-trigger").forEach((trigger) => {
        if (trigger.dataset.bareNestedBound === "1") {
          return;
        }
        trigger.dataset.bareNestedBound = "1";
        const nestedId = trigger.getAttribute("aria-controls");
        const nested = nestedId ? document.getElementById(nestedId) : null;

        function showChild() {
          clearLeave();
          openPrimary(el, tip, el.classList.contains("is-pinned"));
          openNested(trigger);
        }

        function hideChild() {
          closeNested(trigger);
        }

        trigger.addEventListener("mouseenter", showChild);
        trigger.addEventListener("focus", showChild);
        if (nested) {
          nested.addEventListener("mouseenter", () => {
            clearLeave();
            showChild();
          });
          nested.addEventListener("mouseleave", () => {
            if (trigger.getAttribute("aria-expanded") !== "true") {
              return;
            }
            // Keep open while pinned via click; hover-only closes with parent leave.
          });
        }
        // Nested click must not toggle the parent tip.
        trigger.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          clearLeave();
          openPrimary(el, tip, true);
          if (trigger.getAttribute("aria-expanded") === "true") {
            hideChild();
          } else {
            showChild();
          }
        });
        trigger.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            event.stopPropagation();
            trigger.click();
          }
        });
      });
    });

    if (scope.dataset.bareFnGlobalBound === "1") {
      return;
    }
    scope.dataset.bareFnGlobalBound = "1";

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }
      const openNestedBtn = document.querySelector(
        ".bare-fn-nested-trigger[aria-expanded='true']"
      );
      if (openNestedBtn) {
        closeNested(openNestedBtn);
        openNestedBtn.focus();
        event.preventDefault();
        return;
      }
      const openPrimaryEl = document.querySelector(".bare-fn.is-open, .bare-fn.is-pinned");
      if (openPrimaryEl) {
        const tip = openPrimaryEl.querySelector(":scope > .bare-fn-tip");
        if (tip) {
          closePrimary(openPrimaryEl, tip);
        }
        openPrimaryEl.focus();
        event.preventDefault();
      }
    });

    document.addEventListener("pointerdown", (event) => {
      const inside = event.target.closest(".bare-fn");
      document.querySelectorAll(".bare-fn.is-open, .bare-fn.is-pinned").forEach((el) => {
        if (inside === el || (inside && el.contains(inside))) {
          return;
        }
        const tip = el.querySelector(":scope > .bare-fn-tip");
        if (tip) {
          closePrimary(el, tip);
        }
      });
    });
  }

  // Leaving an active revision queue asks first. Deliberately outside
  // initLearn: the guard is about history, not mode state, and initLearn is
  // pinned by tests to contain no pushState of its own.
  //
  // The sentinel works because nothing else in this app pushes history —
  // switchModeLocal and the phone's showDeck both use replaceState, so they
  // add no entry and structurally cannot fire popstate. A popstate here can
  // only mean the user pressed Back.
  function initRevisionGuard() {
    const learn = document.querySelector(".learn[data-session-id]");
    const modal = document.querySelector("[data-revision-exit-modal]");
    if (!learn || !modal || typeof modal.showModal !== "function") {
      return;
    }
    let leaving = false;
    let pendingHref = "/dashboard";

    function arm() {
      history.pushState({ rtcRevisionGuard: true }, "", window.location.href);
    }

    function ask(href) {
      pendingHref = href || "/dashboard";
      if (!modal.open) modal.showModal();
    }

    arm();

    window.addEventListener("popstate", function () {
      if (leaving) {
        return;
      }
      // Put the sentinel back before asking, so Keep revising leaves the URL
      // and the current unit exactly as they were.
      arm();
      ask("/dashboard");
    });

    // The deck header's "← Article N" genuinely leaves the queue. The phone's
    // deck-back control is a button that only returns to the deck WITHIN this
    // unit, and the mode tabs stay inside it — neither is guarded.
    document.addEventListener("click", function (event) {
      if (leaving) {
        return;
      }
      const link = event.target.closest("a.mobile-back[href]");
      if (!link || !learn.contains(link)) {
        return;
      }
      event.preventDefault();
      ask(link.getAttribute("href"));
    });

    const exitBtn = modal.querySelector("[data-revision-exit]");
    if (exitBtn) {
      exitBtn.addEventListener("click", function () {
        // Exiting never destroys the session: completed items stay completed,
        // pending items stay pending, and Today resumes with "N left".
        leaving = true;
        modal.close();
        window.location.assign(pendingHref);
      });
    }
  }

  function initLearn() {
    const learn = document.querySelector(".learn");
    if (!learn) {
      return;
    }
    learn.classList.add("is-ready");
    initBareFns(learn);

    const clozePanel = learn.querySelector('[data-learn-panel="cloze"]');
    const lettersPanel = learn.querySelector('[data-learn-panel="letters"]');
    const typePanel = learn.querySelector('[data-learn-panel="type"]');
    const recitePanel = learn.querySelector('[data-learn-panel="recite"]');
    const testPanel = learn.querySelector('[data-learn-panel="test"]');
    const doneBtn = document.getElementById("learn-done-btn");

    const MODE_LABELS = {
      read: "Read",
      cloze: "Cloze",
      letters: "Letters",
      type: "Type",
      recite: "Recite",
      test: "Test",
    };
    const isGuest = learn.hasAttribute("data-guest-learn");
    const unitId = learn.getAttribute("data-unit-id") || "";
    // Scoped to the tab strip on purpose. The phone's deck cards also carry
    // data-learn-mode so clicks route through the handler below, but
    // applyTabMarks rewrites textContent — over a card that wipes its title,
    // description and status and leaves a bare "Read ✓".
    const tabs = Array.from(learn.querySelectorAll(".mode-tab"));
    const trackerEl = document.getElementById("methods-tracker");

    function parseModes(raw) {
      const set = new Set();
      String(raw || "")
        .split(",")
        .forEach((part) => {
          const value = part.trim();
          if (LEARN_MODES.has(value)) {
            set.add(value);
          }
        });
      return set;
    }

    const confirmedModes = parseModes(learn.getAttribute("data-modes-seen"));
    const guestVisitedModes = parseModes(learn.getAttribute("data-modes-seen"));
    const lockedModes = parseModes(learn.getAttribute("data-locked-modes"));
    // Entitlement-aware required set: six normally; the four open modes for
    // guests / cap-reached Articles (Type/Recite locked).
    const requiredModesRaw = parseModes(learn.getAttribute("data-required-modes"));
    const requiredModes = requiredModesRaw.size > 0 ? requiredModesRaw : new Set(LEARN_MODES);
    // Unclaimed Articles keep mode visits provisional until claimed on Done —
    // tracked in sessionStorage so a reload keeps the marks without any server
    // persistence (R2: three saved Articles, not unlimited half-saved ones).
    const seenProvisional = learn.getAttribute("data-seen-provisional") === "true";
    const provisionalKey = "cm-provisional:" + unitId;
    const provisionalModes = (function () {
      if (!seenProvisional) {
        return new Set();
      }
      try {
        return parseModes(sessionStorage.getItem(provisionalKey));
      } catch (_e) {
        return new Set();
      }
    })();
    function saveProvisional() {
      if (!seenProvisional) {
        return;
      }
      try {
        sessionStorage.setItem(provisionalKey, Array.from(provisionalModes).join(","));
      } catch (_e) {
        /* ignore */
      }
      // Keep the claim form's mode list in sync with every provisional mark.
      const claimModes = document.querySelector("[data-claim-modes]");
      if (claimModes) {
        claimModes.value = Array.from(provisionalModes).join(",");
      }
    }
    function visitedUnion() {
      const union = new Set(confirmedModes);
      provisionalModes.forEach(function (mode) {
        union.add(mode);
      });
      return union;
    }
    const inFlight = new Set();
    let serverDoneUnlocked = learn.dataset.doneUnlocked === "true";

    // Gated modes report a completed attempt through markModeAttempted (or the
    // graded quiz payload); auto-seen modes are marked on tab visit instead.
    //
    // These run last on purpose: initLetters fires its callback during init
    // when the saved view is "Just read", and markModeAttempted reads the
    // consts above. Constructed any earlier, that first callback throws a
    // temporal-dead-zone error and takes the whole Learn page down.
    const cloze = initCloze(clozePanel, function () {
      markModeAttempted("cloze");
    });
    const letters = initLetters(lettersPanel, function () {
      markModeAttempted("letters");
    });
    const typeMode = initType(typePanel, function () {
      markModeAttempted("type");
    });
    const recite = initRecite(recitePanel, function () {
      markModeAttempted("recite");
    });
    const testMode = initTest(testPanel, function (payload) {
      applyQuizPayload(payload);
    });

    function requiredVisitedCount(visited) {
      let count = 0;
      requiredModes.forEach(function (mode) {
        if (visited.has(mode)) {
          count += 1;
        }
      });
      return count;
    }

    function methodsTrackerLine(count) {
      const total = requiredModes.size;
      if (count >= total) {
        return "All " + total + " methods visited — revision complete, mark it Done";
      }
      const word = total === 6 ? "six" : String(total);
      return (
        count +
        " of " + total + " methods visited · revision completes when you've been through all " +
        word
      );
    }

    function lockedMethodsLeftLabel(confirmedCount) {
      const remaining = requiredModes.size - confirmedCount;
      if (remaining <= 0) {
        return null;
      }
      if (remaining === 1) {
        return "1 method left";
      }
      return remaining + " methods left";
    }

    function localVisited() {
      return isGuest ? guestVisitedModes : visitedUnion();
    }

    function applyLockedDoneLabel() {
      if (!doneBtn || serverDoneUnlocked) {
        return;
      }
      const label = lockedMethodsLeftLabel(requiredVisitedCount(localVisited()));
      if (label) {
        doneBtn.textContent = label;
      }
    }

    function maybeUnlockLocalDone() {
      // Guests and unclaimed Articles persist nothing server-side, so the
      // Done affordance unlocks from the local set; the server re-validates
      // on POST (guests get the sign-in prompt instead).
      if (serverDoneUnlocked || !doneBtn) {
        return;
      }
      if (!isGuest && !seenProvisional) {
        return;
      }
      if (requiredVisitedCount(localVisited()) >= requiredModes.size) {
        serverDoneUnlocked = true;
        applyDoneUnlocked(isGuest ? "Mark as mastered" : "Mark it Done");
      } else {
        applyLockedDoneLabel();
      }
    }

    function applyTabMarks(visited) {
      tabs.forEach((tab) => {
        const tabMode = tab.getAttribute("data-learn-mode");
        if (!LEARN_MODES.has(tabMode)) {
          return;
        }
        const label = MODE_LABELS[tabMode] || tabMode;
        if (lockedModes.has(tabMode)) {
          // Locked modes never earn a ✓ — keep the restrained lock mark.
          tab.textContent = label + " 🔒";
          return;
        }
        tab.textContent = visited.has(tabMode) ? label + " ✓" : label;
      });
    }

    function applyTracker(visited) {
      if (!trackerEl) {
        return;
      }
      const count = requiredVisitedCount(visited);
      trackerEl.setAttribute("data-count", String(count));
      trackerEl.textContent = methodsTrackerLine(count);
    }

    function applyDoneUnlocked(label) {
      if (!doneBtn) {
        return;
      }
      doneBtn.disabled = false;
      doneBtn.removeAttribute("disabled");
      doneBtn.setAttribute("aria-disabled", "false");
      doneBtn.classList.remove("btn-done-locked");
      doneBtn.classList.add("btn-accent");
      if (label) {
        doneBtn.textContent = label;
      }
    }

    // One local mark per completed gated attempt (or auto-seen visit),
    // routed to the right store for the current access level.
    function markModeAttempted(mode) {
      if (lockedModes.has(mode)) {
        return;
      }
      if (isGuest) {
        guestVisitedModes.add(mode);
        applyTabMarks(guestVisitedModes);
        applyTracker(guestVisitedModes);
        maybeUnlockLocalDone();
        return;
      }
      if (seenProvisional) {
        provisionalModes.add(mode);
        saveProvisional();
        applyTabMarks(visitedUnion());
        applyTracker(visitedUnion());
        maybeUnlockLocalDone();
        return;
      }
      persistSeen(mode);
    }

    // Shared server-payload handling for /seen and /quiz responses.
    function applySeenPayload(payload) {
      const seen = Array.isArray(payload.seen) ? payload.seen : [];
      seen.forEach((item) => {
        if (LEARN_MODES.has(item)) {
          confirmedModes.add(item);
        }
      });
      applyTabMarks(visitedUnion());
      applyTracker(visitedUnion());
      if (payload.done && payload.done.unlocked === true) {
        serverDoneUnlocked = true;
        applyDoneUnlocked(payload.done.label);
      } else if (serverDoneUnlocked) {
        /* keep unlocked; ignore stale unlocked:false */
      } else {
        applyLockedDoneLabel();
      }
    }

    // Test is /quiz-only. Never mark it from a tab visit or markModeAttempted.
    function applyQuizPayload(payload) {
      if (!payload || payload.ok !== true) {
        return;
      }
      if (isGuest) {
        guestVisitedModes.add("test");
        applyTabMarks(guestVisitedModes);
        applyTracker(guestVisitedModes);
        maybeUnlockLocalDone();
        return;
      }
      if (payload.persisted === false) {
        provisionalModes.add("test");
        saveProvisional();
        applyTabMarks(visitedUnion());
        applyTracker(visitedUnion());
        maybeUnlockLocalDone();
        return;
      }
      applySeenPayload(payload);
    }

    function resetDestination(nextMode, prevMode) {
      if (prevMode === "recite" && nextMode !== "recite" && recite) {
        recite.reset();
      }
      if (nextMode === "test" && testMode) {
        testMode.reset();
      }
      if (nextMode === "cloze" && cloze) {
        cloze.reset();
      }
      if (nextMode === "letters" && letters) {
        letters.reset();
      }
      if (nextMode === "type" && typeMode) {
        typeMode.reset();
      }
      if (nextMode === "recite" && prevMode !== "recite" && recite) {
        recite.reset();
      }
    }

    function switchModeLocal(nextMode, tab) {
      const prevMode = learn.dataset.mode || "read";
      learn.dataset.mode = nextMode;
      tabs.forEach((item) => {
        const active = item.getAttribute("data-learn-mode") === nextMode;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      const href = tab.getAttribute("href");
      if (href) {
        history.replaceState({}, "", href);
      }
      resetDestination(nextMode, prevMode);
    }

    function persistSeen(mode) {
      if (
        isGuest ||
        lockedModes.has(mode) ||
        confirmedModes.has(mode) ||
        provisionalModes.has(mode) ||
        inFlight.has(mode) ||
        !unitId
      ) {
        return;
      }
      inFlight.add(mode);
      const body = new FormData();
      body.append("mode", mode);
      fetch("/learn/" + encodeURIComponent(unitId) + "/seen", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: body,
      })
        .then((response) => {
          const type = response.headers.get("content-type") || "";
          if (!response.ok || !type.includes("application/json")) {
            throw new Error("seen-failed");
          }
          return response.json();
        })
        .then((payload) => {
          inFlight.delete(mode);
          if (payload && payload.persisted === false) {
            // Provisional visit — track locally until the Article is claimed.
            provisionalModes.add(mode);
            saveProvisional();
            applyTabMarks(visitedUnion());
            applyTracker(visitedUnion());
            maybeUnlockLocalDone();
            return;
          }
          applySeenPayload(payload);
        })
        .catch(() => {
          inFlight.delete(mode);
        });
    }

    learn.addEventListener("click", (event) => {
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        event.button !== 0
      ) {
        return;
      }
      const tab = event.target.closest("[data-learn-mode]");
      if (!tab || !learn.contains(tab)) {
        return;
      }
      const nextMode = tab.getAttribute("data-learn-mode");
      if (!LEARN_MODES.has(nextMode)) {
        return;
      }
      event.preventDefault();
      const current = learn.dataset.mode || "read";
      if (nextMode === current) {
        // Re-clicking the open tab only re-marks auto-seen modes; gated
        // modes wait for their completed attempt.
        if (!isGuest && AUTO_SEEN_MODES.has(nextMode)) {
          persistSeen(nextMode);
        }
        return;
      }
      switchModeLocal(nextMode, tab);
      if (AUTO_SEEN_MODES.has(nextMode)) {
        markModeAttempted(nextMode);
      }
    });

    // Provisional boot: the server records nothing for unclaimed Articles, so
    // count the currently open mode locally and restore prior session marks.
    if (seenProvisional) {
      const bootMode = learn.dataset.mode || "read";
      if (!lockedModes.has(bootMode) && AUTO_SEEN_MODES.has(bootMode)) {
        provisionalModes.add(bootMode);
        saveProvisional();
      }
      applyTabMarks(visitedUnion());
      applyTracker(visitedUnion());
      maybeUnlockLocalDone();
      // The server-rendered claim panel re-validates the mode gate on POST.
      const claimModes = document.querySelector("[data-claim-modes]");
      if (claimModes) {
        claimModes.value = Array.from(provisionalModes).join(",");
      }
    }

    // Honor server-rendered mode (e.g. hard navigation to ?mode=…).
    // Reset interactive panels when landing on them.
    const mode = learn.dataset.mode || "read";
    if (mode === "test" && testMode) {
      testMode.reset();
    }
    if (mode === "cloze" && cloze) {
      cloze.reset();
    }
    if (mode === "letters" && letters) {
      letters.reset();
    }
    if (mode === "type" && typeMode) {
      typeMode.reset();
    }
    if (mode === "recite" && recite) {
      recite.reset();
    }

    if (doneBtn) {
      const unlocked = learn.dataset.doneUnlocked === "true";
      doneBtn.disabled = !unlocked;
      if (unlocked) {
        doneBtn.removeAttribute("disabled");
      } else {
        doneBtn.setAttribute("disabled", "disabled");
      }
    }
  }

  function initBrowseArticle() {
    const root = document.querySelector(".browse-article [data-bare-fn-root]");
    if (!root) {
      return;
    }
    initBareFns(root);
  }

  function cardHasMark(card, key) {
    const raw = card.getAttribute("data-browse-marks") || "";
    return raw.split(/\s+/).filter(Boolean).indexOf(key) !== -1;
  }

  function initBrowseIndex() {
    const panel = document.querySelector("section.browse");
    if (!panel) {
      return;
    }
    const cards = Array.from(panel.querySelectorAll(".browse-article-card"));
    const legendItems = Array.from(panel.querySelectorAll(".browse-legend-item"));
    let active = null;

    function applyFilter(next) {
      if (next && next === active) {
        active = null;
      } else {
        active = next || null;
      }
      if (active) {
        panel.setAttribute("data-mark-filter", active);
      } else {
        panel.removeAttribute("data-mark-filter");
      }
      legendItems.forEach((item) => {
        item.setAttribute(
          "aria-pressed",
          item.getAttribute("data-browse-filter") === active ? "true" : "false"
        );
      });
      cards.forEach((card) => {
        const hide = Boolean(active) && !cardHasMark(card, active);
        card.classList.toggle("is-mark-hidden", hide);
      });
      panel.querySelectorAll(".browse-chapter").forEach((chapter) => {
        const visible = chapter.querySelectorAll(
          ".browse-article-card:not(.is-mark-hidden)"
        );
        chapter.classList.toggle("is-filter-empty", Boolean(active) && visible.length === 0);
      });
      panel.querySelectorAll(".browse-part").forEach((part) => {
        const visible = part.querySelectorAll(
          ".browse-article-card:not(.is-mark-hidden)"
        );
        part.classList.toggle("is-filter-empty", Boolean(active) && visible.length === 0);
      });
    }

    panel.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-browse-filter]");
      if (!trigger || !panel.contains(trigger)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      applyFilter(trigger.getAttribute("data-browse-filter"));
    });
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function getDoneAudio() {
    if (!doneAudio) {
      doneAudio = new Audio(DONE_SOUND_SRC);
      doneAudio.preload = "auto";
    }
    return doneAudio;
  }

  function ensureAudio() {
    const audio = getDoneAudio();
    // Unlock playback under the Done click; stay silent until persist confirms.
    audio.muted = true;
    const playing = audio.play();
    if (playing && playing.then) {
      playing
        .then(function () {
          audio.pause();
          audio.currentTime = 0;
          audio.muted = false;
        })
        .catch(function () {
          audio.muted = false;
        });
    } else {
      audio.muted = false;
    }
    return audio;
  }

  function playCompletionSound() {
    return new Promise(function (resolve) {
      const audio = getDoneAudio();
      let settled = false;
      function finish() {
        if (settled) {
          return;
        }
        settled = true;
        audio.removeEventListener("ended", finish);
        audio.removeEventListener("error", finish);
        resolve();
      }
      audio.muted = false;
      try {
        audio.currentTime = 0;
      } catch (_e) {
        /* ignore */
      }
      audio.addEventListener("ended", finish);
      audio.addEventListener("error", finish);
      const playing = audio.play();
      if (playing && playing.catch) {
        playing.catch(finish);
      }
      window.setTimeout(finish, 2300);
    });
  }

  function cleanDoneParam(urlString) {
    const u = new URL(urlString, window.location.origin);
    u.searchParams.delete("done");
    return u.pathname + u.search + u.hash;
  }

  function showNotConfirmed(root) {
    const host = root || document.querySelector(".learn") || document.querySelector("main") || document.body;
    if (host.querySelector(".rtc-not-confirmed")) {
      return;
    }
    const box = document.createElement("div");
    box.className = "rtc-not-confirmed";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    box.innerHTML =
      '<p class="rtc-not-confirmed-eyebrow">Not confirmed</p>' +
      "<p>Could not confirm whether this review was saved. Reload to check your progress.</p>" +
      '<button type="button" class="rtc-not-confirmed-reload">Reload</button>';
    const reload = box.querySelector(".rtc-not-confirmed-reload");
    reload.addEventListener("click", function () {
      window.location.reload();
    });
    host.insertBefore(box, host.firstChild);
  }

  function buildAffirmationEl(payload) {
    const quote = payload.quote || {};
    const continueLabel = payload.continue_label
      ? "Continue to " + payload.continue_label
      : "Continue";
    const wrap = document.createElement("div");
    wrap.className = "rtc-affirmation";
    wrap.setAttribute("data-rtc-completion", "");
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-modal", "true");
    wrap.setAttribute("aria-live", "polite");
    wrap.innerHTML =
      '<div class="rtc-affirmation-scrim" data-rtc-advance tabindex="-1"></div>' +
      '<div class="rtc-affirmation-card">' +
      '<p class="rtc-affirmation-eyebrow"></p>' +
      '<blockquote class="rtc-affirmation-quote" id="rtc-affirmation-quote"></blockquote>' +
      '<p class="rtc-affirmation-attr"></p>' +
      '<p class="rtc-affirmation-ledger"><span></span><span></span></p>' +
      '<div class="rtc-affirmation-actions">' +
      '<a class="rtc-affirmation-continue" data-rtc-advance href="#"></a>' +
      '<span class="rtc-affirmation-esc">Esc</span></div>' +
      '<div class="rtc-affirmation-hold" aria-hidden="true"></div></div>';
    wrap.querySelector(".rtc-affirmation-eyebrow").textContent = payload.eyebrow || "Review complete";
    wrap.querySelector(".rtc-affirmation-quote").textContent = quote.text || "";
    wrap.querySelector(".rtc-affirmation-attr").textContent = quote.author ? "— " + quote.author : "";
    const ledger = wrap.querySelectorAll(".rtc-affirmation-ledger span");
    ledger[0].textContent = payload.article_ref || "";
    ledger[1].textContent = payload.ledger || "";
    const link = wrap.querySelector(".rtc-affirmation-continue");
    link.textContent = continueLabel;
    link.setAttribute("href", cleanDoneParam(payload.next_url || "/"));
    return wrap;
  }

  function holdAffirmation(el) {
    return new Promise(function (resolve) {
      let settled = false;
      function finish(event) {
        if (settled) {
          return;
        }
        if (event && event.type === "click" && event.currentTarget.tagName === "A") {
          event.preventDefault();
        }
        settled = true;
        window.clearTimeout(timer);
        document.removeEventListener("keydown", onKey);
        el.classList.add("is-exiting");
        el.classList.remove("is-holding");
        window.setTimeout(resolve, motionEnabled() ? 200 : 0);
      }
      function onKey(event) {
        if (event.key === "Escape") {
          finish();
        }
      }
      el.querySelectorAll("[data-rtc-advance]").forEach(function (node) {
        node.addEventListener("click", finish);
      });
      document.addEventListener("keydown", onKey);
      el.classList.add("is-open", "is-holding");
      const timer = window.setTimeout(finish, AFFIRMATION_HOLD_MS);
    });
  }

  async function presentAffirmation(el, nextUrl) {
    if (!el.isConnected) {
      document.body.appendChild(el);
    }
    await holdAffirmation(el);
    el.remove();
    if (nextUrl) {
      window.location.assign(cleanDoneParam(nextUrl));
    }
  }

  async function initServerAffirmation() {
    const el = document.querySelector("[data-rtc-completion]");
    if (!el) {
      return;
    }
    const u = new URL(window.location.href);
    u.searchParams.delete("done");
    window.history.replaceState(null, "", u.pathname + u.search + u.hash);
    const href = el.querySelector(".rtc-affirmation-continue");
    const nextUrl = href ? href.getAttribute("href") : u.pathname + u.search + u.hash;
    await presentAffirmation(el, nextUrl);
  }

  function buildClaimDialog(payload) {
    const article = String(payload.article_number || "");
    const slots = Number(payload.slots_remaining || 0);
    const dialog = document.createElement("dialog");
    dialog.className = "guest-modal claim-modal";
    dialog.setAttribute("aria-labelledby", "claim-modal-title");
    dialog.innerHTML =
      '<div class="guest-modal-card">' +
      '<h2 class="guest-modal-title" id="claim-modal-title"></h2>' +
      '<p class="guest-modal-body"></p>' +
      '<div class="guest-modal-actions">' +
      '<button type="button" class="btn" data-claim-confirm></button>' +
      '<button type="button" class="btn btn-ghost" data-claim-dismiss>Not now</button>' +
      "</div>" +
      '<p class="claim-modal-note"></p>' +
      "</div>";
    dialog.querySelector(".guest-modal-title").textContent =
      "Add Article " + article + " to your Free Articles?";
    dialog.querySelector(".guest-modal-body").textContent =
      "Article " + article + " and all its clauses will count as 1 of your 3 permanent " +
      "Free Articles. You’ll keep its progress and scheduled revisions.";
    dialog.querySelector("[data-claim-confirm]").textContent = "Add Article " + article;
    dialog.querySelector(".claim-modal-note").textContent =
      slots + " of 3 Free Article slot" + (slots === 1 ? "" : "s") + " remaining.";
    return dialog;
  }

  function confirmClaim(payload) {
    return new Promise(function (resolve) {
      const dialog = buildClaimDialog(payload);
      document.body.appendChild(dialog);
      let settled = false;
      function finish(confirmed) {
        if (settled) {
          return;
        }
        settled = true;
        try {
          dialog.close();
        } catch (_e) {
          /* ignore */
        }
        dialog.remove();
        resolve(confirmed);
      }
      dialog.querySelector("[data-claim-confirm]").addEventListener("click", function () {
        finish(true);
      });
      dialog.querySelector("[data-claim-dismiss]").addEventListener("click", function () {
        finish(false);
      });
      dialog.addEventListener("cancel", function () {
        finish(false);
      });
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
    });
  }

  function initDoneInterceptor() {
    const form = document.querySelector("form.learn-action-done");
    if (!form) {
      return;
    }
    const btn = form.querySelector("#learn-done-btn") || form.querySelector("button[type='submit']");
    let fetchAttempted = false;

    function restoreButton(original) {
      btn.classList.remove("is-rtc-saving");
      btn.textContent = original;
      btn.disabled = false;
    }

    async function postDone(extraFields) {
      const body = new FormData(form);
      // Unclaimed Articles track mode visits provisionally (sessionStorage);
      // the Done POST carries that list so the server can validate the gate.
      const learnEl = form.closest(".learn");
      if (learnEl && learnEl.getAttribute("data-seen-provisional") === "true") {
        const unit = learnEl.getAttribute("data-unit-id") || "";
        let provisional = "";
        try {
          provisional = sessionStorage.getItem("cm-provisional:" + unit) || "";
        } catch (_e) {
          /* ignore */
        }
        if (provisional) {
          body.set("modes", provisional);
        }
      }
      if (extraFields) {
        Object.keys(extraFields).forEach(function (key) {
          body.set(key, extraFields[key]);
        });
      }
      const response = await fetch(form.getAttribute("action"), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: body,
      });
      const type = response.headers.get("content-type") || "";
      if (!type.includes("application/json")) {
        return null;
      }
      return response.json();
    }

    async function celebrate(payload) {
      btn.classList.remove("is-rtc-saving");
      btn.classList.add("is-rtc-saved");
      btn.textContent = "Saved";
      // First-login tour: the guide narrates this moment and immediately
      // leads on to Calendar → Settings, so the quote affirmation would
      // block the remaining steps. Skip it; a brief "Saved" beat is enough.
      if (document.body.getAttribute("data-onboarding") === "active") {
        await wait(motionEnabled() ? 350 : 60);
        window.location.assign(cleanDoneParam(payload.next_url));
        return;
      }
      const soundP = soundEnabled() ? playCompletionSound() : Promise.resolve();
      await wait(motionEnabled() ? 120 : 0);
      const modal = buildAffirmationEl(payload);
      await presentAffirmation(modal, null);
      await soundP;
      window.location.assign(cleanDoneParam(payload.next_url));
    }

    function surfaceError(payload, original) {
      showNotConfirmed(form.closest(".learn"));
      const box = document.querySelector(".rtc-not-confirmed p:not(.rtc-not-confirmed-eyebrow)");
      if (box && payload && payload.error === "modes_incomplete") {
        box.textContent = "All six methods need a visit before Done can save.";
      } else if (box && payload && payload.error === "subscription_required") {
        box.textContent =
          "Your 3 Free Articles are in use, so this review can’t be saved on the Free plan.";
      } else if (box && payload && payload.error && payload.error !== "sign_in_required") {
        box.textContent = String(payload.error);
      }
      restoreButton(original);
    }

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (!btn || btn.disabled) {
        return;
      }
      if (fetchAttempted) {
        return;
      }
      fetchAttempted = true;
      ensureAudio();
      const original = btn.textContent;
      btn.disabled = true;
      btn.classList.add("is-rtc-saving");
      btn.textContent = "Saving…";
      try {
        let payload = await postDone(null);
        if (!payload) {
          showNotConfirmed(form.closest(".learn"));
          restoreButton(original);
          return;
        }
        if (!payload.ok && payload.error === "claim_required") {
          const confirmed = await confirmClaim(payload);
          if (!confirmed) {
            // "Not now" — nothing persisted; the learner may press Done again.
            restoreButton(original);
            fetchAttempted = false;
            return;
          }
          // User-confirmed second action (not an auto-retry).
          payload = await postDone({ claim_article: "1" });
          if (!payload) {
            showNotConfirmed(form.closest(".learn"));
            restoreButton(original);
            return;
          }
        }
        if (!payload.ok) {
          surfaceError(payload, original);
          return;
        }
        await celebrate(payload);
      } catch (_err) {
        showNotConfirmed(form.closest(".learn"));
        restoreButton(original);
      }
    });
  }

  function initExperienceControls() {
    function stored(key, fallback) {
      try {
        const value = localStorage.getItem(key);
        return value === "on" || value === "off" ? value : fallback;
      } catch (_e) {
        return fallback;
      }
    }
    function persist(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch (_e) {
        /* ignore */
      }
    }

    const motionPref = stored(MOTION_KEY, "on");
    const soundPref = stored(SOUND_KEY, "on");
    document.querySelectorAll("[data-motion-set]").forEach(function (el) {
      const on = el.getAttribute("data-motion-set") === motionPref;
      el.classList.toggle("is-active", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
      el.addEventListener("click", function () {
        if (prefersReducedMotion()) {
          return;
        }
        const next = el.getAttribute("data-motion-set");
        persist(MOTION_KEY, next);
        document.querySelectorAll("[data-motion-set]").forEach(function (btn) {
          const active = btn.getAttribute("data-motion-set") === next;
          btn.classList.toggle("is-active", active);
          btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
        syncRtcAnim();
      });
    });
    document.querySelectorAll("[data-sound-set]").forEach(function (el) {
      const on = el.getAttribute("data-sound-set") === soundPref;
      el.classList.toggle("is-active", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
      el.addEventListener("click", function () {
        const next = el.getAttribute("data-sound-set");
        persist(SOUND_KEY, next);
        document.querySelectorAll("[data-sound-set]").forEach(function (btn) {
          const active = btn.getAttribute("data-sound-set") === next;
          btn.classList.toggle("is-active", active);
          btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
      });
    });

    const motionRow = document.querySelector('[data-experience-row="motion"]');
    const note = document.querySelector("[data-motion-note]");
    if (prefersReducedMotion() && motionRow) {
      motionRow.classList.add("is-os-reduced");
      if (note) {
        note.textContent = "Following your system — reduced motion is on.";
      }
    }
    syncRtcAnim();
  }

  function initPricing() {
    const root = document.querySelector("[data-pricing]");
    if (!root) {
      return;
    }
    let plans = [];
    try {
      const data = document.getElementById("pricing-data");
      plans = data ? JSON.parse(data.textContent || "[]") : [];
    } catch (_e) {
      return; // fall back to full-page navigation via the pill links
    }
    const byDays = {};
    plans.forEach(function (plan) {
      byDays[String(plan.days)] = plan;
    });
    const pills = Array.from(root.querySelectorAll("[data-pricing-days]"));
    const els = {
      title: root.querySelector("[data-pricing-title]"),
      price: root.querySelector("[data-pricing-price]"),
      perday: root.querySelector("[data-pricing-perday]"),
      tagline: root.querySelector("[data-pricing-tagline]"),
      annotation: root.querySelector("[data-pricing-annotation]"),
      journey: root.querySelector("[data-pricing-journey]"),
      cta: root.querySelector("[data-pricing-cta]"),
      ctaNote: root.querySelector("[data-pricing-cta-note]"),
      billing: root.querySelector("[data-pricing-billing]"),
    };

    function select(days) {
      const plan = byDays[String(days)];
      if (!plan) {
        return;
      }
      root.setAttribute("data-selected-days", String(plan.days));
      pills.forEach(function (pill) {
        const active = pill.getAttribute("data-pricing-days") === String(plan.days);
        pill.classList.toggle("is-selected", active);
        pill.setAttribute("aria-checked", active ? "true" : "false");
      });
      if (els.title) {
        els.title.textContent = plan.days + "-Day Recall";
      }
      if (els.price) {
        els.price.textContent = "₹" + plan.price_inr;
      }
      if (els.perday) {
        els.perday.textContent = "₹" + plan.per_day.toFixed(2) + " / day";
      }
      if (els.tagline) {
        els.tagline.textContent = plan.tagline;
      }
      if (els.annotation) {
        els.annotation.textContent = plan.annotation || "";
        els.annotation.hidden = !plan.annotation;
      }
      if (els.journey) {
        els.journey.hidden = plan.days !== 180;
      }
      if (els.cta) {
        els.cta.textContent = "Start my " + plan.days + " days →";
        const href = els.cta.getAttribute("href");
        if (href) {
          const target = new URL(href, window.location.origin);
          target.searchParams.set("d", String(plan.days));
          els.cta.setAttribute("href", target.pathname + target.search);
        }
      }
      if (els.billing) {
        els.billing.textContent = plan.billing_line;
      }
      // Update only the d param — preserve any other query params and hash.
      const u = new URL(window.location.href);
      u.searchParams.set("d", String(plan.days));
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    }

    pills.forEach(function (pill, index) {
      pill.addEventListener("click", function (event) {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
          return;
        }
        event.preventDefault();
        select(pill.getAttribute("data-pricing-days"));
        pill.focus();
      });
      pill.addEventListener("keydown", function (event) {
        let target = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          target = pills[(index + 1) % pills.length];
        } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          target = pills[(index - 1 + pills.length) % pills.length];
        } else if (event.key === "Home") {
          target = pills[0];
        } else if (event.key === "End") {
          target = pills[pills.length - 1];
        } else {
          return;
        }
        event.preventDefault();
        if (target.hidden) {
          setMoreOpen(true);
        }
        select(target.getAttribute("data-pricing-days"));
        target.focus();
      });
    });

    const moreToggle = root.querySelector("[data-pricing-more-toggle]");
    const morePills = pills.filter(function (pill) {
      return pill.classList.contains("is-more");
    });

    function setMoreOpen(open) {
      morePills.forEach(function (pill) {
        pill.hidden = !open && !pill.classList.contains("is-selected");
      });
      if (moreToggle) {
        moreToggle.setAttribute("aria-expanded", open ? "true" : "false");
        moreToggle.textContent = open ? "Fewer options" : "More options";
      }
    }

    if (moreToggle) {
      moreToggle.addEventListener("click", function () {
        setMoreOpen(moreToggle.getAttribute("aria-expanded") !== "true");
      });
    }
  }

  function initSlotsWhy() {
    const btn = document.querySelector("[data-slots-why]");
    const body = document.querySelector("[data-slots-why-body]");
    if (!btn || !body) {
      return;
    }
    btn.addEventListener("click", function () {
      const open = body.hidden;
      body.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open
        ? "Why can't I swap an Article? −"
        : "Why can't I swap an Article? +";
    });
  }

  function initCheckout() {
    const button = document.querySelector("[data-checkout-pay]");
    if (!button) {
      return;
    }
    let config = null;
    try {
      const node = document.getElementById("billing-data");
      config = node ? JSON.parse(node.textContent || "null") : null;
    } catch (_e) {
      config = null;
    }
    const errorEl = document.querySelector("[data-checkout-error]");
    if (!config) {
      return; // placeholder page — nothing to wire
    }

    function showError(message) {
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.hidden = false;
      }
      button.disabled = false;
    }

    function clearError() {
      if (errorEl) {
        errorEl.hidden = true;
        errorEl.textContent = "";
      }
    }

    async function verifyPayment(payload) {
      // Server-side HMAC verification is the only thing that marks a
      // payment as paid — the client never decides success on its own.
      const resp = await fetch(config.verify_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json().catch(function () {
        return {};
      });
      if (resp.ok && body.ok && body.next) {
        window.location.assign(body.next);
        return;
      }
      showError(
        "Payment received but could not be verified. Nothing further was " +
          "charged — contact support with your payment id " +
          (payload.razorpay_payment_id || "") + "."
      );
    }

    button.addEventListener("click", async function () {
      if (typeof window.Razorpay !== "function") {
        showError("Checkout is still loading — try again in a moment.");
        return;
      }
      clearError();
      button.disabled = true;
      let order = null;
      try {
        const resp = await fetch(config.order_url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ days: config.days }),
        });
        const body = await resp.json().catch(function () {
          return {};
        });
        if (resp.status === 401) {
          window.location.assign("/login?next=/pricing");
          return;
        }
        if (!resp.ok || !body.ok) {
          showError("Could not start the payment. Nothing was charged — try again.");
          return;
        }
        order = body;
      } catch (_e) {
        showError("Could not start the payment. Nothing was charged — try again.");
        return;
      }
      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        order_id: order.order_id,
        name: config.name,
        description: config.description,
        prefill: {
          email: config.prefill_email || undefined,
          contact: config.prefill_contact || undefined,
        },
        handler: function (response) {
          verifyPayment({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
        },
        modal: {
          ondismiss: function () {
            // User closed the modal — nothing was charged.
            button.disabled = false;
          },
        },
      });
      rzp.on("payment.failed", function (event) {
        const reason =
          event && event.error && event.error.description
            ? event.error.description
            : "The payment did not go through.";
        showError(reason + " Nothing changed on your account — you can try again.");
      });
      rzp.open();
    });
  }

  function initFirstPaidSession() {
    const KEY = "cm-first-paid-session";
    // On the receipt: remember the fresh pass for the next Learn screen.
    const receipt = document.querySelector("[data-purchase-receipt]");
    if (receipt) {
      try {
        sessionStorage.setItem(
          KEY,
          JSON.stringify({
            days: receipt.getAttribute("data-receipt-days") || "",
            until: receipt.getAttribute("data-receipt-until") || "",
          })
        );
      } catch (_e) {
        /* ignore */
      }
      return;
    }
    // On the first Learn screen after purchase: show the band once (design
    // 03·4), then clear the flag so it never reappears.
    const learn = document.querySelector(".panel.learn");
    if (!learn) {
      return;
    }
    let pass = null;
    try {
      pass = JSON.parse(sessionStorage.getItem(KEY) || "null");
      if (pass) {
        sessionStorage.removeItem(KEY);
      }
    } catch (_e) {
      pass = null;
    }
    if (!pass || !pass.days) {
      return;
    }
    const band = document.createElement("div");
    band.className = "first-session-band";
    band.setAttribute("role", "status");
    const chip = document.createElement("span");
    chip.className = "first-session-chip";
    chip.textContent = "Recall active · " + pass.days + " days";
    band.appendChild(chip);
    if (pass.until) {
      const until = document.createElement("span");
      until.className = "first-session-until";
      until.textContent = "Access until " + pass.until;
      band.appendChild(until);
    }
    learn.insertBefore(band, learn.firstChild);
  }

  function initGcalTimezone() {
    let tz = "";
    try {
      tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (_e) {
      tz = "";
    }
    // Prefill the Settings field when empty.
    const field = document.querySelector("[data-gcal-timezone]");
    if (field && !field.value.trim() && tz) {
      field.value = tz;
    }
    // Carry the browser timezone INTO the connect flow so the very first
    // calendar + events use local time, not UTC (server stores set-if-unset).
    const connect = document.querySelector("[data-gcal-connect]");
    if (connect && tz) {
      try {
        const target = new URL(connect.getAttribute("href"), window.location.origin);
        target.searchParams.set("tz", tz);
        connect.setAttribute("href", target.pathname + target.search);
      } catch (_e) {
        /* keep the plain href */
      }
    }
  }

  function initGcalReminderPrompt() {
    // The dialog ships with the open attribute so it works without JS;
    // upgrade to showModal() for the backdrop + focus trap when we can.
    const modal = document.querySelector("[data-gcal-reminder-modal]");
    if (!modal) {
      return;
    }
    if (typeof modal.showModal === "function") {
      try {
        modal.removeAttribute("open");
        modal.showModal();
      } catch (_e) {
        modal.setAttribute("open", "");
      }
    }
    const dismiss = modal.querySelector("[data-gcal-reminder-dismiss]");
    if (dismiss) {
      dismiss.addEventListener("click", function () {
        // Dismiss saves nothing: events already default to the 10-minute
        // reminder, and the prompt returns on the next connect redirect only.
        modal.close ? modal.close() : modal.removeAttribute("open");
      });
    }
    // The save round-trips the server (settings write + sync flag + reload),
    // which can take a few seconds on production — acknowledge the click
    // immediately so it never feels like nothing happened.
    modal.querySelectorAll("form").forEach(function (form) {
      form.addEventListener("submit", function () {
        modal.querySelectorAll("button").forEach(function (b) {
          b.disabled = true;
        });
        const btn = form.querySelector(".gcal-cadence-btn");
        if (btn) {
          btn.classList.add("is-saving");
          const name = btn.querySelector(".gcal-cadence-name");
          if (name) {
            name.textContent = "Saving\u2026";
          }
        }
      });
    });
  }

  function initGuestStrip() {
    const strip = document.querySelector("[data-guest-strip]");
    if (!strip) {
      return;
    }
    const KEY = "cm-guest-strip-dismissed";
    try {
      if (sessionStorage.getItem(KEY) === "1") {
        strip.hidden = true;
        return;
      }
    } catch (_e) {
      /* ignore */
    }
    const dismiss = strip.querySelector("[data-guest-strip-dismiss]");
    if (dismiss) {
      dismiss.addEventListener("click", function () {
        strip.hidden = true;
        try {
          sessionStorage.setItem(KEY, "1");
        } catch (_e) {
          /* ignore */
        }
      });
    }
  }

  function bootInteraction() {
    syncRtcAnim();
    getDoneAudio();
    initHeadingReveal();
    initDoneInterceptor();
    initServerAffirmation();
    initExperienceControls();
    initPricing();
    initGuestStrip();
    initSlotsWhy();
    initCheckout();
    initFirstPaidSession();
    initGcalTimezone();
    initGcalReminderPrompt();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initLearn();
      initRevisionGuard();
      initBrowseArticle();
      initBrowseIndex();
      initExplainBack();
      initThemeToggle();
      bootInteraction();
    });
  } else {
    initLearn();
    initRevisionGuard();
    initBrowseArticle();
    initBrowseIndex();
    initExplainBack();
    initThemeToggle();
    bootInteraction();
  }

  function wordCount(text) {
    const trimmed = text.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  }

  function initExplainBack() {
    const root = document.querySelector("[data-gloss-article]");
    if (!root) {
      return;
    }
    const article = root.getAttribute("data-gloss-article");
    const input = root.querySelector("[data-gloss-input]");
    const meta = root.querySelector("[data-gloss-meta]");
    const clearBtn = root.querySelector("[data-gloss-clear]");
    if (!article || !input || !meta || !clearBtn) {
      return;
    }

    const emptyHint =
      "Saved automatically — rewrite it whenever your understanding sharpens.";
    let timer = null;
    let lastSaved = input.value;

    function renderMeta(text) {
      const n = wordCount(text);
      if (n === 0) {
        meta.textContent = emptyHint;
        clearBtn.hidden = true;
      } else {
        meta.textContent = n + " word" + (n === 1 ? "" : "s") + " · saved";
        clearBtn.hidden = false;
      }
    }

    function persist(text) {
      const trimmed = text.trim();
      if (!trimmed) {
        return fetch("/browse/article/" + encodeURIComponent(article) + "/gloss", {
          method: "DELETE",
        }).then(() => {
          lastSaved = "";
          renderMeta("");
        });
      }
      return fetch("/browse/article/" + encodeURIComponent(article) + "/gloss", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
      }).then((res) => {
        if (!res.ok) {
          throw new Error("save failed");
        }
        lastSaved = text;
        renderMeta(text);
      });
    }

    function scheduleSave() {
      if (timer) {
        clearTimeout(timer);
      }
      timer = setTimeout(() => {
        timer = null;
        const value = input.value;
        if (value === lastSaved) {
          renderMeta(value);
          return;
        }
        persist(value).catch(() => {
          meta.textContent = "Couldn’t save — try again.";
        });
      }, 500);
    }

    input.addEventListener("input", () => {
      const value = input.value;
      const n = wordCount(value);
      if (n === 0) {
        meta.textContent = emptyHint;
        clearBtn.hidden = true;
      } else {
        meta.textContent = n + " word" + (n === 1 ? "" : "s") + " · saving…";
        clearBtn.hidden = false;
      }
      scheduleSave();
    });

    clearBtn.addEventListener("click", () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      input.value = "";
      persist("").catch(() => {
        meta.textContent = "Couldn’t clear — try again.";
      });
    });
  }

  function initThemeToggle() {
    const btn = document.getElementById("theme-toggle");
    const KEY = "cm-theme";
    const CYCLE = ["auto", "dark", "light"];
    const LABELS = {
      auto: "◐ Auto",
      dark: "● Dark",
      light: "○ Light",
    };

    function systemDark() {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    function effective(pref) {
      if (pref === "dark") return "dark";
      if (pref === "light") return "light";
      return systemDark() ? "dark" : "light";
    }

    function persist(pref) {
      const body = new URLSearchParams();
      body.set("theme", pref);
      fetch("/api/theme", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      }).catch(() => {
        /* ignore */
      });
    }

    function syncSettingsButtons(pref) {
      document.querySelectorAll("[data-theme-set]").forEach((el) => {
        const on = el.getAttribute("data-theme-set") === pref;
        el.classList.toggle("is-active", on);
        el.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    function apply(pref) {
      const resolved = effective(pref);
      document.documentElement.setAttribute("data-theme", resolved);
      document.documentElement.setAttribute("data-theme-preference", pref);
      document.documentElement.style.colorScheme = resolved;
      if (btn) {
        btn.dataset.themePref = pref;
        btn.textContent = LABELS[pref] || LABELS.auto;
      }
      syncSettingsButtons(pref);
      try {
        localStorage.setItem(KEY, pref);
      } catch (_e) {
        /* ignore */
      }
    }

    let pref = (btn && btn.dataset.themePref) || "auto";
    try {
      const stored = localStorage.getItem(KEY);
      if (stored === "auto" || stored === "dark" || stored === "light") {
        pref = stored;
      }
    } catch (_e) {
      /* ignore */
    }
    apply(pref);

    if (btn) {
      btn.addEventListener("click", () => {
        const current = btn.dataset.themePref || "auto";
        const idx = CYCLE.indexOf(current);
        const next = CYCLE[(idx + 1) % CYCLE.length];
        apply(next);
        persist(next);
      });
    }

    document.querySelectorAll("[data-theme-set]").forEach((el) => {
      el.addEventListener("click", () => {
        const next = el.getAttribute("data-theme-set");
        if (next !== "auto" && next !== "dark" && next !== "light") {
          return;
        }
        apply(next);
        persist(next);
      });
    });

    if (window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = () => {
        const current = (btn && btn.dataset.themePref) || document.documentElement.getAttribute("data-theme-preference") || "auto";
        if (current === "auto") {
          apply("auto");
        }
      };
      if (typeof mq.addEventListener === "function") {
        mq.addEventListener("change", onChange);
      } else if (typeof mq.addListener === "function") {
        mq.addListener(onChange);
      }
    }
  }
})();
