"""Playground overlay on NDPS + BNS verbatim JSON."""

from __future__ import annotations

import html
import re
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.cloze import has_cloze_blanks
from constitution_memorizer.playground.locators import parse_locator, section_locator
from constitution_memorizer.playground.revision import INTERVAL_LADDER, advance_interval
from constitution_memorizer.playground.source import (
    canonical_body_text,
    resolve_section,
    source_hash,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db"))


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
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _mu_client(tmp_path: Path, *, signed_in: bool) -> TestClient:
    provider = FakeAuthProvider()
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_mu_settings(),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
        )
    )
    if signed_in:
        provider.seed_google_user(
            user_id=USER_ID, email="a@example.com", display_name="A"
        )
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        client.get(
            f"/auth/callback?code=fake-google-code&state={state}",
            follow_redirects=False,
        )
    return client


def _cloze_attr(page: str) -> str:
    match = re.search(r'data-cloze-text="([^"]*)"', page)
    assert match is not None
    return html.unescape(match.group(1))


def _add_and_select(client: TestClient, law_id: str, number: str) -> None:
    added = client.post(f"/playground/{law_id}/add", follow_redirects=False)
    assert added.status_code == 303
    saved = client.post(
        f"/playground/{law_id}/select",
        data={"section": number},
        follow_redirects=False,
    )
    assert saved.status_code == 303


def test_locator_round_trip_from_json():
    for law_id in ("ndps", "bns"):
        act = get_bare_act(law_id)
        assert act is not None
        section = act.section("1")
        assert section is not None
        loc = section_locator(law_id, section.number)
        parsed = parse_locator(loc.value)
        assert parsed.law_id == law_id
        assert parsed.number == "1"
        again, resolved = resolve_section(parsed)
        assert again.slug == law_id
        assert resolved.number == section.number


def test_canonical_body_and_hash_are_deterministic():
    for law_id in ("ndps", "bns"):
        act = get_bare_act(law_id)
        assert act is not None
        section = act.section("1")
        assert section is not None
        body = canonical_body_text(section)
        assert body
        assert has_cloze_blanks(body)
        assert source_hash(section) == source_hash(section)


def test_revision_ladder_matches_audit():
    assert INTERVAL_LADDER == (1, 3, 7, 15, 30, 60)
    assert advance_interval(1) == 3
    assert advance_interval(60) is None


def test_guest_cannot_persist_playground(tmp_path: Path):
    client = _mu_client(tmp_path, signed_in=False)
    response = client.post("/playground/ndps/add", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/laws/ndps"
    listed = client.get("/playground", follow_redirects=False)
    assert listed.status_code == 303
    assert "/login?next=/playground" in listed.headers["location"]


def test_add_to_playground_is_idempotent(tmp_path: Path):
    client = _client(tmp_path)
    first = client.post("/playground/ndps/add", follow_redirects=False)
    second = client.post("/playground/ndps/add", follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 303
    repo = client.app.state.playground
    items = repo.list_items(LOCAL_USER_ID)
    assert [item.law_id for item in items] == ["ndps"]


def test_bare_act_head_has_add_button(tmp_path: Path):
    client = _client(tmp_path)
    ndps = client.get("/laws/ndps")
    assert ndps.status_code == 200
    assert "Add to Playground" in ndps.text
    bns = client.get("/laws/bns")
    assert bns.status_code == 200
    assert "Add to Playground" in bns.text


def test_cloze_integrity_ndps_and_bns_section_1(tmp_path: Path):
    client = _client(tmp_path)
    for law_id in ("ndps", "bns"):
        act = get_bare_act(law_id)
        assert act is not None
        section = act.section("1")
        assert section is not None
        canonical = canonical_body_text(section)
        _add_and_select(client, law_id, "1")
        page = client.get(f"/playground/{law_id}/learn/1")
        assert page.status_code == 200
        assert _cloze_attr(page.text) == canonical
        done = client.post(f"/playground/{law_id}/learn/1/complete")
        assert done.status_code == 200
        payload = done.json()
        assert payload["ok"] is True
        assert payload["revealed"] == canonical
        assert payload["canonical_body"] == canonical
        assert payload["status"] == "review"
        assert payload["interval_days"] == 1


def test_source_hash_mismatch_is_flagged_not_wiped(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    client.post("/playground/ndps/learn/1/complete")
    loc = section_locator("ndps", "1").value
    repo = client.app.state.playground
    repo.conn.execute(
        """
        UPDATE user_playground_progress
        SET source_hash = 'deadbeef'
        WHERE user_id = ? AND law_id = ? AND source_locator = ?
        """,
        (str(LOCAL_USER_ID), "ndps", loc),
    )
    repo.conn.commit()
    page = client.get("/playground/ndps/learn/1")
    assert page.status_code == 200
    assert "This provision has changed" in page.text
    remaining = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert remaining is not None
    assert remaining.source_hash == "deadbeef"


def test_cloze_complete_idempotent_before_due(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    repo = client.app.state.playground
    loc = section_locator("ndps", "1").value
    act = get_bare_act("ndps")
    section = act.section("1")
    live = source_hash(section)
    first = repo.complete_cloze(
        LOCAL_USER_ID,
        "ndps",
        loc,
        source_version="v",
        source_hash=live,
        as_of=date.today(),
        live_hash=live,
    )
    second = repo.complete_cloze(
        LOCAL_USER_ID,
        "ndps",
        loc,
        source_version="v",
        source_hash=live,
        as_of=date.today(),
        live_hash=live,
    )
    assert first.interval_days == 1
    assert second.interval_days == 1
    assert second.times_completed == 1
    later = repo.complete_cloze(
        LOCAL_USER_ID,
        "ndps",
        loc,
        source_version="v",
        source_hash=live,
        as_of=date.today() + timedelta(days=1),
        live_hash=live,
    )
    assert later.interval_days == 3
    assert later.times_completed == 2


def test_unknown_playground_law_404(tmp_path: Path):
    client = _client(tmp_path)
    response = client.post("/playground/ipc/add", follow_redirects=False)
    assert response.status_code == 404


def test_alembic_playground_tables_enable_rls():
    text = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260906_0017_playground_overlay.py"
    ).read_text(encoding="utf-8")
    for table in (
        "user_playground_item",
        "user_playground_selection",
        "user_playground_progress",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text
        assert f"ALTER TABLE IF EXISTS {table} ENABLE ROW LEVEL SECURITY" in text
