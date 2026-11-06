(function () {
  function closeTips(except) {
    document.querySelectorAll(".sched-lang[data-open='true']").forEach(function (el) {
      if (el !== except) el.removeAttribute("data-open");
    });
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-sched-list-toggle]");
    if (toggle) {
      var open = toggle.getAttribute("aria-expanded") === "true";
      var next = !open;
      toggle.setAttribute("aria-expanded", next ? "true" : "false");
      var label = toggle.querySelector("[data-sched-list-label]");
      if (label) label.textContent = next ? "Collapse ▴" : "Expand ▾";
      var body = toggle.parentElement && toggle.parentElement.querySelector(".sched-list-body");
      if (body) body.hidden = !next;
      return;
    }

    var lang = event.target.closest(".sched-lang[data-sched-tip]");
    if (lang) {
      var on = lang.getAttribute("data-open") === "true";
      closeTips(lang);
      if (on) lang.removeAttribute("data-open");
      else lang.setAttribute("data-open", "true");
      return;
    }
    closeTips();
  });

  document.addEventListener("mouseenter", function (event) {
    var lang = event.target.closest && event.target.closest(".sched-lang[data-sched-tip]");
    if (!lang) return;
    closeTips(lang);
    lang.setAttribute("data-open", "true");
  }, true);

  document.addEventListener("mouseleave", function (event) {
    var lang = event.target.closest && event.target.closest(".sched-lang[data-open='true']");
    if (lang) lang.removeAttribute("data-open");
  }, true);

  document.addEventListener("focusin", function (event) {
    var lang = event.target.closest && event.target.closest(".sched-lang[data-sched-tip]");
    if (lang) {
      closeTips(lang);
      lang.setAttribute("data-open", "true");
    }
  });

  document.addEventListener("focusout", function (event) {
    var lang = event.target.closest && event.target.closest(".sched-lang");
    if (lang) lang.removeAttribute("data-open");
  });
})();
