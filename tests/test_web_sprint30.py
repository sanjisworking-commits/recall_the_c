"""Sprint 30 — six-method Done gate, How-to-use, rebrand, theme."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ModesIncompleteError, ReminderEngine
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MINI_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "mini_reviewed.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=MINI_REVIEWED if MINI_REVIEWED.exists() else None,
    )
    return TestClient(app)


@pytest.fixture
def engine(tmp_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)


def test_brand_and_how_to_use(client: TestClient):
    html = client.get("/").text
    assert "Recall the C" in html
    assert "main_logo.png" in html
    assert "How to use" in html
    assert "Read the Bare Act wording twice, verbatim." in html
    assert "Answer a short auto-made quiz — new questions each revision." in html
    assert "theme-toggle" in html

    assert "styles.css?v=main39" in html


def test_dashboard_surfaces_use_theme_tokens():
    """Dark mode broke when dash cards hard-coded #fff under light ink vars."""
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "constitution_memorizer"
        / "web"
        / "static"
        / "styles.css"
    ).read_text(encoding="utf-8")
    assert ".dash-card {" in css
    card_block = css.split(".dash-card {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in card_block
    assert "background: #fff" not in card_block
    strip_block = css.split(".dash-strip {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in strip_block
    assert 'html[data-theme="dark"]' in css
    assert "--paper: #1e1e1d" in css
    assert "--ink: #f2f2f0" in css
    # Default .btn must carry primary fill so CTAs stay readable on themed cards.
    btn_block = css.split(".btn {", 1)[1].split("}", 1)[0]
    assert "background: var(--accent)" in btn_block
    assert "color: var(--on-accent)" in btn_block


def test_learn_browse_notes_use_theme_tokens():
    """Kind/amendment badges and Explain-it-back notes must invert with the theme."""
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "constitution_memorizer"
        / "web"
        / "static"
        / "styles.css"
    ).read_text(encoding="utf-8")
    kind = css.split(".kind-badge {", 1)[1].split("}", 1)[0]
    assert "color: var(--on-accent)" in kind
    assert "color: #fff" not in kind
    amdt = css.split(".amendment-badge {", 1)[1].split("}", 1)[0]
    assert "color: var(--on-accent)" in amdt
    assert "color: #fff" not in amdt
    notes = css.split(".explain-back-input {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in notes
    assert "color: var(--ink)" in notes
    assert "background: #fdfdfc" not in notes
    type_input = css.split(".learn-type-input {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in type_input
    assert "background: #fff" not in type_input


def test_signin_surfaces_use_theme_tokens():
    """Sign-in rail/inputs must not keep light fills under dark --ink."""
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "constitution_memorizer"
        / "web"
        / "static"
        / "styles.css"
    ).read_text(encoding="utf-8")
    assert "color-scheme: dark" in css.split('html[data-theme="dark"] {', 1)[1].split("}", 1)[0]
    rail = css.split(".auth-rail {", 1)[1].split("}", 1)[0]
    assert "background: var(--rail)" in rail
    assert "background: #f7f7f5" not in rail
    phone = css.split(".phone-national {", 1)[1].split("}", 1)[0]
    assert "color: var(--ink)" in phone
    assert "background: transparent" in phone
    field = css.split(".field-input {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in field
    assert "color: var(--ink)" in field


def test_calendar_surfaces_use_theme_tokens():
    """Calendar cells/chips must not keep white fills under dark --ink."""
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "constitution_memorizer"
        / "web"
        / "static"
        / "styles.css"
    ).read_text(encoding="utf-8")
    cell = css.split(".calendar-cell {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in cell
    assert "background: #fff" not in cell
    blank = css.split(".calendar-cell.is-blank {", 1)[1].split("}", 1)[0]
    assert "background: var(--wash)" in blank
    due = css.split(".calendar-chip.is-due {", 1)[1].split("}", 1)[0]
    assert "background: var(--paper)" in due
    assert "background: #fff" not in due
    memorized = css.split(".calendar-chip.is-memorized {", 1)[1].split("}", 1)[0]
    assert "color: var(--on-accent)" in memorized
    assert "color: #fff" not in memorized
    dow = css.split(".calendar-dow {", 1)[1].split("}", 1)[0]
    assert "background: var(--wash)" in dow
    assert "--learning: #4a4a48" in css


def test_learn_marks_read_and_locks_done(client: TestClient):
    html = client.get("/learn/clause-1").text
    assert "methods-tracker" in html
    assert "1 of 6 methods visited" in html
    assert "Read ✓" in html
    assert "btn-done-locked" in html
    assert "5 methods left" in html
    assert 'aria-disabled="true"' in html


def test_seen_endpoint_unlocks_done(client: TestClient):
    client.get("/learn/clause-1")  # marks read
    for mode in ("cloze", "letters", "type", "recite"):
        resp = client.post("/learn/clause-1/seen", data={"mode": mode})
        assert resp.status_code == 200
        assert resp.json()["done"]["unlocked"] is False
    from tests.quiz_helpers import submit_quiz
    resp = submit_quiz(client, MINI_UNITS, "clause-1")
    data = resp.json()
    assert data["done"]["unlocked"] is True
    assert data["done"]["label"] == "Done — next unit"
    html = client.get("/learn/clause-1?mode=test").text
    assert "All 6 methods visited" in html
    assert "Done — next unit" in html
    assert "btn-done-locked" not in html
    assert 'data-done-unlocked="true"' in html
    assert 'aria-disabled="false"' in html


def test_gated_mode_get_does_not_mark(client: TestClient):
    # Opening a gated tab (cloze/type/recite) never earns a check.
    for mode in ("cloze", "letters", "type", "recite"):
        client.get(f"/learn/clause-1?mode={mode}")
    html = client.get("/learn/clause-1?mode=cloze").text
    assert "btn-done-locked" in html
    assert "methods left" in html
    tabs = html.split("mode-tabs")[1].split("</div>")[0]
    assert "Cloze ✓" not in tabs
    assert "Type ✓" not in tabs
    assert "Recite ✓" not in tabs


def test_done_blocked_until_six_modes(client: TestClient):
    client.get("/learn/clause-1")  # marks read
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1"


def test_done_advances_after_all_modes(client: TestClient):
    from tests.quiz_helpers import submit_quiz
    client.get("/learn/clause-1")
    for mode in ("cloze", "letters", "type", "recite"):
        client.post("/learn/clause-1/seen", data={"mode": mode})
    submit_quiz(client, MINI_UNITS, "clause-1")
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/learn/")


def test_mark_done_clears_modes_for_next_cycle(engine: ReminderEngine):
    engine.mark_all_modes_seen("clause-1")
    assert engine.modes_complete("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 21))
    assert engine.modes_seen("clause-1") == set()


def test_mark_done_raises_when_incomplete(engine: ReminderEngine):
    engine.mark_mode_seen("clause-1", "read")
    with pytest.raises(ModesIncompleteError):
        engine.mark_done("clause-1", as_of=date(2026, 7, 21))


def test_theme_api_persists(client: TestClient):
    resp = client.post("/api/theme", data={"theme": "dark"})
    assert resp.status_code == 200
    assert resp.json()["theme"] == "dark"
    # Preference surfaces on next page via context processor
    html = client.get("/").text
    assert 'data-theme-preference="dark"' in html


def test_reset_unit_clears_modes(client: TestClient):
    client.get("/learn/clause-1")
    client.post("/learn/clause-1/seen", data={"mode": "cloze"})
    html = client.get("/learn/clause-1").text
    assert "Cloze ✓" in html
    client.post("/learn/clause-1/reset")
    html = client.get("/learn/clause-1").text
    assert "1 of 6 methods visited" in html
    assert "Cloze ✓" not in html
    assert "Read ✓" in html
