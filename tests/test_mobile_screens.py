"""Backing view-models and routes for the phone designs (Mobile Screens 01–24).

Covers only what the phone layouts added on the server: the Part drill-down
route (designs 02/03/16), the Revisions view-model (19), the Today "Upcoming"
strip (01), and the mobile chrome the base template emits.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.browse import (
    browse_parts_sections,
    find_part_section,
    part_href,
    part_progress_summary,
    part_slug,
)
from constitution_memorizer.web.calendar_view import build_revisions_view
from constitution_memorizer.web.dashboard import upcoming_revisions

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine, Path]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine, db


# ── Part slugs and hrefs ─────────────────────────────────────────────────────


def test_part_slug_handles_spaces_and_dots():
    assert part_slug("III") == "iii"
    assert part_slug("IV A") == "iv-a"
    assert part_slug("XIV.A") == "xiva"
    assert part_href("IV A") == "/browse/part/iv-a"


def test_find_part_section_matches_on_slug(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    sections = browse_parts_sections(engine, None)
    wanted = sections[0].part_number
    assert find_part_section(sections, part_slug(wanted)) is sections[0]
    assert find_part_section(sections, "not-a-part") is None


# ── Part progress summary (the "3 of 4 learned" line on each Part card) ──────


def test_part_progress_summary_counts_learned_articles(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    sections = browse_parts_sections(engine, None)
    section = next(s for s in sections if s.cards)

    before = part_progress_summary(engine, section)
    assert before.learned == 0
    assert before.percent == 0
    assert before.label == "Not started"
    assert before.total == len(section.cards)

    for unit_id in list(engine.units):
        engine.mark_all_modes_seen(unit_id)
        engine.mark_done(unit_id)
    after = part_progress_summary(engine, section)
    assert after.learned == after.total
    assert after.percent == 100
    assert after.label == f"{after.total} of {after.total} learned"


def test_part_progress_summary_reports_due_count(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    sections = browse_parts_sections(engine, None, as_of=today)
    section = next(s for s in sections if s.cards)
    assert part_progress_summary(engine, section, today=today).due_count == 1


# ── /browse/part/{slug} ──────────────────────────────────────────────────────


def test_browse_part_route_renders_article_rows(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    sections = browse_parts_sections(engine, None)
    section = next(s for s in sections if s.cards)
    response = client.get(part_href(section.part_number))
    assert response.status_code == 200
    html = response.text
    assert f"Part {section.part_number}" in html
    assert "part-row" in html
    assert "← All Parts" in html
    for card in section.cards:
        assert f"Art. {card.article_number}" in html


def test_browse_part_route_404s_on_unknown_part(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    assert client.get("/browse/part/zzz").status_code == 404


def test_browse_index_links_every_part_to_its_page(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    html = client.get("/browse").text
    assert "browse-part-rail" in html
    for section in browse_parts_sections(engine, None):
        assert part_href(section.part_number) in html


def test_browse_index_phone_cards_match_redesign(tmp_path: Path):
    """Phone Browse is Part cards + Reference, not the desktop article grid."""
    client, _, _ = _client(tmp_path)
    html = client.get("/browse").text
    assert 'class="browse-part-rail"' in html
    assert "part-card-track" in html
    assert 'class="browse-reference"' in html
    assert 'href="/laws"' in html
    assert 'href="/tables"' in html
    assert "Relevant laws" in html
    css = client.get("/static/mobile.css").text
    card = css.split(".part-card {", 1)[1].split("}", 1)[0]
    assert "border-radius: var(--rc-radius-card)" in card
    track = css.split(".part-card-track {", 1)[1].split("}", 1)[0]
    assert "height: 4px" in track
    fill = css.split(".part-card-fill {", 1)[1].split("}", 1)[0]
    assert "var(--rc-teal)" in fill
    due = css.split(".part-card-due {", 1)[1].split("}", 1)[0]
    assert "var(--rc-teal-tint)" in due


def test_browse_part_rows_use_node_status(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    sections = browse_parts_sections(engine, None)
    section = next(s for s in sections if s.cards)
    html = client.get(part_href(section.part_number)).text
    assert "part-row-node" in html
    assert "part-row-status" in html
    assert "part-head-progress" in html
    assert "Not started" in html


def test_part_page_title_sits_under_all_parts(tmp_path: Path):
    """The shared topbar is 44px + 4px margin, which read as a hole between
    All Parts and PART III / the title. The part screen sizes that row to
    the Marks chip and drops the extra margin."""
    client, engine, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    topbar = css.split(
        'body[data-mscreen="part"] .mobile-topbar {', 1
    )
    # The last (tightening) rule, not the shared padding/background block.
    tight = topbar[-1].split("}", 1)[0]
    assert "min-height: 36px" in tight
    assert "margin: 0" in tight
    back = css.split(
        'body[data-mscreen="part"] .mobile-back {', 1
    )[1].split("}", 1)[0]
    assert "min-height: 36px" in back
    head_block = css.split(
        "body[data-mscreen=\"part\"] .part-head {\n    padding-top: 4px;", 1
    )
    assert len(head_block) == 2
    sections = browse_parts_sections(engine, None)
    section = next(s for s in sections if s.cards)
    html = client.get(part_href(section.part_number)).text
    assert "← All Parts" in html
    assert "part-head-title" in html


def test_article_page_links_back_to_its_part(tmp_path: Path):
    """The phone's back link needs a Part even with no reviewed Bare Act."""
    client, _, _ = _client(tmp_path)
    html = client.get("/browse/article/20").text
    assert "/browse/part/iii" in html
    assert "← Part III" in html


# ── Revisions (design 19) ────────────────────────────────────────────────────


