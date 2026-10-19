"""M1 — Guest shell parity (docs/design/milestones/M1.md).

Guests get the same navigation shell as signed-in users: the five-tab phone
bar and the five-link top nav with a Sign in button. Signed-in pages are
regression checks here, plus the two owner-added shell items:
DV-20 (account slot subtitle on every shared-shell page) and
DV-21 (full top nav on the signed-in gate, plans and Add routes).
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
STATIC = ROOT / "src" / "constitution_memorizer" / "web" / "static"

TAB_ORDER = ["/dashboard", "/browse", "/playground", "/calendar", "/profile"]
TAB_LABELS = ["Today", "Browse", "Playground", "Calendar", "Profile"]

# route -> expected active tab href (None = no tab is current)
GUEST_ROUTES = {
    "/browse": "/browse",
    "/laws": "/browse",
    "/laws/ndps": "/browse",
    "/laws/uapa": "/browse",
    "/laws/bns": "/browse",
    "/tables": "/browse",
    "/search": "/browse",
    "/playground": "/playground",
    "/dashboard": "/dashboard",
    "/settings": "/profile",
    "/profile": "/profile",
    "/terms": None,
    "/privacy": None,
    "/grievance": None,
}


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(**overrides) -> MultiUserSettings:
    base = dict(
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
    base.update(overrides)
    return MultiUserSettings(_env_file=None, **base)


def _app(tmp_path: Path, provider: FakeAuthProvider | None = None, **overrides):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(**overrides),
        auth_provider=provider or FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )


def _guest(tmp_path: Path, **overrides) -> TestClient:
    return TestClient(_app(tmp_path, **overrides))


def _signed_in(tmp_path: Path, **overrides) -> TestClient:
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name="User A",
    )
    client = TestClient(_app(tmp_path, provider, **overrides))
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    authed = client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert authed.status_code == 303
    return client


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _top_nav(html: str) -> str:
    return html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]


def _phone_bars(html: str) -> list[str]:
    return re.findall(r'<nav class="mobile-tabbar[^"]*"[^>]*>.*?</nav>', html, flags=re.S)


def _links(fragment: str) -> list[tuple[str, str, bool, bool]]:
    """(href, label, is_active, aria_current) for every <a> in a fragment."""
    out = []
    for m in re.finditer(r'<a\s+([^>]*)>(.*?)</a>', fragment, flags=re.S):
        attrs, inner = m.group(1), m.group(2)
        href = re.search(r'href="([^"]*)"', attrs)
        label = re.sub(r"<[^>]+>", "", inner).strip()
        label = re.sub(r"\s+", " ", label)
        out.append((href.group(1) if href else "", label, "is-active" in attrs, 'aria-current="page"' in attrs))
    return out


# ───────────────────────── phone bar: five tabs on every guest page ─────────────────────────


@pytest.mark.parametrize("route,active", sorted(GUEST_ROUTES.items()))
def test_guest_phone_bar_has_five_tabs_with_one_current(tmp_path: Path, route: str, active: str | None) -> None:
    html = _guest(tmp_path).get(route).text
    assert 'class="mobile-tabbar is-guest"' not in html
    bars = _phone_bars(html)
    assert len(bars) == 1, f"{route}: expected exactly one phone bar, found {len(bars)}"
    bar = bars[0]
    assert 'PrimaryTabs--bottom' in bar and 'aria-label="Mobile"' in bar and 'data-guest-phone-tabs' in bar
    links = _links(bar)
    assert [l[0] for l in links] == TAB_ORDER, route
    assert [l[1] for l in links] == TAB_LABELS, route
    current = [l[0] for l in links if l[3]]
    actives = [l[0] for l in links if l[2]]
    if active is None:
        assert current == [] and actives == [], f"{route}: no tab should be current"
    else:
        assert current == [active] and actives == [active], f"{route}: current={current} active={actives}"
    for href in TAB_ORDER:
        assert f'href="{href}"' in bar


def test_guest_phone_bar_omits_playground_when_feature_off(tmp_path: Path) -> None:
    html = _guest(tmp_path, PLAYGROUND_ENABLED="false").get("/browse").text
    bar = _phone_bars(html)[0]
    assert [l[0] for l in _links(bar)] == ["/dashboard", "/browse", "/calendar", "/profile"]
    nav = _top_nav(html)
    assert 'href="/playground"' not in nav


def test_guest_phone_bar_is_rendered_visible_on_settings_and_search() -> None:
    css = (STATIC / "mobile.css").read_text(encoding="utf-8")
    # The generic rule still hides the bar on settings/search for signed-in screens;
    # the guest override must come after it and restore the grid.
    hide = css.index('body[data-mscreen="settings"] .mobile-tabbar {')
    override = css.index('body.is-guest[data-mscreen="settings"] .mobile-tabbar')
    assert override > hide
    assert 'body.is-guest[data-mscreen="search"] .mobile-tabbar' in css
    assert ".mobile-tabbar.is-guest" not in css


# ───────────────────────── top nav: five links + Sign in, no legacy chrome ─────────────────────────


@pytest.mark.parametrize("route,active", sorted(GUEST_ROUTES.items()))
def test_guest_top_nav_is_the_five_product_links(tmp_path: Path, route: str, active: str | None) -> None:
    html = _guest(tmp_path).get(route).text
    header = _header(html)
    nav = _top_nav(html)
    links = _links(nav)
    assert [l[0] for l in links] == TAB_ORDER, route
    assert [l[1] for l in links] == TAB_LABELS, route
    current = [l[0] for l in links if l[3]]
    assert current == ([active] if active else []), route
    for legacy in (">Home<", ">Search<", ">Learn<", "Learning as guest", "guest-pill",
                   "data-guest-account-menu", "Not signed in", "data-guest-pg-brand",
                   "data-pg-gate-phone-brand", "data-guest-profile-brand"):
        assert legacy not in header, f"{route}: {legacy}"
    assert header.count('class="nav-signin"') == 1, route
    assert re.search(r'<a[^>]+class="nav-signin"[^>]+href="/login"|<a[^>]+href="/login"[^>]+class="nav-signin"', header), route
    assert header.count('class="brand"') == 1, route


def test_guest_header_shell_is_identical_across_routes(tmp_path: Path) -> None:
    client = _guest(tmp_path)
    shells = {}
    for route in ("/browse", "/laws", "/laws/ndps", "/playground", "/dashboard", "/settings", "/profile", "/terms"):
        header = _header(client.get(route).text)
        # normalise the active marker so only structural differences remain
        header = header.replace(" is-active", "").replace(' aria-current="page"', "")
        shells[route] = re.sub(r"\s+", " ", header)
    assert len(set(shells.values())) == 1, {k: v[:120] for k, v in shells.items()}


def test_auth_surface_and_standalone_pages_are_unchanged_exceptions(tmp_path: Path) -> None:
    client = _guest(tmp_path)
    landing = client.get("/").text
    assert "<header" not in landing and "mobile-tabbar" not in landing
    login = client.get("/login").text
    assert 'aria-label="Primary"' not in login and "mobile-tabbar" not in login
    signed_out = client.get("/signed-out").text
    nav = _top_nav(signed_out)
    assert 'href="/login"' in nav and ">Home<" in nav  # auth_surface branch kept


# ───────────────────────── gates and footer preserved ─────────────────────────


def test_guest_gates_are_preserved(tmp_path: Path) -> None:
    client = _guest(tmp_path)
    cal = client.get("/calendar", follow_redirects=False)
    assert cal.status_code == 303 and cal.headers["location"].startswith("/login?next=%2Fcalendar")
    dev = client.get("/profile/security/devices", follow_redirects=False)
    assert dev.status_code == 303 and dev.headers["location"].startswith("/login?next=")
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200 and "Sign in to use Playground" in gate.text


def test_guest_footer_keeps_functions_and_a_route_to_settings(tmp_path: Path) -> None:
    html = _guest(tmp_path).get("/browse").text
    footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
    for needle in ('href="/tables"', 'href="/settings"', "Contact us", 'href="/terms"', 'href="/privacy"', 'href="/grievance"', 'id="theme-toggle"'):
        assert needle in footer, needle


def test_shared_shell_viewport_allows_zoom(tmp_path: Path) -> None:
    html = _guest(tmp_path).get("/browse").text
    meta = re.search(r'<meta name="viewport" content="([^"]+)"', html).group(1)
    assert "user-scalable=no" not in meta and "maximum-scale" not in meta
    assert "width=device-width" in meta and "initial-scale=1" in meta


# ───────────────────────── signed-in regression + DV-20 + DV-21 ─────────────────────────

SIGNED_IN_ROUTES = ["/dashboard", "/browse", "/laws", "/laws/ndps", "/laws/uapa", "/playground",
                    "/playground?stage=plans", "/playground?stage=plans&tier=plus",
                    "/playground/laws/uapa/add", "/calendar", "/profile", "/settings",
                    "/profile/security/devices", "/tables", "/search", "/terms"]


@pytest.mark.parametrize("route", SIGNED_IN_ROUTES)
def test_signed_in_top_nav_and_account_slot(tmp_path: Path, route: str) -> None:
    html = _signed_in(tmp_path).get(route).text
    header = _header(html)
    nav = _top_nav(html)
    assert [l[0] for l in _links(nav)][:5] == TAB_ORDER, route
    assert "nav-signin" not in header and "guest-pill" not in header, route
    # DV-20: the account slot always carries the plan subtitle
    assert 'class="account-menu-btn-name">User A<' in header, route
    assert 'class="account-menu-btn-status">Free account<' in header, route


def test_signed_in_free_phone_bar_unchanged_outside_special_screens(tmp_path: Path) -> None:
    client = _signed_in(tmp_path)
    for route in ("/dashboard", "/browse", "/calendar", "/profile"):
        bars = _phone_bars(client.get(route).text)
        assert len(bars) == 1, route
        assert "data-guest-phone-tabs" not in bars[0], route
        assert [l[0] for l in _links(bars[0])] == TAB_ORDER, route


def test_dv21_gate_plans_and_add_no_longer_hide_the_top_nav() -> None:
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    playground = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert 'body.is-authed[data-mscreen="playground"]:has([data-signed-in-pg-gate]) .PrimaryTabs--top {' not in styles
    assert 'body.is-guest[data-mscreen="playground"]:has([data-guest-pg-intro]) .PrimaryTabs--top,' not in styles
    # the hard-gate rule may still hide phone bars, but never the desktop nav
    hard = playground.split('[data-hard-gate="true"]', 1)[1][:400]
    assert ".PrimaryTabs--top" not in hard


def test_asset_pins_were_bumped_for_shell_css(tmp_path: Path) -> None:
    html = _guest(tmp_path).get("/browse").text
    assert "styles.css?v=main86" not in html and "mobile.css?v=mob105" not in html
