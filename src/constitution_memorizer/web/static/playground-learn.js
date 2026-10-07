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
  const speechUrl = root.getAttribute("data-pg-speech-url") || "";
  const learnedUrl = root.getAttribute("data-pg-learned-url") || "";
  const masteredUrl = root.getAttribute("data-pg-mastered-url") || "";
  const workspaceUrl = root.getAttribute("data-pg-workspace") || "";
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

  const revision = root.getAttribute("data-pg-revision") || "";
  const rung = root.getAttribute("data-pg-rung") || "";

  function revisionFields() {
    const extra = {};
    if (revision) {
      extra.revision = 1;
      if (rung) {
        extra.rung_days = Number(rung);
      }
    }
    return extra;
  }

  function withRevisionHref(href) {
    if (!revision || !href) {
      return href;
    }
    return href + (href.indexOf("?") >= 0 ? "&" : "?") + "revision=1";
  }

  function postJson(url, payload) {
    const body = Object.assign({ csrf_token: csrf }, revisionFields(), payload || {});
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

  function showFail(message) {
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = message;
    }
  }

  function showDone(payload) {
    const allDone = payload && payload.all_methods_complete;
    const nextMode = payload && payload.next_mode;
    const completeLabel =
      (payload && payload.methods_complete_label) ||
      (allDone ? "6 of 6 methods complete" : "Done.");
    const completionHref = (payload && payload.completion_href) || "";
    const mastered = payload && payload.mastered;
    const isRevision = payload && payload.revision;
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = completeLabel;
    }
    if (feedback) {
      feedback.hidden = false;
      if (feedbackMsg) {
        feedbackMsg.textContent = completeLabel;
      }
      if (feedbackSub) {
        if (isRevision && payload.revision_next_line) {
          feedbackSub.textContent = payload.revision_next_line;
        } else if (allDone) {
          feedbackSub.textContent = isRevision
            ? "This revision rung is complete."
            : "Every method on this provision is complete.";
        } else {
          feedbackSub.textContent = "Continue to the next method when you are ready.";
        }
      }
      if (feedbackGo) {
        if (allDone && (!isRevision || mastered)) {
          const href =
            completionHref ||
            (mastered ? masteredUrl : learnedUrl);
          if (href) {
            feedbackGo.setAttribute("href", href);
            feedbackGo.textContent = mastered ? "Mastered, verbatim." : "Continue";
            window.location.assign(href);
            return;
          }
        }
        if (isRevision && allDone) {
          feedbackGo.setAttribute("href", workspaceUrl || feedbackGo.getAttribute("href"));
          feedbackGo.textContent = "Back to Act";
          return;
        }
        if (nextMode) {
          const href = withRevisionHref(
            completeUrl.replace(/\/learn\/[^/]+\/complete$/, "/learn/" + nextMode)
          );
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
      if (out.status === 409 && out.payload && out.payload.error === "stale_revision") {
        showFail("This revision already moved on. Refresh to continue.");
        return out;
      }
      if (out.status === 409 && out.payload && out.payload.error === "not_due") {
        showFail("This revision is not due yet.");
        return out;
      }
      if (out.status === 400 && out.payload && out.payload.error === "not_selected") {
        showFail("This provision is not in your selection.");
        return out;
      }
      if (out.ok && out.payload && out.payload.ok) {
        showDone(out.payload);
      } else {
        showFail("Could not save this method yet.");
      }
      return out;
    }).catch(function () {
      showFail("Could not save this method yet.");
    });
  }

  function speechClient() {
    return window.RecallSpeech || null;
  }

  function transcribeSpeech(opts) {
    const Speech = speechClient();
    if (!Speech || !Speech.transcribe || !speechUrl) {
      return Promise.reject(Object.assign(new Error("speech-failed"), { code: "unavailable" }));
    }
    return Speech.transcribe(
      Object.assign(
        {
          url: speechUrl,
          csrf: csrf,
          mode: mode,
        },
        opts || {}
      )
    );
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
    const status = panel.querySelector("[data-letters-status]");
    let full = false;
    let recorder = null;
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
    function setStatus(text) {
      if (status) {
        status.hidden = false;
        status.textContent = text;
      }
    }
    if (speakBtn) {
      speakBtn.addEventListener("click", function () {
        markStarted();
        const Speech = speechClient();
        if (!Speech || !Speech.isSupported || !Speech.isSupported() || !speechUrl) {
          setStatus("Microphone unavailable. Use the typed path.");
          return;
        }
        if (recorder) {
          const handle = recorder;
          recorder = null;
          speakBtn.textContent = "▸ Speak it";
          handle.stop().then(function (blob) {
            return transcribeSpeech({ blob: blob, mode: "letters", fromIndex: 0 });
          }).then(function (payload) {
            const hits = (payload.alignment || []).filter(function (row) {
              return row.status === "match";
            }).length;
            setStatus("Matched " + hits + " word" + (hits === 1 ? "" : "s") + ".");
          }).catch(function (err) {
            const code = err && err.code ? err.code : "";
            if (code === "unavailable" || code === "rate_limited" || code === "provider_error") {
              setStatus("Speech recognition is unavailable. Type the words instead.");
            } else {
              setStatus("I didn't catch that. Type the words instead.");
            }
          });
          return;
        }
        Speech.startRecording().then(function (handle) {
          recorder = handle;
          speakBtn.textContent = "Stop";
          setStatus("Listening… tap Stop when you finish.");
        }).catch(function () {
          setStatus("Microphone unavailable. Use the typed path.");
        });
      });
    }
    const check = panel.querySelector("[data-letters-check-text]");
    if (check) {
      check.addEventListener("click", function () {
        markStarted();
        const manual = panel.querySelector("[data-letters-manual]");
        const typed = manual ? manual.value : "";
        transcribeSpeech({ text: typed, mode: "letters", fromIndex: 0 }).then(function (payload) {
          const hits = (payload.alignment || []).filter(function (row) {
            return row.status === "match";
          }).length;
          setStatus("Matched " + hits + " word" + (hits === 1 ? "" : "s") + ".");
        }).catch(function () {
          setStatus("Could not check those words yet.");
        });
      });
    }
    render();
    if (fallback) {
      fallback.hidden = false;
    }
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

  function renderReciteMap(panel, alignment) {
    const map = panel.querySelector("[data-recite-map]");
    const stats = panel.querySelector("[data-recite-stats]");
    const completeBtn = panel.querySelector("[data-pg-complete]");
    const sourceWords = alignment.source_words || [];
    const hitSet = {};
    (alignment.hit_indices || []).forEach(function (index) {
      hitSet[index] = true;
    });
    if (stats) {
      stats.hidden = false;
      stats.textContent = alignment.stats_label || (alignment.percent + "%");
    }
    if (map) {
      map.hidden = false;
      map.replaceChildren();
      sourceWords.forEach(function (word, index) {
        const span = document.createElement("span");
        span.textContent = word + " ";
        span.className = hitSet[index] ? "is-hit" : "is-miss";
        map.appendChild(span);
      });
    }
    if (completeBtn) {
      completeBtn.hidden = false;
    }
  }

  function initRecite(panel) {
    const toggle = panel.querySelector("[data-recite-toggle]");
    const peek = panel.querySelector("[data-recite-peek]");
    const blur = panel.querySelector("[data-recite-blur]");
    const check = panel.querySelector("[data-recite-check]");
    const manual = panel.querySelector("[data-recite-manual]");
    const status = panel.querySelector("[data-recite-status]");
    let recorder = null;

    function setStatus(text) {
      if (status) {
        status.hidden = false;
        status.textContent = text;
      }
    }

    if (toggle) {
      toggle.addEventListener("click", function () {
        markStarted();
        const Speech = speechClient();
        if (!Speech || !Speech.isSupported || !Speech.isSupported() || !speechUrl) {
          setStatus("Microphone unavailable. Use the typed fallback.");
          if (manual) {
            manual.focus();
          }
          return;
        }
        if (recorder) {
          const handle = recorder;
          recorder = null;
          toggle.textContent = "▸ Start reciting";
          handle.stop().then(function (blob) {
            return transcribeSpeech({ blob: blob, mode: "recite" });
          }).then(function (payload) {
            if (payload.alignment && !Array.isArray(payload.alignment)) {
              renderReciteMap(panel, payload.alignment);
            } else {
              setStatus("Recited. Mark Recite done when you are ready.");
              const completeBtn = panel.querySelector("[data-pg-complete]");
              if (completeBtn) {
                completeBtn.hidden = false;
              }
            }
          }).catch(function (err) {
            const code = err && err.code ? err.code : "";
            if (code === "unavailable" || code === "rate_limited" || code === "provider_error") {
              setStatus("Speech recognition is unavailable. Type what you recited.");
            } else {
              setStatus("I didn't catch that. Type what you recited.");
            }
          });
          return;
        }
        Speech.startRecording().then(function (handle) {
          recorder = handle;
          toggle.textContent = "Stop";
          setStatus("Listening… tap Stop for your accuracy map.");
        }).catch(function () {
          setStatus("Microphone unavailable. Use the typed fallback.");
          if (manual) {
            manual.focus();
          }
        });
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
        const spoken = manual ? manual.value : "";
        transcribeSpeech({ text: spoken, mode: "recite" }).then(function (payload) {
          if (payload.alignment && !Array.isArray(payload.alignment)) {
            renderReciteMap(panel, payload.alignment);
          }
        }).catch(function () {
          setStatus("Could not score that recitation yet.");
        });
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
        showFail("Answer every question to finish Test.");
        return;
      }
      const cycle = Number(root.getAttribute("data-pg-cycle") || "0");
      postJson(quizUrl, { cycle: cycle, answers: answers }).then(function (out) {
        if (out.status === 409 && out.payload && out.payload.error === "stale_revision") {
          showFail("This revision already moved on. Refresh to continue.");
          return;
        }
        if (out.status === 409) {
          showFail("This quiz expired. Refresh for a new checkpoint.");
          return;
        }
        if (out.ok && out.payload && out.payload.ok) {
          showDone(out.payload);
          if (out.payload.total) {
            showFail("Score " + out.payload.correct + " of " + out.payload.total + ".");
          }
        } else {
          showFail("Could not grade this Test yet.");
        }
      }).catch(function () {
        showFail("Could not grade this Test yet.");
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
