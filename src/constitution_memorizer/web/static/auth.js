/* Auth + guest UX enhancements (progressive enhancement over form POSTs). */
(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  /* —— OTP cells —— */
  function initOtp() {
    var form = qs("[data-otp-form]");
    if (!form) return;
    var cells = qsa("[data-otp-cells] .otp-cell", form);
    var combined = qs("#otp-combined", form);
    var verify = qs("[data-verify-otp]", form);
    if (!cells.length) return;

    function sync() {
      var value = cells.map(function (c) { return (c.value || "").replace(/\D/g, "").slice(0, 1); }).join("");
      cells.forEach(function (c, i) { c.value = value.charAt(i) || ""; });
      if (combined) combined.value = value;
      if (verify) verify.disabled = value.length !== 6;
    }

    cells.forEach(function (cell, index) {
      cell.addEventListener("input", function () {
        var digits = (cell.value || "").replace(/\D/g, "");
        if (digits.length > 1) {
          digits.split("").forEach(function (d, offset) {
            if (cells[index + offset]) cells[index + offset].value = d;
          });
          var next = cells[Math.min(index + digits.length, cells.length - 1)];
          if (next) next.focus();
        } else {
          cell.value = digits;
          if (digits && cells[index + 1]) cells[index + 1].focus();
        }
        sync();
      });
      cell.addEventListener("keydown", function (ev) {
        if (ev.key === "Backspace" && !cell.value && index > 0) {
          cells[index - 1].focus();
          cells[index - 1].value = "";
          sync();
          ev.preventDefault();
        } else if (ev.key === "ArrowLeft" && index > 0) {
          cells[index - 1].focus();
          ev.preventDefault();
        } else if (ev.key === "ArrowRight" && index < cells.length - 1) {
          cells[index + 1].focus();
          ev.preventDefault();
        }
      });
      cell.addEventListener("focus", function () { cell.select(); });
    });
    sync();
    cells[0].focus();

    var timerEl = qs("[data-resend-count]", form);
    var timerWrap = qs("[data-resend-timer]", form);
    var resendBtn = qs("[data-resend-btn]", form);
    var seconds = 30;
    if (timerEl && resendBtn && timerWrap) {
      var tick = setInterval(function () {
        seconds -= 1;
        if (seconds <= 0) {
          clearInterval(tick);
          timerWrap.hidden = true;
          resendBtn.hidden = false;
        } else {
          timerEl.textContent = String(seconds);
        }
      }, 1000);
    }
  }

  /* —— Phone send loading —— */
  function initPhoneForm() {
    var form = qs("[data-phone-form]");
    if (!form) return;
    form.addEventListener("submit", function () {
      var btn = qs("[data-send-otp]", form);
      var label = qs("[data-send-label]", form);
      if (btn) {
        btn.disabled = true;
        btn.classList.add("is-loading");
      }
      if (label) label.textContent = "Sending…";
    });
  }

  /* —— Google loading —— */
  function initGoogle() {
    var link = qs("[data-google-signin]");
    if (!link) return;
    link.addEventListener("click", function () {
      var label = qs("[data-google-label]", link);
      link.classList.add("is-loading");
      if (label) label.textContent = "Opening Google…";
    });
  }

  /* —— Auth transition auto-advance —— */
  function initTransition() {
    var el = qs("[data-auth-transition]");
    if (!el || el.getAttribute("data-next") == null) return;
    if (el.querySelector(".actions a.btn") && el.textContent.indexOf("Could not") !== -1) return;
    var next = el.getAttribute("data-next") || "/dashboard";
    setTimeout(function () {
      window.location.href = next;
    }, 1200);
  }

  /* —— Guest modal —— */
  function initGuestModal() {
    var dialog = qs("[data-guest-modal]");
    if (!dialog) return;
    var copyNode = qs("#guest-modal-copy");
    var copy = { default: "", mastered: "", again: "", note: "" };
    try {
      if (copyNode) copy = JSON.parse(copyNode.textContent || "{}");
    } catch (_e) { /* ignore */ }
    var body = qs("[data-guest-modal-body]", dialog);
    var signin = qs("[data-guest-modal-signin]", dialog);
    var title = qs(".guest-modal-title", dialog);
    var titles = {};
    var titleNode = qs("#guest-modal-titles");
    try {
      if (titleNode) titles = JSON.parse(titleNode.textContent || "{}");
    } catch (_e) { /* ignore */ }
    var defaultTitle = title ? title.textContent : "";
    var DONE_PROMPT_KEY = "cm-guest-done-prompted";

    function openGuestModal(reason) {
      var key = reason || "default";
      // The Done prompt is the earned moment — it fires on the first Done of a
      // session, not on every one (design 06·B).
      if (key === "mastered") {
        try {
          if (sessionStorage.getItem(DONE_PROMPT_KEY) === "1") {
            var quiet = qs("[data-guest-done-note]");
            if (quiet) quiet.hidden = false;
            return;
          }
          sessionStorage.setItem(DONE_PROMPT_KEY, "1");
        } catch (_e) { /* ignore */ }
      }
      if (title) title.textContent = titles[key] || defaultTitle;
      if (body) body.textContent = copy[key] || copy.default || body.textContent;
      if (signin) {
        var next = window.location.pathname + window.location.search;
        signin.href = "/login?next=" + encodeURIComponent(next) + "&reason=" + encodeURIComponent(key);
      }
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "open");
    }

    function closeGuestModal() {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      try {
        document.dispatchEvent(new CustomEvent("rtc:guest-modal-dismiss"));
      } catch (_e) { /* ignore */ }
    }

    qsa("[data-guest-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openGuestModal(btn.getAttribute("data-guest-action") || "default");
      });
    });
    qsa("[data-guest-modal-dismiss]").forEach(function (btn) {
      btn.addEventListener("click", closeGuestModal);
    });
    window.openGuestModal = openGuestModal;
    window.closeGuestModal = closeGuestModal;
  }

  /* —— Account menu —— */
  function initAccountMenu() {
    var root = qs("[data-account-menu]");
    if (!root) return;
    var toggle = qs("[data-account-toggle]", root);
    var panel = qs("[data-account-panel]", root);
    if (!toggle || !panel) return;
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", open ? "false" : "true");
      panel.hidden = open;
    });
    document.addEventListener("click", function (ev) {
      if (!root.contains(ev.target)) {
        toggle.setAttribute("aria-expanded", "false");
        panel.hidden = true;
      }
    });
  }

  /* —— Profile dialogs —— */
  function initProfileDialogs() {
    qsa("[data-open-signout]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var d = qs("#signout-modal");
        if (d && d.showModal) d.showModal();
      });
    });
    qsa("[data-open-reset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var d = qs("#reset-modal");
        if (d && d.showModal) d.showModal();
      });
    });
    qsa("[data-open-delete]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var d = qs("#delete-modal");
        if (d && d.showModal) d.showModal();
      });
    });
    qsa("[data-close-dialog]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var d = btn.closest("dialog");
        if (d && d.close) d.close();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initOtp();
    initPhoneForm();
    initGoogle();
    initTransition();
    initGuestModal();
    initAccountMenu();
    initProfileDialogs();
  });
})();
