"""Phone Halted Calendar (M6 Q4, owner 2026-11-11): the halted account's phone
Calendar shares the phone Expired Calendar rules (`playground.css` M6 block,
marker substituted). Mirrors `test_phone_expired_calendar_screen5.py` for the
halted state: chrome, month navigation, sibling states, CSS scope, and a
Playwright capture that skips when Playwright is absent.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH
from tests.test_account_family import USER, _client

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
TAB_HREFS = (("Today", "/dashboard"), ("Browse", "/browse"), ("Playground", "/playground"), ("Calendar", "/calendar"), ("Profile", "/profile"))
RENDER_INVENTED = ("Premium", "Unlock all", "Study archive", "1 UNITS", "first revision · Playground", "ladder 7 → 15",
                   "Resume required", "Locked", "Your plan expired", "Subscription required", "Resume Playground", "View Playground plans")


def _phone(html: str) -> str:
    return html.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]


def _tabs(html: str) -> str:
    return html.split('class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    snap = client.app.state.entitlement_service.resolve(USER)
    return {"sub": None if stored is None else (stored.id, stored.status, stored.tier, stored.is_current),
            "can_open": snap.can_open_playground, "block": snap.playground_block_reason}


def _assert_halted_calendar_chrome(html: str, *, today: date) -> None:
    assert 'data-halted-calendar="desktop"' in html
    assert "data-signed-in-calendar" in html
    assert "data-plus-calendar" not in html
    assert "data-paid-calendar" not in html
    assert "data-expired-calendar" not in html
    assert 'data-mscreen="revisions"' in html
    phone = _phone(html)
    assert "Calendar" in phone
    assert today.strftime("%B %Y") in unescape(phone)
    assert "data-cal-filter" not in phone and "Add task" not in phone and "view=week" not in phone and "data-cal-source" not in phone
    dows = [m.strip() for m in re.findall(r'class="cal-m-dow"[^>]*>([^<]*)', phone)]
    assert dows[:7] == ["S", "M", "T", "W", "T", "F", "S"]
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs and label_text in tabs
    assert 'aria-current="page"' in tabs and ">Calendar<" in tabs
    text = unescape(phone)
    for phrase in RENDER_INVENTED:
        assert phrase not in text, phrase


@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_phone_halted_calendar_empty_has_no_invented_chips(tmp_path: Path, tier_model: str) -> None:
    client = _client(tmp_path, "halted", tier_model=tier_model)
    before = _facts(client)
    assert before["can_open"] is False and before["sub"][1] == "halted"
    page = client.get("/calendar")
    assert page.status_code == 200
    assert _facts(client) == before  # GET is mutation-free
    html = page.text
    today = date.today()
    _assert_halted_calendar_chrome(html, today=today)
    phone = _phone(html)
    assert "Nothing due today" in phone
    assert "cal-m-today-continue" not in phone
    assert PLAYGROUND_BILLING_PATH not in phone and "/playground/" not in phone
    assert "1 → 3 → 7 → 15 → 30 → 60" in unescape(html)
    desk = html.split("calendar-header", 1)[1]
    assert 'data-cal-continue-recall href="/dashboard"' in desk  # M6 Q5
    if tier_model == "choices":
        assert 'id="cal-si-upgrade"' in html and 'id="cal-si-editor"' not in html
    else:
        assert 'id="cal-si-upgrade"' not in html and 'id="cal-si-editor"' in html
    assert 'id="cal-si-viewer"' in html  # 5-6a


def test_phone_halted_calendar_month_nav_is_real_get_links(tmp_path: Path) -> None:
    client = _client(tmp_path, "halted")
    today = date.today()
    phone = _phone(client.get("/calendar").text)
    assert 'aria-label="Previous month"' in phone and 'aria-label="Next month"' in phone
    assert "/calendar?year=" in phone and "view=week" not in phone
    other = today.replace(day=1) - timedelta(days=1)
    jumped = client.get(f"/calendar?year={other.year}&month={other.month}")
    assert jumped.status_code == 200
    jumped_phone = _phone(jumped.text)
    assert other.strftime("%B %Y") in unescape(jumped_phone)
    assert "cal-m-today-continue" not in jumped_phone
    assert 'data-halted-calendar="desktop"' in jumped.text


def test_guest_free_plus_pro_expired_calendar_are_not_halted_phone_05(tmp_path: Path) -> None:
    guest = _client(tmp_path, "guest").get("/calendar", follow_redirects=False)
    assert guest.status_code == 303 and "/login" in guest.headers["location"]
    for state, marker in (("free", None), ("plus", 'data-plus-calendar="desktop"'), ("pro", 'data-paid-calendar="desktop"'), ("expired", 'data-expired-calendar="desktop"')):
        html = _client(tmp_path, state).get("/calendar").text
        assert "data-signed-in-calendar" in html
        assert "data-halted-calendar" not in html, state
        if marker:
            assert marker in html, state


def test_phone_halted_calendar_css_scope_pins_and_desktop_09_untouched() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "/* ── M6 · Calendar" in css
    halted = css.split("/* ── M6 · Calendar", 1)[1].split("/* Q1:", 1)[0]
    assert "@media (max-width: 560px)" in halted
    assert "@media (min-width: 561px)" not in halted
    assert '[data-halted-calendar="desktop"]' in halted
    assert "[data-expired-calendar" not in halted and "[data-plus-calendar" not in halted and "[data-paid-calendar" not in halted
    for needle in ("safe-area-inset-bottom", "overflow-x: hidden", "min-width: 44px", "min-height: 44px", "var(--m-tabbar, 60px)",
                   ".mobile-tabbar", "grid-template-columns: repeat(5, 1fr)", "position: fixed", "position: static", ".cal-m-cell.is-selected"):
        assert needle in halted, needle
    compact = halted.replace(" ", "")
    assert 'href*="/billing/subscriptions"' in compact and 'href*="/playground/"' in compact
    assert "#0e7569" not in halted and "#3a3a38" not in halted
    # the expired phone block does not acquire the halted marker; the halted desktop block (Screen 09) is untouched
    expired_phone = css.split("/* Phone Expired Calendar is expired/05-screen", 1)[1].split("/* Plus desktop /profile", 1)[0]
    assert "[data-halted-calendar" not in expired_phone
    desk = css.split("halted/09-screen", 1)[1].split("plus/10-screen", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "[data-halted-calendar-phone]" not in css
    mobile = MOBILE.read_text(encoding="utf-8")
    assert ":not([data-halted-calendar])" in mobile
    assert 'data-halted-calendar="desktop"] {' not in mobile
    cal = CAL.read_text(encoding="utf-8")
    assert "data-halted-calendar-phone" not in cal
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg57" in base and "styles.css?v=main94" in base and "mobile.css?v=mob113" in base


def test_phone_halted_calendar_screen05_captures(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    from tests.test_phone_expired_calendar_screen5 import _cookie, _serve
    from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME

    client = _client(tmp_path, "halted")
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(client.app)
    origin = f"http://127.0.0.1:{port}"
    out = tmp_path / "captures"
    out.mkdir()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        for theme in ("light", "dark"):
            context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            context.add_cookies(_cookie(session, origin))
            page = context.new_page()
            page.emulate_media(color_scheme=theme)
            page.goto(f"{origin}/calendar")
            page.wait_for_selector('[data-halted-calendar="desktop"]')
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(out / f"phone_halted_calendar_screen05_{theme}_390x844.png"), full_page=True)
            context.close()
        browser.close()
