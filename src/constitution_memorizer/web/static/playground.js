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

  function rolloverActionLabel(form) {
    var unresolved = false;
    var seen = false;
    form.querySelectorAll("[data-rollover-candidate]").forEach(function (article) {
      seen = true;
      var checked = article.querySelector('input[type="radio"]:checked');
      var value = checked
        ? checked.value
        : (article.getAttribute("data-rollover-decision") || "undecided");
      if (value !== "keep" && value !== "decline") {
        unresolved = true;
      }
    });
    if (!seen) {
      return "Done";
    }
    return unresolved ? "Continue with these" : "Done";
  }

  function syncRolloverAction(form) {
    var root = form.closest(".RolloverPlanner") || document;
    var label = rolloverActionLabel(form);
    root.querySelectorAll("[data-rollover-submit]").forEach(function (btn) {
      btn.textContent = label;
    });
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
        syncRolloverAction(form);
      });
    });
    syncRolloverAction(form);
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
    var lastOpener = null;
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.className = "pg-sheet";
      dialog.setAttribute("data-pg-sheet-host", "");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("role", "dialog");
      document.body.appendChild(dialog);
    } else {
      dialog.setAttribute("data-pg-sheet-host", "");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("role", "dialog");
    }

    // Immediate feedback while the sheet is fetched: the trigger announces
    // itself busy and reads "Opening…" until the dialog is shown or the
    // request falls back to a plain navigation. The href is untouched, so
    // the link still works as a link.
    function setOpening(trigger, on) {
      if (on) {
        if (!trigger.hasAttribute("data-pg-label")) {
          trigger.setAttribute("data-pg-label", trigger.textContent);
        }
        trigger.setAttribute("aria-busy", "true");
        trigger.classList.add("is-opening");
        trigger.textContent = "Opening\u2026";
      } else {
        trigger.removeAttribute("aria-busy");
        trigger.classList.remove("is-opening");
        if (trigger.hasAttribute("data-pg-label")) {
          trigger.textContent = trigger.getAttribute("data-pg-label");
          trigger.removeAttribute("data-pg-label");
        }
      }
    }

    function ensureCloseButton(panel) {
      if (panel.querySelector(".pg-sheet-close")) {
        return;
      }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pg-sheet-close";
      btn.setAttribute("data-pg-sheet-close", "");
      btn.setAttribute("aria-label", "Close");
      btn.textContent = "\u2715";
      panel.insertBefore(btn, panel.firstChild);
    }

    // One dialog landmark: the host <dialog> owns role/aria-modal/label, so a
    // panel lifted into it must not announce a second modal dialog.
    function demoteToPanel(panel) {
      panel.removeAttribute("role");
      panel.removeAttribute("aria-modal");
      panel.removeAttribute("aria-labelledby");
    }

    function visibleHeading(panel) {
      var headings = panel.querySelectorAll("h1, h2");
      for (var i = 0; i < headings.length; i += 1) {
        if (headings[i].offsetParent !== null) {
          return headings[i];
        }
      }
      return headings[0] || panel.querySelector("[id]");
    }

    function labelledBy(panel) {
      var heading = visibleHeading(panel);
      if (heading) {
        if (!heading.id) {
          heading.id = "pg-sheet-title";
        }
        dialog.setAttribute("aria-labelledby", heading.id);
      }
    }
    dialog.addEventListener("pg-sheet:relabel", function () {
      var panel = dialog.querySelector(".pg-sheet-panel");
      if (panel) {
        labelledBy(panel);
      }
    });

    document.addEventListener("click", function (event) {
      var closeBtn = event.target.closest("[data-pg-sheet-close]");
      if (closeBtn && dialog.contains(closeBtn)) {
        event.preventDefault();
        dialog.close();
        return;
      }
      var link = event.target.closest("[data-pg-sheet]");
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      if (link.getAttribute("href") === "#") {
        return;
      }
      event.preventDefault();
      // One request per trigger: a second click while the sheet is being
      // fetched does nothing (the first request will open it).
      if (link.getAttribute("aria-busy") === "true") {
        return;
      }
      var href = link.getAttribute("href");
      lastOpener = link;
      setOpening(link, true);
      fetch(href, { credentials: "same-origin", headers: { Accept: "text/html", "X-Requested-With": "pg-sheet" } })
        .then(function (response) {
          return response.text().then(function (html) {
            return { ok: response.ok, html: html, url: response.url };
          });
        })
        .then(function (out) {
          if (!out.ok) {
            setOpening(link, false);
            window.location.href = href;
            return;
          }
          var parsed = document.createElement("div");
          parsed.innerHTML = out.html;
          var panel = parsed.querySelector(".pg-sheet-panel");
          if (!panel) {
            setOpening(link, false);
            window.location.href = href;
            return;
          }
          ensureCloseButton(panel);
          demoteToPanel(panel);
          dialog.replaceChildren(panel);
          if (typeof dialog.showModal === "function") {
            dialog.showModal();
          } else {
            setOpening(link, false);
            window.location.href = href;
            return;
          }
          setOpening(link, false);
          // Label after the panel is attached and shown: a detached heading
          // has no offsetParent, so a panel that opens at the scope step
          // (confirmation skipped) would otherwise take the hidden heading.
          labelledBy(panel);
          var nodes = focusables(dialog);
          if (nodes[0]) {
            nodes[0].focus();
          }
        })
        .catch(function () {
          setOpening(link, false);
          window.location.href = href;
        });
    });
    // M2-R (D6): the Add flow swaps a freshly fetched panel into the open
    // dialog (Retry re-reads the state) without closing and re-opening it.
    dialog.addEventListener("pg-sheet:swap", function (event) {
      var panel = event.detail && event.detail.panel;
      if (!panel) {
        return;
      }
      ensureCloseButton(panel);
      demoteToPanel(panel);
      dialog.replaceChildren(panel);
      labelledBy(panel);
      var nodes = focusables(dialog);
      if (nodes[0]) {
        nodes[0].focus();
      }
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
    dialog.addEventListener("close", function () {
      dialog.removeAttribute("aria-labelledby");
      if (lastOpener && typeof lastOpener.focus === "function") {
        lastOpener.focus();
      }
      lastOpener = null;
      // A dialog the server opened (direct URL) closes back onto the Act it
      // was drawn over: same page, the Act's own address.
      var back = dialog.getAttribute("data-pg-sheet-return");
      if (back && window.history && typeof window.history.replaceState === "function") {
        window.history.replaceState(null, "", back);
        dialog.removeAttribute("data-pg-sheet-return");
      }
    });

    // Direct URL: the panel is already in the document inside an open
    // <dialog>. Re-open it as a modal so the scrim, focus trap and Escape
    // behave exactly as for an in-page open.
    var served = dialog.querySelector(".pg-sheet-panel");
    if (served && dialog.hasAttribute("data-pg-sheet-direct")) {
      ensureCloseButton(served);
      demoteToPanel(served);
      if (typeof dialog.showModal === "function") {
        // Drop the server's `open` attribute without close(): close() would
        // queue the dismissal handler, which strips the label and rewrites
        // the URL while the modal is still showing.
        if (dialog.open) {
          dialog.removeAttribute("open");
        }
        dialog.showModal();
        labelledBy(served);
        var first = focusables(dialog);
        if (first[0]) {
          first[0].focus();
        }
      }
    }
  }

  // M2R-F03 (D6): the scope step posts from inside the open dialog and
  // reports a failed save in place, with the server's own verdict — the
  // choice is never consumed twice because Retry re-reads the state rather
  // than re-posting the form.
  function addFailureCopy(outcome, name) {
    if (outcome === "rolled_back") {
      return "Couldn\u2019t add " + name + ". Nothing was changed.";
    }
    return (
      "We couldn\u2019t confirm this save \u2014 the connection failed before Playground answered. " +
      name + " may or may not have been added; check Playground before trying again."
    );
  }

  function showAddFailure(root, outcome) {
    var box = root.querySelector("[data-pg-add-alert]");
    if (!box) {
      return false;
    }
    var name = root.getAttribute("data-pg-law-name") || "this law";
    box.replaceChildren();
    var text = document.createElement("p");
    text.className = "pg-add-alert-text";
    text.textContent = addFailureCopy(outcome, name);
    var actions = document.createElement("div");
    actions.className = "pg-add-alert-actions";
    var retry = document.createElement("button");
    retry.type = "button";
    retry.className = "pg-add-alert-btn";
    retry.setAttribute("data-pg-add-retry", outcome);
    retry.textContent = outcome === "rolled_back" ? "Retry" : "Check and retry";
    actions.appendChild(retry);
    if (outcome !== "rolled_back") {
      var open = document.createElement("a");
      open.className = "pg-add-alert-link";
      open.href = "/playground";
      open.textContent = "Open Playground";
      actions.appendChild(open);
    }
    box.appendChild(text);
    box.appendChild(actions);
    box.setAttribute("data-outcome", outcome);
    box.hidden = false;
    retry.focus();
    return true;
  }

  function swapOrNavigate(root, html, url) {
    var host = root.closest("dialog");
    var parsed = document.createElement("div");
    parsed.innerHTML = html;
    var panel = parsed.querySelector(".pg-sheet-panel");
    if (panel && host) {
      panel.classList.add("is-enhanced");
      host.dispatchEvent(new CustomEvent("pg-sheet:swap", { detail: { panel: panel } }));
      return;
    }
    window.location.assign(url);
  }

  // Retry re-reads: GET the Add sheet again (the server redirects to the law
  // when the save did commit) and swap it in at the scope step.
  function rereadAddSheet(root) {
    var action = root.getAttribute("data-pg-add-action") || "";
    if (!action) {
      window.location.reload();
      return;
    }
    var sep = action.indexOf("?") >= 0 ? "&" : "?";
    fetch(action + sep + "step=scope", {
      credentials: "same-origin",
      headers: { Accept: "text/html", "X-Requested-With": "pg-sheet" },
    })
      .then(function (response) {
        return response.text().then(function (html) {
          return { ok: response.ok, redirected: response.redirected, url: response.url, html: html };
        });
      })
      .then(function (out) {
        if (out.redirected || !out.ok) {
          window.location.assign(out.url || action);
          return;
        }
        swapOrNavigate(root, out.html, out.url || action);
      })
      .catch(function () {
        window.location.assign(action);
      });
  }

  function enhanceAddFlow() {
    document.querySelectorAll("[data-pg-add]").forEach(function (root) {
      root.classList.add("is-enhanced");
    });
    document.addEventListener("click", function (event) {
      var retry = event.target.closest("[data-pg-add-retry]");
      if (!retry) {
        return;
      }
      var root = retry.closest("[data-pg-add]");
      if (!root) {
        return;
      }
      event.preventDefault();
      retry.setAttribute("aria-busy", "true");
      retry.disabled = true;
      rereadAddSheet(root);
    });
    document.addEventListener("submit", function (event) {
      var form = event.target.closest("[data-add-step='scope'] form");
      if (!form || !window.fetch || !window.FormData) {
        return;
      }
      var root = form.closest("[data-pg-add]");
      // Only the in-dialog flow is enhanced: the standalone (no-JS or
      // POST re-render) page keeps the plain form post and the server's
      // save-failed page.
      if (!root || !root.closest("dialog")) {
        return;
      }
      var submitter = event.submitter;
      if (!submitter || !submitter.name) {
        return;
      }
      event.preventDefault();
      if (root.getAttribute("data-pg-saving") === "true") {
        return;
      }
      root.setAttribute("data-pg-saving", "true");
      root.setAttribute("data-pg-add-action", form.getAttribute("action") || "");
      submitter.setAttribute("aria-busy", "true");
      var alertBox = root.querySelector("[data-pg-add-alert]");
      if (alertBox) {
        alertBox.hidden = true;
        alertBox.replaceChildren();
        alertBox.removeAttribute("data-outcome");
      }
      var data = new FormData(form);
      data.append(submitter.name, submitter.value);
      var body = new URLSearchParams();
      data.forEach(function (value, key) {
        body.append(key, value);
      });
      function done() {
        root.removeAttribute("data-pg-saving");
        submitter.removeAttribute("aria-busy");
      }
      fetch(form.getAttribute("action"), {
        method: "POST",
        credentials: "same-origin",
        body: body,
        headers: {
          Accept: "application/json, text/html;q=0.9",
          "X-Requested-With": "pg-sheet",
        },
      })
        .then(function (response) {
          var type = (response.headers.get("content-type") || "").toLowerCase();
          if (type.indexOf("application/json") >= 0) {
            return response.json().then(function (json) {
              return { json: json, ok: response.ok, redirected: response.redirected, url: response.url };
            });
          }
          return response.text().then(function (html) {
            return { html: html, ok: response.ok, redirected: response.redirected, url: response.url };
          });
        })
        .then(function (out) {
          done();
          if (out.json) {
            if (out.json.ok === false && out.json.error === "save_failed") {
              // The server's verdict: ``rolled_back`` only when it observed
              // its own rollback; anything else is ``unknown``.
              showAddFailure(root, out.json.outcome === "rolled_back" ? "rolled_back" : "unknown");
              return;
            }
            // Any other JSON denial: re-read the sheet so the current state
            // (limit reached, pending, already active) is what the user sees.
            rereadAddSheet(root);
            return;
          }
          if (out.redirected) {
            window.location.assign(out.url);
            return;
          }
          swapOrNavigate(root, out.html, out.url);
        })
        .catch(function () {
          done();
          // No answer at all: the transaction may have committed. Never claim
          // "nothing was changed" here.
          showAddFailure(root, "unknown");
        });
    });
    document.addEventListener("submit", function (event) {
      var form = event.target.closest("[data-pg-add-confirm]");
      if (!form) {
        return;
      }
      var root = form.closest("[data-pg-add]");
      if (!root || root.getAttribute("data-skip-confirm") === "true") {
        return;
      }
      event.preventDefault();
      root.setAttribute("data-step", "scope");
      var confirmStep = root.querySelector("[data-add-step='confirm']");
      var scopeStep = root.querySelector("[data-add-step='scope']");
      if (confirmStep) {
        confirmStep.hidden = true;
      }
      if (scopeStep) {
        scopeStep.hidden = false;
        // The accessible name follows the step: the host dialog (in-page or
        // direct) or the standalone panel is now labelled by the scope title.
        var scopeTitle = scopeStep.querySelector("h1, h2");
        var host = root.closest("dialog");
        if (scopeTitle && scopeTitle.id) {
          if (host) {
            host.dispatchEvent(new Event("pg-sheet:relabel"));
          } else if (root.hasAttribute("aria-labelledby")) {
            root.setAttribute("aria-labelledby", scopeTitle.id);
          }
        }
        var focus = scopeStep.querySelector("button, [href]");
        if (focus) {
          focus.focus();
        }
      }
    });
  }

  enhanceSheets();
  enhanceAddFlow();
})();

