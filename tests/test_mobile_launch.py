"""The phone landing: a black launch screen with two doors.

The split is CSS-only — one response for every device, the same way every
other screen in this app decides what a phone sees. So these assert markup and
scoping, not that the response differs by user agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _guest_client(tmp_path: Path) -> TestClient:
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
    )
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=settings,
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )


def test_launch_screen_offers_the_constitution_and_the_laws(tmp_path: Path):
    html = _guest_client(tmp_path).get("/").text
    launch = html.split('<section class="rc-launch">', 1)[1].split("</section>", 1)[0]
    assert ">Recall the C</p>" in launch
    assert "The Constitution, remembered." in launch
    assert '<a class="rc-launch-cta" href="/browse">Explore the Constitution</a>' in launch
    assert '<a class="rc-launch-cta is-ghost" href="/laws">Explore Laws</a>' in launch
    assert "BARE ACT · VERBATIM · DAY 1 · 3 · 7 · 15 · 30 · 60" in launch
    # The C mark is Abril Fatface, loaded for this page only.
    assert "family=Abril+Fatface" in html
    assert '"Abril Fatface",Georgia,serif' in html


def test_the_launch_screen_belongs_to_the_phone(tmp_path: Path):
    html = _guest_client(tmp_path).get("/").text
    # Hidden by default; the 560px query is what swaps the two over.
    assert ".rc-launch{display:none}" in html
    phone = html.split("@media (max-width:560px){", 1)[1]
    assert ".rc-landing-full{display:none}" in phone
    assert ".rc-launch{display:block" in phone


def test_the_desktop_landing_is_untouched(tmp_path: Path):
    html = _guest_client(tmp_path).get("/").text
    assert 'class="rc-landing-full"' in html
    # Its corridor, canvas and CTAs are all still there.
    assert 'data-brain="1"' in html
    assert 'id="arithmetic"' in html
    assert 'data-stage="1"' in html
    assert 'href="/browse"' in html
    assert 'href="/login"' in html
    assert "</footer>" in html


def test_the_launch_screen_is_not_a_first_run_state(tmp_path: Path):
    """Width decides this, not a remembered visit."""
    client = _guest_client(tmp_path)
    first = client.get("/")
    assert "rc-launch" in first.text
    assert not [c for c in first.cookies.keys() if "launch" in c or "seen" in c]
    # Same markup on the next visit — nothing was recorded to suppress it.
    assert client.get("/").text == first.text


def test_the_desktop_landing_still_boots_after_crossing_the_breakpoint(
    tmp_path: Path,
):
    """A phone that rotates into landscape must not get a dead landing."""
    js = _guest_client(tmp_path).get("/static/landing.js").text
    tail = js.split("function bootWhenWide()", 1)[1]
    assert "phone.matches" in tail
    assert "addEventListener('change', onChange)" in tail
    assert "if (booted) return;" in js


def test_landing_assets_are_cache_busted(tmp_path: Path):
    html = _guest_client(tmp_path).get("/").text
    assert "/static/landing.js?v=" in html
    assert "/static/brain-path.js?v=" in html
