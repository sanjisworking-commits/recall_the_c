(function () {
  const root = document.querySelector("[data-pg-learn]");
  if (!root) {
    return;
  }

  const DENSITY_THRESH = { light: 8, medium: 6, heavy: 4 };
  const csrf = root.getAttribute("data-pg-csrf") || "";
  const completeUrl = root.getAttribute("data-pg-complete-url") || "";
  const startUrl = root.getAttribute("data-pg-start-url") || "";
  const quizUrl = root.getAttribute("data-pg-quiz-url") || "";
  const mode = root.getAttribute("data-pg-mode") || "";
  const statusEl = root.querySelector("[data-pg-complete-status]");
  const feedback = root.querySelector("[data-pg-feedback]");
  const feedbackMsg = root.querySelector("[data-pg-feedback-msg]");
  const feedbackSub = root.querySelector("[data-pg-feedback-sub]");
  const feedbackGo = root.querySelector("[data-pg-feedback-go]");
  let started = false;

  function letterLen(word) {
    return word.replace(/[^A-Za-z]/g, "").length;
  }

  function postJson(url, payload) {
    const body = Object.assign({ csrf_token: csrf }, payload || {});
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      },
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, payload: data };
      });
    });
  }

  function markStarted() {
    if (started || !startUrl) {
      return;
    }
    started = true;
    postJson(startUrl, {}).catch(function () {
      started = false;
    });
  }

  function showDone(payload) {
    const allDone = payload && payload.all_methods_complete;
    const nextMode = payload && payload.next_mode;
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = allDone ? "6 of 6 methods complete" : "Done.";
    }
    if (feedback) {
      feedback.hidden = false;
      if (feedbackMsg) {
        feedbackMsg.textContent = allDone ? "6 of 6 methods complete" : "Done";
      }
      if (feedbackSub) {
        feedbackSub.textContent = allDone
          ? "Every method on this provision is complete."
          : "Continue to the next method when you are ready.";
      }
      if (feedbackGo) {
        if (nextMode) {
          const href = completeUrl.replace(/\/learn\/[^/]+\/complete$/, "/learn/" + nextMode);
          feedbackGo.setAttribute("href", href);
          feedbackGo.textContent = "Next method";
        } else {
          feedbackGo.textContent = "Continue";
        }
      }
    }
  }

  function completeMode(extra) {
    if (!completeUrl) {
      return Promise.resolve();
    }
    return postJson(completeUrl, extra || {}).then(function (out) {
      if (out.ok && out.payload && out.payload.ok) {
        showDone(out.payload);
      } else if (statusEl) {
        statusEl.hidden = false;
        statusEl.textContent = "Could not save this method yet.";
      }
      return out;
    }).catch(function () {
      if (statusEl) {
        statusEl.hidden = false;
        statusEl.textContent = "Could not save this method yet.";
      }
    });
  }

  root.querySelectorAll("[data-pg-complete]").forEach(function (button) {
    button.addEventListener("click", function () {
      completeMode();
    });
  });

  function initCloze(panel) {
    const textEl = panel.querySelector(".learn-cloze-text");
    if (!textEl) {
      return;
    }
    const status = panel.querySelector("[data-cloze-status]");
    const densityBtns = panel.querySelectorAll("[data-cloze-density]");
    const source = panel.getAttribute("data-cloze-text") || "";
    const words = source.trim() ? source.trim().split(/\s+/) : [];
    let density = panel.getAttribute("data-cloze-density") || "medium";
    const revealed = new Set();
    const tapRevealed = new Set();
    let completed = false;

    function threshold() {
      return DENSITY_THRESH[density] || 6;
    }
    function isBlank(word) {
      return letterLen(word) >= threshold();
    }
    function checkTapComplete() {
      if (completed) {
        return;
      }
      const blanks = [];
      words.forEach(function (word, index) {
        if (isBlank(word)) {
          blanks.push(index);
        }
      });
      if (blanks.length === 0) {
        return;
      }
      if (blanks.every(function (index) { return tapRevealed.has(index); })) {
        completed = true;
        completeMode();
      }
    }
    function render() {
      textEl.replaceChildren();
      let hidden = 0;
      let shown = 0;
      words.forEach(function (word, index) {
        const span = document.createElement("span");
        span.className = "learn-cloze-word";
        span.textContent = word + " ";
        if (isBlank(word)) {
          hidden += 1;
          span.classList.add("is-blank");
          span.setAttribute("role", "button");
          span.setAttribute("tabindex", "0");
          span.setAttribute("aria-label", "Reveal hidden word");
          if (revealed.has(index)) {
            shown += 1;
            span.classList.add("is-revealed");
            span.removeAttribute("tabindex");
            span.removeAttribute("role");
          } else {
            const reveal = function () {
              markStarted();
              revealed.add(index);
              tapRevealed.add(index);
              render();
              checkTapComplete();
            };
            span.addEventListener("click", reveal);
            span.addEventListener("keydown", function (event) {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                reveal();
              }
            });
          }
        }
        textEl.appendChild(span);
      });
      if (status) {
        status.textContent = shown + " of " + hidden + " revealed — tap a blank";
      }
    }
    densityBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const next = btn.getAttribute("data-cloze-density");
        if (!DENSITY_THRESH[next]) {
          return;
        }
        density = next;
        revealed.clear();
        tapRevealed.clear();
        densityBtns.forEach(function (other) {
          const active = other.getAttribute("data-cloze-density") === next;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-pressed", active ? "true" : "false");
        });
        render();
      });
    });
    const toggleAll = panel.querySelector('[data-cloze-action="toggle-all"]');
    if (toggleAll) {
      toggleAll.addEventListener("click", function () {
        const blanks = [];
        words.forEach(function (word, index) {
          if (isBlank(word)) {
            blanks.push(index);
          }
        });
        const allShown = blanks.length > 0 && blanks.every(function (i) { return revealed.has(i); });
        if (allShown) {
          revealed.clear();
          toggleAll.textContent = "Reveal all";
        } else {
          blanks.forEach(function (i) { revealed.add(i); });
          toggleAll.textContent = "Hide again";
        }
        render();
      });
    }
    render();
  }

  function initials(text) {
    return String(text || "")
      .split(/\s+/)
      .filter(Boolean)
      .map(function (word) {
        const match = word.match(/[A-Za-z]/);
        return match ? match[0] : word.slice(0, 1);
      })
      .join(" ");
  }

  function initLetters(panel) {
    const source = panel.getAttribute("data-letters-text") || "";
    const display = panel.querySelector("[data-letters-display]");
    const toggle = panel.querySelector("[data-letters-toggle]");
    const fallback = panel.querySelector("[data-letters-fallback]");
    const speakBtn = panel.querySelector("[data-letters-speak]");
    let full = false;
    function render() {
      if (!display) {
        return;
      }
      display.textContent = full ? source : initials(source);
      display.classList.toggle("is-initials", !full);
      if (toggle) {
        toggle.textContent = full ? "First letters" : "Full text";
      }
    }
    if (toggle) {
      toggle.addEventListener("click", function () {
        markStarted();
        full = !full;
        render();
      });
    }
    panel.querySelectorAll("[data-letters-view-set]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const view = btn.getAttribute("data-letters-view-set");
        panel.querySelectorAll("[data-letters-view-set]").forEach(function (other) {
          const active = other === btn;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (view === "plain") {
          full = false;
          render();
        }
      });
    });
    function showFallback() {
      if (fallback) {
        fallback.hidden = false;
      }
    }
    if (speakBtn) {
      speakBtn.addEventListener("click", function () {
        markStarted();
        const Speech = window.SpeechClient;
        if (!Speech || !Speech.isSupported || !Speech.isSupported()) {
          showFallback();
          return;
        }
        showFallback();
      });
    }
    const check = panel.querySelector("[data-letters-check-text]");
    if (check) {
      check.addEventListener("click", function () {
        markStarted();
        const status = panel.querySelector("[data-letters-status]");
        if (status) {
          status.hidden = false;
          status.textContent = "Checked against first letters.";
        }
      });
    }
    render();
  }

  function initType(panel) {
    const source = panel.getAttribute("data-type-text") || "";
    const input = panel.querySelector("[data-type-input]");
    const stats = panel.querySelector("[data-type-count]");
    const completeBtn = panel.querySelector("[data-pg-complete]");
    const checkBtn = panel.querySelector("[data-type-check]");
    const align = window.RecallAlign && window.RecallAlign.alignText;
    if (!input) {
      return;
    }
    function update() {
      markStarted();
      const typed = input.value || "";
      const words = source.trim().split(/\s+/).filter(Boolean);
      if (!align) {
        if (stats) {
          stats.textContent = typed.trim().split(/\s+/).filter(Boolean).length + " of " + words.length + " words";
        }
        return;
      }
      const result = align(source, typed);
      if (stats) {
        stats.textContent = result.hits + " of " + result.total + " words · " + result.percent + "%";
      }
      if (completeBtn && result.total && result.hits === result.total) {
        completeBtn.hidden = false;
      }
    }
    input.addEventListener("input", update);
    if (checkBtn) {
      checkBtn.addEventListener("click", function () {
        update();
        if (completeBtn) {
          completeBtn.hidden = false;
        }
      });
    }
  }

  function initRecite(panel) {
    const source = panel.getAttribute("data-recite-text") || "";
    const map = panel.querySelector("[data-recite-map]");
    const stats = panel.querySelector("[data-recite-stats]");
    const completeBtn = panel.querySelector("[data-pg-complete]");
    const toggle = panel.querySelector("[data-recite-toggle]");
    const peek = panel.querySelector("[data-recite-peek]");
    const blur = panel.querySelector("[data-recite-blur]");
    const check = panel.querySelector("[data-recite-check]");
    const manual = panel.querySelector("[data-recite-manual]");
    const align = window.RecallAlign && window.RecallAlign.alignText;

    function showMap(spoken) {
      if (!align) {
        if (completeBtn) {
          completeBtn.hidden = false;
        }
        return;
      }
      const result = align(source, spoken || "");
      if (stats) {
        stats.hidden = false;
        stats.textContent = result.statsLabel || result.percent + "%";
      }
      if (map) {
        map.hidden = false;
        map.replaceChildren();
        result.sourceWords.forEach(function (word, index) {
          const span = document.createElement("span");
          span.textContent = word + " ";
          span.className = result.hitIndices.has(index) ? "is-hit" : "is-miss";
          map.appendChild(span);
        });
      }
      if (completeBtn) {
        completeBtn.hidden = false;
      }
    }

    if (toggle) {
      toggle.addEventListener("click", function () {
        markStarted();
        const Speech = window.SpeechClient;
        if (!Speech || !Speech.isSupported || !Speech.isSupported()) {
          const status = panel.querySelector("[data-recite-status]");
          if (status) {
            status.hidden = false;
            status.textContent = "Microphone unavailable. Use the typed fallback.";
          }
          if (manual) {
            manual.focus();
          }
          return;
        }
        const status = panel.querySelector("[data-recite-status]");
        if (status) {
          status.hidden = false;
          status.textContent = "Listening… use the typed fallback if speech is blocked.";
        }
      });
    }
    if (peek && blur) {
      function down() {
        blur.classList.remove("is-blurred");
      }
      function up() {
        blur.classList.add("is-blurred");
      }
      peek.addEventListener("mousedown", down);
      peek.addEventListener("mouseup", up);
      peek.addEventListener("mouseleave", up);
      peek.addEventListener("keydown", function (event) {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          down();
        }
      });
      peek.addEventListener("keyup", up);
    }
    if (check) {
      check.addEventListener("click", function () {
        markStarted();
        showMap(manual ? manual.value : "");
      });
    }
  }

  function initTest(panel) {
    const form = panel.querySelector("[data-pg-quiz-form]");
    if (!form) {
      return;
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const fields = panel.querySelectorAll("[data-quiz-q]");
      const answers = [];
      let complete = true;
      fields.forEach(function (field) {
        const kind = field.getAttribute("data-kind");
        if (kind === "mcq") {
          const picked = field.querySelector("input[type='radio']:checked");
          if (!picked) {
            complete = false;
            answers.push(null);
          } else {
            answers.push(Number(picked.value));
          }
        } else {
          const fill = field.querySelector("[data-quiz-fill]");
          const value = fill ? fill.value : "";
          if (!String(value || "").trim()) {
            complete = false;
          }
          answers.push(value || "");
        }
      });
      if (!complete) {
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = "Answer every question to finish Test.";
        }
        return;
      }
      const cycle = Number(root.getAttribute("data-pg-cycle") || "0");
      postJson(quizUrl, { cycle: cycle, answers: answers }).then(function (out) {
        if (out.status === 409) {
          if (statusEl) {
            statusEl.hidden = false;
            statusEl.textContent = "This quiz expired. Refresh for a new checkpoint.";
          }
          return;
        }
        if (out.ok && out.payload && out.payload.ok) {
          showDone(out.payload);
          if (statusEl && out.payload.total) {
            statusEl.hidden = false;
            statusEl.textContent =
              "Score " + out.payload.correct + " of " + out.payload.total + ".";
          }
        } else if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = "Could not grade this Test yet.";
        }
      }).catch(function () {
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = "Could not grade this Test yet.";
        }
      });
    });
  }

  const cloze = root.querySelector('[data-pg-learn-panel="cloze"]');
  if (cloze) {
    initCloze(cloze);
  }
  const letters = root.querySelector('[data-pg-learn-panel="letters"]');
  if (letters) {
    initLetters(letters);
  }
  const typePanel = root.querySelector('[data-pg-learn-panel="type"]');
  if (typePanel) {
    initType(typePanel);
  }
  const recite = root.querySelector('[data-pg-learn-panel="recite"]');
  if (recite) {
    initRecite(recite);
  }
  const testPanel = root.querySelector('[data-pg-learn-panel="test"]');
  if (testPanel) {
    initTest(testPanel);
  }

  if (mode === "read") {
    /* GET must not complete Read. Mark as read is explicit. */
  }
})();