def test_revisions_view_week_strip_is_seven_days_around_today(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 8, 21)
    view = build_revisions_view(engine, today=today)
    assert len(view.week) == 7
    assert view.week[0].iso == (today - timedelta(days=1)).isoformat()
    assert view.week[1].is_today is True
    assert sum(1 for d in view.week if d.is_today) == 1
    assert view.month_label == "August 2026"


def test_revisions_view_sorts_overdue_then_due_then_done(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 8, 21)
    # clause-1 lands on the 1-day rung 3 days ago → overdue today.
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=3))
    # clause-2 completed today → done.
    engine.mark_all_modes_seen("clause-2")
    engine.mark_done("clause-2", as_of=today)
    view = build_revisions_view(engine, today=today)
    states = [row.state for row in view.rows]
    assert states == sorted(states, key=lambda s: {"overdue": 0, "due": 1, "done": 2}[s])
    assert "overdue" in states
    assert "done" in states
    assert view.today_label.startswith("Today · 1 unit")


def test_revisions_view_labels_an_empty_and_an_all_done_day(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 8, 21)
    assert build_revisions_view(engine, today=today).today_label == "Today · nothing due"
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today)
    assert build_revisions_view(engine, today=today).today_label == "Today · all done"


def test_revisions_ladder_covers_every_rung(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1")
    view = build_revisions_view(engine)
    assert [rung.label for rung in view.ladder] == [
        "Day 1",
        "Day 3",
        "Day 7",
        "Day 15",
        "Day 30",
        "Day 60",
    ]
    assert sum(rung.count for rung in view.ladder) == 1
    assert max(rung.percent for rung in view.ladder) == 100


def test_calendar_grid_renders_for_every_month(tmp_path: Path):
    """Regression: the phone block used to be gated on `revisions`, which the
    route only builds for the current month — so the nav arrows led to a blank
    page. The grid works off calendar.days and must render for any month; only
    the Today list is today-specific."""
    client, _, _ = _client(tmp_path)
    today = date.today()
    here = client.get("/calendar").text
    assert "cal-m-grid" in here
    assert "data-today-list" in here

    away = client.get(f"/calendar?year={today.year - 1}&month={today.month}")
    assert away.status_code == 200
    assert "revisions-mobile" in away.text
    assert "cal-m-grid" in away.text
    assert "cal-m-legend" in away.text
    # No "Today · N units" on a month that is not this one.
    assert "data-today-list" not in away.text


def test_calendar_days_are_openable(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1")
    html = client.get("/calendar").text
    # Cells are buttons carrying their date, with a per-day list to reveal.
    assert 'class="cal-m-cell' in html
    assert "data-day-list=" in html
    assert "data-day-empty" in html
    js = client.get("/static/mobile.js").text
    assert "initCalendarDays" in js


# ── Today's Upcoming strip (design 01) ───────────────────────────────────────


def test_upcoming_revisions_lists_future_days_soonest_first(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 8, 21)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today)
    rows = upcoming_revisions(engine, as_of=today)
    assert rows
    assert rows[0]["when"] == "Tomorrow"
    assert rows[0]["rung"] == "Day 1"
    assert rows[0]["href"] == "/learn/clause-1"


def test_upcoming_revisions_excludes_today_and_the_past(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 8, 21)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=3))
    assert upcoming_revisions(engine, as_of=today) == []


# ── Mobile chrome emitted by base.html ───────────────────────────────────────


