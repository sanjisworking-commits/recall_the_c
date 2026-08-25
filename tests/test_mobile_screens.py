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


def test_calendar_page_renders_revisions_only_for_this_month(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    today = date.today()
    assert "revisions-mobile" in client.get("/calendar").text
    other_year = today.year - 1
    away = client.get(f"/calendar?year={other_year}&month={today.month}")
    assert away.status_code == 200
    assert "revisions-mobile" not in away.text


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


def test_learn_mode_view_keeps_session_on_deck_back_contract(tmp_path: Path):
    client, engine, _ = _client(tmp_path)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    start = client.post("/study/revision/start", follow_redirects=False)
    loc = start.headers["location"]
    assert "session=" in loc
    sid = loc.rsplit("session=", 1)[-1].split("&")[0]
    unit_id = loc.split("/learn/")[1].split("?")[0]
    html = client.get(f"/learn/{unit_id}?session={sid}&mode=read").text
    assert 'data-mobile-view="mode"' in html
    assert f'data-session-id="{sid}"' in html
    assert "data-deck-back" in html
    assert f"session={sid}" in html
    js = Path("src/constitution_memorizer/web/static/mobile.js").read_text(
        encoding="utf-8"
    )
    assert 'searchParams.delete("mode")' in js


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
