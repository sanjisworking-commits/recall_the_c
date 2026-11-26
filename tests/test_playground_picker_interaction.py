"""M7b (Q8) — the section picker's behaviour, executed.

The shipped script (`static/playground-select.js`) is run under Node against a
stand-in DOM built from the picker page the server rendered
(`tests/js/picker_harness.js`). Each interaction's form values are then saved
through the real endpoint and the page is reloaded, so the cycle

    whole section → one clause unticked (partial) → ticked back (whole) → cleared

is checked end to end: what the script shows, what it submits, what the server
stores and what the script shows again after a reload.

Needs `node` on the PATH; skipped otherwise. This is not a browser test: the
stand-in implements only what the script uses. The same cycle in a real
browser is recorded by `m7b/tools/trace_picker_m7b.py` in the evidence folder.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.playground.urls import sections_path
from tests.test_account_family import _main
from tests.test_playground_learn_family import LAW, _block, _picker_client, _post, _section_with_clauses, _state, _units

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "playground-select.js"
HARNESS = ROOT / "tests" / "js" / "picker_harness.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed; the picker script cannot be executed")


def _blocks(html: str, numbers: list[str]) -> list[dict]:
    """The picker state of the named sections, exactly as the server rendered it."""
    out = []
    for number in numbers:
        block = _block(html, number)
        state = _state(html, number)
        labels = re.findall(r"<strong>(.*?)</strong>", block.split("pg-pick-clauses", 1)[1]) if "pg-pick-clauses" in block else []
        values = _units(block)
        out.append({
            "number": number,
            "title": re.search(r'class="pg-pick-title">(.*?)<', block, flags=re.S).group(1).strip(),
            "checked": state["section_checked"],
            "indeterminate": 'data-indeterminate="1"' in block,
            "checkState": state["check_state"],
            "disabled": "is-disabled" in block.split(">", 1)[0],
            "units": [
                {"value": v, "label": labels[i] if i < len(labels) else "", "checked": v in state["units_checked"]}
                for i, v in enumerate(values)
            ],
        })
    return out


def _run(blocks: list[dict], steps: list[dict]) -> dict:
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        input=json.dumps({"script": str(SCRIPT), "blocks": blocks, "steps": steps}),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["exceptions"] == [], result["exceptions"]
    return result


def _save(client: TestClient, submits: dict) -> None:
    resp = _post(client, sections_path(LAW), {"section": submits["section"], "unit": submits["unit"]})
    assert resp.status_code == 303, (resp.status_code, resp.text[:200])


def test_whole_partial_whole_cleared_with_save_and_reload(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    html = client.get(sections_path(LAW)).text
    target, units = _section_with_clauses(html)
    other = next(n for n in re.findall(r'data-section="([^"]+)"', _main(html)) if n != target and not _units(_block(html, n)))
    n = len(units)
    everything = list(range(1, n + 1))

    # ── nothing selected → tick the other section (kept throughout) and the target section
    run = _run(_blocks(html, [other, target]), [{"click": "section", "section": other}, {"click": "section", "section": target}])
    assert run["initial"]["blocks"][target] == {
        "sectionChecked": False, "sectionIndeterminate": False, "ariaChecked": "false",
        "checkState": "none", "clausesTicked": [], "clauseCount": n,
    }
    assert run["initial"]["submitDisabled"] is True
    whole = run["steps"][-1]
    assert whole["blocks"][target] == {
        "sectionChecked": True, "sectionIndeterminate": False, "ariaChecked": "true",
        "checkState": "all", "clausesTicked": everything, "clauseCount": n,
    }
    assert sorted(whole["submits"]["section"]) == sorted([other, target]) and whole["submits"]["unit"] == units
    assert whole["submitLabel"] == "Add 2 sections →" and whole["submitDisabled"] is False
    _save(client, whole["submits"])

    # ── reload: the server stores one whole section; the script shows its clauses ticked
    html = client.get(sections_path(LAW)).text
    assert _state(html, target) == {"check_state": "all", "section_checked": True, "aria": "true", "units_checked": []}
    run = _run(_blocks(html, [other, target]), [{"click": "unit", "section": target, "index": 1}])
    assert run["initial"]["blocks"][target]["clausesTicked"] == everything
    assert run["initial"]["blocks"][target]["sectionChecked"] is True
    partial = run["steps"][0]
    # unticking the second clause leaves every other clause selected
    assert partial["blocks"][target] == {
        "sectionChecked": False, "sectionIndeterminate": True, "ariaChecked": "mixed",
        "checkState": "some", "clausesTicked": [i for i in everything if i != 2], "clauseCount": n,
    }
    kept = [u for i, u in enumerate(units) if i != 1]
    assert partial["submits"] == {"section": [other], "unit": kept}
    assert partial["submitLabel"] == f"Add 2 sections ({n - 1} clauses partial) →"
    _save(client, partial["submits"])

    # ── reload: those clauses are stored; ticking the missing one promotes to the whole section
    html = client.get(sections_path(LAW)).text
    state = _state(html, target)
    assert state["check_state"] == "some" and state["units_checked"] == kept and state["section_checked"] is False
    run = _run(_blocks(html, [other, target]), [{"click": "unit", "section": target, "index": 1}])
    assert run["initial"]["blocks"][target]["sectionIndeterminate"] is True
    assert run["initial"]["blocks"][target]["clausesTicked"] == [i for i in everything if i != 2]
    promoted = run["steps"][0]
    assert promoted["blocks"][target]["checkState"] == "all" and promoted["blocks"][target]["sectionChecked"] is True
    assert promoted["blocks"][target]["clausesTicked"] == everything
    assert sorted(promoted["submits"]["section"]) == sorted([other, target])
    _save(client, promoted["submits"])

    # ── reload: whole again; unticking the section clears every clause
    html = client.get(sections_path(LAW)).text
    assert _state(html, target)["check_state"] == "all"
    run = _run(_blocks(html, [other, target]), [{"click": "section", "section": target}])
    cleared = run["steps"][0]
    assert cleared["blocks"][target] == {
        "sectionChecked": False, "sectionIndeterminate": False, "ariaChecked": "false",
        "checkState": "none", "clausesTicked": [], "clauseCount": n,
    }
    assert cleared["submits"] == {"section": [other], "unit": []}
    assert cleared["submitLabel"] == "Add 1 section →"
    _save(client, cleared["submits"])
    html = client.get(sections_path(LAW)).text
    assert _state(html, target)["check_state"] == "none"
    assert _state(html, other)["check_state"] == "all"


def test_clicking_an_indeterminate_section_selects_the_whole_section(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    html = client.get(sections_path(LAW)).text
    target, units = _section_with_clauses(html)
    run = _run(_blocks(html, [target]), [
        {"click": "unit", "section": target, "index": 0},     # one clause → partial
        {"click": "section", "section": target},              # click the indeterminate box → whole
        {"click": "section", "section": target},              # click again → nothing
    ])
    one, whole, none = run["steps"]
    assert one["blocks"][target]["checkState"] == "some" and one["blocks"][target]["clausesTicked"] == [1]
    assert one["submits"] == {"section": [], "unit": [units[0]]}
    assert whole["blocks"][target]["checkState"] == "all"
    assert whole["blocks"][target]["clausesTicked"] == list(range(1, len(units) + 1))
    assert none["blocks"][target]["checkState"] == "none" and none["submits"] == {"section": [], "unit": []}
    assert none["submitDisabled"] is True and none["submitLabel"] == "Select sections to add"


def test_the_previous_script_fails_this_cycle(tmp_path: Path) -> None:
    """Guards the harness itself: the behaviour the baseline trace recorded must be
    reproducible here, otherwise a pass above would prove nothing."""
    old_handlers = '''      if (sectionBox) {
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
      });'''
    old_sync = '''    function syncSectionState(block) {
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
      if (allUnits || sectionBox.checked) {
        sectionBox.checked = true;
        sectionBox.indeterminate = false;
        units.forEach(function (box) {
          box.checked = false;
        });
        block.setAttribute("data-check-state", "all");
        return;
      }
      if (mixed) {
        sectionBox.indeterminate = true;
        block.setAttribute("data-check-state", "some");
        return;
      }
      sectionBox.indeterminate = false;
      block.setAttribute("data-check-state", "none");
    }

'''
    js = SCRIPT.read_text(encoding="utf-8")
    a = js.index("    // M7b (Q8). One state per section")
    b = js.index("    function paint() {")
    c = js.index("      if (sectionBox && sectionBox.checked && !sectionBox.disabled) {")
    d = js.index("      var details = $(\"details\", block);")
    old = js[:a] + old_sync + js[b:c] + old_handlers + "\n" + js[d:]
    legacy = tmp_path / "playground-select-legacy.js"
    legacy.write_text(old, encoding="utf-8")

    client = _picker_client(tmp_path / "app")
    html = client.get(sections_path(LAW)).text
    target, _units_ = _section_with_clauses(html)
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        input=json.dumps({"script": str(legacy), "blocks": _blocks(html, [target]),
                          "steps": [{"click": "section", "section": target}, {"click": "unit", "section": target, "index": 1}]}),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    steps = json.loads(proc.stdout)["steps"]
    # the defect: after a whole-section tick, clicking clause 2 leaves only clause 2
    assert steps[0]["blocks"][target]["clausesTicked"] == []
    assert steps[1]["blocks"][target]["clausesTicked"] == [2]
