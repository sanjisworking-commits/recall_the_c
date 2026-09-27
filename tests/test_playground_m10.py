"""Milestone 10: public statutory SEO vs private learning/account noindex.

Does not rebuild seo.py / sitemaps.py architecture. Proves canonical helpers,
Playground/account robots policy, X-Robots-Tag on private non-HTML, and
manifest-backed zero-hydration sitemaps. Alembic head stays 0027.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse, Response

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.seo import (
    DEFAULT_SEO_DESCRIPTION,
    DEFAULT_SEO_TITLE,
    apply_private_robots_headers,
    is_noindex_path,
    laws_hub_canonical_url,
    provision_canonical_url,
)
from constitution_memorizer.web.sitemaps import (
    build_laws_hub_sitemap,
    build_sitemap_index,
    load_law_sitemap_manifest,
)
from constitution_memorizer.playground.urls import (
    law_path,
    learn_path,
    roster_next_path,
    roster_path,
    source_review_path,
)
from constitution_memorizer.web import app as web_app
from constitution_memorizer.web import sitemaps as sitemaps_mod
from tests.test_playground import _add_and_select, _client
from tests.test_private_noindex import _has_noindex, _robots, _mu_settings
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
_ROBOTS_HEADER = "noindex, nofollow"


def test_alembic_head_unchanged_by_m10():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]
    versions = ROOT / "alembic" / "versions"
    assert not list(versions.glob("*0028*"))


def test_shared_seo_helpers_are_the_only_engine():
    app_src = inspect.getsource(web_app)
    assert "build_laws_hub_seo(" in app_src
    assert "laws_hub_canonical_url(" in app_src
    assert "law_canonical_url(" in app_src
    assert "provision_canonical_url(" in app_src
    assert "schedule_canonical_url(" in app_src
    assert "build_law_seo(" in app_src
    assert "build_provision_seo(" in app_src
    assert "build_schedule_seo(" in app_src
    assert "apply_private_robots_headers(" in app_src
    sitemap_tree = ast.parse(inspect.getsource(sitemaps_mod))
    called_names = {
        node.func.id
        for node in ast.walk(sitemap_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imported_names = {
        alias.name
        for node in ast.walk(sitemap_tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "get_bare_act" not in called_names
    assert "list_bare_acts" not in called_names
    assert "get_bare_act" not in imported_names
    assert "list_bare_acts" not in imported_names
    sitemap_src = inspect.getsource(sitemaps_mod)
    assert "playground_seo" not in app_src
    assert "NDPS Act" not in sitemap_src
    routes = (ROOT / "src/constitution_memorizer/playground/routes.py").read_text(
        encoding="utf-8"
    )
    ast.parse(routes)
    assert "build_law_seo" not in routes


def test_query_variants_do_not_index_as_distinct_pages(tmp_path: Path):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    for path in ("/laws?q=bail", "/laws?subject=criminal", "/laws?q=bail&subject=criminal"):
        html = client.get(path).text
        match = re.search(
            r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
            html,
            re.I,
        )
        assert match and match.group(1) == laws_hub_canonical_url()
        assert _title(html) != DEFAULT_SEO_TITLE
        assert _meta_desc(html) != DEFAULT_SEO_DESCRIPTION
        assert _robots(html) is None


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip() if m else ""


def _meta_desc(html: str) -> str:
    m = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html,
        re.I,
    )
    return m.group(1) if m else ""


def test_section_canonical_keeps_string_identifiers():
    assert provision_canonical_url("ndps", "section", "27A").endswith("/section/27A")
    assert provision_canonical_url("ndps", "section", "68-I").endswith("/section/68-I")
    assert provision_canonical_url("ndps", "section", "68-O").endswith("/section/68-O")


@pytest.mark.parametrize(
    "path",
    [
        "/playground",
        "/playground/roster",
        "/playground/roster/next",
        "/playground/laws/ndps",
        "/playground/laws/ndps/sections",
        "/playground/laws/ndps/add",
    ],
)
def test_playground_html_is_noindex(tmp_path: Path, path: str):
    client = _client(tmp_path)
    if path.startswith("/playground/laws/ndps"):
        _add_and_select(client, "ndps", "1")
    resp = client.get(path)
    assert resp.status_code == 200
    assert _has_noindex(resp.text)
    assert "nofollow" in (_robots(resp.text) or "").lower()
    assert "X-Robots-Tag" not in resp.headers


def test_playground_learn_revision_and_source_review_are_noindex(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    for path in (
        learn_path("ndps", "1", "read"),
        learn_path("ndps", "1", "read", revision=1),
        source_review_path("ndps"),
        law_path("ndps"),
        roster_path(),
        roster_next_path(),
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert _has_noindex(resp.text), path


def test_private_json_gets_x_robots_tag(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    token = client.cookies.get("rtc_csrf") or ""
    resp = client.post(
        f"{learn_path('ndps', '1', 'read')}/start",
        headers={"X-CSRF-Token": token, "Accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    assert resp.headers.get("X-Robots-Tag") == _ROBOTS_HEADER


def test_public_non_html_does_not_get_x_robots(tmp_path: Path):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "X-Robots-Tag" not in sitemap.headers
    hub = client.get("/laws")
    assert hub.status_code == 200
    assert "X-Robots-Tag" not in hub.headers
    assert _robots(hub.text) is None


def test_apply_private_robots_headers_skips_html_and_public():
    html = Response(content="<html></html>", media_type="text/html")
    apply_private_robots_headers("/playground", html)
    assert "X-Robots-Tag" not in html.headers
    public = JSONResponse({"ok": True})
    apply_private_robots_headers("/laws", public)
    assert "X-Robots-Tag" not in public.headers
    private = JSONResponse({"ok": True})
    apply_private_robots_headers("/playground/laws/ndps", private)
    assert private.headers["X-Robots-Tag"] == _ROBOTS_HEADER


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/laws",
        "/laws/ndps",
        "/laws/ndps/section/27A",
        "/browse/article/21",
        "/terms",
        "/privacy",
        "/grievance",
    ],
)
def test_public_pages_stay_indexable(tmp_path: Path, path: str):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    resp = client.get(path)
    assert resp.status_code == 200
    assert _robots(resp.text) is None
    assert not is_noindex_path(path)


def test_account_device_payment_and_auth_are_noindex(tmp_path: Path):
    clear_settings_cache()
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    admin = UUID("55555555-5555-4555-8555-555555555555")
    provider.seed_google_user(user_id=admin, email="admin@recall.app", display_name="A")
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
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    from datetime import datetime, timezone

    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(admin), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()
    try:
        for path in (
            "/dashboard",
            "/calendar",
            "/progress",
            "/profile",
            "/profile/security/devices",
            "/settings",
            "/admin",
            "/billing/subscriptions",
            "/welcome",
            "/session-expired",
        ):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert _has_noindex(resp.text), path
        login = client.get("/login", follow_redirects=True)
        assert _has_noindex(login.text)
        assert "nofollow" in (_robots(login.text) or "").lower()
        signed = client.get("/signed-out")
        assert signed.status_code == 200
        assert _has_noindex(signed.text)
        subscribe = client.get("/subscribe/confirm")
        if subscribe.status_code == 200:
            assert _has_noindex(subscribe.text)
    finally:
        clear_settings_cache()


def test_guest_playground_redirect_is_not_required_to_carry_canonical(
    tmp_path: Path,
):
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
        client = TestClient(app)
        resp = client.get("/playground", follow_redirects=False)
        assert resp.status_code in {302, 303}
        assert "/login" in resp.headers.get("location", "")
        login = client.get("/login")
        assert _has_noindex(login.text)
        assert "nofollow" in (_robots(login.text) or "").lower()
    finally:
        clear_settings_cache()


def test_sitemap_index_has_core_hub_and_laws_without_private_urls():
    load_law_sitemap_manifest.cache_clear()
    xml = build_sitemap_index()
    assert "sitemap-core.xml" in xml
    assert "sitemap-laws.xml" in xml
    assert "sitemap-laws-ndps.xml" in xml
    for private in (
        "/playground",
        "/dashboard",
        "/calendar",
        "/profile",
        "/settings",
        "/billing",
        "/learn",
        "/progress",
    ):
        assert private not in xml
    hub = build_laws_hub_sitemap()
    assert laws_hub_canonical_url() in hub
    load_law_sitemap_manifest.cache_clear()


def test_sitemaps_module_has_no_per_law_route_table():
    src = (ROOT / "src/constitution_memorizer/web/sitemaps.py").read_text(
        encoding="utf-8"
    )
    assert "ndps" not in src.lower() or "slug" in src
    assert "BARE_ACTS" in src
    assert 'if slug == "ndps"' not in src
    assert 'if slug == "bns"' not in src
