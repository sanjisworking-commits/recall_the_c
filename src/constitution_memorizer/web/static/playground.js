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

(function () {
  function syncVerbatim(block) {
    var open = block.getAttribute("data-open") !== "false";
    var btn = block.querySelector("[data-verbatim-toggle]");
    var quote = block.querySelector("blockquote");
    if (quote) {
      quote.hidden = !open;
    }
    if (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "Hide verbatim text" : "Show verbatim text";
    }
  }

  document.querySelectorAll("[data-verbatim]").forEach(function (block) {
    syncVerbatim(block);
    var btn = block.querySelector("[data-verbatim-toggle]");
    if (!btn) {
      return;
    }
    btn.addEventListener("click", function () {
      var open = block.getAttribute("data-open") !== "false";
      block.setAttribute("data-open", open ? "false" : "true");
      syncVerbatim(block);
    });
  });

  function syncGroup(group) {
    var article = group.closest("[data-rollover-candidate]");
    var selected = "";
    group.querySelectorAll("label").forEach(function (label) {
      var input = label.querySelector("input");
      var on = Boolean(input && input.checked);
      label.classList.toggle("is-selected", on);
      if (on && input) {
        selected = input.value;
      }
    });
    if (article) {
      article.setAttribute("data-rollover-decision", selected || "undecided");
    }
  }

  function updateKeepAvailability(form) {
    var limitAttr = form.getAttribute("data-limit");
    if (limitAttr === "" || limitAttr === null) {
      return;
    }
    var limit = Number(limitAttr);
    var keepChecked = 0;
    form.querySelectorAll('input[type="radio"][value="keep"]:checked').forEach(function () {
      keepChecked += 1;
    });
    var month = form.getAttribute("data-month") || "This month";
    form.querySelectorAll("[data-rollover-candidate]").forEach(function (article) {
      var keep = article.querySelector('input[type="radio"][value="keep"]');
      if (!keep) {
        return;
      }
      if (keep.disabled && keep.getAttribute("data-server-disabled") === "true") {
        return;
      }
      if (keep.disabled && !keep.hasAttribute("data-init")) {
        keep.setAttribute("data-server-disabled", "true");
        return;
      }
      keep.setAttribute("data-init", "true");
      var allow = keep.checked || keepChecked < limit;
      keep.disabled = !allow;
      var hint = article.querySelector("[data-keep-full]");
      if (!keep.checked && keep.disabled) {
        if (!hint) {
          hint = document.createElement("p");
          hint.className = "pg-lede";
          hint.setAttribute("data-keep-full", "true");
          hint.textContent = month + " is full. Remove another law to keep this one.";
          article.appendChild(hint);
        }
      } else if (hint) {
        hint.remove();
      }
    });
  }

  document.querySelectorAll("[data-rollover-form]").forEach(function (form) {
    form.querySelectorAll('[role="radiogroup"]').forEach(function (group) {
      syncGroup(group);
      group.addEventListener("change", function () {
        syncGroup(group);
        updateKeepAvailability(form);
      });
    });
  });

  function focusables(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    ).filter(function (el) {
      return !el.disabled && el.offsetParent !== null;
    });
  }

  function enhanceSheets() {
    var dialog = document.querySelector("dialog.pg-sheet");
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.className = "pg-sheet";
      dialog.setAttribute("aria-modal", "true");
      document.body.appendChild(dialog);
    }
    document.addEventListener("click", function (event) {
      var link = event.target.closest("[data-pg-sheet]");
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      if (link.getAttribute("href") === "#") {
        return;
      }
      event.preventDefault();
      var href = link.getAttribute("href");
      fetch(href, { credentials: "same-origin", headers: { Accept: "text/html" } })
        .then(function (response) {
          return response.text().then(function (html) {
            return { ok: response.ok, html: html, url: response.url };
          });
        })
        .then(function (out) {
          if (!out.ok) {
            window.location.href = href;
            return;
          }
          var parsed = document.createElement("div");
          parsed.innerHTML = out.html;
          var panel = parsed.querySelector(".pg-sheet-panel");
          if (!panel) {
            window.location.href = href;
            return;
          }
          dialog.replaceChildren(panel);
          if (typeof dialog.showModal === "function") {
            dialog.showModal();
          } else {
            window.location.href = href;
            return;
          }
          var nodes = focusables(dialog);
          if (nodes[0]) {
            nodes[0].focus();
          }
        })
        .catch(function () {
          window.location.href = href;
        });
    });
    dialog.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        dialog.close();
      }
      if (event.key !== "Tab") {
        return;
      }
      var nodes = focusables(dialog);
      if (!nodes.length) {
        return;
      }
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  }

  enhanceSheets();
})();

