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
P06 Learn: the mode deck is retired; the six mode tabs remain as links with
    the current and completed marks; at 1040 px the stage is one reading column.
P07 Learn action bar: each mode's primary action carries the bar class; the
    bar sticks only in a wide and tall window, is ordinary flow elsewhere, is
    not drawn while its only button is hidden, and the page keeps focused
    controls clear of it.
P08 Act progress: three groups in today's order (lead, charts, actions) that
    form two columns from 900 px on the theme's paper surface; the badge sits
    beside the title there.
P09 Completion pages: tick badge, the Act's name beside the citation, a ladder
    row that runs Learned, six days, Mastered, with reached / next / to-come
    said in text and drawn differently; the first-revision line and Continue
    stay; no quotation.
P10 Picker chapter headings: still h2, in the small label style from 561 px.
P11 Learn control sizes: "Reveal all", the letters practice-style switch and
    each test answer's whole label reach 44 px.

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
from tests.test_account_family import _client, _csrf, _main, _text

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


def _design_block() -> str:
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert css.count("/* ── M7b · design batch") == 1
    return css.split("/* ── M7b · design batch", 1)[1]


def _learn_client(tmp_path: Path) -> TestClient:
    client = _picker_client(tmp_path)
    assert _post(client, sections_path(LAW), {"section": ["1", "2"]}).status_code == 303
    return client


LEARN = f"/playground/laws/{LAW}/sections/1/learn"
MODES = ("read", "cloze", "letters", "type", "recite", "test")


def test_p06_learn_has_tabs_and_no_deck(tmp_path: Path) -> None:
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    template = (TEMPLATES / "playground_learn.html").read_text(encoding="utf-8")
    assert "pg-learn-deck" not in css and "pg-learn-card" not in css
    assert "pg-learn-deck" not in template and "learn-deck-card" not in template
    block = _design_block()
    column = block.split("@media (min-width: 1040px) {", 1)[1].split(".pg-learn {", 1)[1].split("}", 1)[0]
    assert "max-width: 760px;" in column and "margin-left: auto;" in column and "margin-right: auto;" in column

    client = _learn_client(tmp_path)
    done = client.post(f"{LEARN}/read/complete", data={"csrf_token": _csrf(client)})
    assert done.status_code == 200
    for mode in MODES:
        html = client.get(f"{LEARN}/{mode}").text
        page = _main(html)
        assert "learn-deck-card" not in page and "pg-learn-deck" not in page, mode
        tabs = page.split('class="mode-tabs pg-mode-tabs" role="tablist"', 1)[1].split("</div>", 1)[0]
        links = re.findall(r'<a\s+class="mode-tab([^"]*)"\s+role="tab"\s+aria-selected="(true|false)"\s+(aria-current="page"\s+)?href="([^"]+)"\s*>([^<]+)</a>', tabs)
        assert len(links) == 6, (mode, len(links))
        # every mode is a link to its own page; exactly one is current; Read carries the completed mark
        assert [href.rsplit("/", 1)[1] for _c, _s, _cur, href, _l in links] == list(MODES)
        current = [href.rsplit("/", 1)[1] for _c, sel, cur, href, _l in links if sel == "true" and cur]
        assert current == [mode]
        read_classes, read_label = links[0][0], links[0][4].strip()
        assert "is-done" in read_classes and read_label == "Read ✓"
        assert all("✓" not in l for _c, _s, _cur, _h, l in links[1:])
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "playground.css?v=pg61" in base


def test_p07_action_bar_rules_and_markup(tmp_path: Path) -> None:
    block = _design_block()
    media = block.split("@media (min-width: 900px) and (min-height: 600px) {", 1)[1]
    bar = media.split(".pg-learn .pg-learn-actionbar {", 1)[1].split("}", 1)[0]
    assert "position: sticky;" in bar and "bottom: 0;" in bar
    assert "background: var(--pg-page);" in bar  # a theme colour, opaque, so text does not show through
    assert ".pg-learn .pg-learn-actionbar:not(:has(> :not([hidden]))) {\n    display: none;" in media
    assert "html:has([data-pg-learn]) {\n    scroll-padding-bottom: 96px;" in media
    # outside that query the bar has no positioning of its own: ordinary flow on phones,
    # short windows and under zoom
    outside = block.replace(media.split("\n}\n", 1)[0], "")
    assert "position: sticky" not in outside and "position: fixed" not in block
    # the page wrappers clip instead of hiding overflow so the window is the scroller
    assert "overflow-x: clip;" in media

    client = _learn_client(tmp_path)
    for mode in MODES:
        page = _main(client.get(f"{LEARN}/{mode}").text)
        panel = page.split(f'data-pg-learn-panel="{mode}"', 1)[1]
        assert panel.count("pg-learn-actionbar") == 1, mode
        bar_html = panel.split("pg-learn-actionbar", 1)[1].split("</p>" if mode != "read" else "</div>", 1)[0]
        assert "pg-btn" in bar_html, mode
        if mode == "test":
            assert 'type="submit"' in bar_html
        elif mode == "type":
            assert "data-type-check" in bar_html and "data-pg-complete" in bar_html
        else:
            assert "data-pg-complete" in bar_html
    # recite: the completion action is hidden until an accuracy check, so its bar is not drawn yet
    recite = _main(client.get(f"{LEARN}/recite").text)
    assert re.search(r'pg-learn-actionbar">\s*<button type="button" class="pg-btn" data-pg-complete hidden>', recite)


