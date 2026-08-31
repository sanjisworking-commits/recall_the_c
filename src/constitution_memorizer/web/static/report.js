/**
 * Shared Report Issue / Contact Us dialog controller.
 * Contact us is site-wide; Report an issue stays Browse Article only.
 */
(function () {
  "use strict";

  var MODE_COPY = {
    report: {
      title: "Report an issue",
      lede: "Found something incorrect, outdated or unclear? Send it for review.",
      primary: "Submit report",
      successTitle: "Thank you",
      successLede: "Your report has been submitted for review.",
      successAnnounce: "Report submitted",
      busy: "Submitting…",
      openAnnounce: "Report an issue dialog opened",
      descriptionLabel: "What seems wrong?",
      descriptionPlaceholder: "Explain what appears incorrect or unclear…",
      turnstileAction: "report_issue",
      endpoint: "/api/report-issue",
    },
    contact: {
      title: "Contact us",
      lede: "Have feedback, found a problem, or want to suggest something? Send us a message.",
      primary: "Send message",
      successTitle: "✓ Message sent",
      successLede: "Thank you for helping us improve Recall the C.",
      successAnnounce: "Message sent",
      busy: "Sending…",
      openAnnounce: "Contact us dialog opened",
      descriptionLabel: "Message",
      descriptionPlaceholder: "Write your message…",
      turnstileAction: "contact_us",
      endpoint: "/api/contact",
    },
    gate: {
      title: "Sign in to contact us",
      lede: "Reporting issues and sending feedback is available to signed-in users.",
      primary: "Sign in",
      successTitle: "",
      successLede: "",
      successAnnounce: "",
      busy: "",
      openAnnounce: "Sign in to contact us",
      descriptionLabel: "",
      descriptionPlaceholder: "",
      turnstileAction: "",
      endpoint: "",
    },
  };

  var SECTION = "Browse Article";
  var MAX_SELECTED = 4000;
  var state = {
    mode: "report",
    articleNumber: "",
    section: SECTION,
    selectedText: "",
    turnstileToken: "",
    turnstileWidgetId: null,
    turnstileAction: "",
    lastTrigger: null,
    open: false,
  };

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function announce(text) {
    var live = $("[data-rc-live]");
    if (!live) return;
    live.textContent = "";
    window.setTimeout(function () {
      live.textContent = text;
    }, 20);
  }

  function selectionInsideArticle() {
    var root = document.querySelector(".browse-article-text");
    var sel = window.getSelection && window.getSelection();
    if (!root || !sel || sel.isCollapsed || !sel.rangeCount) return "";
    var text = String(sel.toString() || "").trim();
    if (!text) return "";
    var node = sel.anchorNode;
    if (!node) return "";
    var el = node.nodeType === 1 ? node : node.parentElement;
    if (!el || !root.contains(el)) return "";
    if (text.length > MAX_SELECTED) text = text.slice(0, MAX_SELECTED);
    return text;
  }

  function setBanner(message) {
    var banner = $("[data-rc-banner]");
    var text = $("[data-rc-banner-text]");
    if (!banner || !text) return;
    if (!message) {
      banner.hidden = true;
      text.textContent = "";
      return;
    }
    text.textContent = message;
    banner.hidden = false;
  }

  function clearFieldErrors() {
    document.querySelectorAll("[data-rc-error-for]").forEach(function (el) {
      el.hidden = true;
      el.textContent = "";
    });
  }

  function setFieldError(name, message) {
    var el = $('[data-rc-error-for="' + name + '"]');
    if (!el) return;
    el.textContent = message || "";
    el.hidden = !message;
  }

  function setTurnstileChip(verified) {
    var chip = $("[data-turnstile-chip]");
    var status = $("[data-turnstile-status]");
    var label = $("[data-turnstile-label]");
    if (!chip) return;
    if (verified) {
      chip.classList.add("is-verified");
      if (status) status.textContent = "✓";
      if (label) label.textContent = "Verified — you're human";
    } else {
      chip.classList.remove("is-verified");
      if (status) status.textContent = "◌";
      if (label) label.textContent = "Checking you're human…";
    }
  }

  function destroyTurnstile() {
    state.turnstileToken = "";
    setTurnstileChip(false);
    if (
      state.turnstileWidgetId != null &&
      window.turnstile &&
      typeof window.turnstile.remove === "function"
    ) {
      try {
        window.turnstile.remove(state.turnstileWidgetId);
      } catch (e) {}
    }
    state.turnstileWidgetId = null;
    state.turnstileAction = "";
    var mount = $("[data-turnstile-widget]");
    if (mount) mount.innerHTML = "";
  }

  function resetTurnstile() {
    state.turnstileToken = "";
    setTurnstileChip(false);
    var overlay = $("[data-report-overlay]");
    if (!overlay || overlay.getAttribute("data-turnstile-enabled") !== "true") return;
    if (
      state.turnstileWidgetId != null &&
      window.turnstile &&
      typeof window.turnstile.reset === "function"
    ) {
      try {
        window.turnstile.reset(state.turnstileWidgetId);
      } catch (e) {}
    }
  }

  function renderTurnstile(action) {
    var overlay = $("[data-report-overlay]");
    if (!overlay || overlay.getAttribute("data-turnstile-enabled") !== "true") return;
    var sitekey = overlay.getAttribute("data-turnstile-sitekey") || "";
    var mount = $("[data-turnstile-widget]");
    if (!sitekey || !mount || !action) return;

    if (state.turnstileWidgetId != null && state.turnstileAction === action) {
      resetTurnstile();
      return;
    }
    destroyTurnstile();

    function doRender() {
      if (!window.turnstile || typeof window.turnstile.render !== "function") return false;
      setTurnstileChip(false);
      state.turnstileAction = action;
      state.turnstileWidgetId = window.turnstile.render(mount, {
        sitekey: sitekey,
        action: action,
        theme: "auto",
        size: "compact",
        appearance: "interaction-only",
        "response-field": false,
        callback: function (token) {
          state.turnstileToken = token || "";
          setTurnstileChip(true);
        },
        "expired-callback": function () {
          state.turnstileToken = "";
          setTurnstileChip(false);
        },
        "error-callback": function () {
          state.turnstileToken = "";
          setTurnstileChip(false);
        },
      });
      return true;
    }

    if (doRender()) return;
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      if (doRender() || attempts > 40) window.clearInterval(timer);
    }, 100);
  }

  function focusableIn(dialog) {
    return Array.prototype.slice
      .call(
        dialog.querySelectorAll(
          'button:not([disabled]):not([hidden]), [href], input:not([disabled]):not([hidden]), select:not([disabled]):not([hidden]), textarea:not([disabled]):not([hidden]), [tabindex]:not([tabindex="-1"])'
        )
      )
      .filter(function (el) {
        return !el.closest("[hidden]") && el.offsetParent !== null;
      });
  }

  function trapFocus(event) {
    if (!state.open || event.key !== "Tab") return;
    var dialog = $(".rc-dialog");
    if (!dialog) return;
    var nodes = focusableIn(dialog);
    if (!nodes.length) return;
    var first = nodes[0];
    var last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function applyModeVisibility(mode) {
    var isReport = mode === "report";
    var isContact = mode === "contact";
    var isGate = mode === "gate";
    var reportFields = $("[data-rc-report-fields]");
    var contactFields = $("[data-rc-contact-fields]");
    var chips = $("[data-rc-chips]");
    var selectedWrap = $("[data-rc-selected-wrap]");
    var disclose = $("[data-rc-disclose]");
    var extra = $("[data-rc-extra]");
    var descField = $("[data-rc-description-field]");
    var formView = $("[data-rc-form-view]");
    var turnstile = $("[data-turnstile-slot]");
    var cancel = $("[data-rc-cancel]");
    var submit = $("[data-rc-submit]");
    var done = $("[data-rc-done]");

    if (reportFields) reportFields.hidden = !isReport;
    if (contactFields) contactFields.hidden = !isContact;
    if (chips) chips.hidden = !isReport;
    if (selectedWrap && !isReport) selectedWrap.hidden = true;
    if (disclose) disclose.hidden = !isReport;
    if (extra && !isReport) extra.hidden = true;
    if (descField) descField.hidden = isGate;
    if (formView) formView.hidden = false;
    if (turnstile) turnstile.hidden = isGate;
    if (cancel) cancel.hidden = false;
    if (submit) {
      submit.hidden = false;
      submit.type = isGate ? "button" : "submit";
    }
    if (done) done.hidden = true;
  }

  function showSuccess(idValue) {
    var copy = MODE_COPY[state.mode] || MODE_COPY.report;
    var formView = $("[data-rc-form-view]");
    var success = $("[data-rc-success]");
    var lede = $("[data-rc-lede]");
    var submit = $("[data-rc-submit]");
    var cancel = $("[data-rc-cancel]");
    var done = $("[data-rc-done]");
    var idEl = $("[data-rc-report-id]");
    var titleEl = $("[data-rc-success-title]");
    var successLede = $("[data-rc-success-lede]");
    var turnstile = $("[data-turnstile-slot]");
    if (formView) formView.hidden = true;
    if (success) success.hidden = false;
    if (lede) lede.hidden = true;
    if (submit) submit.hidden = true;
    if (cancel) cancel.hidden = true;
    if (done) done.hidden = false;
    if (turnstile) turnstile.hidden = true;
    if (titleEl) titleEl.textContent = copy.successTitle;
    if (successLede) successLede.textContent = copy.successLede;
    if (idEl) {
      if (state.mode === "report") {
        var shortId = String(idValue || "").replace(/-/g, "").slice(0, 8);
        idEl.textContent = shortId ? "Report #" + shortId : "";
      } else {
        idEl.textContent = "";
      }
    }
    setBanner("");
    announce(copy.successAnnounce);
    if (done) done.focus();
  }

  function resetFormView() {
    var form = $("[data-report-form]");
    var formView = $("[data-rc-form-view]");
    var success = $("[data-rc-success]");
    var lede = $("[data-rc-lede]");
    var submit = $("[data-rc-submit]");
    var cancel = $("[data-rc-cancel]");
    var done = $("[data-rc-done]");
    var turnstile = $("[data-turnstile-slot]");
    var extra = $("[data-rc-extra]");
    var disclose = $("[data-rc-disclose]");
    var caret = $("[data-rc-disclose-caret]");
    if (form) form.reset();
    if (formView) formView.hidden = false;
    if (success) success.hidden = true;
    if (lede) lede.hidden = false;
    if (submit) {
      submit.hidden = false;
      submit.disabled = false;
      submit.classList.remove("is-busy", "btn-ghost");
    }
    if (cancel) cancel.hidden = false;
    if (done) done.hidden = true;
    if (turnstile) turnstile.hidden = false;
    if (extra) extra.hidden = true;
    if (disclose) disclose.setAttribute("aria-expanded", "false");
    if (caret) caret.textContent = "▸";
    clearFieldErrors();
    setBanner("");
    destroyTurnstile();
  }

  function closeDialog() {
    var overlay = $("[data-report-overlay]");
    if (!overlay || !state.open) return;
    overlay.hidden = true;
    state.open = false;
    document.body.style.overflow = "";
    document.removeEventListener("keydown", onKeydown, true);
    destroyTurnstile();
    if (state.lastTrigger && typeof state.lastTrigger.focus === "function") {
      state.lastTrigger.focus();
    }
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDialog();
      return;
    }
    trapFocus(event);
  }

  function openDialog(opts) {
    opts = opts || {};
    var mode = opts.mode || "report";
    if (!MODE_COPY[mode]) return;
    var overlay = $("[data-report-overlay]");
    var dialog = overlay && $(".rc-dialog", overlay);
    if (!overlay || !dialog) return;

    var context = opts.context || {};
    state.mode = mode;
    state.articleNumber = String(context.articleNumber || "");
    state.section = String(context.section || SECTION);
    state.selectedText = String(context.selectedText || "");
    state.lastTrigger = opts.trigger || document.activeElement;

    resetFormView();
    applyModeVisibility(mode);

    var copy = MODE_COPY[mode];
    var title = $("#rc-title");
    var lede = $("[data-rc-lede]");
    var submit = $("[data-rc-submit]");
    var descLabel = $("[data-rc-description-label]");
    var description = $("[data-rc-description]");
    if (title) title.textContent = copy.title;
    if (lede) lede.textContent = copy.lede;
    if (submit) submit.textContent = copy.primary;
    if (descLabel && copy.descriptionLabel) descLabel.textContent = copy.descriptionLabel;
    if (description && copy.descriptionPlaceholder) {
      description.placeholder = copy.descriptionPlaceholder;
    }

    if (mode === "report") {
      var chipArticle = $("[data-rc-chip-article]");
      var chipSection = $("[data-rc-chip-section]");
      var selectedWrap = $("[data-rc-selected-wrap]");
      var selected = $("[data-rc-selected]");
      if (chipArticle) {
        chipArticle.textContent = state.articleNumber
          ? "Article " + state.articleNumber
          : state.section && state.section !== SECTION
            ? state.section
            : "Article";
      }
      if (chipSection) {
        chipSection.hidden = !state.selectedText;
        chipSection.textContent = state.section || SECTION;
      }
      if (selectedWrap && selected) {
        if (state.selectedText) {
          selectedWrap.hidden = false;
          selected.value = state.selectedText;
        } else {
          selectedWrap.hidden = true;
          selected.value = "";
        }
      }
    }

    overlay.hidden = false;
    state.open = true;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeydown, true);
    announce(copy.openAnnounce);

    if (mode === "gate") {
      if (submit) {
        submit.onclick = function () {
          var next = encodeURIComponent(
            window.location.pathname + window.location.search || "/"
          );
          window.location.href = "/login?next=" + next + "&reason=default";
        };
      }
    } else {
      if (submit) submit.onclick = null;
      renderTurnstile(copy.turnstileAction);
    }

    window.setTimeout(function () {
      if (mode === "report") {
        var issueType = $("[data-rc-issue-type]");
        if (issueType) {
          issueType.focus();
          return;
        }
      } else if (mode === "contact") {
        var topic = $("[data-rc-topic]");
        if (topic) {
          topic.focus();
          return;
        }
      }
      var closeBtn = $("[data-rc-close]");
      if (closeBtn) closeBtn.focus();
    }, 0);
  }

  function buildReportPayload() {
    var issueType = ($("[data-rc-issue-type]") || {}).value || "";
    var description = (($("[data-rc-description]") || {}).value || "").trim();
    var selected = (($("[data-rc-selected]") || {}).value || "").trim();
    var correction = (($("[data-rc-correction]") || {}).value || "").trim();
    var source = (($("[data-rc-source]") || {}).value || "").trim();
    var payload = {
      issue_type: issueType,
      description: description,
      page_url: window.location.pathname + window.location.search,
      section: state.section || SECTION,
    };
    if (state.articleNumber) payload.article_number = state.articleNumber;
    if (selected) payload.selected_text = selected.slice(0, MAX_SELECTED);
    if (correction) payload.suggested_correction = correction;
    if (source) payload.source_url = source;
    var overlay = $("[data-report-overlay]");
    if (overlay && overlay.getAttribute("data-turnstile-enabled") === "true") {
      if (state.turnstileToken) payload.turnstile_token = state.turnstileToken;
    }
    return payload;
  }

  function buildContactPayload() {
    var topicEl = document.querySelector("[data-rc-topic]:checked");
    var topic = topicEl ? topicEl.value : "";
    var message = (($("[data-rc-description]") || {}).value || "").trim();
    var payload = {
      topic: topic,
      message: message,
      page_url: window.location.pathname + window.location.search,
    };
    var overlay = $("[data-report-overlay]");
    if (overlay && overlay.getAttribute("data-turnstile-enabled") === "true") {
      if (state.turnstileToken) payload.turnstile_token = state.turnstileToken;
    }
    return payload;
  }

  function validateReport(payload) {
    clearFieldErrors();
    var ok = true;
    if (!payload.issue_type) {
      setFieldError("issue_type", "Choose an issue type.");
      ok = false;
    }
    if (!payload.description) {
      setFieldError("description", "Tell us what seems wrong.");
      ok = false;
    }
    return ok;
  }

  function validateContact(payload) {
    clearFieldErrors();
    var ok = true;
    if (!payload.topic) {
      setFieldError("topic", "Choose a topic.");
      ok = false;
    }
    if (!payload.message) {
      setFieldError("message", "Write a message.");
      ok = false;
    }
    return ok;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (state.mode === "gate") return;

    var copy = MODE_COPY[state.mode] || MODE_COPY.report;
    var submit = $("[data-rc-submit]");
    var payload =
      state.mode === "contact" ? buildContactPayload() : buildReportPayload();
    var valid =
      state.mode === "contact" ? validateContact(payload) : validateReport(payload);
    if (!valid) {
      announce("Validation failure");
      return;
    }

    if (submit) {
      submit.disabled = true;
      submit.textContent = copy.busy;
      submit.classList.add("is-busy", "btn-ghost");
    }
    announce(state.mode === "contact" ? "Sending message" : "Submitting report");
    setBanner("");

    try {
      var resp = await fetch(copy.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      });
      var data = null;
      try {
        data = await resp.json();
      } catch (e) {
        data = null;
      }

      if (resp.status === 201 && data && data.success) {
        showSuccess(
          state.mode === "contact" ? data.message_id : data.report_id
        );
        return;
      }

      var detail = (data && data.detail) || "";
      if (typeof detail !== "string") {
        detail =
          state.mode === "contact"
            ? "Unable to send message right now."
            : "Unable to submit report right now.";
      }

      if (resp.status === 400 || resp.status === 503) {
        var msg = detail;
        if (resp.status === 503) {
          msg =
            detail +
            (detail.slice(-1) === "." ? " " : ". ") +
            "Your text is still here — try again in a moment.";
        }
        setBanner(msg);
        resetTurnstile();
        announce("Submission failed");
      } else if (resp.status === 401) {
        setBanner(
          detail ||
            (state.mode === "contact"
              ? "Sign in to contact us."
              : "Sign in to report an issue.")
        );
        announce("Sign in required");
      } else if (resp.status === 422) {
        setBanner("Please check the highlighted fields.");
        announce("Validation failure");
      } else {
        setBanner(
          state.mode === "contact"
            ? "Unable to send message right now. Your text is still here — try again in a moment."
            : "Unable to submit report right now. Your text is still here — try again in a moment."
        );
        announce("Submission failed");
      }
    } catch (err) {
      setBanner(
        state.mode === "contact"
          ? "Unable to send message right now. Your text is still here — try again in a moment."
          : "Unable to submit report right now. Your text is still here — try again in a moment."
      );
      announce("Submission failed");
      resetTurnstile();
    } finally {
      var success = $("[data-rc-success]");
      if (submit && (!success || success.hidden)) {
        submit.disabled = false;
        submit.textContent = copy.primary;
        submit.classList.remove("is-busy", "btn-ghost");
      }
    }
  }

  function onDisclose() {
    var extra = $("[data-rc-extra]");
    var disclose = $("[data-rc-disclose]");
    var caret = $("[data-rc-disclose-caret]");
    if (!extra || !disclose) return;
    var open = disclose.getAttribute("aria-expanded") === "true";
    extra.hidden = open;
    disclose.setAttribute("aria-expanded", open ? "false" : "true");
    if (caret) caret.textContent = open ? "▸" : "▾";
  }

  function init() {
    var overlay = $("[data-report-overlay]");
    if (!overlay) return;

    document.querySelectorAll("[data-report-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openDialog({
          mode: "report",
          trigger: btn,
          context: {
            articleNumber: btn.getAttribute("data-article-number") || "",
            section: btn.getAttribute("data-report-section") || SECTION,
            selectedText: selectionInsideArticle(),
          },
        });
      });
    });

    document.querySelectorAll("[data-contact-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var mode = btn.getAttribute("data-contact-mode") || "contact";
        openDialog({ mode: mode, trigger: btn });
      });
    });

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) closeDialog();
    });

    var form = $("[data-report-form]");
    if (form) form.addEventListener("submit", onSubmit);

    ["data-rc-close", "data-rc-cancel", "data-rc-done"].forEach(function (attr) {
      var el = $("[" + attr + "]");
      if (el) el.addEventListener("click", closeDialog);
    });

    var disclose = $("[data-rc-disclose]");
    if (disclose) disclose.addEventListener("click", onDisclose);

    window.RecallReport = { openDialog: openDialog, closeDialog: closeDialog };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
