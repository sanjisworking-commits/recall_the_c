// Runs the shipped section-picker script (static/playground-select.js) against a
// small stand-in DOM and reports what it does. Driven by
// tests/test_playground_picker_interaction.py, which builds the picker's state
// from the page the server actually rendered.
//
// stdin  {script, blocks: [{number, title, checked, indeterminate, disabled,
//                           units: [{value, label, checked}]}],
//         steps: [{click: "section" | "unit", section, index}]}
// stdout {initial, steps: [...], exceptions: []} — each state lists, per block,
//        the section box, the ticked clauses, the block's data-check-state and
//        the values a form submission would carry.
//
// The stand-in implements only what the script uses: class / attribute / tag
// selectors, closest(), attributes, change and toggle listeners, textContent
// and innerHTML as plain properties.
"use strict";
const fs = require("fs");
const vm = require("vm");

class El {
  constructor(tag, opts = {}) {
    this.tagName = tag.toUpperCase();
    this.classes = new Set(opts.classes || []);
    this.attrs = Object.assign({}, opts.attrs || {});
    this.children = [];
    this.parent = null;
    this.listeners = {};
    this.checked = !!opts.checked;
    this.indeterminate = false;
    this.disabled = !!opts.disabled;
    this.value = opts.value;
    this.textContent = opts.text || "";
    this.innerHTML = "";
    this.open = false;
  }
  add(child) { child.parent = this; this.children.push(child); return child; }
  getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type) { (this.listeners[type] || []).forEach((fn) => fn.call(this, { type, target: this })); }
  matches(sel) {
    if (sel.startsWith(".")) return this.classes.has(sel.slice(1));
    if (sel.startsWith("[")) return Object.prototype.hasOwnProperty.call(this.attrs, sel.slice(1, -1));
    return this.tagName === sel.toUpperCase();
  }
  descendants(out = []) { for (const c of this.children) { out.push(c); c.descendants(out); } return out; }
  querySelectorAll(sel) { return this.descendants().filter((e) => e.matches(sel)); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  closest(sel) { let e = this; while (e) { if (e.matches(sel)) return e; e = e.parent; } return null; }
}

function build(blocks) {
  const doc = new El("document");
  const root = doc.add(new El("section", { attrs: { "data-pg-picker": "" } }));
  const form = root.add(new El("form", { attrs: { "data-pg-picker-form": "" } }));
  const index = {};
  for (const b of blocks) {
    const li = form.add(new El("li", { classes: ["pg-pick-section"], attrs: { "data-section": b.number, "data-check-state": b.checkState || "none" } }));
    const sectionAttrs = { name: "section", "aria-checked": b.checked ? "true" : b.indeterminate ? "mixed" : "false" };
    if (b.indeterminate) sectionAttrs["data-indeterminate"] = "1";
    const box = li.add(new El("input", { classes: ["pg-pick-check"], attrs: sectionAttrs, checked: b.checked, disabled: b.disabled, value: b.number }));
    li.add(new El("p", { classes: ["pg-pick-title"], text: b.title || "" }));
    const units = [];
    if (b.units && b.units.length) {
      const details = li.add(new El("details"));
      details.add(new El("summary"));
      for (const u of b.units) {
        const label = details.add(new El("label"));
        units.push(label.add(new El("input", { classes: ["pg-pick-clause-check"], attrs: { name: "unit" }, checked: u.checked, disabled: b.disabled, value: u.value })));
        label.add(new El("strong", { text: u.label || "" }));
      }
    }
    index[b.number] = { li, box, units };
  }
  form.add(new El("p", { attrs: { "data-pg-count": "" } }));
  const submit = form.add(new El("button", { attrs: { "data-pg-submit": "" } }));
  root.add(new El("strong", { attrs: { "data-pg-aside-n": "" } }));
  root.add(new El("span", { attrs: { "data-pg-aside-label": "" } }));
  root.add(new El("ul", { attrs: { "data-pg-aside-list": "" } }));
  root.add(new El("button", { attrs: { "data-pg-aside-submit": "" } }));
  return { doc, form, index, submit };
}

function snapshot(dom) {
  const out = { blocks: {}, submits: { section: [], unit: [] }, submitLabel: dom.submit.textContent, submitDisabled: !!dom.submit.disabled };
  for (const [number, b] of Object.entries(dom.index)) {
    out.blocks[number] = {
      sectionChecked: b.box.checked,
      sectionIndeterminate: b.box.indeterminate,
      ariaChecked: b.box.getAttribute("aria-checked"),
      checkState: b.li.getAttribute("data-check-state"),
      clausesTicked: b.units.map((u, i) => (u.checked ? i + 1 : null)).filter(Boolean),
      clauseCount: b.units.length,
    };
    // what a browser would put in the form data: checked, enabled inputs
    if (b.box.checked && !b.box.disabled) out.submits.section.push(b.box.value);
    for (const u of b.units) if (u.checked && !u.disabled) out.submits.unit.push(u.value);
  }
  return out;
}

function click(el) {
  // a click on a checkbox toggles it, clears any indeterminate display, then fires change
  el.checked = !el.checked;
  el.indeterminate = false;
  el.dispatch("change");
}

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const dom = build(input.blocks);
const exceptions = [];
try {
  vm.runInNewContext(fs.readFileSync(input.script, "utf8"), { document: dom.doc }, { filename: input.script });
} catch (err) {
  exceptions.push(String(err && err.stack ? err.stack : err));
}
const result = { initial: snapshot(dom), steps: [], exceptions };
for (const step of input.steps || []) {
  try {
    const b = dom.index[step.section];
    click(step.click === "section" ? b.box : b.units[step.index]);
  } catch (err) {
    exceptions.push(String(err && err.stack ? err.stack : err));
  }
  result.steps.push(snapshot(dom));
}
process.stdout.write(JSON.stringify(result));
