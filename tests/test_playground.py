"""Playground overlay on full Bare Acts (catalogue + BareActSpec)."""

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
from constitution_memorizer.playground.eligibility import (
    is_playground_eligible_law,
    list_playground_eligible_laws,
)
from constitution_memorizer.playground.locators import (
    LocatorError,
    parse_locator,
    section_locator,
)
from constitution_memorizer.playground.revision import INTERVAL_LADDER, advance_interval
from constitution_memorizer.playground.source import (
    canonical_body_text,
    resolve_section,
    source_hash,
)
from constitution_memorizer.playground.urls import (
    add_path,
    law_path,
    learn_complete_path,
    learn_path,
    sections_path,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import clear_bare_act_cache, get_bare_act

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
    added = client.post(add_path(law_id), follow_redirects=False)
    assert added.status_code == 303
    saved = client.post(
        sections_path(law_id),
        data={"section": number},
        follow_redirects=False,
    )
    assert saved.status_code == 303


def _hydrate_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    hydrated: list[str] = []
    real = bare_acts._load_cached

    def wrapped(slug: str, identity: str):
        hydrated.append(slug)
        return real(slug, identity)

    monkeypatch.setattr(bare_acts, "_load_cached", wrapped)
    return hydrated


def test_eligibility_covers_full_acts_not_key_provisions():
    assert is_playground_eligible_law("ndps") is True
    assert is_playground_eligible_law("bns") is True
    assert is_playground_eligible_law("bnss") is True
    assert is_playground_eligible_law("uapa-1967") is False
    assert is_playground_eligible_law("unknown") is False
    assert is_playground_eligible_law("") is False
    assert list_playground_eligible_laws() == ("bns", "bnss", "ndps")


def test_eligibility_and_locator_parse_do_not_hydrate(
    monkeypatch: pytest.MonkeyPatch,
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("eligibility must not call get_bare_act/list_bare_acts")

    monkeypatch.setattr(bare_acts, "get_bare_act", boom)
    monkeypatch.setattr(bare_acts, "list_bare_acts", boom)
    assert is_playground_eligible_law("ndps") is True
    assert is_playground_eligible_law("bnss") is True
    assert is_playground_eligible_law("uapa-1967") is False
    assert parse_locator("ndps:section:8").number == "8"
    assert parse_locator("bnss:section:479").law_id == "bnss"
    assert hydrated == []


def test_locator_round_trip_from_json():
    samples = (("ndps", "8"), ("bns", "103"), ("bnss", "479"))
    for law_id, number in samples:
        loc = section_locator(law_id, number)
        parsed = parse_locator(loc.value)
        assert parsed.law_id == law_id
        assert parsed.number == number
        assert isinstance(parsed.number, str)
        assert parsed.number != int(number)
        again, resolved = resolve_section(parsed)
        assert again.slug == law_id
        assert resolved.number == number


def test_locator_rejects_unknown_and_malformed():
    with pytest.raises(LocatorError):
        parse_locator("unknown:section:8")
    with pytest.raises(LocatorError):
        parse_locator("ndps:chapter:1")
    with pytest.raises(LocatorError):
        parse_locator("ndps:section:")
    with pytest.raises(LocatorError):
        parse_locator("NDPS:section:8")
    with pytest.raises(LocatorError):
        section_locator("ipc", "1")


def test_canonical_body_and_hash_are_deterministic():
    for law_id in ("ndps", "bns", "bnss"):
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
    response = client.post(add_path("ndps"), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/laws/ndps"
    listed = client.get("/playground", follow_redirects=False)
    assert listed.status_code == 303
    assert "/login?next=/playground" in listed.headers["location"]


def test_add_to_playground_is_idempotent(tmp_path: Path):
    client = _client(tmp_path)
    first = client.post(add_path("ndps"), follow_redirects=False)
    second = client.post(add_path("ndps"), follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 303
    repo = client.app.state.playground
    items = repo.list_items(LOCAL_USER_ID)
    assert [item.law_id for item in items] == ["ndps"]


def test_bare_act_head_has_add_button_for_eligible_laws(tmp_path: Path):
    client = _client(tmp_path)
    for law_id in ("ndps", "bns", "bnss"):
        page = client.get(f"/laws/{law_id}")
        assert page.status_code == 200
        assert "Add to Playground" in page.text
        assert add_path(law_id) in page.text
    key_provisions = client.get("/laws/uapa-1967")
    assert key_provisions.status_code == 200
    assert "Add to Playground" not in key_provisions.text


def test_cloze_integrity_ndps_bns_bnss_section_1(tmp_path: Path):
    client = _client(tmp_path)
    for law_id in ("ndps", "bns", "bnss"):
        act = get_bare_act(law_id)
        assert act is not None
        section = act.section("1")
        assert section is not None
        canonical = canonical_body_text(section)
        _add_and_select(client, law_id, "1")
        page = client.get(learn_path(law_id, "1"))
        assert page.status_code == 200
        assert _cloze_attr(page.text) == canonical
        done = client.post(learn_complete_path(law_id, "1"))
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
    client.post(learn_complete_path("ndps", "1"))
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
    page = client.get(learn_path("ndps", "1"))
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
    response = client.post(add_path("ipc"), follow_redirects=False)
    assert response.status_code == 404
    assert client.post(add_path("uapa-1967"), follow_redirects=False).status_code == 404


def test_final_namespace_and_retired_proof_urls(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/playground").status_code == 200
    for law_id in ("ndps", "bns", "bnss"):
        added = client.post(add_path(law_id), follow_redirects=False)
        assert added.status_code == 303
        assert added.headers["location"] == sections_path(law_id)
        workspace = client.get(law_path(law_id), follow_redirects=False)
        assert workspace.status_code == 200
    assert client.get("/playground/roster").status_code == 404
    assert client.get("/playground/ndps").status_code == 404
    assert client.post("/playground/ndps/add", follow_redirects=False).status_code == 404
    assert client.get("/laws/bnss").status_code == 200
    assert client.get("/laws/ndps").status_code == 200
    assert client.get("/").status_code == 200


def test_opening_bnss_playground_does_not_hydrate_ndps_or_bns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client = _client(tmp_path)
    empty_home = list(hydrated)
    client.get("/playground")
    assert hydrated == empty_home
    client.post(add_path("bnss"), follow_redirects=False)
    client.get(law_path("bnss"))
    assert "bnss" in hydrated
    assert "ndps" not in hydrated
    assert "bns" not in hydrated


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
