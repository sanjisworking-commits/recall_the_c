(function () {
  const DENSITY_THRESH = { light: 8, medium: 6, heavy: 4 };

  function letterLen(word) {
    return word.replace(/[^A-Za-z]/g, "").length;
  }

  function initPlaygroundCloze(panel, onComplete) {
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
      if (blanks.length === 0) {
        return;
      }
      if (blanks.every((index) => tapRevealed.has(index))) {
        completed = true;
        if (onComplete) {
          onComplete({
            recalled: tapRevealed.size,
            total: blanks.length,
            revealed: source,
          });
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

    let justRevealed = null;

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
            if (index === justRevealed) {
              span.classList.add("is-new");
            }
            span.removeAttribute("tabindex");
            span.removeAttribute("role");
            span.removeAttribute("aria-label");
          } else {
            const reveal = () => {
              revealed.add(index);
              tapRevealed.add(index);
              justRevealed = index;
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
      justRevealed = null;
      updateStatus();
    }

    function setDensity(next) {
      if (!DENSITY_THRESH[next]) {
        return;
      }
      density = next;
      panel.setAttribute("data-cloze-density", next);
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
    return { source };
  }

  document.querySelectorAll("[data-playground-cloze]").forEach(function (panel) {
    const status = document.querySelector("[data-playground-complete-status]");
    initPlaygroundCloze(panel, function (result) {
      const url = panel.getAttribute("data-complete-url");
      if (!url) {
        return;
      }
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (out) {
          if (!status) {
            return;
          }
          status.hidden = false;
          if (out.ok && out.payload && out.payload.revealed === result.revealed) {
            status.textContent = "Cloze saved. Revealed text matches the Bare Act.";
          } else if (out.ok) {
            status.textContent = "Cloze saved.";
          } else {
            status.textContent = "Could not save this Cloze yet.";
          }
        })
        .catch(function () {
          if (status) {
            status.hidden = false;
            status.textContent = "Could not save this Cloze yet.";
          }
        });
    });
  });
})();
