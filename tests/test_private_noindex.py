"""Private-surface indexability hygiene.

Personalized / account / application / admin pages must carry
``<meta name="robots" content="noindex, nofollow">`` so they cannot enter a
search index, while the public marketing, Constitution Browse, and Bare Act
surfaces must NOT. Private URLs must also never appear in any sitemap, and the
existing auth/access behavior must be unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS
from constitution_memorizer.web.seo import NOINDEX_PATH_PREFIXES, is_noindex_path
from constitution_memorizer.web.sitemaps import (
    SITEMAP_NS,
    build_law_sitemap,
    build_laws_hub_sitemap,
    build_sitemap_index,
    load_law_sitemap_manifest,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
_ROBOTS_RE = re.compile(
    r'<meta[^>]*name=["\']robots["\'][^>]*content=["\']([^"\']*)["\']', re.I
)


def _robots(html: str) -> str | None:
    m = _ROBOTS_RE.search(html)
    return m.group(1) if m else None


def _has_noindex(html: str) -> bool:
    content = (_robots(html) or "").lower()
    return "noindex" in content


# ── Unit: path classifier ────────────────────────────────────────────────────


@pytest.mark.parametrize("prefix", list(NOINDEX_PATH_PREFIXES))
def test_noindex_prefixes_classified_private(prefix: str):
    assert is_noindex_path(prefix)
    assert is_noindex_path(prefix + "/anything/deep")


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/browse",
        "/browse/article/21",
        "/browse/part/fundamental-rights",
        "/laws",
        "/laws/ndps",
        "/laws/ndps/section/27A",
        "/laws/bnss/schedule/first-schedule",
        "/search",
        "/tables",
        "/pricing",
        "/terms",
        "/privacy",
        "/grievance",
    ],
)
def test_public_paths_stay_indexable(path: str):
    assert not is_noindex_path(path)


def test_learn_prefix_does_not_swallow_laws():
    # Guard the substring trap: /laws must not match the /learn prefix.
    assert not is_noindex_path("/laws")
    assert not is_noindex_path("/laws/ndps/section/50A")
    assert is_noindex_path("/learn")
    assert is_noindex_path("/learn/clause-1")


# ── Single-user integration ──────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )


@pytest.mark.parametrize(
    "path",
    [
        "/progress",
        "/progress/mastered",
        "/calendar",
        "/settings",
        "/onboarding/plan",
        "/learning/plan-my-day",
    ],
)
def test_private_pages_carry_noindex(client: TestClient, path: str):
    resp = client.get(path)
    assert resp.status_code == 200
    assert _has_noindex(resp.text), f"{path} missing noindex meta"
    assert "nofollow" in (_robots(resp.text) or "").lower()


def test_learn_reader_page_carries_noindex(client: TestClient):
    # /learn redirects to the first personalized unit; the reader itself is private.
    resp = client.get("/learn", follow_redirects=True)
    assert resp.status_code == 200
    assert _has_noindex(resp.text)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/browse",
        "/browse/article/20",
        "/laws",
        "/laws/ndps",
        "/laws/ndps/section/27A",
        "/laws/ndps/schedule/psychotropic-substances",
        "/search",
        "/tables",
        "/terms",
        "/privacy",
        "/grievance",
    ],
)
def test_public_pages_have_no_robots_meta(client: TestClient, path: str):
    resp = client.get(path)
    assert resp.status_code == 200
    assert _robots(resp.text) is None, f"{path} unexpectedly carries a robots meta"


# ── Multi-user (authenticated) integration ───────────────────────────────────


def _mu_settings(**overrides) -> MultiUserSettings:
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
        "ADMIN_ENABLED": "true",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


_ADMIN_ID = UUID("55555555-5555-4555-8555-555555555555")


@pytest.fixture()
def authed_admin(tmp_path: Path):
    clear_settings_cache()
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=_ADMIN_ID, email="admin@recall.app", display_name="Admin"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    from datetime import datetime, timezone

    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(_ADMIN_ID), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()
    try:
        yield client
    finally:
        clear_settings_cache()


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/profile", "/welcome", "/settings", "/admin", "/admin/users"],
)
def test_authenticated_private_pages_carry_noindex(authed_admin: TestClient, path: str):
    resp = authed_admin.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    assert _has_noindex(resp.text), f"authenticated {path} missing noindex meta"


# NB: "/" is intentionally excluded — an authenticated user hitting "/" is
# redirected (303) to their private /dashboard, so its final page is noindexed
# by design. The public *content* surfaces below must stay indexable regardless
# of who is signed in.
@pytest.mark.parametrize(
    "path", ["/laws", "/laws/ndps", "/browse/article/20"]
)
def test_authenticated_public_pages_stay_indexable(authed_admin: TestClient, path: str):
    resp = authed_admin.get(path, follow_redirects=True)
    assert resp.status_code == 200
    assert _robots(resp.text) is None, f"{path} unexpectedly noindexed for authed user"


def test_login_page_is_noindex(authed_admin: TestClient):
    # login.html is standalone (its own <head>) but must still be noindex.
    resp = authed_admin.get("/login", follow_redirects=True)
    assert _has_noindex(resp.text)


# ── Sitemap absence ──────────────────────────────────────────────────────────


def test_no_private_url_appears_in_any_sitemap():
    load_law_sitemap_manifest.cache_clear()
    ns = f"{{{SITEMAP_NS}}}"

    def locs(xml: str) -> list[str]:
        return [el.text for el in ET.fromstring(xml).iter(f"{ns}loc")]

    all_locs: list[str] = []
    all_locs += locs(build_laws_hub_sitemap())
    for slug in BARE_ACTS:
        xml = build_law_sitemap(slug)
        if xml:
            all_locs += locs(xml)
    # Core sitemap (Constitution + marketing) is a packaged file.
    from constitution_memorizer.web import sitemaps as _s

    core = (_s._WEB_DIR / "sitemap-core.xml").read_text(encoding="utf-8")
    all_locs += locs(core)

    assert all_locs, "expected sitemap URLs to check"
    offenders = [loc for loc in all_locs if is_noindex_path(urlparse(loc).path)]
    assert not offenders, f"private URLs leaked into a sitemap: {offenders[:5]}"

    # The sitemap index only lists child sitemap documents, none private.
    idx_children = locs(build_sitemap_index())
    assert all(not is_noindex_path(urlparse(c).path) for c in idx_children)
    load_law_sitemap_manifest.cache_clear()


# ── Auth/access behavior unchanged ───────────────────────────────────────────


@pytest.fixture()
def guest_client(tmp_path: Path) -> TestClient:
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_mu_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )
    try:
        yield TestClient(app)
    finally:
        clear_settings_cache()


@pytest.mark.parametrize("path", ["/calendar", "/admin", "/profile"])
def test_guest_gated_pages_still_redirect_to_login(guest_client: TestClient, path: str):
    # Auth gating is unchanged by the noindex work: these still bounce to login.
    resp = guest_client.get(path, follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/login" in resp.headers.get("location", "")


@pytest.mark.parametrize("path", ["/dashboard", "/progress", "/settings"])
def test_guest_gate_pages_are_still_served_and_noindexed(
    guest_client: TestClient, path: str
):
    # These serve an inline guest gate (200) rather than redirecting; that
    # unchanged behavior must still be kept out of the index.
    resp = guest_client.get(path, follow_redirects=False)
    assert resp.status_code == 200
    assert _has_noindex(resp.text), f"guest {path} gate missing noindex meta"
