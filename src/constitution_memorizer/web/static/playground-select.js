(function () {
  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function noun(n, one, many) {
    return n === 1 ? one : many;
  }

  function ctaCopy(sectionCount, partialCount) {
    if (sectionCount <= 0) {
      return "Select sections to add";
    }
    var label = "Add " + sectionCount + " " + noun(sectionCount, "section", "sections") + " →";
    if (partialCount) {
      label =
        "Add " +
        sectionCount +
        " " +
        noun(sectionCount, "section", "sections") +
        " (" +
        partialCount +
        " " +
        noun(partialCount, "clause", "clauses") +
        " partial) →";
    }
    return label;
  }

  function enhancePicker(root) {
    var form = $("[data-pg-picker-form]", root);
    if (!form) {
      return;
    }
    var submit = $("[data-pg-submit]", form);
    var asideSubmit = $("[data-pg-aside-submit]", root);
    var countEl = $("[data-pg-count]", root);
    var asideN = $("[data-pg-aside-n]", root);
    var asideLabel = $("[data-pg-aside-label]", root);
    var asideList = $("[data-pg-aside-list]", root);

    function sectionBlocks() {
      return $$(".pg-pick-section", form);
    }

    function syncSectionState(block) {
      var sectionBox = $(".pg-pick-check", block);
      var units = $$(".pg-pick-clause-check", block);
      if (!sectionBox || sectionBox.disabled) {
        return;
      }
      var unitOn = units.filter(function (box) {
        return box.checked;
      }).length;
      var mixed = unitOn > 0 && unitOn < units.length;
      var allUnits = units.length > 0 && unitOn === units.length;
      if (allUnits) {
        sectionBox.checked = true;
        sectionBox.indeterminate = false;
        sectionBox.setAttribute("aria-checked", "true");
        units.forEach(function (box) {
          box.checked = false;
        });
        block.setAttribute("data-check-state", "all");
        return;
      }
      if (sectionBox.checked) {
        sectionBox.indeterminate = false;
        sectionBox.setAttribute("aria-checked", "true");
        units.forEach(function (box) {
          box.checked = false;
        });
        block.setAttribute("data-check-state", "all");
        return;
      }
      if (mixed || unitOn > 0) {
        sectionBox.checked = false;
        sectionBox.indeterminate = true;
        sectionBox.setAttribute("aria-checked", "mixed");
        block.setAttribute("data-check-state", "some");
        return;
      }
      sectionBox.checked = false;
      sectionBox.indeterminate = false;
      sectionBox.setAttribute("aria-checked", "false");
      block.setAttribute("data-check-state", "none");
    }

    function paint() {
      var sectionCount = 0;
      var partial = 0;
      var provisions = 0;
      var items = [];
      sectionBlocks().forEach(function (block) {
        syncSectionState(block);
        var sectionBox = $(".pg-pick-check", block);
        var title = ($(".pg-pick-title", block) || {}).textContent || "";
        var number = block.getAttribute("data-section") || "";
        var units = $$(".pg-pick-clause-check", block).filter(function (box) {
          return box.checked;
        });
        if (sectionBox && sectionBox.checked && !sectionBox.indeterminate) {
          sectionCount += 1;
          provisions += 1;
          items.push({ citation: "Section " + number, title: title });
        } else if (units.length) {
          sectionCount += 1;
          partial += units.length;
          provisions += units.length;
          units.forEach(function (box) {
            var label = box.closest("label");
            var printed = label ? (($("strong", label) || {}).textContent || "") : "";
            items.push({ citation: "Section " + number + printed, title: title });
          });
        }
        var details = $("details", block);
        var caret = details ? $("summary", details) : null;
        if (caret) {
          caret.setAttribute("aria-expanded", details.open ? "true" : "false");
        }
      });
      var cta = ctaCopy(sectionCount, partial);
      if (submit) {
        submit.textContent = cta;
        submit.disabled = sectionCount === 0;
      }
      if (asideSubmit) {
        asideSubmit.textContent = cta;
        asideSubmit.disabled = sectionCount === 0;
      }
      if (countEl) {
        countEl.textContent = provisions === 1 ? "1 provision" : provisions + " provisions";
      }
      if (asideN) {
        asideN.textContent = String(sectionCount);
      }
      if (asideLabel) {
        asideLabel.textContent = noun(sectionCount, "section selected", "sections selected");
      }
      if (asideList) {
        asideList.innerHTML = items
          .map(function (item) {
            return (
              "<li><strong>" +
              item.citation +
              "</strong><span>" +
              item.title +
              "</span></li>"
            );
          })
          .join("");
      }
    }

    sectionBlocks().forEach(function (block) {
      var sectionBox = $(".pg-pick-check", block);
      if (sectionBox && sectionBox.getAttribute("data-indeterminate") === "1") {
        sectionBox.indeterminate = true;
        sectionBox.checked = false;
        sectionBox.setAttribute("aria-checked", "mixed");
      }
      if (sectionBox) {
        sectionBox.addEventListener("change", function () {
          if (sectionBox.checked) {
            $$(".pg-pick-clause-check", block).forEach(function (box) {
              box.checked = false;
            });
          }
          paint();
        });
      }
      $$(".pg-pick-clause-check", block).forEach(function (box) {
        box.addEventListener("change", function () {
          if (box.checked && sectionBox) {
            sectionBox.checked = false;
          }
          paint();
        });
      });
      var details = $("details", block);
      if (details) {
        details.addEventListener("toggle", paint);
      }
    });
    paint();
  }

  document.querySelectorAll("[data-pg-picker]").forEach(enhancePicker);
})();
