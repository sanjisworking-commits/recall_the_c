"""Landing motion: reduced-motion fallback and mobile animation budget."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
LANDING_JS = ROOT / "src/constitution_memorizer/web/static/landing.js"
LANDING_HTML = ROOT / "src/constitution_memorizer/web/templates/landing.html"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _landing_client(tmp_path: Path) -> TestClient:
    clear_settings_cache()
    settings = MultiUserSettings(
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
        PRICING_ENABLED="false",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=settings,
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )
    return TestClient(app)


def test_landing_js_keeps_motion_hooks_and_avoids_ua_sniffing():
    js = LANDING_JS.read_text()
    assert "snap-active" in js
    assert "setupModeIntro" in js
    assert "data-cloze" in js
    assert "prefers-reduced-motion" in js
    assert "cacheDom" in js
    assert "measureGeometry" in js
    assert "applyScroll" in js
    assert "(pointer: coarse)" in js
    assert "FIELD_BUDGET_MOBILE" in js
    assert "FIELD_BUDGET_DESKTOP" in js
    assert "fieldDpr" in js
    assert "document.hidden" in js
    assert "orientationchange" in js
    assert "navigator.userAgent" not in js
    assert "navigator.platform" not in js
    assert "/iPhone" not in js
    assert "/Android" not in js
    assert "iPhone" not in js


def test_landing_js_mobile_field_budget_is_a_quality_profile_not_off():
    js = LANDING_JS.read_text()
    desktop = None
    mobile = None
    for line in js.splitlines():
        if "FIELD_BUDGET_DESKTOP" in line and "=" in line and "var " in line:
            desktop = int(line.split("=")[1].strip().rstrip(";"))
        if "FIELD_BUDGET_MOBILE" in line and "=" in line and "var " in line:
            mobile = int(line.split("=")[1].strip().rstrip(";"))
    assert desktop == 1250
    assert mobile is not None
    assert 0.5 * desktop <= mobile <= 0.7 * desktop
    assert "buildField" in js


def test_landing_html_keeps_reduced_motion_static_layout():
    html = LANDING_HTML.read_text()
    assert "@media (prefers-reduced-motion:reduce)" in html
    assert "@media (max-width:900px) and (prefers-reduced-motion:reduce)" in html
    assert "transform:none !important" in html
    assert "height:600vh" in html
    assert "100svh" in html
    assert "data-vh-probe" in html
    assert "data-brain" in html


def test_served_landing_still_has_reduced_motion_and_canvas(tmp_path: Path):
    client = _landing_client(tmp_path)
    try:
        home = client.get("/", follow_redirects=False)
        assert home.status_code == 200
        html = home.text
        assert "data-brain" in html
        assert "landing.js" in html
        assert "prefers-reduced-motion" in html
        assert "100svh" in html
        assert "data-vh-probe" in html
        assert 'id="landing-theme-toggle"' not in html
    finally:
        clear_settings_cache()
