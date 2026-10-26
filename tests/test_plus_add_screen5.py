"""Plus cohort desktop NDPS Add-dialog Screen 05 (CTA map plus/05-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground/laws/ndps/add
with a real active Plus EntitlementSnapshot. M2: one Add sheet per state
for every Act and both widths — a direct URL is the Act page with the sheet
open in a <dialog> (M2 Q4); the in-page fetch and the no-JS POST re-render
ship the panel on its own. Guest / Free / Pro / expired / halted get the
same sheet with their own state. Choose sections continues to the existing
playground_select route.
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
from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, InMemorySessionStore
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
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD_TPL = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
PANEL_TPL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
SELECT_TPL = ROOT / "src/constitution_memorizer/web/templates/playground_select.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
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
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
)
LEGACY_MARKERS = (
    "data-plus-add",
    "data-guest-add-desktop",
    "data-guest-add-phone",
    "data-signed-in-add-desktop",
    "data-signed-in-add-phone",
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


def _panel_attrs(html: str) -> str:
    match = re.search(r'<section\s+class="pg-sheet-panel"[^>]*>', html, re.S)
    assert match, "no Add sheet panel on the page"
    return re.sub(r"\s+", " ", match.group(0))


def _sheet(html: str) -> str:
    """The one panel, whichever wrapper served it."""
    return unescape(
        html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]
    )


def _confirm(html: str) -> str:
    sheet = _sheet(html)
    assert 'data-add-step="confirm"' in sheet, "no confirm step in the sheet"
    return sheet.split('data-add-step="confirm"', 1)[1].split(
        'data-add-step="scope"', 1
    )[0]


def _scope(html: str) -> str:
    return unescape(html.split('data-add-step="scope"', 1)[1])


def _assert_no_legacy(html: str) -> None:
    """No per-surface twins or classes; `data-guest-add-gate` is a kept hook."""
    for marker in LEGACY_MARKERS:
        assert re.search(marker, html) is None, marker


def _assert_act_page_underneath(html: str, law_id: str) -> None:
    """A direct Add URL is the Act page with the dialog open (M2 Q4)."""
    assert f'data-act-head="{law_id}"' in html
    assert 'class="panel ActHead' in html
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    assert "data-hard-gate" not in html
    dialog = re.search(r"<dialog[^>]*>", html)
    assert dialog, "no dialog on the page"
    for attr in (
        'class="pg-sheet"',
        "data-pg-sheet-host",
        "data-pg-sheet-direct",
        f'data-pg-sheet-return="/laws/{law_id}"',
        'aria-labelledby="pg-add-title"',
        " open",
    ):
        assert attr in dialog.group(0), attr
    assert html.count("<dialog") == 1
    assert html.count('class="pg-sheet-panel"') == 1


def _assert_subscriber_confirm(
    html: str, *, law_id: str, reading_name: str, law_limit: int, remaining: int
) -> None:
    confirm = _confirm(html)
    assert f'<p class="pg-eyebrow">{MONTH}</p>' in confirm
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in confirm
    assert confirm.count(TITLE) == 2
    assert f'<p class="pg-add-lede">{_lede(reading_name)}</p>' in confirm
    assert (
        f'<p class="pg-add-note pg-add-note--left">This will use 1 of your {law_limit} law spaces for {MONTH}.</p>'
        in confirm
    )
    assert (
        f'<p class="pg-add-note pg-add-note--left">You\'ll have {remaining} spaces remaining.</p>'
        in confirm
    )
    assert f'<form method="post" action="{add_path(law_id)}" data-pg-add-confirm>' in confirm
    assert 'name="csrf_token"' in confirm
    assert 'name="confirm" value="add"' in confirm
    assert f'<button type="submit" class="pg-add-primary">{TITLE}</button>' in confirm
    assert f'<a class="pg-add-secondary" href="/laws/{law_id}" data-pg-sheet-close>Cancel</a>' in confirm
    assert FOOTER not in confirm
    assert "reopening it never uses another space" not in confirm


def test_plus_add_sheet_copy_is_shared_m2_lede_not_plus_variant(tmp_path: Path) -> None:
    """The NDPS-only plus_add copy variant is no longer rendered: Plus and
    Pro get the one lede with the roster's own numbers."""
    plus = _plus_client(tmp_path / "plus")
    plus_html = unescape(plus.get(add_path("ndps")).text)
    _assert_subscriber_confirm(
        plus_html, law_id="ndps", reading_name=NDPS_READING_NAME, law_limit=10, remaining=9
    )
    assert f"in {MONTH}. 9 will remain." not in plus_html
    assert "plus_add" not in plus_html
    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get(add_path("ndps")).text)
    _assert_subscriber_confirm(
        pro_html, law_id="ndps", reading_name=NDPS_READING_NAME, law_limit=30, remaining=29
    )
    assert _confirm(plus_html).replace("10 law", "").replace(" 9 spaces", "") == _confirm(
        pro_html
    ).replace("30 law", "").replace(" 29 spaces", "").replace(
        re.search(r'name="csrf_token" value="([^"]*)"', _confirm(pro_html)).group(1),
        re.search(r'name="csrf_token" value="([^"]*)"', _confirm(plus_html)).group(1),
    )


