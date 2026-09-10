"""Playground overlay on full Bare Acts (catalogue + BareActSpec)."""

from __future__ import annotations

import html
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
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
from constitution_memorizer.playground.db import ensure_sqlite_schema
from constitution_memorizer.playground.eligibility import (
    is_playground_eligible_law,
    list_playground_eligible_laws,
    playground_law_source_identity,
)
from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
from constitution_memorizer.playground.service import activate_law, playground_home_cards
from constitution_memorizer.playground import source as playground_source
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
from constitution_memorizer.web.bare_acts import BARE_ACTS, clear_bare_act_cache, get_bare_act

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


RUNTIME_JSON_NAMES = frozenset(
    {
        "ndps_act_final.json",
        "ndps_schedule_patch.json",
        "bns_runtime_v1.json",
        "bnss_runtime_v1.json",
    }
)


def _sqlite_repo(tmp_path: Path) -> SqlitePlaygroundRepository:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(tmp_path / "playground-unit.db")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    return SqlitePlaygroundRepository(conn)


def _guard_runtime_file_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    real = Path.read_bytes

    def wrapped(self):
        if Path(self).name in RUNTIME_JSON_NAMES:
            raise AssertionError(f"must not read runtime JSON {Path(self).name}")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", wrapped)


def _insert_progress(
    conn,
    user_id,
    law_id: str,
    locator: str,
    *,
    cloze_done: int = 1,
    status: str = "review",
    next_revision: str | None = "2026-09-10",
) -> None:
    conn.execute(
        """
        INSERT INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done,
            times_completed, last_completed, next_revision, interval_days,
            source_version, source_hash, updated_at
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 1, '1', 'h', ?)
        """,
        (
            str(user_id),
            law_id,
            locator,
            status,
            cloze_done,
            next_revision,
            next_revision,
            "2026-09-10T00:00:00+00:00",
        ),
    )
    conn.commit()


