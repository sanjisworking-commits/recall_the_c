"""M7b — Act progress, section picker, Learn and completion pages.

Decision Q8 of `docs/design/milestones/M7.md` (plan approved 2026-11-16):
a whole-section tick shows every clause ticked; unticking one clause leaves
the rest selected; ticking the last clause promotes back to the whole section;
what the server stores is unchanged.

P01 what the picker submits for each of those three states is saved as the
    decided selection, and the saved state comes back on the page: a whole
    section submitted with its clause values is one whole section; all clauses
    without the section box are promoted to the whole section; all but one
    clause stay as those clauses.
P02 the picker script keeps one state per section (whole / some / none) and
    no longer clears the clause boxes of a whole section; its version pin moved.
P03 the picker page itself is unchanged in markup: a whole section is rendered
    as the section box alone and the script ticks its clauses on load.
P04 Act progress ring: the fraction label and the paper disc share one grid
    cell (they were stacked, which pushed the disc off the ring's centre).
P05 "On the ladder": a rung with sections on it renders a filled bar whose
    height follows its share; the bars no longer collapse to nothing.
P06 Learn, desktop: the mode deck keeps its natural height instead of
    stretching to the text panel.

The click-by-click behaviour in a browser is recorded by
`docs/design/proto-comparison-2026-10-19/m7b/tools/trace_picker_m7b.py`
(baseline and candidate traces in the evidence folder); no browser is
available to the test suite.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.playground.urls import add_path, sections_path
from tests.test_account_family import _client, _csrf, _main

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "constitution_memorizer" / "web" / "static"
TEMPLATES = ROOT / "src" / "constitution_memorizer" / "web" / "templates"
LAW = "bns"


def _post(client: TestClient, path: str, data: dict):
    return client.post(path, data={"csrf_token": _csrf(client), **data}, follow_redirects=False)


def _picker_client(tmp_path: Path, tier_model: str = "monthly") -> TestClient:
    client = _client(tmp_path, "plus", tier_model=tier_model)
    client.get("/playground")
    scope = _post(client, add_path(LAW), {"confirm": "add", "scope": "sections"})
    assert scope.status_code == 303 and scope.headers["location"].endswith(sections_path(LAW))
    return client


def _block(html: str, number: str) -> str:
    main = _main(html)
    marker = main.index(f'data-section="{number}"')
    start = main.rindex("<li", 0, marker)
    end = main.find('class="pg-pick-section', marker)  # the next section's opening tag
    return main[start:end if end != -1 else len(main)]


def _units(block: str) -> list[str]:
    return re.findall(r'name="unit"\s+value="([^"]+)"', block)


def _section_with_clauses(html: str) -> tuple[str, list[str]]:
    for number in re.findall(r'data-section="([^"]+)"', _main(html)):
        units = _units(_block(html, number))
        if len(units) >= 3:
            return number, units
    raise AssertionError("no section with three clauses in the fixture Act")


def _state(html: str, number: str) -> dict:
    block = _block(html, number)
    section_input = block.split('class="pg-pick-check"', 1)[1].split(">", 1)[0]
    return {
        "check_state": re.search(r'data-check-state="([^"]*)"', block).group(1),
        "section_checked": bool(re.search(r"\bchecked\b", section_input.replace("aria-checked", ""))),
        "aria": re.search(r'aria-checked="([^"]*)"', section_input).group(1),
        "units_checked": [
            value
            for value, rest in re.findall(r'name="unit"\s+value="([^"]+)"([^>]*)>', block)
            if re.search(r"\bchecked\b", rest)
        ],
    }


# --------------------------------------------------------------------------- #
# P01 — what the picker submits is what is saved                               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_p01_whole_section_submitted_with_its_clauses_is_one_whole_section(tmp_path: Path, tier_model: str) -> None:
    client = _picker_client(tmp_path, tier_model)
    number, units = _section_with_clauses(client.get(sections_path(LAW)).text)
    # the Q8 picker shows a whole section with every clause ticked, so the form
    # carries the section value and all of its clause values
    saved = _post(client, sections_path(LAW), {"section": [number], "unit": units})
    assert saved.status_code == 303
    state = _state(client.get(sections_path(LAW)).text, number)
    assert state == {"check_state": "all", "section_checked": True, "aria": "true", "units_checked": []}


def test_p01_every_clause_without_the_section_box_is_promoted(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    number, units = _section_with_clauses(client.get(sections_path(LAW)).text)
    assert _post(client, sections_path(LAW), {"unit": units}).status_code == 303
    state = _state(client.get(sections_path(LAW)).text, number)
    assert state["check_state"] == "all" and state["section_checked"] is True and state["units_checked"] == []


def test_p01_all_but_one_clause_stays_as_those_clauses(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    number, units = _section_with_clauses(client.get(sections_path(LAW)).text)
    kept = [u for i, u in enumerate(units) if i != 1]  # the user unticked the second clause
    assert _post(client, sections_path(LAW), {"unit": kept}).status_code == 303
    state = _state(client.get(sections_path(LAW)).text, number)
    assert state["check_state"] == "some" and state["section_checked"] is False and state["aria"] == "mixed"
    assert state["units_checked"] == kept
    # ticking it back and saving promotes to the whole section again
    assert _post(client, sections_path(LAW), {"unit": units}).status_code == 303
    assert _state(client.get(sections_path(LAW)).text, number)["check_state"] == "all"


def test_p01_unticking_everything_in_a_section_removes_it(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    html = client.get(sections_path(LAW)).text
    number, units = _section_with_clauses(html)
    other = next(n for n in re.findall(r'data-section="([^"]+)"', _main(html)) if n != number)
    assert _post(client, sections_path(LAW), {"section": [number, other], "unit": units}).status_code == 303
    assert _post(client, sections_path(LAW), {"section": [other]}).status_code == 303
    after = client.get(sections_path(LAW)).text
    assert _state(after, number)["check_state"] == "none"
    assert _state(after, other)["check_state"] == "all"


# --------------------------------------------------------------------------- #
# P02 — the script                                                             #
# --------------------------------------------------------------------------- #
def test_p02_picker_script_keeps_one_state_per_section() -> None:
    js = (STATIC / "playground-select.js").read_text(encoding="utf-8")
    assert "function setSectionBox(block, sectionBox, state)" in js
    sync = js.split("function syncSectionState(block) {", 1)[1].split("function paint()", 1)[0]
    # the state is derived from the clause boxes; a whole section never clears them
    assert "box.checked = false" not in sync
    assert 'setSectionBox(block, sectionBox, "all")' in sync
    assert 'setSectionBox(block, sectionBox, "some")' in sync
    assert 'setSectionBox(block, sectionBox, "none")' in sync
    handlers = js.split("sectionBlocks().forEach(function (block) {", 2)[2]
    # ticking or unticking the section sets every clause box to the same value
    assert "var on = sectionBox.checked;" in handlers and "box.checked = on;" in handlers
    # a clause change only repaints: it no longer unticks the section by hand
    assert 'box.addEventListener("change", paint);' in handlers
    assert "sectionBox.checked = false;\n          }\n          paint();" not in js
    # a server-rendered whole section gets its clauses ticked on load
    assert "sectionBox.checked && !sectionBox.disabled" in handlers and "box.checked = true;" in handlers
    assert js.count("aria-checked") >= 2  # set in setSectionBox and for the server's indeterminate state
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "playground-select.js?v=pg2" in base and "playground-select.js?v=pg1" not in base


# --------------------------------------------------------------------------- #
# P03 — markup unchanged                                                       #
# --------------------------------------------------------------------------- #
def test_p03_picker_markup_is_unchanged(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    html = client.get(sections_path(LAW)).text
    number, units = _section_with_clauses(html)
    assert _post(client, sections_path(LAW), {"section": [number]}).status_code == 303
    block = _block(client.get(sections_path(LAW)).text, number)
    # whole section: the section box alone is rendered checked, the details stay closed
    assert 'data-check-state="all"' in block and "is-all" in block
    assert _state(client.get(sections_path(LAW)).text, number)["units_checked"] == []
    assert '<details class="pg-pick-expand">' in block
    assert len(_units(block)) == len(units)
    template = (TEMPLATES / "playground_select.html").read_text(encoding="utf-8")
    assert 'name="section"' in template and 'name="unit"' in template
    assert "data-pg-picker-form" in template


# --------------------------------------------------------------------------- #
# P04–P06 — Act progress and Learn layout defects                              #
# --------------------------------------------------------------------------- #
def _m7b_block() -> str:
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert css.count("/* ── M7b · Act progress and Learn: baseline defects") == 1
    return css.split("/* ── M7b · Act progress and Learn: baseline defects", 1)[1]


def test_p04_ring_label_and_disc_share_one_cell() -> None:
    block = _m7b_block()
    rule = block.split(".pg-progress-ring--act > .pg-progress-ring-label,\n.pg-progress-ring--act::after {", 1)[1].split("}", 1)[0]
    assert "grid-area: 1 / 1;" in rule
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    # the ring is still a grid that centres its content; only the placement was missing
    ring = css.split(".pg-progress-ring {", 1)[1].split("}", 1)[0]
    assert "display: grid;" in ring and "place-items: center;" in ring
    template = (TEMPLATES / "playground_law.html").read_text(encoding="utf-8")
    assert '<span class="pg-progress-ring-label">{{ progress.fraction_label }}</span>' in template


def test_p05_ladder_bars_take_their_height_from_the_rung(tmp_path: Path) -> None:
    block = _m7b_block()
    bar = block.split(".pg-rung-bar--act .pg-rung {", 1)[1].split("}", 1)[0]
    assert "flex: 0 0 auto;" in bar  # no longer a zero-basis flex item
    assert "height: calc(var(--pg-rung-h, 0%) * 0.5);" in bar and "min-height: 2px;" in bar
    assert ".pg-rung-bar--act {\n  align-items: stretch;\n}" in block
    assert ".pg-rung-bar--act .pg-rung.is-filled {\n  background: var(--pg-teal);\n}" in block

    from datetime import date, timedelta

    from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
    from tests.test_account_family import USER

    client = _picker_client(tmp_path)
    assert _post(client, sections_path(LAW), {"section": ["1", "2"]}).status_code == 303
    repo = client.app.state.playground
    for mode in PLAYGROUND_LEARN_MODES:  # section 1 learned: it stands on the first rung
        repo.complete_mode(USER, LAW, f"{LAW}:section:1", mode, source_version="v", source_hash="h",
                           as_of=date.today() - timedelta(days=1))
    page = _main(client.get(f"/playground/laws/{LAW}").text)
    chart = page.split('class="pg-rung-bar pg-rung-bar--act"', 1)[1].split("</div>", 1)[0]
    cols = chart.split('class="pg-rung-col"')[1:]
    assert len(cols) == 6
    filled = [c for c in cols if 'class="pg-rung pg-grow is-filled"' in c]
    empty = [c for c in cols if 'class="pg-rung pg-grow"' in c]
    assert len(filled) == 1 and len(empty) == 5
    assert '<span class="pg-rung-count">1</span>' in filled[0]
    assert "--pg-rung-h: 0%" not in filled[0]
    assert all('<span class="pg-rung-count">0</span>' in c for c in empty)


def test_p06_learn_deck_keeps_its_natural_height_on_desktop() -> None:
    block = _m7b_block()
    media = block.split("@media (min-width: 1040px) {", 1)[1]
    deck = media.split(".pg-learn-deck {", 1)[1].split("}", 1)[0]
    assert "align-content: start;" in deck and "align-self: start;" in deck
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "playground.css?v=pg59" in base