def test_plus_add_is_subscriber_confirm_only(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    _assert_no_legacy(html)
    _assert_act_page_underneath(html, "ndps")
    attrs = _panel_attrs(html)
    assert 'data-pg-kind="eligible_to_add"' in attrs
    assert 'data-step="confirm"' in attrs
    assert 'data-skip-confirm="false"' in attrs
    assert 'data-roster-confirm="ndps"' in attrs
    # One dialog landmark: the host <dialog> carries role/aria-modal/label.
    assert 'role="dialog"' not in attrs
    assert 'aria-labelledby="pg-add-title"' in html.split("<dialog ", 1)[1].split(">", 1)[0]
    assert "data-expired-add" not in attrs
    assert "data-halted-add" not in attrs
    _assert_subscriber_confirm(
        html, law_id="ndps", reading_name=NDPS_READING_NAME, law_limit=10, remaining=9
    )
    sheet = _sheet(html)
    assert 'data-add-step="confirm" >' in sheet or 'data-add-step="confirm">' in sheet
    assert 'data-add-step="scope" hidden' in sheet
    assert "Sign in" not in sheet
    assert "Create an account" not in sheet
    assert "Unlock Playground" not in sheet
    assert "Resume Playground" not in sheet
    assert "Playground full this month" not in sheet
    assert "temporarily unavailable" not in sheet
    assert "Device limit" not in sheet
    assert "Subscribe to use Playground" not in sheet
    assert "Already in Playground" not in sheet
    for phrase in INVENTED:
        assert phrase not in sheet, phrase
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert client.app.state.playground.get_item(USER, "ndps") is None


def test_plus_add_in_page_fetch_and_post_ship_the_panel_alone(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    fetched = client.get(add_path("ndps"), headers={"X-Requested-With": "pg-sheet"})
    assert fetched.status_code == 200
    html = unescape(fetched.text)
    _assert_no_legacy(html)
    assert "<dialog" not in html
    assert 'class="panel ActHead' not in html
    assert 'data-pg-kind="eligible_to_add"' in _panel_attrs(html)
    _assert_subscriber_confirm(
        html, law_id="ndps", reading_name=NDPS_READING_NAME, law_limit=10, remaining=9
    )
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    posted = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert posted.status_code == 200
    posted_html = unescape(posted.text)
    assert "<dialog" not in posted_html
    assert 'class="panel ActHead' not in posted_html
    assert 'data-step="scope"' in _panel_attrs(posted_html)
    assert 'data-add-step="confirm" hidden' in _sheet(posted_html)
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_plus_re_add_keeps_no_extra_space_copy(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "entire"
    added = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert added.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    removed = client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert removed.status_code == 303
    html = unescape(client.get(add_path("ndps")).text)
    _assert_no_legacy(html)
    _assert_act_page_underneath(html, "ndps")
    assert 'data-pg-kind="re_add"' in _panel_attrs(html)
    confirm = _confirm(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in confirm
    assert f'<p class="pg-add-lede">{LEDE}</p>' in confirm
    assert '<p class="pg-add-note pg-add-note--left">Your progress will be saved.</p>' in confirm
    assert '<p class="pg-add-note pg-add-note--left">No extra space used.</p>' in confirm
    assert '<button type="submit" class="pg-add-primary">Add back</button>' in confirm
    assert SPACE not in confirm
    assert REMAIN not in confirm
    assert FOOTER not in html


def test_plus_add_is_one_sheet_for_both_widths(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = unescape(client.get(add_path("ndps")).text)
    _assert_no_legacy(html)
    assert html.count('class="pg-sheet-panel"') == 1
    assert html.count("data-pg-add ") + html.count("data-pg-add\n") == 1
    assert html.count('id="pg-add-title"') == 1
    assert html.count("data-pg-add-confirm") == 1
    assert html.count('data-add-step="confirm"') == 1
    assert html.count('data-add-step="scope"') == 1
    assert html.count(f'<p class="pg-add-lede">{LEDE}</p>') == 1
    assert html.count("data-pg-sheet-close>Cancel</a>") == 2
    assert f"Add NDPS Act to {MONTH}?" not in html


def test_plus_add_scope_choice_is_existing_machine(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get(add_path("ndps")).text
    scope = _scope(html)
    assert f'<h1 id="pg-add-scope-title" class="pg-add-title">Add {NDPS_READING_NAME}</h1>' in scope
    assert (
        f'<p class="pg-add-lede">Choose how much of {NDPS_READING_NAME} enters your recall schedule.</p>'
        in scope
    )
    assert "Add NDPS Act" not in scope
    assert ">Entire Act<" in scope
    assert ">Choose sections<" in scope
    assert "Pick sections — or open one and pick single clauses" in scope
    assert (
        '<p class="pg-add-note pg-add-note--left">Nothing is scheduled yet — provisions activate the first time you learn them.</p>'
        in scope
    )
    assert f'<form method="post" action="{add_path("ndps")}">' in scope
    assert 'name="scope" value="entire"' in scope
    assert 'name="scope" value="sections"' in scope
    assert 'name="csrf_token"' in scope
    assert 'name="confirm" value="add"' in scope
    assert '<a class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in scope
    assert "Unlock Playground" not in scope
    assert "Create an account" not in scope


def test_plus_add_confirm_post_then_choose_sections(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    missing = client.post(
        add_path("ndps"),
        data={"confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert missing.status_code == 403

    unconfirmed = client.post(
        add_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert unconfirmed.status_code == 303
    assert "/playground/roster" in (unconfirmed.headers.get("location") or "")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    scope_page = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert scope_page.status_code == 200
    assert 'data-add-step="scope"' in scope_page.text
    assert ">Entire Act<" in scope_page.text
    assert "learnable" in unescape(scope_page.text)
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    payload["scope"] = "sections"
    added = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert added.status_code == 303
    assert added.headers.get("location") == sections_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    select = client.get(sections_path("ndps"))
    assert select.status_code == 200
    assert "Choose what to learn" in select.text
    assert 'data-pg-picker' in select.text
    assert 'name="csrf_token"' in select.text
    assert "data-pg-add" not in select.text
    assert "pg-add-title" not in select.text
    empty = client.post(
        sections_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert empty.status_code in {303, 400}
    if empty.status_code == 400:
        assert empty.json().get("detail") == "invalid_selection"


def test_plus_add_entire_act_uses_existing_endpoint(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "entire"
    added = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert added.status_code == 303
    assert added.headers.get("location") == law_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    again = client.get(add_path("ndps"), follow_redirects=False)
    assert again.status_code == 303


def test_plus_add_does_not_open_from_bare_act_without_sheet_cta(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get("/laws/ndps").text
    head = re.search(r'<section\s+class="panel ActHead[^>]*>', html, re.S).group(0)
    assert "data-plus-bareact" in head
    assert 'data-pg-kind="eligible_to_add"' in head
    cta = html.split('class="ActHead-cta LawPlaygroundCta"', 1)[1].split("</div>", 1)[0]
    assert "+ Add to Playground" in cta
    assert f'href="{add_path("ndps")}"' in cta
    assert "data-pg-sheet" in cta
    assert 'data-pg-kind="eligible_to_add"' in cta
    assert "Already in Playground" not in cta
    # The sheet is not in the Act page; it opens from the CTA or by URL.
    assert "<dialog" not in html
    assert "data-pg-add" not in html


def test_halted_expired_pro_free_guest_get_the_same_sheet_with_own_state(
    tmp_path: Path,
) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = unescape(halted.get(add_path("ndps")).text)
    _assert_no_legacy(halted_html)
    _assert_act_page_underneath(halted_html, "ndps")
    halted_attrs = _panel_attrs(halted_html)
    assert "data-halted-add" in halted_attrs
    assert 'data-pg-kind="resume"' in halted_attrs
    halted_sheet = _sheet(halted_html)
    assert 'class="pg-add-primary" href="/billing/subscriptions">Manage subscription<' in halted_sheet
    assert '<a class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in halted_sheet
    assert LEDE not in halted_sheet
    assert "data-pg-add-confirm" not in halted_sheet

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="expired")
    expired_html = unescape(expired.get(add_path("ndps")).text)
    _assert_no_legacy(expired_html)
    _assert_act_page_underneath(expired_html, "ndps")
    assert LEDE not in _sheet(expired_html)
    assert "data-pg-add-confirm" not in _sheet(expired_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get(add_path("ndps")).text)
    _assert_no_legacy(pro_html)
    _assert_act_page_underneath(pro_html, "ndps")
    assert 'data-pg-kind="eligible_to_add"' in _panel_attrs(pro_html)
    _assert_subscriber_confirm(
        pro_html, law_id="ndps", reading_name=NDPS_READING_NAME, law_limit=30, remaining=29
    )

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = unescape(free.get(add_path("ndps")).text)
    _assert_no_legacy(free_html)
    _assert_act_page_underneath(free_html, "ndps")
    assert 'data-pg-kind="subscribe"' in _panel_attrs(free_html)
    free_sheet = _sheet(free_html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in free_sheet
    assert (
        f'<p class="pg-add-lede">Turning {NDPS_READING_NAME} into a learning experience needs a plan. Reading it stays free.</p>'
        in free_sheet
    )
    assert '<a class="pg-add-primary" href="/playground">Unlock Playground</a>' in free_sheet
    assert '<p class="pg-add-note">Plus · Pro · Max — ' in free_sheet
    assert "/ month. Constitution learning stays free.</p>" in free_sheet
    assert ">Cancel<" not in free_sheet
    assert "data-pg-add-confirm" not in free_sheet

    guest_html = unescape(TestClient(_mu_app(tmp_path / "guest")).get(add_path("ndps")).text)
    _assert_no_legacy(guest_html)
    _assert_act_page_underneath(guest_html, "ndps")
    assert 'data-pg-kind="guest"' in _panel_attrs(guest_html)
    guest_sheet = _sheet(guest_html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in guest_sheet
    assert (
        f"Playground needs an account. Reading {NDPS_READING_NAME} stays free — sign in and you’ll come right back here."
        in guest_sheet
    )
    login_href = f"/login?next={add_path('ndps')}"
    assert f'<a class="pg-add-primary" href="{login_href}" data-guest-add-gate>Sign in</a>' in guest_sheet
    assert (
        f'<a class="pg-add-secondary" href="{login_href}" data-guest-add-gate>Create an account</a>'
        in guest_sheet
    )
    assert "data-pg-add-confirm" not in guest_sheet


def test_plus_add_serves_other_laws_with_their_own_reading_name(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    bns = unescape(client.get(add_path("bns")).text)
    _assert_no_legacy(bns)
    _assert_act_page_underneath(bns, "bns")
    assert 'data-pg-kind="eligible_to_add"' in _panel_attrs(bns)
    _assert_subscriber_confirm(
        bns, law_id="bns", reading_name=BNS_READING_NAME, law_limit=10, remaining=9
    )
    assert NDPS_READING_NAME not in _sheet(bns)
    assert f'<h1 id="pg-add-scope-title" class="pg-add-title">Add {BNS_READING_NAME}</h1>' in bns
    assert f"Add BNS to {MONTH}?" not in bns
    assert "Add Bharatiya" not in bns


def test_plus_add_marker_uses_shared_predicate() -> None:
    add_src = ADD_TPL.read_text(encoding="utf-8")
    assert '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}' in add_src
    assert "{% block act_dialog %}" in add_src
    assert "data-pg-sheet-direct" in add_src
    assert 'data-pg-sheet-return="{{ cancel_href }}"' in add_src
    assert add_src.count('{% include "partials/playground_add_panel.html" %}') == 2
    panel_src = PANEL_TPL.read_text(encoding="utf-8")
    assert "data-pg-add-confirm" in panel_src
    assert ">Entire Act<" in panel_src
    assert ">Choose sections<" in panel_src
    assert "Pick sections — or open one and pick single clauses" in panel_src
    assert "provisions activate the first time you learn them." in panel_src
    assert "reading_name|default(short_title) }} joins this month's Playground" in panel_src
    assert "Unlock Playground" not in panel_src.split("{% else %}", 1)[-1]
    for src in (add_src, panel_src):
        _assert_no_legacy(src)
        assert "plus_add" not in src
        for phrase in ("Premium", "Unlimited", "renews"):
            assert phrase not in src
    select = SELECT_TPL.read_text(encoding="utf-8")
    assert "data-pg-picker" in select
    assert "Choose what to learn" in select
    assert "data-pg-add" not in select
    routes = ROUTES.read_text(encoding="utf-8")
    assert "playground_bare_act_spec(law_id)" in routes
    assert '"reading_name": reading_name' in routes
    assert "bare_act_page_context(request, bare)" in routes
    assert '== "pg-sheet"' in routes
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    css = PG_CSS.read_text(encoding="utf-8")
    assert "Add sheet (M2)" in css
    sheet_css = css.split("Add sheet (M2)", 1)[1].split("Guest desktop Playground intro", 1)[0]
    assert "min-height: 50px" in sheet_css.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert "padding: 26px 28px 26px" in sheet_css.split(".pg-sheet-panel[data-pg-add] {", 1)[1].split("}", 1)[0]
    assert "[data-plus-add-desktop]" not in css
    assert "plus-add-submit" not in css
    js = PG_JS.read_text(encoding="utf-8")
    assert "data-pg-sheet-direct" in js
    assert "data-pg-sheet-return" in js
    assert "pg-sheet" in js.split("X-Requested-With", 1)[1][:40]
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg52" in base
    assert "playground.css?v=pg49" not in base
    assert "playground.css?v=pg34" not in base
    bare = BARE.read_text(encoding="utf-8")
    assert "{% block act_dialog %}{% endblock %}" in bare
    assert "data-plus-add-desktop" not in bare
    assert "data-plus-bareact" in bare
    assert 'data-plus-bareact="desktop"' not in bare


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


def test_plus_add_1280_dialog_scope_and_select(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_add_screen5_1280.png"
    select_path = artifact_dir / "plus_add_screen5_select_1280.png"
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

        def open_dialog():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
            page.wait_for_selector("[data-pg-add]", timeout=8000)

        open_dialog()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              const submit = confirmStep.querySelector('.pg-add-primary');
              const cancel = confirmStep.querySelector('.pg-add-secondary[data-pg-sheet-close]');
              const closeBtn = panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const head = document.querySelector('.ActHead[data-plus-bareact]');
              const box = panel.getBoundingClientRect();
              const eyebrow = confirmStep.querySelector('.pg-eyebrow');
              const titleEl = confirmStep.querySelector('.pg-add-title');
              const ledeEl = confirmStep.querySelector('.pg-add-lede');
              const notes = [...confirmStep.querySelectorAll('.pg-add-note--left')];
              const closeStyle = closeBtn && getComputedStyle(closeBtn);
              const panelStyle = getComputedStyle(panel);
              const backdrop = getComputedStyle(dialog, '::backdrop');
              return {
                open: dialog && dialog.open,
                kind: panel.getAttribute('data-pg-kind'),
                panels: document.querySelectorAll('[data-pg-add]').length,
                twins: panel.querySelectorAll('[data-plus-add-desktop], [data-plus-add-phone]').length,
                eyebrow: eyebrow && eyebrow.textContent.trim(),
                eyebrowDisplay: eyebrow && getComputedStyle(eyebrow).display,
                title: titleEl.textContent.trim(),
                titleSize: getComputedStyle(titleEl).fontSize,
                titleWeight: getComputedStyle(titleEl).fontWeight,
                lede: ledeEl.textContent.trim(),
                notes: notes.map((el) => el.textContent.trim()),
                submitText: submit.textContent.trim(),
                submitH: submit.getBoundingClientRect().height,
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                cancelHref: cancel && cancel.getAttribute('href'),
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                closeTop: closeStyle && closeStyle.top,
                closeRight: closeStyle && closeStyle.right,
                panelW: box.width,
                panelPad: panelStyle.padding,
                scrim: backdrop.backgroundColor,
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                leaked: {
                  already: confirmStep.innerText.includes('Already in Playground'),
                  resume: confirmStep.innerText.includes('Resume Playground'),
                  full: confirmStep.innerText.includes('Playground full'),
                  pending: confirmStep.innerText.includes('temporarily unavailable'),
                  signin: confirmStep.innerText.includes('Create an account'),
                  unlock: confirmStep.innerText.includes('Unlock Playground'),
                  reopen: confirmStep.innerText.includes('reopening it never uses another space'),
                },
                background: Boolean(head),
                addCta: head && head.querySelector('[data-pg-sheet]') &&
                  head.querySelector('[data-pg-sheet]').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-pg-add] [data-add-step='confirm'] .pg-add-primary").click()
        scope_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              const entire = [...scopeStep.querySelectorAll('button')].find(
                (b) => (b.getAttribute('name') === 'scope' && b.getAttribute('value') === 'entire')
              );
              const sections = [...scopeStep.querySelectorAll('button')].find(
                (b) => (b.getAttribute('name') === 'scope' && b.getAttribute('value') === 'sections')
              );
              return {
                path: location.pathname,
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                title: scopeStep.querySelector('h1') && scopeStep.querySelector('h1').textContent.trim(),
                entire: entire && entire.innerText,
                sections: sections && sections.innerText,
                note: scopeStep.querySelector('.pg-add-note--left') &&
                  scopeStep.querySelector('.pg-add-note--left').textContent.trim(),
              };
            }"""
        )
        page.locator(".pg-sheet-close").click()

        open_dialog()
        page.locator(".pg-sheet-close").click()
        closed_x = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
                head: Boolean(document.querySelector('.ActHead[data-plus-bareact]')),
                focused: document.activeElement &&
                  document.activeElement.hasAttribute('data-pg-sheet'),
              };
            }"""
        )

        open_dialog()
        page.evaluate(
            """() => document.querySelector("[data-pg-add] [data-add-step='confirm'] .pg-add-secondary[data-pg-sheet-close]").click()"""
        )
        closed_cancel = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
              };
            }"""
        )

        open_dialog()
        page.keyboard.press("Escape")
        closed_esc = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return Boolean(dialog && dialog.open);
            }"""
        )

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").first.click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const title = confirmStep.querySelector('.pg-add-title');
              const cancel = confirmStep.querySelector('.pg-add-secondary[data-pg-sheet-close]');
              return {
                kind: panel.getAttribute('data-pg-kind'),
                panels: document.querySelectorAll('[data-pg-add]').length,
                twins: panel.querySelectorAll('[data-plus-add-desktop], [data-plus-add-phone]').length,
                panelDisplay: getComputedStyle(panel).display,
                title: title && title.textContent.trim(),
                lede: confirmStep.querySelector('.pg-add-lede')
                  && confirmStep.querySelector('.pg-add-lede').textContent.trim(),
                notes: [...confirmStep.querySelectorAll('.pg-add-note--left')].map(
                  (el) => el.textContent.trim()
                ),
                cancelHref: cancel && cancel.getAttribute('href'),
              };
            }"""
        )

        page.set_viewport_size({"width": 1280, "height": 800})
        open_dialog()
        page.locator("[data-pg-add] [data-add-step='confirm'] .pg-add-primary").click()
        page.locator('button[name="scope"][value="sections"]').click()
        page.wait_for_url("**/playground/laws/ndps/sections", timeout=8000)
        select_geo = page.evaluate(
            """() => {
              const picker = document.querySelector('[data-pg-picker]');
              const submit = document.querySelector('[data-pg-submit]');
              return {
                path: location.pathname,
                present: Boolean(picker),
                title: document.querySelector('h1') && document.querySelector('h1').textContent.trim(),
                submitDisabled: submit ? submit.disabled : null,
                submitText: submit && submit.textContent.trim(),
                addSheet: Boolean(document.querySelector('[data-pg-add]')),
              };
            }"""
        )
        page.screenshot(path=str(select_path), full_page=False)
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "eligible_to_add"
    assert geo["panels"] == 1
    assert geo["twins"] == 0
    assert geo["eyebrow"] == MONTH
    assert geo["eyebrowDisplay"] != "none"
    assert geo["title"] == TITLE
    assert geo["titleSize"] == "22px"
    assert geo["titleWeight"] in ("500", "bold")
    assert geo["lede"] == LEDE
    assert geo["notes"] == [SPACE, REMAIN]
    assert geo["submitText"] == TITLE
    assert geo["submitH"] == pytest.approx(50, abs=2)
    assert geo["cancelDisplay"] != "none"
    assert geo["cancelHref"] == "/laws/ndps"
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["closeTop"] == "14px"
    assert geo["closeRight"] == "14px"
    assert geo["panelW"] == pytest.approx(460, abs=8)
    assert "26px" in geo["panelPad"]
    assert "28px" in geo["panelPad"]
    assert "0.35" in (geo["scrim"] or "") or "rgba(20, 20, 20, 0.35)" in (geo["scrim"] or "")
    assert geo["confirmHidden"] is False
    assert geo["scopeHidden"] is True
    assert geo["leaked"]["already"] is False
    assert geo["leaked"]["resume"] is False
    assert geo["leaked"]["full"] is False
    assert geo["leaked"]["pending"] is False
    assert geo["leaked"]["signin"] is False
    assert geo["leaked"]["unlock"] is False
    assert geo["leaked"]["reopen"] is False
    assert geo["background"] is True
    assert geo["addCta"] == "+ Add to Playground"
    assert scope_geo["path"] == "/laws/ndps"
    assert scope_geo["confirmHidden"] is True
    assert scope_geo["scopeHidden"] is False
    assert scope_geo["title"] == f"Add {NDPS_READING_NAME}"
    assert scope_geo["entire"] and "Entire Act" in scope_geo["entire"]
    assert scope_geo["sections"] and "Choose sections" in scope_geo["sections"]
    assert "provisions activate the first time you learn them" in (scope_geo["note"] or "")
    assert select_geo["path"] == sections_path("ndps")
    assert select_geo["present"] is True
    assert select_geo["title"] == "Choose what to learn"
    assert select_geo["submitDisabled"] is True
    assert select_geo["submitText"] == "Select sections to add"
    assert select_geo["addSheet"] is False
    assert closed_x["open"] is False
    assert closed_x["path"] == "/laws/ndps"
    assert closed_x["head"] is True
    assert closed_x["focused"] is True
    assert closed_cancel["open"] is False
    assert closed_cancel["path"] == "/laws/ndps"
    assert closed_esc is False
    assert phone_geo["kind"] == "eligible_to_add"
    assert phone_geo["panels"] == 1
    assert phone_geo["twins"] == 0
    assert phone_geo["panelDisplay"] != "none"
    assert phone_geo["title"] == TITLE
    assert phone_geo["lede"] == LEDE
    assert phone_geo["notes"] == [SPACE, REMAIN]
    assert phone_geo["cancelHref"] == "/laws/ndps"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
    assert select_path.is_file()
    assert select_path.stat().st_size > 1000