def test_designed_screens_declare_their_mobile_screen(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    for path, screen in (
        ("/browse", "browse"),
        ("/browse/article/20", "article"),
        ("/browse/part/iii", "part"),
        ("/search", "search"),
        ("/calendar", "revisions"),
        ("/settings", "settings"),
    ):
        html = client.get(path).text
        assert f'data-mscreen="{screen}"' in html, path


def test_mobile_assets_are_linked_once(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/browse").text
    assert html.count("/static/mobile.css") == 1
    assert html.count("/static/mobile.js") == 1


# ── Learn action bar (Next → … → Done → quote) ───────────────────────────────


def test_learn_page_renders_the_next_action_bar(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1").text
    assert "learn-mode-nav" in html
    assert "data-mode-next" in html
    assert 'class="learn-mode-next"' in html


def test_quiz_submit_is_bound_to_its_form_by_id(tmp_path: Path):
    """The phone moves the submit into the action bar, outside the form —
    only the form= association keeps it submitting."""
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1?mode=test").text
    assert 'id="learn-quiz-form"' in html
    assert 'form="learn-quiz-form"' in html


def test_learn_mode_inits_run_after_their_dependencies(tmp_path: Path):
    """Regression: initLetters fires its callback during init when the saved
    Letters view is "Just read", and that callback reads `lockedModes`. With
    the inits constructed above that declaration it threw a temporal dead zone
    error and took the whole Learn page down."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    locked_decl = js.index("const lockedModes = parseModes(")
    for init in ("initCloze(clozePanel", "initLetters(lettersPanel", "initType(typePanel"):
        assert locked_decl < js.index(init), init


# ── Type mode must not show the answer while you type ────────────────────────


def test_type_panel_never_renders_the_bare_act_wording(tmp_path: Path):
    """Checking reports the score; it does not print the answer. The mirror
    shows the user's own words, colour-coded, and that is the whole feedback —
    otherwise a junk attempt plus a tap would hand over the text to copy."""
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1?mode=type").text
    assert "data-type-mirror" in html
    assert 'class="learn-type-field"' in html
    assert "data-type-count" in html
    assert "data-type-fix" in html
    # No corrections surface at all.
    assert "data-type-diff" not in html
    js = client.get("/static/app.js").text
    assert "renderCorrections" not in js


def test_type_mirror_never_renders_source_words(tmp_path: Path):
    """The whole point of the mode: while typing, only the user's own tokens
    reach the DOM. `renderMirror` must write the token it is iterating, never
    `words[i]` — that regression is what put the full clause on screen."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    body = js[js.index("function renderMirror("): js.index("function renderStats(")]
    assert "span.textContent = part;" in body
    assert "words[" not in body, "renderMirror must not read the source text"


def test_type_field_css_hides_the_textarea_glyphs(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    overlay = css.split("\n.learn-type-input {\n  position: relative;", 1)[1].split("}", 1)[0]
    assert "-webkit-text-fill-color: transparent" in overlay
    assert "caret-color: var(--ink)" in overlay
    # A draggable or scrolling textarea slides out from under its mirror.
    assert "resize: none" in overlay
    assert "overflow: hidden" in overlay
    # Anchor past the shared block, whose selector list ends the same way.
    mirror = css.split("\n.learn-type-mirror {\n  position: relative;", 1)[1].split("}", 1)[0]
    assert "user-select: none" in mirror
    assert "pointer-events: none" in mirror


def test_type_layers_share_one_metric_block(tmp_path: Path):
    """The rule that stops this technique rotting: every metric-affecting
    property is set on both layers at once. A font-size or line-height on one
    layer alone drifts the underlines off their words, one line at a time."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    shared = css.split(".learn-type-input,\n.learn-type-mirror {", 1)[1].split("}", 1)[0]
    for prop in (
        "padding: 14px",
        "white-space: pre-wrap",
        "overflow-wrap: break-word",
        "-webkit-text-size-adjust: 100%",
        "font-optical-sizing: none",
    ):
        assert prop in shared, prop
    # Ratio line-heights round differently in a textarea than in a block box.
    assert "line-height: 26px" in shared
    assert "line-height: 1.6" not in shared
    # `pretty` would balance the mirror's last line and rewrap it alone.
    assert "text-wrap: wrap" in shared


def test_no_solo_metric_rule_for_the_type_input(tmp_path: Path):
    """Guards the same discipline across both stylesheets."""
    import re

    client, _, _ = _client(tmp_path)
    for asset in ("/static/styles.css", "/static/mobile.css"):
        css = client.get(asset).text
        for match in re.finditer(r"([^{}]*\.learn-type-input[^{}]*)\{([^}]*)\}", css):
            selector, body = match.group(1).strip(), match.group(2)
            if "learn-type-mirror" in selector:
                continue
            for prop in ("font-size", "line-height", "letter-spacing", "padding", "font-family"):
                assert prop + ":" not in body, f"{asset}: {selector} sets {prop} alone"


def test_type_correctness_is_not_colour_alone(tmp_path: Path):
    """Teal vs amber flattens to one colour under forced-colors and is lost to
    colour blindness; the underline style carries the distinction too."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    assert "underline solid var(--browse-due)" in css
    assert "underline wavy var(--browse-mark-news)" in css


def test_type_js_handles_composition_and_restore(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    for hook in ("compositionstart", "compositionupdate", "compositionend", "pageshow"):
        assert hook in js, hook


def test_type_check_button_is_the_only_reveal(tmp_path: Path):
    """No second CTA was added — Check is still the sole control."""
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1?mode=type").text
    assert html.count("data-type-check") == 1
    assert "Check my attempt" in html


# ── Learn deck: cards, Next rotation, single CTA ─────────────────────────────


def test_tab_marks_cannot_reach_the_deck_cards(tmp_path: Path):
    """Regression: `tabs` used to select every [data-learn-mode] element, which
    includes the phone's deck cards. applyTabMarks then rewrote each card's
    textContent to "Read ✓", wiping its title, description and status footer
    and leaving the deck looking empty."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    assert 'querySelectorAll(".mode-tab")' in js
    assert 'const tabs = Array.from(learn.querySelectorAll("[data-learn-mode]"))' not in js


def test_deck_cards_ship_their_full_content(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1").text
    assert "learn-deck-card-eyebrow" in html
    assert "learn-deck-card-title" in html
    assert "learn-deck-card-lede" in html
    assert "learn-deck-card-state" in html
    # One card per mode, each with its numbered eyebrow.
    assert html.count("learn-deck-card-title") == 6
    assert "01 · READ" in html


def test_next_walks_only_outstanding_modes(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    for helper in ("pendingModes", "nextTarget", "isModeDone"):
        assert helper in js, helper
    # Positional "is this the last mode" is what the pending set replaced.
    assert "isLastMode" not in js


def test_next_is_constant_and_yields_only_to_a_live_mic(tmp_path: Path):
    """Design 3b: "Next is constant on the right — it never moves, whatever
    the mode brings." The single exception is an open mic (3c/3d), where the
    record button takes the primary slot. Nothing else may hide it, or a gate
    becomes a dead end instead of a stated reason."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    assert "GATE_ACTIONS" not in js
    assert "is-promoted" not in js
    assert "nextBtn.hidden" not in js

    css = client.get("/static/mobile.css").text
    assert ".learn-mode-nav.is-recording .learn-mode-next" in css
    assert ".learn-mode-nav.is-solo-cta .learn-mode-next" in css
    # Exactly two rules may take Next off screen: a live mic, and Type — whose
    # own check button morphs into the advance. Nothing else may quietly hide
    # the exit, or a gate becomes a dead end instead of a stated reason.
    hiding = [
        block
        for block in css.split("}")
        if "learn-mode-next" in block and "display: none" in block
    ]
    assert len(hiding) == 2, hiding
    assert any("is-recording" in block for block in hiding)
    assert any("is-solo-cta" in block for block in hiding)


def test_recording_state_uses_tokens_not_raw_hex(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    rec = css.split(".rec-dot {", 1)[1].split("}", 1)[0]
    assert "var(--recording-indicator)" in rec
    assert "#3ba08f" not in rec
    styles = client.get("/static/styles.css").text
    assert "--recording-indicator:" in styles
    assert "--calendar-done:" in styles


def test_morphing_buttons_reserve_their_widest_label(tmp_path: Path):
    """Relabelling must not reflow the bar."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    for selector in (
        ".learn-mode-nav .learn-type-check",
        ".learn-mode-nav .learn-test-submit",
        ".learn-mode-nav .learn-recite-toggle",
        ".learn-mode-nav .learn-letters-speak",
        ".learn-mode-nav .learn-cloze-btn",
        ".learn-mode-next",
    ):
        block = css.split(selector + " {", 1)[1].split("}", 1)[0]
        assert "min-width" in block, selector


def test_phone_drops_again_tomorrow_and_the_ledger_line(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    for selector in (
        'body[data-mscreen="learn"] .learn-action-again',
        'body[data-mscreen="learn"] [data-guest-action="again"]',
        'body[data-mscreen="learn"] .learn-meta',
    ):
        assert selector in css, selector
    # Still served for desktop — hidden by CSS, not removed from the template.
    assert "Again tomorrow" in client.get("/learn/clause-1").text


def test_desktop_hides_phone_article_chrome_and_learn_ledger(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    block = css.split("@media (min-width: 561px)", 1)[1].split("@media", 1)[0]
    for selector in (
        ".eyebrow-phone",
        ".article-phone-meta",
        ".methods-tracker",
        ".learn-meta",
    ):
        assert selector in block, selector
    html = client.get("/browse/article/20").text
    assert "eyebrow-phone" in html
    assert "article-phone-meta" in html or "browse-article-meta" in html


def test_clause_rail_shows_labels_without_per_clause_counts(tmp_path: Path):
    """The rail names the sibling clauses and marks the current one. The
    per-clause "2/6" is gone: it asked the reader to track six separate
    method counts across the rail while already reading one for the clause
    they were on."""
    client, engine, _ = _client(tmp_path)
    engine.mark_all_modes_seen("clause-1")
    html = client.get("/learn/clause-1").text
    if "sibling-chip" in html:
        assert "sibling-chip-count" not in html
        assert "6/6" not in html
        # The rail itself still works — label plus current-state marker.
        assert 'aria-current="true"' in html


# ── Calendar tab + month grid (handoff §1–§3) ────────────────────────────────


def test_fourth_tab_reads_calendar():
    """The signed-in tab bar only renders under multiuser, which this fixture
    is not, so assert the template contract directly."""
    base = (
        Path(__file__).parent.parent
        / "src/constitution_memorizer/web/templates/base.html"
    ).read_text()
    tabbar = base.split('class="mobile-tabbar" aria-label="Mobile"', 1)[1].split(
        "</nav>", 1
    )[0]
    assert ">Calendar</a>" in tabbar
    assert ">Profile</a>" in tabbar
    assert ">Learn</a>" not in tabbar
    assert ">Revisions</a>" not in tabbar
    assert 'href="/calendar"' in tabbar
    assert 'href="/progress"' in tabbar
    assert "path.startswith('/progress')" in tabbar
    # Calendar must not also light up on Profile.
    calendar_line = [line for line in tabbar.splitlines() if 'href="/calendar"' in line][0]
    assert "/progress" not in calendar_line


def test_dominant_kind_priority(tmp_path: Path):
    from constitution_memorizer.web.calendar_view import CalendarChip, CalendarDay

    def chip(kind):
        return CalendarChip(kind=kind, unit_id="u", label="l", title="t")

    # ChipKind has no "overdue" — a past day holding a due chip is one.
    assert CalendarDay(1, "i", is_past=True, chips=[chip("due")]).dominant_kind == "overdue"
    assert CalendarDay(1, "i", chips=[chip("due")]).dominant_kind == "due"
    assert CalendarDay(1, "i", chips=[chip("scheduled")]).dominant_kind == "scheduled"
    assert CalendarDay(1, "i", chips=[chip("review_done")]).dominant_kind == "done"
    # Most urgent wins when a day carries several.
    mixed = CalendarDay(1, "i", is_past=True, chips=[chip("review_done"), chip("due")])
    assert mixed.dominant_kind == "overdue"
    assert CalendarDay(1, "i").dominant_kind is None


def test_phone_calendar_renders_a_month_grid(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/calendar").text
    assert "cal-m-grid" in html
    assert "cal-m-legend" in html
    # The week strip and the ladder are superseded.
    assert "revisions-week" not in html
    assert "revisions-rung" not in html
    # Desktop grid untouched.
    assert 'class="calendar-grid"' in html
    css = client.get("/static/mobile.css").text
    assert ".revisions-week" not in css
    assert ".revisions-rung" not in css


# ── Article CTA: personalised after paint, never in the render ───────────────


def test_article_html_ships_the_neutral_cta(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/browse/article/20").text
    assert "Learn this Article" in html
    assert "data-article-cta" in html
    # The personalised labels are client-side only.
    assert "Continue · " not in html
    assert "Revise — due today" not in html


def test_article_progress_endpoint_reports_one_units_state(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    body = client.get("/api/articles/20/progress").json()
    assert body["ok"] is True
    assert body["state"] == "not_started"
    assert body["modes_total"] == 6

    engine.mark_mode_seen("clause-1", "read")
    engine.mark_mode_seen("clause-1", "cloze")
    body = client.get("/api/articles/20/progress").json()
    assert body["state"] == "started"
    # One clause speaks for the Article — counts are never summed across units.
    assert body["modes_done"] <= body["modes_total"]


def test_article_progress_endpoint_flags_a_due_unit(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date.today() - timedelta(days=30))
    assert client.get("/api/articles/20/progress").json()["state"] == "due"


def test_article_cta_script_skips_guests(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    block = js.split("function initArticleCta", 1)[1].split("function boot", 1)[0]
    assert 'classList.contains("is-authed")' in block
    assert "/api/articles/" in block
    # A failed fetch must leave the server label alone.
    assert ".catch(" in block


# ── Type: one CTA that morphs into Next/Done ─────────────────────────────────


def test_type_bar_has_a_single_cta(tmp_path: Path):
    """The design draws no bar for Type — frame 10 shows one ink CTA — so its
    check button carries the advance instead of sitting beside a second one."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    assert ".learn-mode-nav.is-solo-cta .learn-mode-next" in css
    solo = css.split(".learn-mode-nav.is-solo-cta .learn-type-check:not([hidden]) {", 1)[1]
    solo = solo.split("}", 1)[0]
    # It is the primary now, not a ghost secondary.
    assert "background: var(--accent)" in solo
    assert "flex: 2 1 auto" in solo


def test_type_check_button_morphs_into_the_advance(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    # The old in-place button labels are gone. ("All correct ✓" still exists,
    # but as the score pane's label — not on the button.)
    assert "check again" not in js
    assert "correct ✓\"" not in js.replace('"All correct ✓"', "")
    assert "typeAdvance" in js
    assert "learn:type-checked" in js
    assert "learn:type-reset" in js
    # The direct handler must stand down once the button is the advance, or a
    # single tap would re-check and advance at the same time.
    # Scope to initType — initLetters has its own `checkBtn`.
    type_src = js.split("function initType", 1)[1].split("function initRecite", 1)[0]
    guard = type_src.split('checkBtn.addEventListener("click"', 1)[1][:400]
    assert "typeAdvance" in guard


def test_type_solo_cta_needs_a_check_button(tmp_path: Path):
    """A locked Type panel renders no check button, so the ordinary Next has
    to stay or the bar would have no CTA at all."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    block = js.split("function syncNextButton", 1)[1].split("function goToMode", 1)[0]
    assert 'querySelector("[data-type-check]")' in block
    assert "Boolean(typeCheck)" in block


# ── Type: clause markers, and the Score / Wording tabs ───────────────────────


def test_type_skips_clause_markers(tmp_path: Path):
    """Clause numbering is not recall. "(3)", "(a)", "(iv)" are dropped from
    the target, and ignored rather than scored wrong if typed anyway — so the
    word alignment holds either way. Same predicate Letters already uses."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    assert "function isStructuralToken" in js
    type_src = js.split("function initType", 1)[1].split("function initRecite", 1)[0]
    assert "sourceWords.filter((word) => !isStructuralToken(word))" in type_src
    assert "is-structural" in type_src


def test_type_check_scores_the_whole_attempt(tmp_path: Path):
    """settledWords drops the trailing token because it is still being typed.
    That is right for the live counter and wrong for a check, where the user
    has finished — otherwise the last word could never be counted."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    type_src = js.split("function initType", 1)[1].split("function initRecite", 1)[0]
    assert "function attemptWords" in type_src
    result = type_src.split("function renderResult", 1)[1].split("function ", 1)[0]
    assert "attemptWords" in result
    assert "settledWords" not in result


def test_type_result_tabs_gate_the_wording(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1?mode=type").text
    assert 'data-type-tab="score"' in html
    assert 'data-type-tab="wording"' in html
    # The wording tab ships hidden; only an imperfect attempt reveals it.
    wording_tab = html.split('data-type-tab="wording"', 1)[1].split(">", 1)[0]
    assert "hidden" in wording_tab
    assert 'data-type-result' in html

    js = client.get("/static/app.js").text
    result = js.split("function renderResult", 1)[1].split("tabs.forEach", 1)[0]
    # Perfect means every target word produced, not merely nothing wrong yet.
    assert "right === words.length" in result
    assert "wordingTab.hidden = perfect" in result


def test_live_counter_yields_to_the_settled_score(tmp_path: Path):
    """Counts must appear in exactly one place at a time. The mobile rule sets
    display:flex, which outranks the [hidden] default, so it needs its own."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    assert '.learn[data-mobile-view="mode"] .learn-type-stats[hidden]' in css


# --------------------------------------------------------------------------- #
# The keyboard, and zoom                                                        #
# --------------------------------------------------------------------------- #


def test_action_bar_lifts_above_the_on_screen_keyboard(tmp_path: Path):
    """iOS does not shrink the LAYOUT viewport for the keyboard, so a
    `bottom: 0` fixed bar sits behind it — "Check my attempt" vanished while
    typing. visualViewport is the only source of the real visible box."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    guard = js.split("function initKeyboardInset", 1)[1].split("\n  function ", 1)[0]
    assert "window.visualViewport" in guard
    # The obscured strip needs offsetTop: iOS scrolls the visual viewport
    # inside the layout viewport once the keyboard is up.
    assert "vv.height + vv.offsetTop" in guard
    assert 'vv.addEventListener("resize"' in guard
    assert 'vv.addEventListener("scroll"' in guard
    assert "translateY(" in guard
    # A collapsing URL bar is not a keyboard.
    assert "covered < 80" in guard
    assert "initKeyboardInset();" in js


def test_action_bar_reclaims_the_safe_area_when_the_keyboard_is_up(tmp_path: Path):
    """The home indicator is behind the keys, so its inset is dead space."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    assert "body.is-keyboard-open .learn[data-mobile-view=\"mode\"] .learn-mode-nav" in css
    bar = css.split('.learn[data-mobile-view="mode"] .learn-mode-nav {', 1)[1].split("}", 1)[0]
    assert "position: fixed" in bar
    assert "transition: transform" in bar


def test_zoom_is_disabled_on_the_app_shell_only(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/browse").text
    assert "user-scalable=no" in html
    assert "maximum-scale=1" in html
    # viewport-fit=cover keeps env(safe-area-inset-*) meaningful.
    assert "viewport-fit=cover" in html


def test_pinch_is_cancelled_in_js_because_ios_ignores_the_meta(tmp_path: Path):
    """Safari has ignored user-scalable/maximum-scale for pinch since iOS 10,
    so the meta tag alone does nothing on an iPhone."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    guard = js.split("function initNoZoom", 1)[1].split("\n  function ", 1)[0]
    assert "gesturestart" in guard
    assert "gesturechange" in guard
    assert "gestureend" in guard
    assert "passive: false" in guard
    # Phone-scoped: desktop and browser/OS zoom stay untouched.
    assert "isPhone()" in guard


def test_form_controls_clear_the_ios_focus_zoom_threshold(tmp_path: Path):
    """Under 16px, iOS zooms the page in on focus and leaves it scaled."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    assert "font-size: max(16px, 1em)" in css
    assert "touch-action: manipulation" in css


# --------------------------------------------------------------------------- #
# Letters: one CTA that morphs Speak → Stop → Next                             #
# --------------------------------------------------------------------------- #


def test_letters_bar_carries_only_the_speak_button(tmp_path: Path):
    """Speak + Full text + Next read as three competing CTAs. The view toggle
    is an aid, not an action, so it stays beside the letters it reveals."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    controls = js.split("var MODE_CONTROLS = {", 1)[1].split("};", 1)[0]
    assert 'letters: ".learn-letters-speak"' in controls
    assert '.learn-letters-controls' not in controls


def test_letters_speak_button_is_the_solo_cta(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    sync = js.split("function syncNextButton", 1)[1].split("function goToMode", 1)[0]
    assert "lettersSolo" in sync
    # Only while the speak button is actually on screen: "Just read" hides it,
    # and Next has to lead there or the bar has no CTA at all.
    assert "!lettersSpeak.hidden" in sync
    assert "lettersAdvance" in sync
    # One shared tail paints every solo mode, so they cannot drift apart.
    assert "function paintAdvance" in sync
    assert 'btn.textContent = "Next →"' in sync
    assert "paintAdvance(lettersSpeak, lettersSpeak.dataset.lettersAdvance)" in sync
    assert "typeSolo || lettersSolo || reciteSolo || quizSolo" in sync


def test_letters_says_stop_while_the_mic_is_open(tmp_path: Path):
    """The tap that ends the recording is the same tap that checks it, so the
    button reads Stop, not "Check phrase"."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    letters = js.split("function initLetters", 1)[1].split("function setNavRecording", 1)[0]
    assert 'startRecClock(speakBtn, label || "Stop")' in letters
    assert "Check phrase" not in letters
    # Completing the clause hands the button over to mobile.js as the advance.
    assert 'speakBtn.dataset.lettersAdvance = "1"' in letters
    assert "learn:letters-advance" in letters
    # …and exiting the mic must not relabel it back to Speak afterwards —
    # but only in the phone bar; off the bar it stays a speak control.
    assert 'speakBtn.closest("[data-mode-nav]") && speakBtn.dataset.lettersAdvance' in letters


def test_just_read_view_restores_next_as_the_cta(tmp_path: Path):
    """Regression: is-solo-cta hid Next while the speak button was hidden too,
    leaving the bar empty and the mode with no way forward."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    assert 'attributeFilter: ["hidden"]' in js
    observer = js.split("var lettersSpeakBtn", 1)[1][:400]
    assert "MutationObserver" in observer
    assert 'syncNextButton("letters")' in observer


def test_letters_solo_cta_has_primary_styling(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    assert ".learn-mode-nav.is-solo-cta .learn-letters-speak:not([hidden])" in css
    assert ".learn-mode-nav.is-solo-cta .learn-letters-speak:disabled" in css
    # The slot now also carries "Next →"/"Done", so it reserves the wider size.
    speak_slot = css.split(".learn-mode-nav .learn-letters-speak {", 1)[1].split("}", 1)[0]
    assert "min-width: 10.5rem" in speak_slot


def test_every_cta_mode_uses_the_same_one_slot_shape(tmp_path: Path):
    """Letters, Recite and Test each showed their own act beside Next — two
    or three CTAs competing. They now share Type's shape: the mode's act,
    then Next, then Done, in one slot."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    controls = js.split("var MODE_CONTROLS = {", 1)[1].split("};", 1)[0]
    # Only the acting button enters the bar; aids stay beside what they act on.
    assert 'letters: ".learn-letters-speak"' in controls
    assert 'recite: ".learn-recite-toggle"' in controls
    assert 'type: ".learn-type-check"' in controls
    assert 'test: ".learn-test-submit"' in controls
    assert ".learn-recite-controls" not in controls
    assert ".learn-letters-controls" not in controls

    sync = js.split("function syncNextButton", 1)[1].split("function goToMode", 1)[0]
    assert "reciteSolo" in sync
    assert "quizSolo" in sync
    assert "typeSolo || lettersSolo || reciteSolo || quizSolo" in sync
    assert "paintAdvance(reciteToggle, reciteToggle.dataset.reciteAdvance)" in sync
    # The old divergence is gone: Test no longer hands Done to a second button
    # on the last card, because there is no second button.
    assert "Try new set" not in sync
    assert "quizRetry" not in sync


def test_recite_hands_its_button_over_once_scored(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/app.js").text
    recite = js.split("function initRecite", 1)[1]
    assert "function markReciteAdvance" in recite
    assert 'toggle.dataset.reciteAdvance = "1"' in recite
    assert "learn:recite-advance" in recite
    # Off the phone bar the button stays a record control, so desktop keeps
    # its "Recite again" state.
    assert 'toggle.closest("[data-mode-nav]") && toggle.dataset.reciteAdvance' in recite
    assert 'toggle.textContent = scored ? "Recite again" : "▸ Start reciting"' in recite


def test_test_mode_submit_carries_done_on_the_last_mode(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    # The click handler, not the syncNextButton lookup of the same selector.
    handler = js.split('event.target.closest("[data-quiz-submit]")', 1)[1].split(
        "}, true);", 1
    )[0]
    # Mid-deck the tap falls through to app.js, which advances the deck.
    assert "nextTarget(currentMode()) !== null" in handler
    assert "doneBtn.click()" in handler


def test_letters_view_switch_is_centred_and_even(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    box = css.split(".learn-letters-viewswitch {", 1)[1].split("}", 1)[0]
    assert "width: fit-content" in box
    assert "margin: 0 auto 14px" in box
    assert "border-radius: 999px" in box
    # Clips the active fill to the rounded edge.
    assert "overflow: hidden" in box
    btn = css.split(".learn-letters-view-btn {", 1)[1].split("}", 1)[0]
    # Equal halves, so the inactive side is never dead space.
    assert "flex: 1 1 0" in btn
    assert "min-width: 5.5rem" in btn


def test_phone_letters_surface_matches_landing_scaffold(tmp_path: Path):
    """Landing §03 Letters is Fraunces + 0.24em initials, not mono.
    Full text must drop the tracking so it reads like Read mode."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    initials = css.split(
        'body[data-mscreen="learn"] .learn-letters-text.is-initials {', 1
    )[1].split("}", 1)[0]
    assert "var(--font-display)" in initials
    assert "letter-spacing: 0.24em" in initials
    assert "font-weight: 600" in initials
    assert "var(--font-mono)" not in initials
    full = css.split(
        'body[data-mscreen="learn"] .learn-letters-text.is-full {', 1
    )[1].split("}", 1)[0]
    assert "var(--font-display)" in full
    assert "letter-spacing: normal" in full
    assert "font-weight: 400" in full


def test_letters_view_switch_labels(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1?mode=letters").text
    assert '>Speak</button>' in html
    assert '>Read</button>' in html
    assert "Speak it" not in html
    assert "Just read" not in html


# --------------------------------------------------------------------------- #
# The "?" now means help                                                       #
# --------------------------------------------------------------------------- #


def test_question_mark_opens_mode_help_not_the_article(tmp_path: Path):
    """A "?" reads as help everywhere. It used to link to the Article's Bare
    Act text — which is what the "← Article N" control beside it suggests but
    does not do, so the two labels were effectively swapped."""
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1").text
    assert "data-mode-help" in html
    assert 'aria-label="How to use this mode"' in html
    # No longer an anchor to /browse/article/…
    bar = html.split('class="learn-mode-bar"', 1)[1].split("</div>", 1)[0]
    assert "mobile-icon-btn" in bar
    assert "href=" not in bar.split("mobile-icon-btn", 1)[1]


def test_mode_help_covers_every_mode(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1").text
    copy = html.split('id="mode-help-copy"', 1)[1].split("</script>", 1)[0]
    import json

    entries = json.loads(copy.split(">", 1)[1])
    assert set(entries) == {"read", "cloze", "letters", "type", "recite", "test"}
    for mode, entry in entries.items():
        assert entry["title"] and entry["body"], mode


def test_mode_help_modal_has_a_close_control(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/learn/clause-1").text
    assert "data-mode-help-modal" in html
    assert "data-mode-help-close" in html
    assert 'aria-label="Close"' in html
    js = client.get("/static/mobile.js").text
    guard = js.split("function initModeHelp", 1)[1].split("\n  function ", 1)[0]
    assert "modal.close()" in guard
    assert "showModal()" in guard
    # Backdrop click closes too, matching the sheets elsewhere.
    assert "event.target === modal" in guard


def test_standing_hint_lines_are_hidden_on_the_phone(tmp_path: Path):
    """The "?" carries this guidance on demand now. Hidden, not deleted:
    desktop has no "?" and keeps its hints."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    for selector in (
        'body[data-mscreen="learn"] .learn-panel-read .learn-hint',
        'body[data-mscreen="learn"] .learn-type-lede',
        'body[data-mscreen="learn"] .learn-test-lede',
        'body[data-mscreen="learn"] .learn-letters-hint',
        'body[data-mscreen="learn"] .learn-recite-hint',
    ):
        assert selector in css, selector
    # The markup survives for desktop.
    html = client.get("/learn/clause-1").text
    assert "learn-type-lede" in html
    assert "learn-test-lede" in html


def test_status_lines_are_not_treated_as_hints(tmp_path: Path):
    """Counts and listening state are live state, not instructions — they
    stay on screen and are no longer lifted alongside the hint lines."""
    client, _, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    lines = js.split("var MODE_STATUS_LINES = {", 1)[1].split("};", 1)[0]
    assert "[data-cloze-status]" in lines
    assert "[data-letters-status]" in lines
    assert "[data-recite-status]" in lines
    assert ".learn-letters-hint" not in lines
    assert ".learn-recite-hint" not in lines


# ── Auto Plan on the phone (designs 4c, 4f) ──────────────────────────────────


def test_planned_new_rows_carry_their_own_state_and_pace(tmp_path: Path):
    """Design 4f: a planned NEW row is not a Scheduled row wearing its colours."""
    client, _, _ = _client(tmp_path)
    eng = client.app.state.engine
    today = date.today()
    eng.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)

    html = client.get("/calendar").text
    assert "revisions-row is-new" in html
    assert "New · Steady plan" in html
    # …and the day mark keeps its own class, which mobile.css now draws open.
    assert "cal-m-mark is-new" in html


# ── Remaining prototype restyle (tab bar, Article, Search, Profile) ──────────


def test_signed_in_tabbar_ships_icons_and_keeps_label_contract():
    base = (
        Path(__file__).parent.parent
        / "src/constitution_memorizer/web/templates/base.html"
    ).read_text()
    tabbar = base.split('class="mobile-tabbar" aria-label="Mobile"', 1)[1].split(
        "</nav>", 1
    )[0]
    assert ">Calendar</a>" in tabbar
    assert ">Profile</a>" in tabbar
    assert "mobile-tab-icon" in tabbar
    css = (
        Path(__file__).parent.parent
        / "src/constitution_memorizer/web/static/mobile.css"
    ).read_text()
    tab = css.split("body[data-mscreen] .mobile-tab {", 1)[1].split("}", 1)[0]
    assert "flex-direction: column" in tab
    assert "font-size: 10.5px" in tab
    assert "border-top: 2px" not in tab
    assert 'body[data-mscreen="search"] .mobile-tabbar' in css
    assert ".mobile-sheet-panel::before" in css


def test_article_phone_shows_clauses_and_bare_preview(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/browse/article/20").text
    assert "Learn this Article" in html
    assert "article-clause-list" in html
    assert "Read the full Article" in html
    assert "article-status" in html
    css = client.get("/static/mobile.css").text
    assert 'body[data-mscreen="article"] .article-clause-list' in css
    clause_item = css.split(
        'body[data-mscreen="article"] .article-clause-list .checklist-item {', 1
    )[1].split("}", 1)[0]
    assert "flex-direction: row" in clause_item
    assert 'body[data-mscreen="article"] .browse-article > .checklist {' not in css
    assert ".article-bare:not(.is-expanded) .browse-article-text" in css
    assert 'body[data-mscreen="article"] .amendment-history' in css
    js = client.get("/static/mobile.js").text
    assert "function initBarePreview" in js
    assert "function initSearchRecent" in js


def test_search_phone_cancel_is_teal_and_hides_the_tabbar(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/search").text
    assert "search-cancel" in html
    assert 'data-search-recent' in html
    css = client.get("/static/mobile.css").text
    cancel = css.split(".search-cancel {", 1)[1].split("}", 1)[0]
    assert "var(--rc-teal)" in cancel
    assert 'body[data-mscreen="search"] .mobile-tabbar' in css


def test_calendar_today_list_is_a_card_with_continue(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/calendar").text
    assert "cal-m-today-card" in html or "cal-m-grid" in html
    css = client.get("/static/mobile.css").text
    assert ".cal-m-today-card" in css
    assert ".cal-m-today-continue" in css
    assert ".cal-m-daylist:not([hidden])::before" in css


def test_profile_phone_title_is_your_recall(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    html = client.get("/progress").text
    assert "progress-stat-grid" in html
    assert "Your Recall" in html
    assert "The revision journey" in html
    css = client.get("/static/mobile.css").text
    assert 'body[data-mscreen="profile"] .progress > .display' in css
    assert 'body[data-mscreen="profile"] .progress-stat-card:nth-child(4)' in css


def test_today_goal_ring_centers_the_fraction(tmp_path: Path):
    css = (
        Path(__file__).parent.parent
        / "src/constitution_memorizer/web/static/mobile.css"
    ).read_text()
    assert ".rc-goal-frac" in css
    assert ".rc-goal-dial" in css
    dash = (
        Path(__file__).parent.parent
        / "src/constitution_memorizer/web/templates/dashboard.html"
    ).read_text()
    assert "dash-greeting-settings" in dash
    assert "Today’s Recall" in dash or "Today's Recall" in dash
    assert "rc-streak-glyph" in dash
    assert "Start revision" in dash
    assert "dash-due-count" in dash


def test_today_current_path_node_is_one_card(tmp_path: Path):
    """Copy + Start must share a card. A 12px row-gap showed page wash
    between the title block and the button, which read as an empty slot."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    path = css.split('body[data-mscreen="today"] .rc-path {', 1)[1].split("}", 1)[0]
    assert "margin: 0" in path
    assert "margin: 14px 0 0" not in path
    current = css.split(
        'body[data-mscreen="today"] .rc-path-node.is-current {', 1
    )[1].split("}", 1)[0]
    assert "gap: 0 14px" in current
    assert "gap: 12px 14px" not in current


def test_phone_tables_frame_scrolls_horizontally(tmp_path: Path):
    """Portrait is narrower than the grid min-width. overflow:hidden clipped
    the last columns (WHAT IT DOES / LIES AGAINST) with no way to pan."""
    client, _, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    frame = css.split(
        'body[data-mscreen="tables"] .tables-frame {', 1
    )[1].split("}", 1)[0]
    assert "overflow-x: auto" in frame
    assert "overflow: hidden" not in frame
    assert "-webkit-overflow-scrolling: touch" in frame
    html = client.get("/tables?tab=writs").text
    assert "Habeas corpus" in html
    assert 'class="tables-frame"' in html
    assert "What it does" in html
