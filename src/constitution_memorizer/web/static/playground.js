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