def test_p08_act_progress_groups_and_desktop_columns(tmp_path: Path) -> None:
    client = _learn_client(tmp_path)
    page = _main(client.get(f"/playground/laws/{LAW}").text)
    order = [page.index(marker) for marker in (
        'class="pg-act-body"', 'class="pg-act-lead"', 'class="pg-act-ring-row"', 'class="pg-act-charts"',
        'class="pg-waffle"', 'class="pg-rung-bar pg-rung-bar--act"', 'class="pg-act-actions"', 'class="pg-actions pg-act-cta"',
    )]
    assert order == sorted(order)  # the same reading order as before: ring, sections, ladder, actions
    assert page.count('class="pg-act-body"') == 1
    block = _design_block()
    media = block.split("@media (min-width: 900px) {", 1)[1].split("/* F3", 1)[0]
    body = media.split(".pg-act-body {", 1)[1].split("}", 1)[0]
    assert "display: grid;" in body and '"lead charts"' in body and '"actions charts"' in body
    assert "background: var(--pg-paper);" in body and "border: 1px solid var(--pg-hairline);" in body
    assert "#fff" not in body and "white" not in body  # theme colours, not a hard-coded white
    head = media.split(".pg-act-head {", 1)[1].split("}", 1)[0]
    assert "display: flex;" in head and "flex-wrap: wrap;" in head
    # nothing in the design block styles these groups below 900px: the phone stays one column
    before_media = block.split("@media (min-width: 900px) {", 1)[0]
    assert ".pg-act-body" not in before_media and ".pg-act-lead" not in before_media
    # a law with nothing selected keeps its empty state and its actions inside the body
    client.get("/playground")
    empty_client = _picker_client(tmp_path / "empty")
    empty = _main(empty_client.get(f"/playground/laws/{LAW}", follow_redirects=True).text)
    if 'class="pg-act-body"' in empty:
        assert 'class="pg-act-empty"' in empty and 'class="pg-act-actions"' in empty


def _complete(client: TestClient, number: str, *, ladder: bool) -> None:
    from datetime import date, timedelta

    from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
    from tests.test_account_family import USER

    repo = client.app.state.playground
    today = date.today()
    start = today - timedelta(days=130) if ladder else today
    for mode in PLAYGROUND_LEARN_MODES:
        repo.complete_mode(USER, LAW, f"{LAW}:section:{number}", mode, source_version="v", source_hash="h", as_of=start)
    if ladder:
        cursor = start + timedelta(days=1)
        for rung in (1, 3, 7, 15, 30, 60):
            for mode in PLAYGROUND_LEARN_MODES:
                repo.complete_revision_mode_and_advance_if_ready(
                    USER, LAW, f"{LAW}:section:{number}", mode, source_version="v", source_hash="h",
                    as_of=cursor, claimed_rung=rung)
            cursor += timedelta(days={1: 3, 3: 7, 7: 15, 15: 30, 30: 60, 60: 0}[rung])


def _ladder(page: str) -> list[tuple[str, str]]:
    row = page.split('class="pg-complete-ladder" role="list" aria-label="Revision ladder"', 1)[1].split("</div>", 1)[0]
    chips = re.findall(r'<span\s+class="pg-complete-chip([^"]*)"\s+role="listitem"\s*>(.*?)</span>\s*(?=<span\s+class="pg-complete-chip|$)', row.strip(), flags=re.S)
    return [(cls.strip(), _text(body)) for cls, body in chips]


