(() => {
  const root = document.querySelector("[data-signed-in-calendar]");
  if (!root) return;
  if (window.matchMedia && !window.matchMedia("(min-width: 561px)").matches) return;

  const token = root.getAttribute("data-study-token") || "";
  const today = root.getAttribute("data-cal-today") || "";
  const $ = (sel, el) => (el || root).querySelector(sel);
  const $$ = (sel, el) => Array.prototype.slice.call((el || root).querySelectorAll(sel));

  const editor = document.getElementById("cal-si-editor");
  const viewer = document.getElementById("cal-si-viewer");
  const form = document.getElementById("cal-si-form");
  const toastEl = document.getElementById("cal-si-toast");
  let current = null;
  let editing = null;
  let lastUndo = null;

  function localDate() {
    return today || new Date().toISOString().slice(0, 10);
  }

  function error(id, message) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = message || "";
    el.hidden = !message;
  }

  function node(tag, text) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    return el;
  }

  async function api(path, body) {
    const response = await fetch("/api/study-materials" + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "X-Study-Token": token } : {},
      body,
    });
    if (!response.ok) {
      let message = "Could not save or load this material. Please try again.";
      try {
        const data = await response.json();
        if (typeof data.detail === "string") message = data.detail;
      } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }

  function eligibleDay(iso) {
    return Boolean(iso) && iso <= localDate();
  }

  function selectedIso() {
    const on = $(".calendar-cell.is-selected", root);
    return (on && on.getAttribute("data-date")) || "";
  }

  function applyFilter(value) {
    $$("[data-cal-source]", root).forEach((el) => {
      const src = el.getAttribute("data-cal-source");
      el.hidden = value !== "all" && src !== value;
    });
    const overdue = $("[data-cal-overdue]", root);
    if (overdue) overdue.hidden = value !== "all" && value !== "my";
  }

  function showPanel(iso) {
    $$("[data-cal-panel-day]", root).forEach((el) => {
      el.hidden = el.getAttribute("data-cal-panel-day") !== iso;
    });
    $$(".calendar-cell[data-date]", root).forEach((cell) => {
      cell.classList.toggle("is-selected", cell.getAttribute("data-date") === iso);
    });
    const add = $("[data-cal-day-add]", root);
    if (add) {
      add.hidden = !eligibleDay(iso);
      add.setAttribute("data-study-date", iso || "");
    }
    const recall = $("[data-cal-continue-recall]", root);
    if (recall) recall.hidden = iso !== localDate();
  }

  function hint() {
    if (!form) return;
    const value = form.elements.studied_on.value;
    const el = document.getElementById("cal-si-schedule-hint");
    if (!el || !value) return;
    el.textContent =
      "Revision dates: " +
      [3, 7, 15, 30, 60]
        .map((offset) => {
          const d = new Date(value + "T12:00:00");
          d.setDate(d.getDate() + offset);
          return d.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
          });
        })
        .join(" · ") +
      ". Dates stay anchored to this study date.";
  }

  function openEditor(day, entry) {
    if (!editor || !form || !token) return;
    editing = entry || null;
    form.reset();
    form.elements.title.value = entry ? entry.title : "";
    form.elements.notes.value = entry ? entry.notes : "";
    form.elements.studied_on.value = entry ? entry.studied_on : day;
    form.elements.studied_on.max = localDate();
    form.elements.studied_on.disabled = !!entry;
    form.elements.activity.value = entry ? entry.activity : "Studied";
    form.elements.activity.disabled = !!entry;
    document.getElementById("cal-si-editor-title").textContent = entry
      ? "Edit study material"
      : "Add study material";
    form.querySelector("[type=submit]").textContent = entry
      ? "Save changes"
      : "Save & schedule";
    error("cal-si-form-error");
    hint();
    editor.showModal();
  }

  function preview(asset) {
    const area = document.getElementById("cal-si-preview");
    if (!area) return;
    area.replaceChildren();
    const url = asset.url || "/api/study-materials/files/" + asset.id;
    const link = node("a", asset.url ? "Open original website ↗" : "Open file in a new tab ↗");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    area.append(link);
    if ((asset.media_type || "").startsWith("image/")) {
      const img = node("img");
      img.alt = asset.name;
      img.src = url;
      area.append(img);
    } else if (asset.url) {
      area.append(
        node("p", "Some websites block embedded viewing. Use “Open original website” if the preview is blank.")
      );
    } else {
      const frame = node("iframe");
      frame.title = asset.name;
      frame.referrerPolicy = "no-referrer";
      frame.src = url;
      area.append(frame);
    }
  }

  function showToast(text, undo) {
    if (!toastEl) return;
    lastUndo = undo || null;
    toastEl.querySelector("[data-cal-toast-text]").textContent = text;
    const undoBtn = toastEl.querySelector("[data-cal-toast-undo]");
    if (undoBtn) undoBtn.hidden = !undo;
    toastEl.hidden = false;
  }

  function hideToast() {
    if (!toastEl) return;
    toastEl.hidden = true;
    lastUndo = null;
  }

  function renderEntry(entry) {
    current = entry;
    document.getElementById("cal-si-view-title").textContent = entry.title;
    document.getElementById("cal-si-view-meta").textContent =
      `${entry.activity} ${entry.studied_on} · ${entry.assets.length} attachment(s)`;
    document.getElementById("cal-si-notes").textContent = entry.notes || "No notes yet.";
    const assets = document.getElementById("cal-si-assets");
    const reviews = document.getElementById("cal-si-reviews");
    assets.replaceChildren();
    reviews.replaceChildren();
    error("cal-si-view-error");
    entry.assets.forEach((asset) => {
      const b = node(
        "button",
        (asset.url ? "↗ " : asset.media_type === "application/pdf" ? "PDF · " : "Photo · ") +
          asset.name
      );
      b.type = "button";
      b.onclick = () => preview(asset);
      assets.append(b);
    });
    entry.reviews.forEach((review) => {
      const row = node("div");
      row.className = "cal-si-review";
      const text = node("span", `Day ${review.offset} · ${review.due_on}`);
      const state = review.completed_on
        ? `Completed ${review.completed_on}`
        : review.due_on < localDate()
          ? "Overdue"
          : review.due_on === localDate()
            ? "Due today"
            : "Scheduled";
      text.append(node("small", state));
      const b = node("button", review.completed_on ? "Undo" : "Mark revised");
      b.type = "button";
      b.disabled = !review.completed_on && review.due_on > localDate();
      b.onclick = async () => {
        b.disabled = true;
        const marking = !review.completed_on;
        try {
          const body = new FormData();
          body.set("done", marking ? "true" : "false");
          const updated = await api(`/${entry.id}/reviews/${review.offset}`, body);
          renderEntry(updated);
          viewer.dataset.changed = "true";
          showToast(
            marking
              ? `Marked revised · Day ${review.offset}`
              : `Revision reopened · Day ${review.offset}`,
            marking
              ? async () => {
                  const undoBody = new FormData();
                  undoBody.set("done", "false");
                  const undone = await api(`/${entry.id}/reviews/${review.offset}`, undoBody);
                  renderEntry(undone);
                  hideToast();
                }
              : null
          );
        } catch (e) {
          error("cal-si-view-error", e.message);
          b.disabled = false;
        }
      };
      row.append(text, b);
      reviews.append(row);
    });
  }

  async function openViewer(id) {
    if (!viewer || !token) return;
    error("cal-si-page-error");
    try {
      const entry = await api("/" + id);
      renderEntry(entry);
      const area = document.getElementById("cal-si-preview");
      area.replaceChildren();
      if (entry.assets.length) preview(entry.assets[0]);
      else area.append(node("p", "No attachments yet. Use “Edit / add attachments” to add PDFs, photos or links."));
      viewer.showModal();
    } catch (e) {
      error("cal-si-page-error", e.message);
    }
  }

  const filter = $("[data-cal-filter]", root);
  if (filter) {
    applyFilter(filter.value || "all");
    filter.addEventListener("change", () => applyFilter(filter.value));
  }

  const storedToast = sessionStorage.getItem("cal-si-toast");
  if (storedToast) {
    sessionStorage.removeItem("cal-si-toast");
    try {
      const payload = JSON.parse(storedToast);
      showToast(
        payload.text,
        payload.undo
          ? async () => {
              const undoBody = new FormData();
              undoBody.set("done", "false");
              await api(`/${payload.undo.id}/reviews/${payload.undo.offset}`, undoBody);
              hideToast();
              location.reload();
            }
          : null
      );
    } catch (_) {}
  }
  const initial =
    ($(".calendar-cell.is-today", root) &&
      $(".calendar-cell.is-today", root).getAttribute("data-date")) ||
    today;
  if (initial) showPanel(initial);

  root.addEventListener("click", (event) => {
    const add = event.target.closest("[data-study-add],[data-study-date]");
    if (add) {
      event.preventDefault();
      event.stopPropagation();
      const iso = add.getAttribute("data-study-date") || selectedIso() || localDate();
      if (add.getAttribute("data-study-date")) showPanel(iso);
      openEditor(eligibleDay(iso) ? iso : localDate());
      return;
    }
    const mark = event.target.closest("[data-study-mark]");
    if (mark) {
      event.preventDefault();
      event.stopPropagation();
      const id = mark.getAttribute("data-study-id-mark");
      const offset = mark.getAttribute("data-study-offset");
      const undo = mark.getAttribute("data-study-undo") === "1";
      (async () => {
        try {
          const body = new FormData();
          body.set("done", undo ? "false" : "true");
          await api(`/${id}/reviews/${offset}`, body);
          sessionStorage.setItem(
            "cal-si-toast",
            JSON.stringify({
              text: undo
                ? `Revision reopened · Day ${offset}`
                : `Marked revised · Day ${offset}`,
              undo: undo ? null : { id, offset },
            })
          );
          location.reload();
        } catch (e) {
          error("cal-si-page-error", e.message);
        }
      })();
      return;
    }
    const study = event.target.closest("[data-study-id]");
    if (study) {
      event.preventDefault();
      event.stopPropagation();
      const cell = study.closest(".calendar-cell[data-date]");
      if (cell) showPanel(cell.getAttribute("data-date"));
      openViewer(study.getAttribute("data-study-id"));
      return;
    }
    const chip = event.target.closest(".calendar-grid a.calendar-chip");
    if (chip) event.preventDefault();
    const cell = event.target.closest(".calendar-cell[data-date]");
    if (cell && !cell.classList.contains("is-blank")) {
      const iso = cell.getAttribute("data-date");
      if (iso) showPanel(iso);
    }
  });

  if (toastEl) {
    toastEl.querySelector("[data-cal-toast-undo]")?.addEventListener("click", async () => {
      if (lastUndo) await lastUndo();
    });
    toastEl.querySelector("[data-cal-toast-dismiss]")?.addEventListener("click", hideToast);
  }

  document.getElementById("cal-si-edit")?.addEventListener("click", () => {
    if (current) openEditor(current.studied_on, current);
  });

  $$("[data-study-close]", document).forEach((btn) => {
    btn.addEventListener("click", () => btn.closest("dialog")?.close());
  });

  viewer?.addEventListener("close", () => {
    document.getElementById("cal-si-preview")?.replaceChildren();
    if (viewer.dataset.changed) location.reload();
  });

  form?.elements.studied_on?.addEventListener("change", hint);
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    error("cal-si-form-error");
    try {
      const body = new FormData(form);
      body.delete("files");
      const files = Array.from(form.elements.files.files || []);
      if (
        files.some((f) => f.size > 25 * 1024 * 1024) ||
        files.reduce((sum, f) => sum + f.size, 0) > 100 * 1024 * 1024
      ) {
        throw new Error("Files are limited to 25 MB each and 100 MB per upload.");
      }
      files.forEach((file) => body.append("files", file));
      const result = await api(editing ? "/" + editing.id : "", body);
      const [year, month] = result.studied_on.split("-");
      location.href = `/calendar?year=${year}&month=${Number(month)}`;
    } catch (e) {
      error("cal-si-form-error", e.message);
    } finally {
      submit.disabled = false;
    }
  });
})();