class _ExecuteProbe:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.execute_sql: list[str] = []
        self.executemany_sql: list[str] = []
        self.executemany_rowcounts: list[int] = []

    def execute(self, sql, parameters=()):
        self.execute_sql.append(sql)
        return self._inner.execute(sql, parameters)

    def executemany(self, sql, seq):
        rows = list(seq)
        self.executemany_sql.append(sql)
        self.executemany_rowcounts.append(len(rows))
        return self._inner.executemany(sql, rows)

    def commit(self):
        return self._inner.commit()

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _PostgresSpyCursor:
    def __init__(self) -> None:
        self.execute_sql: list[str] = []
        self.executemany_sql: list[str] = []
        self.executemany_rowcounts: list[int] = []

    def execute(self, sql, params=None):
        self.execute_sql.append(sql)

    def executemany(self, sql, seq_of_params):
        rows = list(seq_of_params)
        self.executemany_sql.append(sql)
        self.executemany_rowcounts.append(len(rows))

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _PostgresSpyConn:
    def __init__(self, cursor: _PostgresSpyCursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0

    def cursor(self, row_factory=None):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _PostgresSpyPool:
    def __init__(self, conn: _PostgresSpyConn) -> None:
        self._conn = conn

    @contextmanager
    def connection(self):
        yield self._conn


def test_request_time_whole_file_hash_helpers_are_gone():
    assert not hasattr(playground_source, "law_file_hash")
    assert not hasattr(playground_source, "law_source_version")


def test_registry_identity_uses_source_hash_or_filename(monkeypatch: pytest.MonkeyPatch):
    spec = BARE_ACTS["ndps"]
    assert spec.source_hash is None
    missing = playground_law_source_identity("ndps")
    assert missing.source_version == spec.source_version
    assert missing.identity_token == spec.filename
    monkeypatch.setitem(BARE_ACTS, "ndps", replace(spec, source_hash="cafe1234"))
    present = playground_law_source_identity("ndps")
    assert present.identity_token == "cafe1234"
    assert present.source_version == spec.source_version


def test_activation_uses_registry_identity_without_reading_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _guard_runtime_file_bytes(monkeypatch)
    opened: list[str] = []
    real_read_json = bare_acts.read_json

    def wrapped_read_json(path):
        opened.append(Path(path).name)
        return real_read_json(path)

    monkeypatch.setattr(bare_acts, "read_json", wrapped_read_json)

    def boom_get(slug):
        raise AssertionError(f"activation must not hydrate {slug}")

    monkeypatch.setattr(bare_acts, "get_bare_act", boom_get)
    monkeypatch.setattr(
        bare_acts,
        "list_bare_acts",
        lambda: (_ for _ in ()).throw(AssertionError("list")),
    )
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    repo = _sqlite_repo(tmp_path)
    spec = BARE_ACTS["ndps"]
    monkeypatch.setitem(BARE_ACTS, "ndps", replace(spec, source_hash="reg-hash-1"))
    item = activate_law(repo, LOCAL_USER_ID, "ndps")
    assert item.source_version == spec.source_version
    assert item.law_source_hash == "reg-hash-1"
    fallback = activate_law(_sqlite_repo(tmp_path / "fallback"), LOCAL_USER_ID, "bns")
    assert fallback.law_source_hash == BARE_ACTS["bns"].filename
    assert fallback.source_version == BARE_ACTS["bns"].source_version
    assert opened == []
    assert hydrated == []

    client = _client(tmp_path)
    added = client.post(add_path("bnss"), follow_redirects=False)
    assert added.status_code == 303
    stored = client.app.state.playground.get_item(LOCAL_USER_ID, "bnss")
    assert stored is not None
    assert stored.law_source_hash == BARE_ACTS["bnss"].filename
    assert stored.source_version == BARE_ACTS["bnss"].source_version
    assert opened == []
    assert hydrated == []


def test_populated_home_and_summaries_hydrate_zero_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    for law_id in ("ndps", "bns", "bnss"):
        added = client.post(add_path(law_id), follow_redirects=False)
        assert added.status_code == 303
    repo = client.app.state.playground
    repo.replace_selection(
        LOCAL_USER_ID,
        "ndps",
        [("ndps:section:1", "1", "h1"), ("ndps:section:2", "1", "h2")],
    )
    _insert_progress(
        repo.conn,
        LOCAL_USER_ID,
        "ndps",
        "ndps:section:1",
        next_revision=date.today().isoformat(),
    )

    def boom_get(slug):
        raise AssertionError(f"dashboard must not call get_bare_act({slug})")

    def boom_list():
        raise AssertionError("dashboard must not call list_bare_acts")

    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    monkeypatch.setattr(bare_acts, "get_bare_act", boom_get)
    monkeypatch.setattr(bare_acts, "list_bare_acts", boom_list)
    summaries = repo.list_playground_summaries(LOCAL_USER_ID, as_of=date.today())
    cards = playground_home_cards(summaries)
    assert {card["law_id"] for card in cards} == {"ndps", "bns", "bnss"}
    assert "act" not in cards[0]
    ndps_card = next(card for card in cards if card["law_id"] == "ndps")
    assert ndps_card["title"] == (
        "The Narcotic Drugs and Psychotropic Substances Act, 1985"
    )
    assert ndps_card["short_title"] == "NDPS Act"
    assert ndps_card["selected_count"] == 2
    assert ndps_card["learned_count"] == 1
    assert ndps_card["to_learn"] == 1
    page = client.get("/playground")
    assert page.status_code == 200
    assert "The Narcotic Drugs and Psychotropic Substances Act, 1985" in page.text
    assert "The Bharatiya Nyaya Sanhita, 2023" in page.text
    assert "The Bharatiya Nagarik Suraksha Sanhita, 2023" in page.text
    assert "Progress" in page.text
    assert hydrated == []


def test_home_outdated_flag_is_law_level_registry_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    assert client.post(add_path("ndps"), follow_redirects=False).status_code == 303
    spec = BARE_ACTS["ndps"]
    monkeypatch.setitem(BARE_ACTS, "ndps", replace(spec, source_version="changed"))
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    page = client.get("/playground")
    assert page.status_code == 200
    assert "A source update may require review" in page.text
    assert hydrated == []


@pytest.mark.parametrize(
    ("law_id", "others"),
    [
        ("ndps", ("bns", "bnss")),
        ("bns", ("ndps", "bnss")),
        ("bnss", ("ndps", "bns")),
    ],
)
def test_one_law_routes_hydrate_only_that_act(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    law_id: str,
    others: tuple[str, ...],
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client = _client(tmp_path)
    _add_and_select(client, law_id, "1")
    assert law_id in hydrated
    for other in others:
        assert other not in hydrated
    for path in (law_path(law_id), sections_path(law_id), learn_path(law_id, "1")):
        clear_bare_act_cache()
        hydrated.clear()
        response = client.get(path)
        assert response.status_code == 200
        assert law_id in hydrated
        for other in others:
            assert other not in hydrated


def test_summary_counts_do_not_cartesian_inflate(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "demo", source_version="1", law_source_hash="tok")
    repo.replace_selection(
        LOCAL_USER_ID,
        "demo",
        [
            ("demo:section:1", "1", "h1"),
            ("demo:section:2", "1", "h2"),
            ("demo:section:3", "1", "h3"),
        ],
    )
    _insert_progress(
        repo.conn,
        LOCAL_USER_ID,
        "demo",
        "demo:section:1",
        next_revision="2026-09-10",
    )
    _insert_progress(
        repo.conn,
        LOCAL_USER_ID,
        "demo",
        "demo:section:2",
        next_revision="2026-09-20",
    )
    _insert_progress(
        repo.conn,
        LOCAL_USER_ID,
        "demo",
        "demo:section:4",
        next_revision="2026-09-01",
    )
    rows = repo.list_playground_summaries(
        LOCAL_USER_ID, as_of=date(2026, 9, 10)
    )
    assert len(rows) == 1
    summary = rows[0]
    assert summary.selected_count == 3
    assert summary.learned_count == 2
    assert summary.to_learn_count == 1
    assert summary.due_count == 1


def test_dashboard_summary_query_count_does_not_scale_with_laws(tmp_path: Path):
    def run(n: int) -> tuple[int, int]:
        repo = _sqlite_repo(tmp_path / f"n{n}")
        now = "2026-09-10T00:00:00+00:00"
        uid = str(LOCAL_USER_ID)
        repo.conn.executemany(
            """
            INSERT INTO user_playground_item (
                user_id, law_id, status, added_at, last_activity_at,
                source_version, law_source_hash
            ) VALUES (?, ?, 'in_playground', ?, ?, '1', 'tok')
            """,
            [(uid, f"law-{i}", now, now) for i in range(n)],
        )
        repo.conn.executemany(
            """
            INSERT INTO user_playground_selection (
                user_id, law_id, source_locator, selected_at,
                source_version, source_hash
            ) VALUES (?, ?, ?, ?, '1', 'h')
            """,
            [
                (uid, "law-0", f"law-0:section:{i}", now)
                for i in range(3)
            ],
        )
        repo.conn.commit()
        _insert_progress(repo.conn, LOCAL_USER_ID, "law-0", "law-0:section:0")
        _insert_progress(repo.conn, LOCAL_USER_ID, "law-0", "law-0:section:1")
        probe = _ExecuteProbe(repo.conn)
        repo.conn = probe
        summaries = repo.list_playground_summaries(
            LOCAL_USER_ID, as_of=date(2026, 9, 10)
        )
        assert len(summaries) == n
        law0 = next(row for row in summaries if row.law_id == "law-0")
        assert law0.selected_count == 3
        assert law0.learned_count == 2
        return len(probe.execute_sql), len(probe.executemany_sql)

    count_3, many_3 = run(3)
    count_30, many_30 = run(30)
    assert count_3 == count_30 == 1
    assert many_3 == many_30 == 0


def test_sqlite_replace_selection_uses_one_executemany(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "demo", source_version="1", law_source_hash="tok")
    probe = _ExecuteProbe(repo.conn)
    repo.conn = probe
    rows = [(f"demo:section:{i}", "1", f"h{i}") for i in range(12)]
    repo.replace_selection(LOCAL_USER_ID, "demo", rows)
    insert_executes = [
        sql for sql in probe.execute_sql if "INSERT INTO user_playground_selection" in sql
    ]
    assert insert_executes == []
    assert len(probe.executemany_sql) == 1
    assert probe.executemany_rowcounts == [12]
    assert any("DELETE FROM user_playground_selection" in sql for sql in probe.execute_sql)
    assert probe._inner.execute(
        "SELECT COUNT(*) AS n FROM user_playground_selection"
    ).fetchone()["n"] == 12


def test_postgres_replace_selection_batches_inserts():
    cursor = _PostgresSpyCursor()
    conn = _PostgresSpyConn(cursor)
    repo = PostgresPlaygroundRepository(_PostgresSpyPool(conn))
    rows = [(f"bnss:section:{i}", "1", f"h{i}") for i in range(20)]
    repo.replace_selection(LOCAL_USER_ID, "bnss", rows)
    assert conn.commits == 1
    assert len(cursor.executemany_sql) == 1
    assert cursor.executemany_rowcounts == [20]
    assert any("DELETE FROM user_playground_selection" in sql for sql in cursor.execute_sql)
    assert not any("INSERT INTO user_playground_selection" in sql for sql in cursor.execute_sql)


def test_postgres_list_playground_summaries_is_one_query():
    cursor = _PostgresSpyCursor()
    conn = _PostgresSpyConn(cursor)
    repo = PostgresPlaygroundRepository(_PostgresSpyPool(conn))
    assert repo.list_playground_summaries(LOCAL_USER_ID, as_of=date(2026, 9, 10)) == []
    assert len(cursor.execute_sql) == 1
    assert "selected_count" in cursor.execute_sql[0]
    assert "learned_count" in cursor.execute_sql[0]


def test_entire_act_selection_hydrates_only_that_law(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client = _client(tmp_path)
    assert client.post(add_path("ndps"), follow_redirects=False).status_code == 303
    hydrated.clear()
    clear_bare_act_cache()
    saved = client.post(
        sections_path("ndps"),
        data={"entire": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert "ndps" in hydrated
    assert "bns" not in hydrated
    assert "bnss" not in hydrated
    selected = client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    assert len(selected) > 10


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
