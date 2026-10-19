"""Phone Shared section picker Screen 01 (CTA map shared/01-screen).

Authorized: ChatGPT. CSS-only restyle of the live R2 picker at ≤560px
for Plus / Pro / Max who can open Playground with the law on this
period's roster. Guest, Free, Expired, Halted, device-blocked, and
inactive-law stay gated. Selection and progress stay per-user.
Desktop R2 ≥900 is unchanged. No template, JS, route, or product
behavior changes.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
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
from constitution_memorizer.devices.token import mint_installation_token
from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_LIMIT,
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import playground_today
from constitution_memorizer.playground.urls import add_path, law_path, sections_path
from constitution_memorizer.web.app import create_app
from tests.test_playground_m8 import _seed_progress

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
SELECT = ROOT / "src/constitution_memorizer/web/templates/playground_select.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_SELECT_JS = ROOT / "src/constitution_memorizer/web/static/playground-select.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
ACCESS = ROOT / "src/constitution_memorizer/playground/access.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
USER_B = UUID("22222222-2222-4222-8222-222222222222")
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
INVENTED = (
    "Invite",
    "Share this",
    "sharing link",
    "Premium",
    "Unlimited",
    "Unlock Playground",
    "Create an account",
    "Resume Playground",
    "View Playground plans",
)
COHORT_MARKERS = (
    "data-plus-add-desktop",
    "data-plus-add-phone",
    "data-plus-playground-phone",
    "data-expired-playground",
    "data-expired-pg-phone",
    "data-halted-playground",
    "data-guest-add-phone",
    "data-signed-in-pg-gate",
    "data-plus-picker",
    "data-shared-picker-phone",
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
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    return app, provider


def _sign_in(
    client: TestClient,
    provider: FakeAuthProvider,
    user_id: UUID = USER,
    email: str = "a@example.com",
    *,
    display_name: str = "Sanjay",
) -> None:
    provider.seed_google_user(
        user_id=user_id,
        email=email,
        display_name=display_name,
        avatar_url=None,
    )
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
    user_id: UUID = USER,
    *,
    tier: str = "plus",
    status: str = "active",
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        user_id,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _plus_client(
    tmp_path: Path, *, tier: str = "plus", email: str = "a@example.com"
) -> TestClient:
    app, provider = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client, provider, USER, email)
    _subscribe(client, USER, tier=tier)
    return client


def _confirm_add_sections(client: TestClient, law_id: str = "ndps"):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "sections"
    return client.post(add_path(law_id), data=payload, follow_redirects=False)


def _open_empty_picker(client: TestClient, law_id: str = "ndps") -> None:
    added = _confirm_add_sections(client, law_id)
    assert added.status_code == 303
    assert added.headers.get("location") == sections_path(law_id)
    assert client.app.state.roster.is_law_active_this_period(USER, law_id) is True
    assert client.app.state.playground.list_selection(USER, law_id) == []


def _seed_picker_progress(client: TestClient, user_id: UUID = USER) -> None:
    repo = client.app.state.playground
    as_of = playground_today()
    _seed_progress(
        repo,
        user_id,
        "ndps",
        "ndps:section:1",
        status="mastered",
        interval_days=60,
        next_revision=None,
        times_completed=6,
        learned_at="2026-01-01",
        last_completed="2026-09-01",
    )
    _seed_progress(
        repo,
        user_id,
        "ndps",
        "ndps:section:2",
        status="review",
        interval_days=3,
        next_revision=(as_of - timedelta(days=1)).isoformat(),
        times_completed=1,
        learned_at="2026-09-01",
        last_completed="2026-09-17",
    )
    _seed_progress(
        repo,
        user_id,
        "ndps",
        "ndps:section:4",
        status="learned",
        interval_days=1,
        next_revision=(as_of + timedelta(days=1)).isoformat(),
        learned_at=as_of.isoformat(),
    )


def _tabs(html: str) -> str:
    start = html.find('class="mobile-tabbar')
    assert start != -1
    return html[start:].split("</nav>", 1)[0]


def _locators(client: TestClient, user_id: UUID, law_id: str = "ndps") -> tuple[str, ...]:
    return tuple(
        row.source_locator
        for row in client.app.state.playground.list_selection(user_id, law_id)
    )


def _progress_fingerprint(
    client: TestClient, user_id: UUID, law_id: str = "ndps"
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (row.source_locator, str(row.status))
            for row in client.app.state.playground.list_progress(user_id, law_id)
        )
    )


def _device_ids(client: TestClient, user_id: UUID) -> tuple[str, ...]:
    svc = getattr(client.app.state, "device_service", None)
    if svc is None:
        return ()
    inner = getattr(svc, "inner", svc)
    rows = inner.list_devices(user_id)
    return tuple(sorted(str(getattr(row, "id", row)) for row in rows))


def test_phone_shared_picker_live_html_empty_first_add(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _open_empty_picker(client)
    before_sel = _locators(client, USER)
    before_progress = _progress_fingerprint(client, USER)
    before_active = client.app.state.roster.is_law_active_this_period(USER, "ndps")
    page = client.get(sections_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-pg-picker' in html
    assert 'data-mscreen="playground"' in html
    for marker in COHORT_MARKERS:
        assert marker not in html, marker
    assert 'data-playground-gate="' not in html
    assert 'data-hard-gate="true"' not in html
    assert 'href="/playground/laws/ndps"' in html
    assert ">← The NDPS Act, 1985<" in html
    assert ">Choose what to learn<" in html
    assert "Whole sections, or open one and pick clauses." in html
    assert 'name="csrf_token"' in html
    assert 'name="section"' in html
    assert 'name="unit"' in html
    assert "Show clauses" in html
    assert "pg-sticky-cta" in html
    assert "pg-pick-footer" in html
    assert "data-pg-submit" in html
    assert "pg-pick-aside" in html
    assert "data-pg-aside-submit" in html
    assert "Select sections to add" in html
    assert "Add 1 section" not in html
    assert 'aria-checked="true"' not in html
    assert 'aria-checked="mixed"' not in html
    submit = html.split("data-pg-submit", 1)[1].split(">", 1)[0]
    assert "disabled" not in submit
    tabs = _tabs(html)
    assert html.count('class="mobile-tabbar') == 1
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label in tabs
    playground = tabs.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in playground
    assert 'aria-current="page"' in playground
    assert tabs.count("is-active") == 1
    browse = tabs.split('href="/browse"', 1)[1].split("</a>", 1)[0]
    assert "is-active" not in browse
    for phrase in INVENTED:
        assert phrase not in html, phrase
    assert _locators(client, USER) == before_sel == ()
    assert _progress_fingerprint(client, USER) == before_progress
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is before_active
    devices_after_get = _device_ids(client, USER)
    again = client.get(sections_path("ndps"))
    assert again.status_code == 200
    assert 'data-pg-picker' in again.text
    assert _locators(client, USER) == ()
    assert _progress_fingerprint(client, USER) == before_progress
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    assert _device_ids(client, USER) == devices_after_get

    missing = client.post(sections_path("ndps"), data={"section": "1"}, follow_redirects=False)
    assert missing.status_code == 403
    assert _locators(client, USER) == ()

    empty = client.post(
        sections_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert empty.status_code in {303, 400}
    if empty.status_code == 400:
        assert empty.json().get("detail") == "invalid_selection"
        assert _locators(client, USER) == ()
    else:
        assert empty.headers.get("location") == law_path("ndps")

    invalid = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "not-a-section"},
        follow_redirects=False,
    )
    assert invalid.status_code == 400
    assert invalid.json().get("detail") == "invalid_selection"
    assert _locators(client, USER) == ()

    saved = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers.get("location") == law_path("ndps")
    assert _locators(client, USER) == ("ndps:section:1",)
    assert _progress_fingerprint(client, USER) == before_progress


def test_phone_shared_picker_seeded_progress_leaves_boxes_unchecked(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    _open_empty_picker(client)
    _seed_picker_progress(client)
    assert _locators(client, USER) == ()
    html = unescape(client.get(sections_path("ndps")).text)
    assert 'data-pg-picker' in html
    assert "Mastered" in html
    assert "Due · Day 3" in html
    assert "Learned · first revision tomorrow" in html
    assert "Not started" in html
    assert "Select sections to add" in html
    assert 'aria-checked="true"' not in html
    assert 'aria-checked="mixed"' not in html
    assert _locators(client, USER) == ()
    one = html.split('data-section="1"', 1)[1].split("</li>", 1)[0]
    two = html.split('data-section="2"', 1)[1].split("</li>", 1)[0]
    four = html.split('data-section="4"', 1)[1].split("</li>", 1)[0]
    assert 'data-check-state="none"' in html.split('data-section="1"', 1)[1].split(">", 1)[0]
    assert 'data-check-state="none"' in html.split('data-section="2"', 1)[1].split(">", 1)[0]
    assert 'data-check-state="none"' in html.split('data-section="4"', 1)[1].split(">", 1)[0]
    assert "Mastered" in one
    assert "Due · Day 3" in two
    assert "Learned · first revision tomorrow" in four


def test_phone_shared_picker_pro_and_max_share_markup(tmp_path: Path) -> None:
    for tier in ("pro", "max"):
        client = _plus_client(tmp_path / tier, tier=tier)
        _open_empty_picker(client)
        html = unescape(client.get(sections_path("ndps")).text)
        assert 'data-pg-picker' in html
        assert ">Choose what to learn<" in html
        for marker in COHORT_MARKERS:
            assert marker not in html, (tier, marker)
        assert "Select sections to add" in html


def test_phone_shared_picker_gated_cohorts_never_receive_picker(tmp_path: Path) -> None:
    guest_app, _provider = _mu_app(tmp_path / "guest")
    guest = TestClient(guest_app).get(sections_path("ndps"))
    assert guest.status_code == 200
    assert 'data-pg-picker' not in guest.text
    assert f'data-playground-gate="{BLOCK_SIGN_IN_REQUIRED}"' in guest.text

    free_app, free_provider = _mu_app(tmp_path / "free")
    free_client = TestClient(free_app)
    _sign_in(free_client, free_provider, USER, "free@example.com")
    free_html = free_client.get(sections_path("ndps"))
    assert free_html.status_code == 200
    assert 'data-pg-picker' not in free_html.text
    assert f'data-playground-gate="{BLOCK_NOT_SUBSCRIBED}"' in free_html.text
    free_post = free_client.post(
        sections_path("ndps"),
        data={**_csrf(free_client), "section": "1"},
        follow_redirects=False,
    )
    assert "data-pg-picker" not in free_post.text
    assert _locators(free_client, USER) == ()

    expired_app, expired_provider = _mu_app(tmp_path / "expired")
    expired = TestClient(expired_app)
    _sign_in(expired, expired_provider)
    _subscribe(expired)
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=datetime(2026, 8, 16, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    expired_page = expired.get(sections_path("ndps"))
    assert expired_page.status_code == 200
    assert 'data-pg-picker' not in expired_page.text
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in expired_page.text
    expired_post = expired.post(
        sections_path("ndps"),
        data={**_csrf(expired), "section": "1"},
        follow_redirects=False,
    )
    assert "data-pg-picker" not in expired_post.text
    assert _locators(expired, USER) == ()

    halted_app, halted_provider = _mu_app(tmp_path / "halted")
    halted = TestClient(halted_app)
    _sign_in(halted, halted_provider)
    _subscribe(halted, status="halted")
    halted_page = halted.get(sections_path("ndps"))
    assert halted_page.status_code == 200
    assert 'data-pg-picker' not in halted_page.text
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in halted_page.text
    halted_post = halted.post(
        sections_path("ndps"),
        data={**_csrf(halted), "section": "1"},
        follow_redirects=False,
    )
    assert "data-pg-picker" not in halted_post.text
    assert _locators(halted, USER) == ()

    limited_app, limited_provider = _mu_app(tmp_path / "device")
    limited = TestClient(limited_app)
    _sign_in(limited, limited_provider)
    _subscribe(limited)
    inner = getattr(limited.app.state.device_service, "inner", limited.app.state.device_service)
    for index in range(2):
        access = inner.ensure_current_device(
            USER,
            mint_installation_token(),
            auth_session_id=f"seed-sess-{index}",
            commercially_eligible=True,
        )
        assert access.current_device_registered is True
    limited_html = limited.get(sections_path("ndps")).text
    assert 'data-pg-picker' not in limited_html
    assert f'data-playground-gate="{BLOCK_DEVICE_LIMIT}"' in limited_html
    assert 'data-hard-gate="true"' in limited_html

    inactive = _plus_client(tmp_path / "inactive")
    missing = inactive.get(sections_path("ndps"), follow_redirects=False)
    assert missing.status_code == 303
    assert missing.headers.get("location") == "/laws/ndps"
    assert "data-pg-picker" not in missing.text
    inactive_post = inactive.post(
        sections_path("ndps"),
        data={**_csrf(inactive), "section": "1"},
        follow_redirects=False,
    )
    assert inactive_post.status_code == 303
    assert inactive_post.headers.get("location") == "/laws/ndps"
    assert _locators(inactive, USER) == ()
    assert inactive.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_shared_picker_cross_user_selection_isolation(tmp_path: Path) -> None:
    app, provider = _mu_app(tmp_path)
    client_a = TestClient(app)
    client_b = TestClient(app)
    _sign_in(client_a, provider, USER, "a@example.com")
    _subscribe(client_a, USER)
    _open_empty_picker(client_a)
    _seed_picker_progress(client_a, USER)
    saved = client_a.post(
        sections_path("ndps"),
        data={**_csrf(client_a), "section": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert _locators(client_a, USER) == ("ndps:section:1",)
    a_progress = _progress_fingerprint(client_a, USER)
    a_html = unescape(client_a.get(sections_path("ndps")).text)
    assert 'data-section="1"' in a_html
    assert 'data-check-state="all"' in a_html.split('data-section="1"', 1)[1].split(">", 1)[0]
    assert "Mastered" in a_html

    provider.google_users.clear()
    _sign_in(client_b, provider, USER_B, "b@example.com", display_name="B")
    _subscribe(client_b, USER_B)
    other = client_b.get(sections_path("ndps"), follow_redirects=False)
    assert other.status_code == 303
    assert other.headers.get("location") == "/laws/ndps"
    added_b = client_b.post(
        add_path("ndps"),
        data={**_csrf(client_b), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert added_b.status_code == 303
    b_html = unescape(client_b.get(sections_path("ndps")).text)
    assert 'data-pg-picker' in b_html
    assert "Select sections to add" in b_html
    assert 'aria-checked="true"' not in b_html
    b_one = b_html.split('data-section="1"', 1)[1].split("</li>", 1)[0]
    assert 'data-check-state="none"' in b_html.split('data-section="1"', 1)[1].split(">", 1)[0]
    assert "Mastered" not in b_one
    assert "Not started" in b_one
    assert _locators(client_b, USER_B) == ()
    mutate = client_b.post(
        sections_path("ndps"),
        data={**_csrf(client_b), "section": "8"},
        follow_redirects=False,
    )
    assert mutate.status_code == 303
    assert _locators(client_a, USER) == ("ndps:section:1",)
    assert _locators(client_b, USER_B) == ("ndps:section:8",)
    assert _progress_fingerprint(client_a, USER) == a_progress
    assert _progress_fingerprint(client_b, USER_B) == ()
    assert _locators(client_b, USER) == ("ndps:section:1",)


def test_phone_shared_picker_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "/* R2 section/clause picker */" in css
    assert "is shared/01-screen:" in css
    r2 = css.split("/* R2 section/clause picker */", 1)[1]
    assert r2.find("is shared/01-screen:") > r2.find("@media (min-width: 900px)")
    assert r2.find("is shared/01-screen:") < r2.find("/* R3 — Act-head, Add, home, gates */")
    shared = r2.split("is shared/01-screen:", 1)[1].split(
        "/* R3 — Act-head, Add, home, gates */", 1
    )[0]
    assert "@media (max-width: 560px)" in shared
    assert "[data-pg-picker]" in shared
    assert "var(--m-tabbar, 60px)" in shared
    assert "safe-area-inset-bottom" in shared
    assert "overflow-x: hidden" in shared
    assert "grid-template-columns: repeat(5, 1fr)" in shared
    assert ".mobile-tabbar" in shared
    assert "scroll-margin-bottom" in shared
    assert "data-plus-playground-phone" not in shared
    assert "data-expired-playground" not in shared
    assert "[data-expired-pg-phone]" not in shared
    assert "data-phone-pg-gate" not in shared
    assert "data-guest-add" not in shared
    assert "data-halted" not in shared
    assert "data-plus-picker" not in shared
    assert "#0e7569" not in shared
    assert "#3a3a38" not in shared
    assert "display: contents" not in shared
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", shared) is None
    assert ".mobile-tabbar" in shared
    tabbar_rules = [
        chunk
        for chunk in shared.split("}")
        if ".mobile-tabbar" in chunk and "display:" in chunk
    ]
    for rule in tabbar_rules:
        assert "display: none" not in rule
    first_560 = css.split("@media (max-width: 560px)", 1)[1].split(
        "/* R2 section/clause picker */", 1
    )[0]
    assert "width: calc(100% - (2 * var(--pg-shell-pad)))" in first_560
    assert "is shared/01-screen:" not in first_560
    plus_home = css.split("is plus/03-screen:", 1)[1].split(
        "is expired/03-screen:", 1
    )[0]
    assert "[data-plus-playground-phone]" in plus_home
    assert "[data-pg-picker]" not in plus_home
    expired_home = css.split("is expired/03-screen:", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "[data-expired-pg-phone]" in expired_home
    assert "[data-pg-picker]" not in expired_home
    aside = r2.split("@media (min-width: 900px)", 1)[1].split(
        "is shared/01-screen:", 1
    )[0]
    assert ".pg-pick-aside" in aside
    assert ".pg-pick-footer" in aside
    assert "display: none" in aside
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg49" in base
    assert "playground.css?v=pg47" not in base
    assert "styles.css?v=main87" in base
    assert "mobile.css?v=mob106" in base
    assert "playground-select.js?v=pg1" in base
    select = SELECT.read_text(encoding="utf-8")
    assert "data-pg-picker" in select
    assert "data-plus-picker" not in select
    assert "data-shared-picker-phone" not in select
    submit = select.split("data-pg-submit", 1)[1].split(">", 1)[0]
    assert "disabled" not in submit
    js = PG_SELECT_JS.read_text(encoding="utf-8")
    assert "submit.disabled = sectionCount === 0" in js
    assert "data-pg-picker" not in STYLES.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "is shared/01-screen:" not in mobile
    routes = ROUTES.read_text(encoding="utf-8")
    get_fn = routes.split("async def playground_select_page", 1)[1].split(
        "async def playground_select_save", 1
    )[0]
    post_fn = routes.split("async def playground_select_save", 1)[1].split(
        "def _open_source_review", 1
    )[0]
    assert "require_law_active_this_period" in get_fn
    assert "require_law_active_this_period" in post_fn
    access = ACCESS.read_text(encoding="utf-8")
    law_fn = access.split("def require_law_active_this_period", 1)[1].split("\ndef ", 1)[0]
    assert "require_playground_open" in law_fn


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


def test_phone_shared_section_picker_screen01_captures(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app, provider = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client, provider)
    _subscribe(client)
    _open_empty_picker(client)
    _seed_picker_progress(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    phone_path = artifact_dir / "phone_shared_section_picker_screen01_390x844.png"
    desk_path = artifact_dir / "phone_shared_section_picker_screen01_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
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

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )

        def open_picker():
            page.goto(f"{origin}{sections_path('ndps')}", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.wait_for_selector("[data-pg-picker]", timeout=8000)
            page.wait_for_timeout(250)

        open_picker()
        phone_geo = page.evaluate(
            """() => {
              const picker = document.querySelector('[data-pg-picker]');
              const header = document.querySelector('.site-header');
              const back = document.querySelector('.pg-back');
              const title = document.querySelector('[data-pg-picker] h1');
              const lede = document.querySelector('[data-pg-picker] .pg-lede');
              const checks = [...document.querySelectorAll('.pg-pick-check')];
              const wrap = document.querySelector('.pg-pick-check-wrap');
              const caret = document.querySelector('.pg-pick-caret');
              const footer = document.querySelector('.pg-sticky-cta.pg-pick-footer');
              const submit = document.querySelector('[data-pg-submit]');
              const aside = document.querySelector('.pg-pick-aside');
              const tabs = [...document.querySelectorAll('.mobile-tabbar .mobile-tab')];
              const tabsEl = document.querySelector('.mobile-tabbar');
              const active = document.querySelector('.mobile-tabbar .mobile-tab.is-active');
              const wrapBox = wrap && wrap.getBoundingClientRect();
              const caretBox = caret && caret.getBoundingClientRect();
              const csHeader = header && getComputedStyle(header);
              return {
                present: Boolean(picker),
                headerDisplay: csHeader ? csHeader.display : 'missing',
                back: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                title: title && title.textContent.trim(),
                titleSize: title && getComputedStyle(title).fontSize,
                lede: lede && lede.textContent.trim(),
                checkCount: checks.length,
                anyChecked: checks.some((el) => el.checked),
                wrapH: wrapBox && wrapBox.height,
                caretH: caretBox && caretBox.height,
                footerDisplay: footer ? getComputedStyle(footer).display : 'missing',
                asideDisplay: aside ? getComputedStyle(aside).display : 'missing',
                submitDisabled: submit ? submit.disabled : null,
                submitText: submit && submit.textContent.trim(),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabLabels: tabs.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabs.map((el) => el.getAttribute('href')),
                activeTab: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                tabDisplay: tabsEl ? getComputedStyle(tabsEl).display : 'missing',
                plusDialog: Boolean(document.querySelector('[data-plus-add-desktop]')),
                mastered: Boolean([...document.querySelectorAll('.pg-pick-status')].some(
                  (el) => el.textContent.includes('Mastered')
                )),
                due: Boolean([...document.querySelectorAll('.pg-pick-status')].some(
                  (el) => el.textContent.includes('Due · Day 3')
                )),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, phone_path)

        page.locator(".pg-sticky-cta.pg-pick-footer").scroll_into_view_if_needed()
        cta_geo = page.evaluate(
            """() => {
              const footer = document.querySelector('.pg-sticky-cta.pg-pick-footer');
              const submit = document.querySelector('[data-pg-submit]');
              const tabsEl = document.querySelector('.mobile-tabbar');
              const cs = getComputedStyle(footer);
              const se = document.scrollingElement || document.documentElement;
              footer.scrollIntoView({ block: 'end', inline: 'nearest' });
              window.scrollTo(0, se.scrollHeight);
              se.scrollTop = se.scrollHeight;
              document.documentElement.scrollTop = se.scrollHeight;
              document.body.scrollTop = se.scrollHeight;
              const submitBox = submit.getBoundingClientRect();
              const tabBox = tabsEl.getBoundingClientRect();
              return {
                display: cs.display,
                position: cs.position,
                paddingBottom: cs.paddingBottom,
                bottom: cs.bottom,
                disabled: submit.disabled,
                text: submit.textContent.trim(),
                submitTop: submitBox.top,
                submitBottom: submitBox.bottom,
                submitH: submitBox.height,
                tabTop: tabBox.top,
                tabH: tabBox.height,
                tabDisplay: getComputedStyle(tabsEl).display,
                aboveTabbar: submitBox.bottom <= tabBox.top + 2,
                inView: submitBox.top >= 0 && submitBox.bottom <= window.innerHeight + 1,
                innerHeight: window.innerHeight,
                scrollTop: se.scrollTop,
                scrollHeight: se.scrollHeight,
              };
            }"""
        )

        page.locator(".pg-pick-check").first.check()
        page.wait_for_timeout(150)
        checked_geo = page.evaluate(
            """() => {
              const submit = document.querySelector('[data-pg-submit]');
              return {
                disabled: submit.disabled,
                text: submit.textContent.trim(),
              };
            }"""
        )
        page.locator(".pg-pick-check").first.uncheck()
        page.wait_for_timeout(150)
        page.locator(".pg-pick-caret").first.click()
        page.wait_for_selector(".pg-pick-expand[open] .pg-pick-clauses", timeout=4000)
        expanded = page.evaluate(
            """() => {
              const details = document.querySelector('.pg-pick-expand');
              const clauses = document.querySelector('.pg-pick-expand[open] .pg-pick-clauses');
              return {
                open: Boolean(details && details.open),
                clauses: Boolean(clauses),
                path: location.pathname,
              };
            }"""
        )

        page.set_viewport_size({"width": 390, "height": 700})
        open_picker()
        page.locator(".pg-sticky-cta.pg-pick-footer").scroll_into_view_if_needed()
        short = page.evaluate(
            """() => {
              const last = [...document.querySelectorAll('.pg-pick-section')].at(-1);
              const submit = document.querySelector('[data-pg-submit]');
              const footer = document.querySelector('.pg-sticky-cta.pg-pick-footer');
              const tabsEl = document.querySelector('.mobile-tabbar');
              const se = document.scrollingElement || document.documentElement;
              last.scrollIntoView({ block: 'end', inline: 'nearest' });
              window.scrollTo(0, se.scrollHeight);
              se.scrollTop = se.scrollHeight;
              document.documentElement.scrollTop = se.scrollHeight;
              document.body.scrollTop = se.scrollHeight;
              let box = last.getBoundingClientRect();
              const submitBox = submit.getBoundingClientRect();
              const tabTop = tabsEl.getBoundingClientRect().top;
              if (box.bottom > submitBox.top) {
                se.scrollTop = se.scrollHeight;
                box = last.getBoundingClientRect();
              }
              const submitAfter = submit.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                lastTop: box.top,
                lastBottom: box.bottom,
                submitTop: submitAfter.top,
                submitBottom: submitAfter.bottom,
                submitH: submitAfter.height,
                tabTop,
                tabH: tabsEl.getBoundingClientRect().height,
                tabDisplay: getComputedStyle(tabsEl).display,
                footerDisplay: getComputedStyle(footer).display,
                footerBottom: getComputedStyle(footer).bottom,
                disabled: submit.disabled,
                aboveTabbar: submitAfter.bottom <= tabTop + 2,
                lastAboveCta: box.bottom <= submitAfter.top + 4 || box.top < submitAfter.top,
                lastReachable: box.top >= 0 && box.top < window.innerHeight,
                innerHeight: window.innerHeight,
                scrollTop: se.scrollTop,
                scrollHeight: se.scrollHeight,
              };
            }"""
        )

        page.set_viewport_size({"width": 1280, "height": 800})
        open_picker()
        desk_geo = page.evaluate(
            """() => {
              const picker = document.querySelector('[data-pg-picker]');
              const layout = document.querySelector('.pg-select-layout');
              const aside = document.querySelector('.pg-pick-aside');
              const footer = document.querySelector('.pg-sticky-cta.pg-pick-footer');
              const submit = document.querySelector('[data-pg-aside-submit]');
              const phoneSubmit = document.querySelector('[data-pg-submit]');
              const csLayout = layout && getComputedStyle(layout);
              return {
                present: Boolean(picker),
                columns: csLayout && csLayout.gridTemplateColumns,
                asideDisplay: aside ? getComputedStyle(aside).display : 'missing',
                footerDisplay: footer ? getComputedStyle(footer).display : 'missing',
                submitDisabled: submit ? submit.disabled : null,
                submitText: submit && submit.textContent.trim(),
                phoneSubmitDisabled: phoneSubmit ? phoneSubmit.disabled : null,
                plusDialog: Boolean(document.querySelector('[data-plus-add-desktop]')),
                title: document.querySelector('h1') && document.querySelector('h1').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, desk_path)
        browser.close()

    assert phone_geo["present"] is True
    assert phone_geo["headerDisplay"] == "none"
    assert phone_geo["back"] == "← The NDPS Act, 1985"
    assert phone_geo["backHref"] == law_path("ndps")
    assert phone_geo["title"] == "Choose what to learn"
    assert phone_geo["titleSize"] == "26px"
    assert phone_geo["lede"] == "Whole sections, or open one and pick clauses."
    assert phone_geo["checkCount"] > 0
    assert phone_geo["anyChecked"] is False
    assert phone_geo["wrapH"] >= 44
    assert phone_geo["caretH"] >= 44
    assert phone_geo["footerDisplay"] != "none"
    assert phone_geo["asideDisplay"] == "none"
    assert phone_geo["submitDisabled"] is True
    assert phone_geo["submitText"] == "Select sections to add"
    assert phone_geo["overflow"] is False
    assert phone_geo["tabLabels"] == [label for label, _href in TAB_HREFS]
    assert phone_geo["tabHrefs"] == [href for _label, href in TAB_HREFS]
    assert phone_geo["activeTab"] == "Playground"
    assert phone_geo["tabDisplay"] != "none"
    assert phone_geo["plusDialog"] is False
    assert phone_geo["mastered"] is True
    assert phone_geo["due"] is True

    assert cta_geo["display"] != "none"
    assert cta_geo["disabled"] is True
    assert cta_geo["text"] == "Select sections to add"
    assert cta_geo["submitH"] >= 44
    assert cta_geo["aboveTabbar"] is True
    assert cta_geo["tabDisplay"] != "none"
    assert cta_geo["inView"] is True

    assert checked_geo["disabled"] is False
    assert checked_geo["text"] == "Add 1 section →"
    assert expanded["open"] is True
    assert expanded["clauses"] is True
    assert expanded["path"] == sections_path("ndps")

    assert short["overflow"] is False
    assert short["tabDisplay"] != "none"
    assert short["footerDisplay"] != "none"
    assert short["disabled"] is True
    assert short["submitH"] >= 44
    assert short["aboveTabbar"] is True, short
    assert short["lastReachable"] is True
    assert short["lastAboveCta"] is True

    assert desk_geo["present"] is True
    assert desk_geo["asideDisplay"] != "none"
    assert desk_geo["footerDisplay"] == "none"
    assert desk_geo["submitDisabled"] is True
    assert desk_geo["submitText"] == "Select sections to add"
    assert desk_geo["plusDialog"] is False
    assert desk_geo["title"] == "Choose what to learn"
    assert desk_geo["columns"] is not None
    assert "280px" in desk_geo["columns"]
    assert phone_path.is_file() and phone_path.stat().st_size > 1000
    assert desk_path.is_file() and desk_path.stat().st_size > 1000
