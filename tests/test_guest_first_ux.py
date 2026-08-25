"""Guest-first multi-user UX: browse/learn without account; gate personal writes."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.exceptions import InvalidCredentialsError
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.phone import normalize_e164, normalize_india_mobile
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"

from tests.quiz_helpers import complete_all_modes  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(**overrides) -> MultiUserSettings:
    base = {
        "APP_ENV": "test",
        "MULTIUSER_ENABLED": "true",
        "AUTH_GOOGLE_ENABLED": "true",
        "AUTH_PHONE_ENABLED": "true",
        "SESSION_SECRET": "test-secret",
        "SUPABASE_URL": "http://example.invalid",
        "SUPABASE_ANON_KEY": "anon",
        "DATABASE_URL": "",
        "COOKIE_SECURE": "false",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _client(
    tmp_path: Path,
    provider: FakeAuthProvider | None = None,
    *,
    pricing: bool = False,
) -> TestClient:
    provider = provider or FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name="User A",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(PRICING_ENABLED="true" if pricing else "false"),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    return TestClient(app)


def test_india_mobile_to_e164():
    assert normalize_india_mobile("9876543210") == "+919876543210"
    assert normalize_e164("9876543210") == "+919876543210"
    assert normalize_e164("+91 98765 43210") == "+919876543210"
    with pytest.raises(InvalidCredentialsError):
        normalize_india_mobile("5876543210")
    with pytest.raises(InvalidCredentialsError):
        normalize_e164("12345")


def test_guest_landing_and_browse_learn(tmp_path: Path):
    client = _client(tmp_path)
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    html = home.text
    assert "Recall the C" in html
    # Existing visual tagline stays; the product name is now the <h1>.
    assert "The whole document." in html
    assert "In your memory." in html
    assert "A memory system for the Bare Act" not in html
    assert "Start learning" in html  # header CTA still present
    assert "Start memorizing" in html  # final-CTA section (unchanged)
    assert 'href="/login"' in html
    assert 'href="/browse"' in html
    assert "Explore as guest" in html
    # §02 interactive cloze card ("From memory") + its heading
    assert "Recognition is not" in html
    assert "From memory" in html
    # Signature of the brain-canvas landing: the letter-field canvas + data file
    assert "data-brain" in html
    assert "brain-path.js" in html
    # §01 rebuilt to the 13 Part squares over a 600vh pin
    assert "Three Articles a day." in html
    assert "height:600vh" in html
    assert 'data-pin="1"' in html
    assert "Fundamental Rights" in html
    # Exactly the 13 Part squares render (not 12, not 14).
    assert html.count('data-pcard="1"') == 13
    # §03 "Learning modes" (six hover-fill circles)
    assert "Learning modes" in html
    assert "data-circles" in html
    # §05 relevant-laws section + "and many more"
    assert "does not act alone" in html
    assert "and many more" in html
    # Closing scrubbed block
    assert "Start with one Article." in html
    # Old §01 bits removed (ruler + day blocks); §04 schedule already gone
    assert "data-ruler" not in html
    assert "data-daycards" not in html
    assert 'id="revision"' not in html
    # Running-head marker removed; light-landing switch disabled (no toggle)
    assert "data-marker" not in html
    assert 'id="landing-theme-toggle"' not in html
    assert "landing.js" in html
    assert "family=Fraunces" in html
    assert "@keyframes hintDrift" in html
    # Scroll-snap corridor hooks: the JS toggles html.snap-active; the CSS snaps.
    assert "scroll-snap-align" in html
    # The motion script carries the corridor + reversible mobile mode-intro.
    landing_js = (
        Path(__file__).resolve().parents[1]
        / "src/constitution_memorizer/web/static/landing.js"
    ).read_text()
    assert "snap-active" in landing_js
    assert "setupModeIntro" in landing_js
    assert "data-cloze" in landing_js
    # Standalone page: no app chrome from base.html
    assert "Learning as guest" not in html
    assert 'class="nav-link">Home' not in html
    assert 'class="nav-link">Browse' not in html
    assert "{% extends" not in html

    browse = client.get("/browse")
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text
    assert "Learning as guest" in browse.text
    assert "guest-signin-modal" in browse.text
    assert 'href="/" class="nav-link">Home' in browse.text
    assert 'href="/browse" class="nav-link is-active">Browse' in browse.text

    learn = client.get("/learn/clause-1")
    assert learn.status_code == 200
    assert "learning as a guest" in learn.text.lower()
    assert "guest-signin-modal" in learn.text


def test_landing_product_name_and_purpose_are_crawlable(tmp_path: Path):
    """Google branding review needs the app name and purpose in the HTML."""
    client = _client(tmp_path)
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    html = home.text
    assert "<title>Recall the C — Learn the Constitution of India</title>" in html
    assert 'name="description" content="Recall the C is an educational platform for learning, recalling and revising the Constitution of India through structured learning methods, visual explanations, progress tracking and spaced repetition."' in html
    assert 'property="og:site_name" content="Recall the C"' in html
    assert html.count("<h1") == 1
    assert ">Recall the C</h1>" in html
    assert (
        "Recall the C is an educational platform for learning, recalling and revising the Constitution of India through structured learning methods, visual explanations, progress tracking and spaced repetition."
        in html
    )
    assert "Independent educational product · Study aid only — not legal advice." in html
    assert "Constitution of India" in html
    assert 'href="/privacy"' in html
    assert 'href="/terms"' in html
    assert 'href="/grievance"' in html
    assert 'data-reveal' not in html.split('id="top"', 1)[1].split('id="arithmetic"', 1)[0]


def test_light_theme_switch_disabled(tmp_path: Path):
    """The light landing is disabled: even a rtc_landing_theme=light cookie
    still serves the dark brain-canvas landing (no way to reach light)."""
    client = _client(tmp_path)
    client.cookies.set("rtc_landing_theme", "light")
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    html = home.text
    # Dark landing served regardless of the cookie.
    assert "data-brain" in html
    assert "brain-path.js" in html
    # Not the light split layout.
    assert "data-fig" not in html
    assert "landing-light.js" not in html
    assert "{% extends" not in html


def test_landing_pricing_nav_when_enabled(tmp_path: Path):
    """With pricing on, the landing links the Pricing nav to /pricing, no teaser."""
    client = _client(tmp_path, pricing=True)
    dark = client.get("/", follow_redirects=False).text
    assert 'href="/pricing"' in dark
    # The inline in-page pricing teaser was removed.
    assert 'id="pricing"' not in dark


def test_landing_only_when_multiuser_guest(tmp_path: Path):
    """Marketing landing is served at / only for unsigned multiuser visitors."""
    from constitution_memorizer.web.app import create_app

    local = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "local.db", multiuser=False)
    )
    local_home = local.get("/", follow_redirects=False)
    assert local_home.status_code == 200
    assert "Today" in local_home.text
    assert "A memory system for the Bare Act" not in local_home.text
    assert "data-modes" not in local_home.text

    guest = _client(tmp_path)
    guest_home = guest.get("/", follow_redirects=False)
    assert guest_home.status_code == 200
    assert "The whole document." in guest_home.text
    assert ">Today<" not in guest_home.text


def test_authed_logo_and_root_go_to_dashboard(tmp_path: Path):
    client = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert 'class="brand" href="/dashboard"' in dash.text
    assert "main_logo.png" in dash.text
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"] == "/dashboard"


def test_guest_post_done_redirects_to_login(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/login")
    assert "reason=mastered" in loc


def test_guest_dashboard_and_progress_gates(tmp_path: Path):
    client = _client(tmp_path)
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Sign in to save your learning" in dash.text
    assert "Create a personal learning record" in dash.text
    prog = client.get("/progress")
    assert prog.status_code == 200
    assert "Sign in to save your learning" in prog.text
    assert "Create a personal learning record" in prog.text
    assert "Progress and mastery are private" not in prog.text


def test_login_ui_india_phone_and_otp_states(tmp_path: Path):
    client = _client(tmp_path)
    html = client.get("/login").text
    assert "+91" in html
    assert 'name="national_number"' in html
    assert "Continue with Google" in html

    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    send = client.post(
        "/auth/phone/send",
        data={
            "national_number": "9876543210",
            "country_code": "+91",
            "csrf_token": csrf,
            "next": "/dashboard",
        },
        follow_redirects=False,
    )
    assert send.status_code == 303
    assert "otp=1" in send.headers["location"]
    assert "+919876543210" in send.headers["location"] or "%2B919876543210" in send.headers[
        "location"
    ]

    otp_page = client.get("/login?otp=1&phone=%2B919876543210")
    assert otp_page.status_code == 200
    assert 'name="otp0"' in otp_page.text
    assert "Enter the code" in otp_page.text

    bad_phone = client.post(
        "/auth/phone/send",
        data={
            "national_number": "1234567890",
            "country_code": "+91",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert "phone_format" in bad_phone.headers["location"]
    assert "invalid-phone" in bad_phone.headers["location"]


def test_phone_otp_welcome_then_dashboard(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _client(tmp_path, provider)
    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/auth/phone/send",
        data={
            "national_number": "9876543210",
            "country_code": "+91",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    verify = client.post(
        "/auth/phone/verify",
        data={
            "phone": "+919876543210",
            "otp": "123456",
            "csrf_token": csrf,
            "otp0": "1",
            "otp1": "2",
            "otp2": "3",
            "otp3": "4",
            "otp4": "5",
            "otp5": "6",
        },
        follow_redirects=False,
    )
    assert verify.status_code == 303
    assert verify.headers["location"] == "/welcome"
    assert SESSION_COOKIE_NAME in verify.cookies

    welcome = client.get("/welcome")
    assert welcome.status_code == 200
    assert "What should we call you" in welcome.text
    csrf2 = client.cookies.get(CSRF_COOKIE_NAME) or csrf
    saved = client.post(
        "/welcome",
        data={"display_name": "Priya", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert saved.headers["location"] == "/dashboard"
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Priya" in dash.text


def test_logout_signed_out_page(tmp_path: Path):
    client = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    out = client.post("/logout", follow_redirects=False)
    assert out.status_code == 303
    assert out.headers["location"] == "/signed-out"
    page = client.get("/signed-out")
    assert page.status_code == 200
    assert "signed out" in page.text.lower()
    gate = client.get("/dashboard")
    assert gate.status_code == 200
    assert "Sign in to save your learning" in gate.text


def test_auth_transition_and_profile_pages(tmp_path: Path):
    client = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    assert cb.headers["location"].startswith("/auth/transition")
    # Follow transition destination
    trans = client.get(cb.headers["location"])
    assert trans.status_code == 200
    assert "Opening your learning space" in trans.text
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Welcome, User." in dash.text or "Good morning, User." in dash.text
    profile = client.get("/profile")
    assert profile.status_code == 200
    assert "Profile" in profile.text
    assert "Learning preferences → Settings" in profile.text
    assert 'name="notification_frequency"' not in profile.text
    assert 'name="theme"' not in profile.text


def test_dashboard_has_no_recent_activity_or_explore_sections(tmp_path: Path):
    """Both secondary cards were removed from Today; the hero is the page."""
    client = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    complete_all_modes(client, MINI_UNITS, "clause-1")
    client.post(
        "/learn/clause-1/done",
        data={
            "claim_article": "1",
            "modes": "read,cloze,letters,type,recite,test",
        },
        follow_redirects=False,
    )
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Recent activity" not in dash.text
    assert "dash-activity-list" not in dash.text
    assert "Explore the Constitution" not in dash.text
    assert "dash-explore-list" not in dash.text
    # And the caught-up copy and quote that sat under the empty hero.
    assert "Browse when you're ready for something new." not in dash.text
    assert "caught-up-quote" not in dash.text


def test_dashboard_multiuser_layout(tmp_path: Path):
    client = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    html = dash.text
    assert 'class="eyebrow"' not in html
    assert "Welcome, User." in html or "Good morning, User." in html
    # Today's hero is mutually exclusive: a fresh account has nothing due, so
    # it gets the learning hero and the "Due today" revision card is absent.
    assert 'data-today-mode="learning"' in html
    assert "Due today" not in html
    assert "Articles started" in html
    assert "Units completed" in html
    assert "Units mastered" in html
    assert "Day streak" in html
    assert "Revisions done" in html
    # Explore the Constitution and Recent activity were removed from Today —
    # covered by test_dashboard_has_no_recent_activity_or_explore_sections.
    assert "→" in html
    assert "dash-progress-summary" not in html
    assert "Progress summary" in html  # aria-label on strip
    # Top-row Progress card (old 3-col) is gone — no started/review/mastered trio labels.
    assert ">Started<" not in html
    assert "dash-card-head" in html
    assert "dash-card-body" in html
    assert "Nothing is due today" in html
    # The learning hero is the only card in this state, so its CTA is primary
    # rather than the secondary outline button it used to be. A fresh account
    # has a first chain unit waiting, so the CTA is Continue, not Browse.
    assert "Continue learning →" in html
    assert "dash-btn-full" in html
    # Account dropdown identity header + menu order
    assert "account-menu-identity" in html
    assert "account-menu-name" in html
    assert "User A" in html
    assert "a@example.com" in html
    assert "account-provider-badge is-google" in html
    profile_i = html.index('href="/profile"')
    settings_i = html.index('href="/settings"')
    calendar_i = html.index('href="/calendar"')
    assert profile_i < settings_i < calendar_i
    # Memory log is feature-flagged off for V1 production.
    assert 'href="/memory"' not in html
    assert "Sign out" in html


def test_dashboard_data_error_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from constitution_memorizer.web import dashboard as dash_mod

    client = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )

    def boom(*args, **kwargs):
        raise RuntimeError("forced dashboard failure")

    monkeypatch.setattr(dash_mod, "build_dashboard_context", boom)
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "We couldn't load your dashboard" in dash.text
    assert "Try again" in dash.text
