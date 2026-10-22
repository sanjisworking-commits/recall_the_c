"""Phone Plus NDPS Add confirm Screen 02 (CTA map plus/02-screen).

Authorized: ChatGPT. Authenticated active Plus overlay from Plus 01
eligible_to_add on /laws/ndps. M2: one Add sheet markup for both widths —
phone raises the same panel as a bottom sheet (CSS), with the existing
confirm form and scope step. re_add / roster_full / already_active keep
their live kinds. Guest 02, Free 02, Expired/Halted, Pro and other laws get
the same sheet with their own state.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.eligibility import playground_bare_act_spec
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.playground.urls import add_path, law_path, remove_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
NDPS_READING_NAME = playground_bare_act_spec("ndps").short_name
BNS_READING_NAME = playground_bare_act_spec("bns").short_name
TITLE = "Add to Playground"


def _lede(reading_name: str) -> str:
    return (
        f"{reading_name} joins this month's Playground — learnable, verbatim. "
        "The reader itself never changes."
    )


LEDE = _lede(NDPS_READING_NAME)
SPACE = f"This will use 1 of your 10 law spaces for {MONTH}."
REMAIN = "You'll have 9 spaces remaining."
FOOTER = "Already yours this month — reopening it never uses another space."
FULL_LAWS = (
    "bns",
    "bnss",
    "uapa",
    "pss",
    "mtp",
    "ipc",
    "crpc",
    "cpc",
    "iea",
    "ida",
)
FORBIDDEN = (
    "Already in Playground",
    "Unlock Playground",
    "Subscribe to use Playground",
    "Sign in",
    "Create an account",
    "Resume Playground",
    "Playground full this month",
    FOOTER,
    "law unlocks",
    "7 will remain",
    "9 will remain",
    "Premium",
    "Unlimited",
    "Free plan",
)
LEGACY_MARKERS = (
    "data-plus-add",
    "data-guest-add-desktop",
    "data-guest-add-phone",
    "data-signed-in-add-desktop",
    "data-signed-in-add-phone",
    "data-expired-add-phone",
    "data-halted-add-phone",
    'data-expired-add="desktop"',
    'data-halted-add="desktop"',
    "plus-add-",
    "guest-add-(?!gate)",
    "signed-add-",
    "expired-add-",
    "halted-add-",
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
    )


def _mu_app(tmp_path: Path, *, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _subscribe(
    client: TestClient,
    *,
    tier: str = "plus",
    status: str = "active",
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _plus_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    return client


def _confirm_add(client: TestClient, law_id: str, *, scope: str = "sections"):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = scope
    return client.post(add_path(law_id), data=payload, follow_redirects=False)


def _seed_roster(client: TestClient, *law_ids: str) -> None:
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    for law_id in law_ids:
        result = roster._repo.consume_law(
            USER,
            period_start=start,
            law_id=law_id,
            law_limit=10,
            allow_new=True,
        )
        assert result.ok, result.status


def _panel_attrs(html: str) -> str:
    match = re.search(r'<section\s+class="pg-sheet-panel"[^>]*>', html, re.S)
    assert match, "no Add sheet panel on the page"
    return re.sub(r"\s+", " ", match.group(0))


def _sheet(html: str) -> str:
    return unescape(
        html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]
    )


def _confirm(html: str) -> str:
    sheet = _sheet(html)
    assert 'data-add-step="confirm"' in sheet, "no confirm step in the sheet"
    return sheet.split('data-add-step="confirm"', 1)[1].split(
        'data-add-step="scope"', 1
    )[0]


def _head_cta(html: str) -> str:
    band = unescape(
        html.split('class="panel ActHead', 1)[1].split('<div class="bareact-chapters"', 1)[0]
    )
    assert 'class="ActHead-cta LawPlaygroundCta"' in band, "no Playground action in the head"
    return band.split('class="ActHead-cta LawPlaygroundCta"', 1)[1].split("<button", 1)[0]


def _assert_no_legacy(html: str) -> None:
    """No per-surface twins or classes; `data-guest-add-gate` is a kept hook."""
    for marker in LEGACY_MARKERS:
        assert re.search(marker, html) is None, marker


def _assert_act_page_underneath(html: str, law_id: str) -> None:
    """A direct Add URL is the Act page with the dialog open (M2 Q4)."""
    assert f'data-act-head="{law_id}"' in html
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    dialog = re.search(r"<dialog[^>]*>", html)
    assert dialog, "no dialog on the page"
    for attr in (
        'class="pg-sheet"',
        "data-pg-sheet-host",
        "data-pg-sheet-direct",
        f'data-pg-sheet-return="/laws/{law_id}"',
        " open",
    ):
        assert attr in dialog.group(0), attr
    assert html.count('class="pg-sheet-panel"') == 1


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    start, _end = playground_month_bounds()
    consumed = ()
    if roster is not None:
        consumed = tuple(
            sorted(
                item.law_id
                for item in roster._repo.list_items(USER, start)
                if item.consumed_at is not None
            )
        )
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "consumed": consumed,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
    }


def test_phone_plus_add_eligible_confirm_uses_m2_sheet_copy(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    _assert_no_legacy(html)
    _assert_act_page_underneath(html, "ndps")
    attrs = _panel_attrs(html)
    assert 'data-pg-kind="eligible_to_add"' in attrs
    assert 'data-step="confirm"' in attrs
    assert 'data-roster-confirm="ndps"' in attrs
    confirm = _confirm(html)
    assert f'<p class="pg-eyebrow">{MONTH}</p>' in confirm
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in confirm
    assert f'<p class="pg-add-lede">{LEDE}</p>' in confirm
    assert f'<p class="pg-add-note pg-add-note--left">{SPACE}</p>' in confirm
    assert f'<p class="pg-add-note pg-add-note--left">{REMAIN}</p>' in confirm
    assert f'<form method="post" action="{add_path("ndps")}" data-pg-add-confirm>' in confirm
    assert 'name="csrf_token"' in confirm
    assert 'name="confirm" value="add"' in confirm
    assert f'<button type="submit" class="pg-add-primary">{TITLE}</button>' in confirm
    # One sheet for both widths: Cancel is a real link back to the Act.
    assert '<a class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in confirm
    assert FOOTER not in confirm
    assert f"Add NDPS Act to {MONTH}?" not in confirm
    for phrase in FORBIDDEN:
        assert phrase not in confirm, phrase
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_plus_add_plus01_trigger_stays_eligible_sheet(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get("/laws/ndps").text
    head = re.search(r'<section\s+class="panel ActHead[^>]*>', html, re.S).group(0)
    assert "data-plus-bareact" in head
    cta = _head_cta(html)
    assert 'data-pg-kind="eligible_to_add"' in cta
    assert f'href="{add_path("ndps")}"' in cta
    assert "data-pg-sheet" in cta
    assert "+ Add to Playground" in cta
    assert "Already in Playground" not in cta
    assert "<dialog" not in html
    assert "data-pg-add" not in html


def test_phone_plus_add_in_page_fetch_ships_the_panel_alone(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    fetched = client.get(add_path("ndps"), headers={"X-Requested-With": "pg-sheet"})
    assert fetched.status_code == 200
    html = unescape(fetched.text)
    _assert_no_legacy(html)
    assert "<dialog" not in html
    assert 'class="panel ActHead' not in html
    assert 'data-pg-kind="eligible_to_add"' in _panel_attrs(html)
    confirm = _confirm(html)
    assert f'<p class="pg-add-lede">{LEDE}</p>' in confirm
    assert f'<p class="pg-add-note pg-add-note--left">{SPACE}</p>' in confirm
    assert "data-pg-add-confirm" in confirm
    assert _facts(client) == before


def test_phone_plus_add_confirm_without_scope_does_not_consume(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    missing = client.post(
        add_path("ndps"),
        data={"confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert missing.status_code == 403
    assert _facts(client) == before

    unconfirmed = client.post(
        add_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert unconfirmed.status_code == 303
    assert "/playground/roster" in (unconfirmed.headers.get("location") or "")
    assert _facts(client) == before

    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    scope_page = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert scope_page.status_code == 200
    assert 'data-step="scope"' in _panel_attrs(scope_page.text)
    assert 'data-add-step="scope"' in scope_page.text
    assert ">Entire Act<" in scope_page.text
    assert ">Choose sections<" in scope_page.text
    # The no-JS re-render is the panel on its own, not the Act page.
    assert "<dialog" not in scope_page.text
    assert 'class="panel ActHead' not in scope_page.text
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_plus_add_scope_still_consumes_through_existing_handler(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    added = _confirm_add(client, "ndps", scope="entire")
    assert added.status_code == 303
    assert added.headers.get("location") == law_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    cap = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER)
    )
    assert cap.used == 1
    assert cap.remaining == 9


def test_phone_plus_re_add_roster_full_already_active_keep_live_kinds(
    tmp_path: Path,
) -> None:
    readd = _plus_client(tmp_path / "readd")
    added = _confirm_add(readd, "ndps", scope="entire")
    assert added.status_code == 303
    used_after_add = readd.app.state.roster.capacity(
        USER, readd.app.state.entitlement_service.resolve(USER)
    ).used
    removed = readd.post(remove_path("ndps"), data=_csrf(readd), follow_redirects=False)
    assert removed.status_code == 303
    html = unescape(readd.get(add_path("ndps")).text)
    _assert_no_legacy(html)
    assert 'data-pg-kind="re_add"' in _panel_attrs(html)
    confirm = _confirm(html)
    assert '<p class="pg-add-note pg-add-note--left">No extra space used.</p>' in confirm
    assert '<p class="pg-add-note pg-add-note--left">Your progress will be saved.</p>' in confirm
    assert '<button type="submit" class="pg-add-primary">Add back</button>' in confirm
    # Same confirm markup as a first add — the lede stays, the lines differ.
    assert f'<p class="pg-add-lede">{LEDE}</p>' in confirm
    assert SPACE not in confirm
    assert REMAIN not in confirm
    assert FOOTER not in html
    restored = _confirm_add(readd, "ndps", scope="entire")
    assert restored.status_code == 303
    assert readd.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    assert (
        readd.app.state.roster.capacity(
            USER, readd.app.state.entitlement_service.resolve(USER)
        ).used
        == used_after_add
    )

    full = _plus_client(tmp_path / "full")
    _seed_roster(full, *FULL_LAWS)
    full_html = unescape(full.get(add_path("ndps")).text)
    _assert_no_legacy(full_html)
    assert 'data-pg-kind="roster_full"' in _panel_attrs(full_html)
    full_sheet = _sheet(full_html)
    assert '<h1 id="pg-add-title" class="pg-add-title">Playground full this month</h1>' in full_sheet
    assert 'data-playground-gate="roster_full"' in full_sheet
    assert 'class="pg-plan-list"' in full_sheet
    assert '<a class="pg-btn pg-btn--ghost" href="/playground/roster/next">Plan next month</a>' in full_sheet
    assert '<a class="pg-btn pg-btn--ghost" href="/playground">Back to Playground</a>' in full_sheet
    assert LEDE not in full_sheet
    assert "data-pg-add-confirm" not in full_sheet

    active = _plus_client(tmp_path / "active")
    seeded = _confirm_add(active, "ndps", scope="entire")
    assert seeded.status_code == 303
    again = active.get(add_path("ndps"), follow_redirects=False)
    assert again.status_code == 303
    assert "data-pg-add" not in (again.headers.get("location") or "")


def test_phone_plus_add_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "Add sheet (M2)" in css
    sheet_css = css.split("Add sheet (M2)", 1)[1].split(
        "Guest desktop Playground intro", 1
    )[0]
    # One rule set, both widths: the phone adjustments in a single block.
    assert sheet_css.count("@media (max-width: 560px)") == 1
    phone_block = sheet_css.split("@media (max-width: 560px)", 1)[1]
    assert "env(safe-area-inset-bottom" in phone_block
    assert ".pg-sheet-panel[data-pg-add] {" in phone_block
    primary = sheet_css.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in primary
    assert "min-height: 50px" in primary
    assert "padding: 26px 28px 26px" in sheet_css.split(
        ".pg-sheet-panel[data-pg-add] {", 1
    )[1].split("}", 1)[0]
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", sheet_css) is None
    # The dialog's own phone geometry: full-bleed bottom sheet.
    dialog_phone = css.split("@media (max-width: 560px) {\n  .pg-sheet,", 1)[1].split(
        "@media", 1
    )[0]
    assert "max-height: min(92dvh, 100%)" in dialog_phone
    assert "safe-area-inset-bottom" in dialog_phone
    assert "width: calc(100% - (2 * var(--pg-shell-pad)))" in dialog_phone
    assert "display: none" in dialog_phone.split(".pg-sheet-close {", 1)[1].split("}", 1)[0]
    for legacy in (
        "is plus/02-screen:",
        ":has([data-plus-add-phone])",
        ":has([data-guest-add-phone])",
        ":has([data-signed-in-add-phone])",
        "[data-plus-add-desktop]",
        "plus-add-submit",
    ):
        assert legacy not in css, legacy
    for path in (MOBILE, STYLES):
        text = path.read_text(encoding="utf-8")
        assert "data-plus-add" not in text
        assert ".pg-add-" not in text
    js = PG_JS.read_text(encoding="utf-8")
    assert "data-plus-add-phone" not in js
    assert "event.target === dialog" in js
    assert '"X-Requested-With": "pg-sheet"' in js
    assert "data-pg-sheet-direct" in js
    assert "data-pg-sheet-return" in js
    assert "history.replaceState" in js
    src = ADD.read_text(encoding="utf-8")
    assert '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}' in src
    assert "data-pg-sheet-direct" in src
    assert src.count('{% include "partials/playground_add_panel.html" %}') == 2
    panel_src = PANEL.read_text(encoding="utf-8")
    _assert_no_legacy(src)
    _assert_no_legacy(panel_src)
    assert "plus_add" not in panel_src
    confirm_src = panel_src.split('data-add-step="confirm"', 1)[1].split(
        'data-add-step="scope"', 1
    )[0]
    assert "data-pg-add-confirm" in confirm_src
    assert "data-pg-sheet-close>Cancel</a>" in confirm_src
    assert "cancel_href" in confirm_src
    assert "reading_name|default(short_title) }} joins this month's Playground" in confirm_src
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg52" in base
    assert "playground.css?v=pg49" not in base
    assert "playground.css?v=pg34" not in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "playground.js?v=pg12" in base


def test_guest_free_expired_halted_pro_other_law_get_the_same_sheet(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest"))
    guest_html = unescape(guest.get(add_path("ndps")).text)
    _assert_no_legacy(guest_html)
    _assert_act_page_underneath(guest_html, "ndps")
    assert 'data-pg-kind="guest"' in _panel_attrs(guest_html)
    guest_sheet = _sheet(guest_html)
    assert 'data-guest-add-gate>Sign in</a>' in guest_sheet
    assert 'data-guest-add-gate>Create an account</a>' in guest_sheet
    assert f"Reading {NDPS_READING_NAME} stays free" in guest_sheet
    assert LEDE not in guest_sheet

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = unescape(free.get(add_path("ndps")).text)
    _assert_no_legacy(free_html)
    _assert_act_page_underneath(free_html, "ndps")
    assert 'data-pg-kind="subscribe"' in _panel_attrs(free_html)
    free_sheet = _sheet(free_html)
    assert '<a class="pg-add-primary" href="/playground">Unlock Playground</a>' in free_sheet
    assert f"Turning {NDPS_READING_NAME} into a learning experience needs a plan." in free_sheet
    assert LEDE not in free_sheet

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=datetime(2026, 8, 16, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    expired_html = unescape(expired.get(add_path("ndps")).text)
    _assert_no_legacy(expired_html)
    _assert_act_page_underneath(expired_html, "ndps")
    expired_attrs = _panel_attrs(expired_html)
    assert "data-expired-add" in expired_attrs
    assert 'data-pg-kind="resume"' in expired_attrs
    expired_sheet = _sheet(expired_html)
    assert ">Resume Playground</a>" in expired_sheet
    assert '<a class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in expired_sheet
    assert LEDE not in expired_sheet

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = unescape(halted.get(add_path("ndps")).text)
    _assert_no_legacy(halted_html)
    _assert_act_page_underneath(halted_html, "ndps")
    halted_attrs = _panel_attrs(halted_html)
    assert "data-halted-add" in halted_attrs
    assert 'data-pg-kind="resume"' in halted_attrs
    assert LEDE not in _sheet(halted_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get(add_path("ndps")).text)
    _assert_no_legacy(pro_html)
    _assert_act_page_underneath(pro_html, "ndps")
    assert 'data-pg-kind="eligible_to_add"' in _panel_attrs(pro_html)
    pro_confirm = _confirm(pro_html)
    assert f'<p class="pg-add-lede">{LEDE}</p>' in pro_confirm
    assert f"This will use 1 of your 30 law spaces for {MONTH}." in pro_confirm
    assert "You'll have 29 spaces remaining." in pro_confirm

    plus = _plus_client(tmp_path / "plus")
    bns = unescape(plus.get(add_path("bns")).text)
    _assert_no_legacy(bns)
    _assert_act_page_underneath(bns, "bns")
    assert LEDE not in bns
    assert f'<p class="pg-add-lede">{_lede(BNS_READING_NAME)}</p>' in _confirm(bns)
    assert NDPS_READING_NAME not in _sheet(bns)


def _screenshot(page, path: Path, *, attempts: int = 5) -> None:
    last: OSError | None = None
    for index in range(attempts):
        try:
            page.screenshot(path=str(path), full_page=False)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.4 * (index + 1))
    assert last is not None
    raise last


def _serve(app, host: str = "127.0.0.1") -> tuple[int, object]:
    import uvicorn

    sock = socket.socket()
    sock.bind((host, 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(80):
        probe = socket.socket()
        probe.settimeout(0.1)
        ready = probe.connect_ex((host, port)) == 0
        probe.close()
        if ready:
            break
        time.sleep(0.05)
    else:
        pytest.fail("server did not bind")
    return port, server


def test_phone_plus_add_screen02_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_add_screen02_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    before = _facts(client)
    act = get_bare_act("ndps")
    assert act is not None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        cookies = [
            {
                "name": SESSION_COOKIE_NAME,
                "value": session,
                "url": origin,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ]
        if csrf:
            cookies.append(
                {
                    "name": CSRF_COOKIE_NAME,
                    "value": csrf,
                    "url": origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            )
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )

        def open_sheet():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
            page.wait_for_selector(
                "[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000
            )
            page.wait_for_timeout(400)

        open_sheet()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              const submit = confirmStep.querySelector('.pg-add-primary');
              const cancel = confirmStep.querySelector('.pg-add-secondary[data-pg-sheet-close]');
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const handle = getComputedStyle(panel, '::before');
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              const head = document.querySelector('.ActHead[data-plus-bareact]');
              const cta = head && head.querySelector('[data-pg-sheet]');
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                panels: document.querySelectorAll('[data-pg-add]').length,
                twins: panel.querySelectorAll('[data-plus-add-desktop], [data-plus-add-phone]').length,
                panelDisplay: getComputedStyle(panel).display,
                title: confirmStep.querySelector('.pg-add-title')
                  && confirmStep.querySelector('.pg-add-title').textContent.trim(),
                lede: confirmStep.querySelector('.pg-add-lede')
                  && confirmStep.querySelector('.pg-add-lede').textContent.trim(),
                notes: [...confirmStep.querySelectorAll('.pg-add-note--left')].map(
                  (el) => el.textContent.trim()
                ),
                submit: {
                  tag: submit && submit.tagName,
                  type: submit && submit.getAttribute('type'),
                  text: submit && submit.textContent.trim(),
                  width: submit && submit.getBoundingClientRect().width,
                  height: submit && submit.getBoundingClientRect().height,
                },
                cancel: Boolean(cancel),
                cancelHref: cancel && cancel.getAttribute('href'),
                cancelH: cancel ? cancel.getBoundingClientRect().height : 0,
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle.display,
                dialog: { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabFocused: Boolean(
                  document.querySelector('[data-plus-bareact-phone-tabs]')
                  && document.querySelector('[data-plus-bareact-phone-tabs]').contains(
                    document.activeElement
                  )
                ),
                backgroundTitle: head && head.querySelector('.ActHead-title')
                  && head.querySelector('.ActHead-title').textContent.trim(),
                addCta: cta && cta.textContent.replace(/\\s+/g, ' ').trim(),
                already: head && head.innerText.includes('Already in Playground'),
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                reopen: confirmStep.innerText.includes('reopening it never uses another space'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const submit = panel.querySelector("[data-add-step='confirm'] .pg-add-primary");
              const box = submit.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                submitW: box.width,
                submitH: box.height,
                inPanel: panel.contains(submit),
                panelBottom: p.bottom,
                panelTop: p.top,
                dialogH: dialog.getBoundingClientRect().height,
                paddingBottom: getComputedStyle(panel).paddingBottom,
              };
            }"""
        )
        page.set_viewport_size({"width": 390, "height": 844})

        panel_top = geo["panel"]["top"]
        page.mouse.click(195, max(20, panel_top - 40))
        page.wait_for_timeout(250)
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const cta = document.querySelector('.ActHead[data-plus-bareact] [data-pg-sheet]');
              const head = document.querySelector('.ActHead[data-plus-bareact]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
                title: head && head.querySelector('.ActHead-title')
                  && head.querySelector('.ActHead-title').textContent.trim(),
                already: head && head.innerText.includes('Already in Playground'),
              };
            }"""
        )

        page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        escaped = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const cta = document.querySelector('.ActHead[data-plus-bareact] [data-pg-sheet]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
              };
            }"""
        )

        page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000)
        page.locator("[data-pg-add] [data-add-step='confirm'] .pg-add-primary").click()
        page.wait_for_timeout(250)
        scoped = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              return {
                path: location.pathname,
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                entire: Boolean(scopeStep && scopeStep.innerText.includes('Entire Act')),
                sections: Boolean(scopeStep && scopeStep.innerText.includes('Choose sections')),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "eligible_to_add"
    assert geo["url"] == "/laws/ndps"
    assert geo["panels"] == 1
    assert geo["twins"] == 0
    assert geo["panelDisplay"] != "none"
    assert geo["title"] == TITLE
    assert geo["lede"] == LEDE
    assert geo["notes"] == [SPACE, REMAIN]
    assert geo["submit"]["tag"] == "BUTTON"
    assert geo["submit"]["type"] == "submit"
    assert geo["submit"]["text"] == TITLE
    assert geo["submit"]["width"] >= 300
    assert geo["submit"]["height"] >= 44
    assert geo["cancel"] is True
    assert geo["cancelHref"] == "/laws/ndps"
    assert geo["cancelH"] >= 44
    assert geo["closeDisplay"] == "none"
    assert geo["handleDisplay"] == "block"
    assert geo["dialog"]["width"] >= 300
    assert geo["dialog"]["width"] <= 390
    assert geo["panel"]["left"] >= 0
    assert geo["panel"]["width"] >= 300
    assert geo["panel"]["bottom"] >= 840
    assert geo["panel"]["top"] > 300
    assert geo["overflow"] is False
    assert geo["backgroundTitle"] == act.title
    assert geo["addCta"] == "+ Add to Playground"
    assert geo["already"] is False
    assert geo["confirmHidden"] is False
    assert geo["scopeHidden"] is True
    assert geo["reopen"] is False
    assert geo["tabFocused"] is False
    assert short["overflow"] is False
    assert short["submitW"] >= 300
    assert short["submitH"] >= 44
    assert short["inPanel"] is True
    assert short["panelBottom"] <= 561
    assert short["panelTop"] >= 0
    assert "env(safe-area-inset-bottom" in PG_CSS.read_text(encoding="utf-8").split(
        "Add sheet (M2)", 1
    )[1].split("@media (max-width: 560px)", 1)[1]
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["focused"] is True
    assert closed["title"] == act.title
    assert closed["already"] is False
    assert escaped["open"] is False
    assert escaped["url"] == "/laws/ndps"
    assert escaped["focused"] is True
    assert scoped["path"] == "/laws/ndps"
    assert scoped["confirmHidden"] is True
    assert scoped["scopeHidden"] is False
    assert scoped["entire"] is True
    assert scoped["sections"] is True
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_add_screen02_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_add_screen02_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        cookies = [
            {
                "name": SESSION_COOKIE_NAME,
                "value": session,
                "url": origin,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ]
        if csrf:
            cookies.append(
                {
                    "name": CSRF_COOKIE_NAME,
                    "value": csrf,
                    "url": origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const submit = confirmStep.querySelector('.pg-add-primary');
              const cancel = confirmStep.querySelector('.pg-add-secondary[data-pg-sheet-close]');
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const d = dialog.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                panels: document.querySelectorAll('[data-pg-add]').length,
                twins: panel.querySelectorAll('[data-plus-add-desktop], [data-plus-add-phone]').length,
                title: confirmStep.querySelector('.pg-add-title').textContent.trim(),
                lede: confirmStep.querySelector('.pg-add-lede').textContent.trim(),
                notes: [...confirmStep.querySelectorAll('.pg-add-note--left')].map(
                  (el) => el.textContent.trim()
                ),
                submitText: submit.textContent.trim(),
                submitH: submit.getBoundingClientRect().height,
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                panelW: panel.getBoundingClientRect().width,
                dialogWidth: d.width,
                notFullBleed: d.width < 800 && d.left > 100,
                reopen: confirmStep.innerText.includes('reopening it never uses another space'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "eligible_to_add"
    assert geo["panels"] == 1
    assert geo["twins"] == 0
    assert geo["title"] == TITLE
    assert geo["lede"] == LEDE
    assert geo["notes"] == [SPACE, REMAIN]
    assert geo["submitText"] == TITLE
    assert geo["submitH"] == pytest.approx(50, abs=2)
    assert geo["cancelDisplay"] != "none"
    assert geo["closeDisplay"] != "none"
    assert geo["panelW"] == pytest.approx(460, abs=8)
    assert geo["notFullBleed"] is True
    assert geo["reopen"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
