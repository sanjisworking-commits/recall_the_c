"""Browse due ribbons, count lines, In news pills, and nav badge (variation 1c)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.browse import (
    article_due_summaries,
    browse_due_total,
    browse_parts_sections,
    parse_news_articles,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _article_card_chunk(html: str, number: str) -> str:
    needle = f"Article {number}"
    start = html.find(needle)
    assert start != -1, f"missing {needle}"
    return html[start : start + 900]


def test_parse_news_articles():
    assert parse_news_articles("19") == {"19"}
    assert parse_news_articles("19, 21") == {"19", "21"}
    assert parse_news_articles(" 14  15,21 ") == {"14", "15", "21"}
    assert parse_news_articles("") == set()
    assert parse_news_articles(None) == set()


def test_article_due_summaries_due_and_overdue(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 19))
    engine.mark_all_modes_seen("clause-2")
    engine.mark_done("clause-2", as_of=date(2026, 7, 18))
    summaries = article_due_summaries(engine, as_of=today)
    assert "20" in summaries
    assert summaries["20"].due_count == 2
    assert summaries["20"].due_kind == "overdue"
    assert browse_due_total(engine, as_of=today) == 2


def test_browse_parts_sections_attaches_due_and_news(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 19))
    engine.set_news_articles_raw("20")
    sections = browse_parts_sections(engine, None, as_of=today)
    cards = [c for s in sections for c in s.cards]
    art20 = next(c for c in cards if c.article_number == "20")
    assert art20.due_count == 1
    assert art20.due_kind == "due"
    assert art20.in_news is True
    assert art20.marks == ("news",)
    assert art20.tracked is True
    untouched = [c for c in cards if c.article_number != "20"]
    assert all(c.due_count == 0 and c.due_kind is None for c in untouched)
    assert all(c.in_news is False for c in untouched)
    assert all(c.marks == () for c in untouched)


def test_browse_index_html_ribbon_count_and_nav_badge(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date.today() - timedelta(days=1))
    engine.set_news_articles_raw("20")
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    home = client.get("/")
    assert home.status_code == 200
    assert "nav-due-badge" in home.text
    browse = client.get("/browse")
    assert browse.status_code == 200
    assert "browse-due-ribbon" in browse.text
    assert "browse-due-count" in browse.text
    assert "browse-due-banner" not in browse.text
    assert "browse-due-bubble" not in browse.text
    assert "Due today" in browse.text
    assert "1 unit due" in browse.text
    assert "browse-mark-news" in browse.text
    assert "browse-legend" in browse.text
    assert "In news" in browse.text
    assert "browse-in-news" not in browse.text
    card = _article_card_chunk(browse.text, "20")
    assert "browse-mark-news" in card
    assert ">In news<" not in card
    assert "is-tracked" in browse.text
    assert "nav-due-badge" in browse.text


def test_browse_overdue_ribbon_and_plural_count(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=3))
    engine.mark_all_modes_seen("clause-2")
    engine.mark_done("clause-2", as_of=today - timedelta(days=2))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    html = client.get("/browse").text
    assert "Overdue" in html
    assert "is-overdue" in html
    assert "2 units due" in html


def test_browse_no_dues_unchanged(tmp_path: Path):
    db = tmp_path / "progress.db"
    ReminderEngine.from_paths(db, MINI_UNITS)
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    html = client.get("/browse").text
    assert "browse-due-ribbon" not in html
    assert "browse-due-count" not in html
    assert "nav-due-badge" not in client.get("/").text


def test_default_news_articles_is_19(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    assert engine.get_news_articles_raw() == "19"
    sections = browse_parts_sections(engine, None)
    cards = [c for s in sections for c in s.cards]
    assert all(c.in_news is False for c in cards)  # mini fixture has Art 20 only


def test_news_articles_moved_off_user_settings(tmp_path: Path):
    """Browse — In news is site-wide, so /settings neither shows nor writes it."""
    db = tmp_path / "progress.db"
    ReminderEngine.from_paths(db, MINI_UNITS)
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    page = client.get("/settings")
    assert page.status_code == 200
    assert 'name="news_articles"' not in page.text

    # Saving reminders must not clear the stored value — it used to, because the
    # parameter defaulted to Form("") and was written unconditionally.
    saved = client.post(
        "/settings",
        data={"notification_frequency": "twice"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    assert engine.get_news_articles_raw() == "19"
    assert parse_news_articles(engine.get_news_articles_raw()) == {"19"}
