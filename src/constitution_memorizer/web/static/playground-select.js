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

    // M7b (Q8). One state per section, shown the same way everywhere:
    //   whole section  -> the section box ticked and every clause box ticked
    //   some clauses   -> the section box indeterminate, those clause boxes ticked
    //   nothing        -> nothing ticked
    // Ticking the section ticks every clause; unticking one clause leaves the
    // rest; ticking the last clause promotes back to the whole section. The
    // server stores a whole section either way (it ignores clause values of a
    // section submitted whole and promotes a full set of clauses itself).
    function setSectionBox(block, sectionBox, state) {
      sectionBox.checked = state === "all";
      sectionBox.indeterminate = state === "some";
      sectionBox.setAttribute(
        "aria-checked",
        state === "all" ? "true" : state === "some" ? "mixed" : "false"
      );
      block.setAttribute("data-check-state", state);
    }

    function syncSectionState(block) {
      var sectionBox = $(".pg-pick-check", block);
      var units = $$(".pg-pick-clause-check", block);
      if (!sectionBox || sectionBox.disabled) {
        return;
      }
      if (!units.length) {
        setSectionBox(block, sectionBox, sectionBox.checked ? "all" : "none");
        return;
      }
      var unitOn = units.filter(function (box) {
        return box.checked;
      }).length;
      if (unitOn === units.length) {
        setSectionBox(block, sectionBox, "all");
      } else if (unitOn > 0) {
        setSectionBox(block, sectionBox, "some");
      } else {
        setSectionBox(block, sectionBox, "none");
      }
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
      if (sectionBox && sectionBox.checked && !sectionBox.disabled) {
        // The server renders a whole section as the section box alone: show
        // its clauses ticked too, so unticking one does what it says.
        $$(".pg-pick-clause-check", block).forEach(function (box) {
          box.checked = true;
        });
      }
      if (sectionBox) {
        sectionBox.addEventListener("change", function () {
          var on = sectionBox.checked;
          $$(".pg-pick-clause-check", block).forEach(function (box) {
            box.checked = on;
          });
          paint();
        });
      }
      $$(".pg-pick-clause-check", block).forEach(function (box) {
        box.addEventListener("change", paint);
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