def test_p09_completion_pages(tmp_path: Path) -> None:
    client = _learn_client(tmp_path)
    _complete(client, "1", ladder=False)
    _complete(client, "2", ladder=True)
    learned = _main(client.get(f"/playground/laws/{LAW}/sections/1/learned").text)
    mastered = _main(client.get(f"/playground/laws/{LAW}/sections/2/mastered").text)
    for page in (learned, mastered):
        assert '<span class="pg-complete-badge" aria-hidden="true">✓</span>' in page
        assert ">Continue</a>" in page and f'href="/playground/laws/{LAW}"' in page
        assert "Verbatim, always." in page
        assert "Ambedkar" not in page and "<blockquote" not in page  # no quotation is invented
    kicker = _text(learned.split('class="pg-complete-kicker">', 1)[1].split("</p>", 1)[0])
    assert kicker.startswith("Section 1 · ") and len(kicker) > len("Section 1 · ")
    assert "Section learned." in learned and "First revision · Day 1" in learned  # the working next step stays

    steps = _ladder(learned)
    assert [t.split(" —")[0].replace(" ✓", "") for _c, t in steps] == ["Learned", "Day 1", "Day 3", "Day 7", "Day 15", "Day 30", "Day 60", "Mastered"]
    assert steps[0] == ("pg-complete-chip--end is-done", "Learned ✓ — reached")
    assert steps[1] == ("is-next", "Day 1 — next")
    assert all(cls == "" and text.endswith("— to come") for cls, text in steps[2:7])
    assert steps[7] == ("pg-complete-chip--end", "Mastered — to come")

    steps = _ladder(mastered)
    assert len(steps) == 8 and all("is-done" in cls and text.endswith("✓ — reached") for cls, text in steps)

    block = _design_block()
    plain = block.split(".pg-complete-chip {", 1)[1].split("}", 1)[0]
    nxt = block.split(".pg-complete-chip.is-next {", 1)[1].split("}", 1)[0]
    done = block.split(".pg-complete-chip.is-done {", 1)[1].split("}", 1)[0]
    # three different drawings: plain outline, accent outline, accent fill
    assert "background: transparent;" in plain and "color: var(--pg-muted);" in plain
    assert "gap: 4px;" in plain  # the tick does not sit flush against the word
    assert "background: transparent;" in nxt and "color: var(--pg-teal);" in nxt
    assert "background: var(--pg-teal);" in done and "color: var(--pg-paper);" in done
    assert _contrast("#9a9a9a", "#141414") >= 4.5  # the to-come step on the completion surface (was 4.49:1 on its fill)
    assert _contrast("#7fc4ba", "#141414") >= 4.5 and _contrast("#1d1d1d", "#7fc4ba") >= 4.5


def _contrast(fg: str, bg: str) -> float:
    def lum(hex_colour: str) -> float:
        channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_p09_completion_surface_tokens_are_the_ones_measured() -> None:
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    surface = css.split(".pg-surface--fixed-dark,", 1)[1].split("}", 1)[0]
    assert "background: #141414;" in surface and "--pg-muted: #9a9a9a;" in surface
    assert "--pg-teal: #7fc4ba;" in surface and "--pg-paper: #1d1d1d;" in surface


def test_p10_picker_chapter_headings_are_small_h2(tmp_path: Path) -> None:
    client = _picker_client(tmp_path)
    page = _main(client.get(sections_path(LAW)).text)
    assert re.search(r'<h2 class="pg-pick-chapter">CHAPTER [IVXLC]+ · ', page)  # still a heading
    block = _design_block()
    rule = block.split("@media (min-width: 561px) {\n  .PlaygroundShell h2.pg-pick-chapter {", 1)[1].split("}", 1)[0]
    assert "font-family: var(--pg-font-ui);" in rule and "font-size: var(--pg-label-size);" in rule
    # clause selection and the indeterminate state are untouched
    assert 'class="pg-pick-clause-check"' in page and 'name="unit"' in page


def test_p11_learn_controls_reach_the_target(tmp_path: Path) -> None:
    block = _design_block()
    sized = block.split(".pg-learn .learn-cloze-btn,\n.pg-learn .learn-letters-view-btn {", 1)[1].split("}", 1)[0]
    assert "min-height: var(--pg-tap);" in sized and "min-width: var(--pg-tap);" in sized
    option = block.split(".pg-learn .learn-test-opt {", 1)[1].split("}", 1)[0]
    assert "display: flex;" in option and "min-height: var(--pg-tap);" in option
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert "--pg-tap: 44px;" in css
    client = _learn_client(tmp_path)
    test_page = _main(client.get(f"{LEARN}/test").text)
    # every answer's radio sits inside its label, so the label is the click target
    for label in re.findall(r'<label class="learn-test-opt">(.*?)</label>', test_page, flags=re.S):
        assert 'class="learn-test-opt-input" type="radio"' in label and 'class="learn-test-opt-text"' in label
    cloze = _main(client.get(f"{LEARN}/cloze").text)
    assert ('data-cloze-action="toggle-all"' in cloze) or ("This provision is short" in cloze)
    letters = _main(client.get(f"{LEARN}/letters").text)
    assert letters.count("learn-letters-view-btn") == 2
