"""Milestone 9: source integrity and amendment review.

Cheap registry identity on home. Targeted one-Act comparison of user-relevant
section hashes. Historical learning rows are never rewritten.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.playground.db import SCHEMA_SQL
from constitution_memorizer.playground.eligibility import playground_law_source_identity
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.playground.locators import parse_locator, section_locator
from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
from constitution_memorizer.playground.source import hash_payload, source_hash
from constitution_memorizer.playground.source_review import (
    CHANGE_KIND_CHANGED,
    CHANGE_KIND_MISSING,
    CHANGE_KIND_OMITTED,
    STATUS_PENDING,
    STATUS_REVIEWED,
    StaleSourceReviewError,
    detect_source_changes,
    historical_section_identity,
    is_law_registry_outdated,
    provenance_lines,
)
from constitution_memorizer.playground.urls import (
    law_path,
    learn_path,
    roster_next_path,
    roster_path,
    source_review_path,
    source_review_reviewed_path,
    source_review_section_path,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.bare_acts import BARE_ACTS, clear_bare_act_cache, get_bare_act
from tests.test_playground import _add_and_select, _add_law, _client, _hydrate_spy, _sqlite_repo
from tests.test_playground_m8 import TODAY, _complete_six, _seed_progress
from tests.test_roster_m5a import NOW, USER, _authed_client, _confirm_add, _subscribe

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
MODES = PLAYGROUND_LEARN_MODES


def _complete_six_hashed(repo, user_id, law_id, locator, digest, *, as_of: date, version: str = "1") -> None:
    for mode in MODES:
        repo.complete_mode(
            user_id,
            law_id,
            locator,
            mode,
            source_version=version,
            source_hash=digest,
            as_of=as_of,
        )


class _ActProxy:
    def __init__(self, act, *, mutate=None, missing=None, omit=None):
        self._act = act
        self._mutate = mutate or {}
        self._missing = {str(n) for n in (missing or ())}
        self._omit = {str(n) for n in (omit or ())}

    def section(self, number):
        key = str(number)
        if key in self._missing:
            return None
        section = self._act.section(number)
        if section is None:
            return None
        if key in self._omit:
            return replace(section, status="omitted")
        if key in self._mutate:
            return replace(section, **self._mutate[key])
        return section

    def __getattr__(self, name):
        return getattr(self._act, name)


def _stale_registry(monkeypatch, law_id="ndps", version="2", token="tok-v2"):
    spec = BARE_ACTS[law_id]
    monkeypatch.setitem(
        BARE_ACTS,
        law_id,
        replace(spec, source_version=version, source_hash=token),
    )
    clear_bare_act_cache()


def _patch_act(monkeypatch, law_id, **kwargs):
    real = get_bare_act

    def wrapped(slug, *args, **inner):
        act = real(slug, *args, **inner) if args or inner else real(slug)
        if slug != law_id or act is None:
            return act
        return _ActProxy(act, **kwargs)

    monkeypatch.setattr(bare_acts, "get_bare_act", wrapped)


def _learning_snapshot(repo, uid, law_id, locator):
    progress = repo.get_progress(uid, law_id, locator)
    modes = [
        (row.mode, row.status, row.source_hash, row.source_version)
        for row in repo.list_mode_progress(uid, law_id, locator)
    ]
    revs = [
        (row.mode, row.rung_days, row.status, row.source_hash)
        for row in repo.list_revision_mode_progress(uid, law_id, locator)
    ]
    selection = [
        (row.source_hash, row.source_version)
        for row in repo.list_selection(uid, law_id)
        if row.source_locator == locator
    ]
    item = repo.get_item(uid, law_id)
    return (
        None
        if progress is None
        else (
            progress.status,
            progress.times_completed,
            progress.interval_days,
            progress.next_revision,
            progress.source_hash,
            progress.source_version,
            progress.learned_at,
        ),
        modes,
        revs,
        selection,
        None if item is None else (item.source_version, item.law_source_hash),
    )


def test_alembic_0027_parent_one_head_rls_and_sqlite_parity():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]
    rev = script.get_revision(EXPECTED_HEAD)
    assert rev.down_revision == "20260925_0026"
    path = ROOT / "alembic" / "versions" / "20260927_0027_playground_source_changes.py"
    text = path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(path))
    assert "user_playground_source_change" in text
    assert "user_playground_source_scan" in text
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "changed', 'missing', 'omitted'" in text or "changed', 'missing'" in text
    assert "pending" in text and "reviewed" in text
    assert "current_source_version" in text
    assert "current_law_source_hash" in text
    assert "user_playground_source_change" in SCHEMA_SQL
    assert "CHECK (change_kind IN ('changed', 'missing', 'omitted'))" in SCHEMA_SQL


def test_identity_layers_locator_version_token_and_section_hash():
    loc = section_locator("ndps", "8")
    assert loc.value == "ndps:section:8"
    assert parse_locator(loc.value).number == "8"
    identity = playground_law_source_identity("ndps")
    spec = BARE_ACTS["ndps"]
    assert identity.source_version == spec.source_version
    assert identity.identity_token == (spec.source_hash or spec.filename)
    assert spec.source_hash is None
    assert identity.identity_token == spec.filename
    section = get_bare_act("ndps").section("1")
    digest = source_hash(section)
    assert digest == source_hash(section)
    mutated = replace(section, title=section.title + " amended")
    assert source_hash(mutated) != digest
    assert "\n" in hash_payload(section)


def test_cheap_same_identity_does_not_hydrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _sqlite_repo(tmp_path)
    identity = playground_law_source_identity("ndps")
    loc = "ndps:section:1"
    repo.add_item(
        LOCAL_USER_ID,
        "ndps",
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(loc, "1", "h")])
    hydrated = _hydrate_spy(monkeypatch)
    summary = detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    assert summary.hydrated is False
    assert summary.registry_outdated is False
    assert hydrated == []


def test_cheap_changed_identity_home_zero_hydration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    assert _add_law(client, "ndps").status_code == 303
    _stale_registry(monkeypatch)
    hydrated = _hydrate_spy(monkeypatch)
    page = client.get("/playground")
    assert page.status_code == 200
    assert "Law updated" in page.text
    assert "Review affected provisions" in page.text
    assert "progress is invalid" not in page.text.lower()
    assert "start over" not in page.text.lower()
    assert hydrated == []
    roster = client.get(roster_path())
    next_page = client.get(roster_next_path())
    assert roster.status_code == 200
    assert next_page.status_code == 200
    assert hydrated == []


def test_targeted_scan_changed_unchanged_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _sqlite_repo(tmp_path)
    identity = playground_law_source_identity("ndps")
    repo.add_item(
        LOCAL_USER_ID,
        "ndps",
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )
    act = get_bare_act("ndps")
    a = "ndps:section:1"
    b = "ndps:section:2"
    c = "ndps:section:3"
    live_a = source_hash(act.section("1"))
    live_b = source_hash(act.section("2"))
    live_c = source_hash(act.section("3"))
    repo.replace_selection(
        LOCAL_USER_ID,
        "ndps",
        [(a, "1", live_a), (b, "1", live_b), (c, "1", live_c)],
    )
    _complete_six_hashed(repo, LOCAL_USER_ID, "ndps", a, live_a, as_of=TODAY)
    _complete_six_hashed(repo, LOCAL_USER_ID, "ndps", b, live_b, as_of=TODAY)
    _stale_registry(monkeypatch)
    _patch_act(
        monkeypatch,
        "ndps",
        mutate={"1": {"title": act.section("1").title + " (amended)"}},
        missing=("3",),
    )
    hydrated = _hydrate_spy(monkeypatch)
    summary = detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    assert summary.hydrated is True
    assert hydrated == ["ndps"]
    kinds = {row.source_locator: row.change_kind for row in summary.changes}
    assert kinds[a] == CHANGE_KIND_CHANGED
    assert b not in kinds
    assert kinds[c] == CHANGE_KIND_MISSING
    assert summary.unchanged_user_relevant_count == 1
    assert summary.missing_count == 1
    again = detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    assert len(again.changes) == len(summary.changes)


def test_unchanged_and_changed_preserve_learning_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _sqlite_repo(tmp_path)
    identity = playground_law_source_identity("ndps")
    repo.add_item(
        LOCAL_USER_ID,
        "ndps",
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )
    act = get_bare_act("ndps")
    loc = "ndps:section:1"
    live = source_hash(act.section("1"))
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(loc, "1", live)])
    _complete_six_hashed(repo, LOCAL_USER_ID, "ndps", loc, live, as_of=TODAY)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="review",
        interval_days=15,
        next_revision=TODAY.isoformat(),
        times_completed=4,
        learned_at=TODAY.isoformat(),
        last_completed=TODAY.isoformat(),
    )
    for mode in MODES[:3]:
        repo.complete_revision_mode_and_advance_if_ready(
            LOCAL_USER_ID,
            "ndps",
            loc,
            mode,
            source_version="v",
            source_hash="h",
            as_of=TODAY,
            claimed_rung=15,
        )
    before = _learning_snapshot(repo, LOCAL_USER_ID, "ndps", loc)
    _stale_registry(monkeypatch)
    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    assert _learning_snapshot(repo, LOCAL_USER_ID, "ndps", loc) == before
    _patch_act(
        monkeypatch,
        "ndps",
        mutate={"1": {"title": act.section("1").title + " x"}},
    )
    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    after = _learning_snapshot(repo, LOCAL_USER_ID, "ndps", loc)
    assert after == before
    rows = repo.list_source_changes(LOCAL_USER_ID, "ndps")
    assert rows
    assert rows[0].status == STATUS_PENDING
    progress = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert progress.interval_days == 15
    assert progress.next_revision == TODAY.isoformat()


def test_reviewed_does_not_touch_learning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _sqlite_repo(tmp_path)
    identity = playground_law_source_identity("ndps")
    repo.add_item(
        LOCAL_USER_ID,
        "ndps",
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )
    act = get_bare_act("ndps")
    loc = "ndps:section:1"
    live = source_hash(act.section("1"))
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(loc, "1", live)])
    _complete_six_hashed(repo, LOCAL_USER_ID, "ndps", loc, live, as_of=TODAY)
    _stale_registry(monkeypatch)
    _patch_act(
        monkeypatch,
        "ndps",
        mutate={"1": {"title": act.section("1").title + " y"}},
    )
    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    before = _learning_snapshot(repo, LOCAL_USER_ID, "ndps", loc)
    from constitution_memorizer.playground.source_review import mark_source_change_reviewed

    new_id = playground_law_source_identity("ndps")
    row = mark_source_change_reviewed(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        detected_source_version=new_id.source_version,
        detected_law_source_hash=new_id.identity_token,
    )
    assert row.status == STATUS_REVIEWED
    assert row.reviewed_at
    assert _learning_snapshot(repo, LOCAL_USER_ID, "ndps", loc) == before


def test_stale_review_does_not_mark_newer_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _sqlite_repo(tmp_path)
    identity = playground_law_source_identity("ndps")
    repo.add_item(
        LOCAL_USER_ID,
        "ndps",
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )
    act = get_bare_act("ndps")
    loc = "ndps:section:1"
    live = source_hash(act.section("1"))
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(loc, "1", live)])
    _complete_six_hashed(repo, LOCAL_USER_ID, "ndps", loc, live, as_of=TODAY)
    _stale_registry(monkeypatch, version="2", token="tok-v2")
    _patch_act(
        monkeypatch,
        "ndps",
        mutate={"1": {"title": act.section("1").title + " z"}},
    )
    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    _stale_registry(monkeypatch, version="3", token="tok-v3")
    from constitution_memorizer.playground.source_review import mark_source_change_reviewed

    with pytest.raises(StaleSourceReviewError):
        mark_source_change_reviewed(
            repo,
            LOCAL_USER_ID,
            "ndps",
            loc,
            detected_source_version="2",
            detected_law_source_hash="tok-v2",
        )
    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    v2 = repo.get_source_change(
        LOCAL_USER_ID,
        "ndps",
        loc,
        current_source_version="2",
        current_law_source_hash="tok-v2",
    )
    v3 = repo.get_source_change(
        LOCAL_USER_ID,
        "ndps",
        loc,
        current_source_version="3",
        current_law_source_hash="tok-v3",
    )
    assert v2 is not None and v2.status == STATUS_PENDING
    assert v3 is not None and v3.status == STATUS_PENDING


def test_workspace_and_review_ux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    repo = client.app.state.playground
    loc = "ndps:section:1"
    live = source_hash(get_bare_act("ndps").section("1"))
    _complete_six_hashed(repo, LOCAL_USER_ID, "ndps", loc, live, as_of=TODAY)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="mastered",
        interval_days=60,
        next_revision=None,
        times_completed=6,
        learned_at=TODAY.isoformat(),
    )
    act = get_bare_act("ndps")
    _stale_registry(monkeypatch)
    _patch_act(
        monkeypatch,
        "ndps",
        mutate={"1": {"title": act.section("1").title + " new"}},
    )
    page = client.get(law_path("ndps"))
    assert page.status_code == 200
    assert "Law updated" in page.text
    assert "learned provision changed" in page.text
    assert "Review affected provisions" in page.text
    assert "Mastered" in page.text
    assert "progress lost" not in page.text.lower()
    review = client.get(source_review_path("ndps"))
    assert review.status_code == 200
    assert "Source version" in review.text
    assert "Gazette" not in review.text
    assert "Ministry" not in review.text
    assert "Changed since you learned it" in review.text
    detail = client.get(source_review_section_path("ndps", "1"))
    assert detail.status_code == 200
    assert "VERBATIM TEXT" in detail.text
    assert "This provision has changed since your recorded learning source." in detail.text
    assert "Old wording" not in detail.text
    token = client.cookies.get("rtc_csrf") or ""
    identity = playground_law_source_identity("ndps")
    posted = client.post(
        source_review_reviewed_path("ndps", "1"),
        data={
            "csrf_token": token,
            "detected_source_version": identity.source_version,
            "detected_law_source_hash": identity.identity_token,
        },
        follow_redirects=False,
    )
    assert posted.status_code == 303
    after = client.get(source_review_path("ndps"))
    assert "All updates reviewed" in after.text
    progress = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert progress.status == "mastered"


def test_missing_section_learn_redirects_to_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    _stale_registry(monkeypatch)
    _patch_act(monkeypatch, "ndps", missing=("1",))
    detect_source_changes(client.app.state.playground, LOCAL_USER_ID, "ndps")
    page = client.get(learn_path("ndps", "1", "read"), follow_redirects=False)
    assert page.status_code == 303
    assert "source-review" in page.headers.get("location", "")
    review = client.get(source_review_section_path("ndps", "1"))
    assert "No longer present in the current source" in review.text
    assert "Revise" not in review.text


def test_zero_affected_after_scan_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    _stale_registry(monkeypatch)
    page = client.get(law_path("ndps"))
    assert page.status_code == 200
    assert "Your learned provisions are unchanged" in page.text
    assert "3 learned provisions changed" not in page.text
    home = client.get("/playground")
    assert "Law updated ·" not in home.text or "affected" not in home.text


def test_generic_second_act_and_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _sqlite_repo(tmp_path)
    identity = playground_law_source_identity("bns")
    repo.add_item(
        LOCAL_USER_ID,
        "bns",
        source_version=identity.source_version,
        law_source_hash=identity.identity_token,
    )
    act = get_bare_act("bns")
    loc = "bns:section:1"
    live = source_hash(act.section("1"))
    repo.replace_selection(LOCAL_USER_ID, "bns", [(loc, "1", live)])
    _complete_six_hashed(repo, LOCAL_USER_ID, "bns", loc, live, as_of=TODAY)
    _stale_registry(monkeypatch, law_id="bns", token="bns-v2")
    _patch_act(monkeypatch, "bns", omit=("1",))
    summary = detect_source_changes(repo, LOCAL_USER_ID, "bns")
    assert summary.changes[0].change_kind == CHANGE_KIND_OMITTED
    assert summary.hydrated is True


def test_amendment_does_not_consume_second_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {303, 200}
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    cap = client.app.state.roster.capacity(USER, snap, now=NOW)
    used = cap.used
    rows = client.app.state.roster.active_roster_items(USER, now=NOW)
    assert [row.law_id for row in rows] == ["ndps"]
    _stale_registry(monkeypatch)
    cap2 = client.app.state.roster.capacity(USER, snap, now=NOW)
    assert cap2.used == used
    rows2 = client.app.state.roster.active_roster_items(USER, now=NOW)
    assert [row.law_id for row in rows2] == ["ndps"]


def test_today_calendar_zero_hydration_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    _stale_registry(monkeypatch)
    hydrated = _hydrate_spy(monkeypatch)
    today = client.get("/dashboard")
    calendar = client.get("/calendar")
    home = client.get("/playground")
    roster = client.get(roster_path())
    assert today.status_code == 200
    assert calendar.status_code == 200
    assert home.status_code == 200
    assert roster.status_code == 200
    assert hydrated == []
    clear_bare_act_cache()
    hydrated.clear()
    review = client.get(source_review_path("ndps"))
    assert review.status_code == 200
    assert hydrated == ["ndps"]


def test_inactive_law_blocks_source_review(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    token = client.cookies.get("rtc_csrf") or ""
    client.post(
        "/playground/roster/ndps/remove",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    page = client.get(source_review_path("ndps"))
    assert page.status_code == 200
    assert "Changed since you learned it" not in page.text
    assert "Mark reviewed" not in page.text


def test_filename_fallback_not_labelled_sha():
    lines = provenance_lines("ndps")
    assert lines == ("Source version 1",)
    joined = " ".join(lines).lower()
    assert "sha" not in joined
    assert "gazette" not in joined


def test_historical_identity_prefers_revision_then_mode():
    from constitution_memorizer.playground.source_review import HistoricalSectionIdentity

    picked = historical_section_identity(
        [
            HistoricalSectionIdentity("l", "1", "sel", "selection", "2026-01-01"),
            HistoricalSectionIdentity("l", "1", "mode", "mode", "2026-02-01"),
            HistoricalSectionIdentity("l", "1", "rev", "revision_mode", "2026-02-01"),
        ]
    )
    assert picked.origin == "revision_mode"
    assert picked.source_hash == "rev"
    later_select = historical_section_identity(
        [
            HistoricalSectionIdentity("l", "1", "sel", "selection", "2026-09-01"),
            HistoricalSectionIdentity("l", "1", "rev", "revision_mode", "2026-02-01"),
        ]
    )
    assert later_select.origin == "revision_mode"


def test_amendment_carry_forward_one_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from tests.test_roster_m5b import OCT_1, SEP_25, _consume, _has, _open, _snap

    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)
    assert roster.capacity(USER, snap, now=SEP_25).used == 1
    _stale_registry(monkeypatch)
    roster.ensure_current_period(USER, snap, now=OCT_1)
    plan = roster.get_rollover_plan(
        USER, snap, has_overlay=lambda law: _has(overlay, USER, law), now=OCT_1
    )
    assert [row.law_id for row in plan.candidates] == ["ndps"]
    kept = roster.confirm_carry_forward(
        USER,
        ["ndps"],
        [],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert kept.ok
    assert kept.used == 1
    current = [
        row.law_id
        for row in roster.get_current_roster(USER, now=OCT_1)
        if row.consumed_at is not None and row.removed_at is None and row.declined_at is None
    ]
    assert current == ["ndps"]


def test_batch_home_source_state_is_not_n_plus_one():
    from constitution_memorizer.playground.source_review import batch_source_presentations

    src = inspect.getsource(batch_source_presentations)
    assert "list_source_scans" in src
    assert "list_source_changes" in src
    assert "list_items" in src
    assert "get_source_scan" not in src
    assert "get_item" not in src


def test_postgres_source_upsert_uses_on_conflict():
    src = inspect.getsource(PostgresPlaygroundRepository.upsert_source_change)
    assert "ON CONFLICT" in src
    sqlite = inspect.getsource(SqlitePlaygroundRepository.upsert_source_change)
    assert "ON CONFLICT" in sqlite


def test_no_progress_lost_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    _stale_registry(monkeypatch)
    for path in ("/playground", law_path("ndps"), source_review_path("ndps")):
        text = client.get(path).text.lower()
        assert "progress is invalid" not in text
        assert "learning deleted" not in text
        assert "start over" not in text
