"""T16 / WS9 N+1 scaling locks, T17 repeated zero-hydration + Halted-home, and T22 / WS12 observability + privacy consolidation.

Integer query counts, path groups, counters, notes, and privacy locks only; no millisecond asserts.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from constitution_memorizer.playground.benchmarking import (
    BENCH_USER,
    HydrationProbe,
    NPLUSONE_LOCATORS_PER_LAW,
    NPLUSONE_ROSTER_SIZES,
    PLAYGROUND_TEST_NOW,
    build_due_heavy_fixture,
    build_nplusone_fixture,
    create_benchmark_app,
    sign_in_benchmark_client,
    synthetic_law_ids,
)
from constitution_memorizer.playground.eligibility import PlaygroundLawIdentity
from constitution_memorizer.playground.roster.period import playground_month_bounds
from constitution_memorizer.playground.service import activate_law
from constitution_memorizer.web.bare_acts import (
    BareActSpec,
    clear_bare_act_cache,
    get_bare_act,
)
from constitution_memorizer.web.request_context import get_last_request_performance
from tests.test_playground import _hydrate_spy

HOME_PATH = "/playground"
TODAY_PATH = "/dashboard"
CALENDAR_PATH = "/calendar?year=2026&month=9"
_SYN_RE = re.compile(r"^syn-[1-9][0-9]*$")
_SPY_METHODS = (
    "list_playground_summaries",
    "list_source_scans",
    "list_source_changes",
    "get_item",
    "get_source_scan",
    "list_due_revisions",
    "list_revision_schedule",
    "list_revision_mode_progress",
)


def _is_syn(law_id: str) -> bool:
    return bool(_SYN_RE.fullmatch(str(law_id or "")))


def install_nplusone_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze Playground/entitlement clocks independently of T13's sticky installer."""

    from constitution_memorizer.entitlements import service as entitlement_service
    from constitution_memorizer.playground.roster import period as period_mod

    real_period_utc = period_mod._as_utc
    real_ent_utc = entitlement_service._utc

    def frozen_period_utc(now):
        return real_period_utc(now or PLAYGROUND_TEST_NOW)

    def frozen_ent_utc(now):
        return real_ent_utc(now or PLAYGROUND_TEST_NOW)

    monkeypatch.setattr(period_mod, "_as_utc", frozen_period_utc)
    monkeypatch.setattr(entitlement_service, "_utc", frozen_ent_utc)


def install_nplusone_eligibility(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test-local syn-* eligibility. Does not change production eligibility."""

    from constitution_memorizer.playground import (
        access,
        eligibility,
        locators,
        service,
        source,
        source_review,
        view,
    )
    from constitution_memorizer.playground.roster import service as roster_service

    real_eligible = eligibility.is_playground_eligible_law
    real_spec = eligibility.playground_bare_act_spec
    real_identity = eligibility.playground_law_source_identity

    def eligible(law_id: str) -> bool:
        return _is_syn(law_id) or real_eligible(law_id)

    def spec(law_id: str):
        if _is_syn(law_id):
            n = law_id.split("-", 1)[1]
            return BareActSpec(
                slug=law_id,
                filename=f"{law_id}.json",
                short_name=f"Synthetic fixture {n}",
                back_label=f"← Syn {n}",
                short_title=f"Syn {n}",
                source_version="stub",
                source_hash="stub",
            )
        return real_spec(law_id)

    def identity(law_id: str):
        if _is_syn(law_id):
            fake = spec(law_id)
            return PlaygroundLawIdentity(
                law_id=fake.slug,
                source_version=fake.source_version,
                identity_token=fake.source_hash or fake.filename,
            )
        return real_identity(law_id)

    for mod, name, fn in (
        (eligibility, "is_playground_eligible_law", eligible),
        (eligibility, "playground_bare_act_spec", spec),
        (eligibility, "playground_law_source_identity", identity),
        (view, "is_playground_eligible_law", eligible),
        (view, "playground_law_source_identity", identity),
        (locators, "is_playground_eligible_law", eligible),
        (access, "is_playground_eligible_law", eligible),
        (service, "is_playground_eligible_law", eligible),
        (source, "is_playground_eligible_law", eligible),
        (roster_service, "is_playground_eligible_law", eligible),
        (source_review, "playground_bare_act_spec", spec),
        (source_review, "playground_law_source_identity", identity),
    ):
        monkeypatch.setattr(mod, name, fn)


class OverlayMethodSpy:
    """Test-only outermost-method spy. Not a production counter."""

    def __init__(self, repo: Any) -> None:
        self.repo = repo
        self.calls: Counter[str] = Counter()
        self.events: list[tuple[str, tuple, dict]] = []
        self._originals: dict[str, Any] = {}

    def install(self) -> OverlayMethodSpy:
        for name in _SPY_METHODS:
            original = getattr(self.repo, name)
            self._originals[name] = original
            setattr(self.repo, name, self._wrap(name, original))
        return self

    def _wrap(self, name: str, original):
        def wrapped(*args, **kwargs):
            self.calls[name] += 1
            self.events.append((name, args, kwargs))
            return original(*args, **kwargs)

        wrapped.__name__ = name
        return wrapped

    def reset(self) -> None:
        self.calls = Counter()
        self.events = []

    def snapshot(self) -> dict[str, Any]:
        return {"calls": dict(self.calls), "events": list(self.events)}

    def restore(self) -> None:
        for name, original in self._originals.items():
            setattr(self.repo, name, original)


def _counter(snap, name: str) -> int:
    return int((snap.counters or {}).get(name, 0))


_CARD_MEMBERSHIP_RE = re.compile(
    r'data-law-id="(syn-[1-9][0-9]*)" data-membership="([^"]+)"'
)


def _home_cards(html: str) -> list[tuple[str, str]]:
    return list(dict.fromkeys(_CARD_MEMBERSHIP_RE.findall(html)))


def _positional_or_kw(args: tuple, kwargs: dict, index: int, key: str):
    if key in kwargs:
        return kwargs[key]
    if len(args) > index:
        return args[index]
    return None


def _source_scan_sizes(events: list[tuple[str, tuple, dict]]) -> list[int]:
    sizes: list[int] = []
    for name, args, kwargs in events:
        if name != "list_source_scans":
            continue
        law_ids = _positional_or_kw(args, kwargs, 1, "law_ids") or ()
        sizes.append(len(list(law_ids)))
    return sizes


def _source_change_split(events: list[tuple[str, tuple, dict]]) -> tuple[int, int, list[int]]:
    batched = 0
    per_law = 0
    sizes: list[int] = []
    for name, args, kwargs in events:
        if name != "list_source_changes":
            continue
        law_ids = kwargs.get("law_ids")
        law_id = kwargs.get("law_id")
        if law_id is None and "law_id" not in kwargs and len(args) >= 2:
            law_id = args[1]
        if law_ids:
            batched += 1
            sizes.append(len(list(law_ids)))
        elif law_id:
            per_law += 1
        else:
            per_law += 1
    return batched, per_law, sizes


def _validate_fixture(app, info: dict[str, Any], n: int) -> None:
    assert info["roster_count"] == n
    assert info["law_ids"] == list(synthetic_law_ids(n))
    start, _end = playground_month_bounds(PLAYGROUND_TEST_NOW)
    roster_rows = app.state.roster._repo.list_items(BENCH_USER, start)
    assert len(roster_rows) == n
    overlay = app.state.playground
    assert len(overlay.list_items(BENCH_USER)) == n
    active = app.state.roster.active_roster_items(BENCH_USER)
    assert len(active) == n
    assert {item.law_id for item in active} == set(info["law_ids"])
    due = overlay.list_due_revisions(
        BENCH_USER, PLAYGROUND_TEST_NOW.date(), list(info["law_ids"])
    )
    expected_due = n * NPLUSONE_LOCATORS_PER_LAW
    assert len(due) == expected_due, (
        f"fixture N={n} due facts {len(due)} != {expected_due}"
    )
    pending = overlay.list_source_changes(
        BENCH_USER, law_ids=list(info["law_ids"]), status="pending"
    )
    pending_laws = {row.law_id for row in pending}
    assert pending_laws == set(info["law_ids"]), (
        f"fixture N={n} pending source-change laws {sorted(pending_laws)}"
    )


def _abort_hidden_fallback(
    n: int, cards: list[tuple[str, str]], html: str
) -> None:
    expected = set(synthetic_law_ids(n))
    card_ids = [law_id for law_id, _membership in cards]
    memberships = {law_id: membership for law_id, membership in cards}
    if (
        set(card_ids) == expected
        and len(card_ids) == n
        and all(memberships[law_id] == "in_playground" for law_id in expected)
    ):
        return
    realish = sorted(
        {
            match.group(1)
            for match in re.finditer(r'data-law-id="([a-z0-9-]+)"', html)
        }
    )
    pytest.fail(
        "T16 eligibility/catalogue patch failed to expose synthetic laws on "
        f"home; refusing a hidden fallback. N={n} expected {sorted(expected)}, "
        f"syn cards={card_ids}, memberships={memberships}, "
        f"all data-law-id={realish}"
    )


async def _measure_n(tmp_path: Path, n: int) -> dict[str, Any]:
    db = tmp_path / f"t16-n{n}.db"
    app = create_benchmark_app(db)
    seed_probe = HydrationProbe()
    seed_probe.install()
    try:
        info = build_nplusone_fixture(app, n)
    finally:
        seed_probe.remove()
    assert seed_probe.calls == 0, (
        f"T16 fixture N={n} hydrated Bare Acts {seed_probe.calls} time(s)"
    )
    _validate_fixture(app, info, n)
    expected_due = n * NPLUSONE_LOCATORS_PER_LAW
    spy = OverlayMethodSpy(app.state.playground).install()
    http_probe = HydrationProbe()
    http_probe.install()
    routes = {
        "home": HOME_PATH,
        "today": TODAY_PATH,
        "calendar": CALENDAR_PATH,
    }
    measured: dict[str, Any] = {}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            for label, path in routes.items():
                spy.reset()
                warmup = await client.get(path)
                assert warmup.status_code == 200, (
                    f"N={n} {label} warmup HTTP {warmup.status_code}"
                )
                spy.reset()
                response = await client.get(path)
                snap = get_last_request_performance()
                assert response.status_code == 200, (
                    f"N={n} {label} measured HTTP {response.status_code}"
                )
                assert snap is not None, f"N={n} {label} missing request snapshot"
                measured[label] = {
                    "path": path,
                    "html": response.text,
                    "snap": snap,
                    "spy": spy.snapshot(),
                }
    finally:
        http_probe.remove()
        spy.restore()
    assert http_probe.calls == 0, (
        f"T16 HTTP cells N={n} hydrated Bare Acts {http_probe.calls} time(s)"
    )
    home_cards = _home_cards(measured["home"]["html"])
    _abort_hidden_fallback(n, home_cards, measured["home"]["html"])
    return {
        "n": n,
        "expected_due": expected_due,
        "home_cards": home_cards,
        "hydration": http_probe.calls,
        **measured,
    }


def _run_all(tmp_path: Path) -> list[dict[str, Any]]:
    async def _go():
        return [await _measure_n(tmp_path, n) for n in NPLUSONE_ROSTER_SIZES]

    return asyncio.run(_go())


def _assert_constant_across_n(rows: list[dict[str, Any]], route: str, name: str) -> list[int]:
    values = [_counter(row[route]["snap"], name) for row in rows]
    assert values[0] == values[1] == values[2], (
        f"{route} {name} must be equal at N=1/10/30, got {values}"
    )
    return values


@pytest.fixture(scope="module")
def nplusone_rows(tmp_path_factory) -> list[dict[str, Any]]:
    mp = pytest.MonkeyPatch()
    install_nplusone_clock(mp)
    install_nplusone_eligibility(mp)
    try:
        tmp_path = tmp_path_factory.mktemp("t16")
        return _run_all(tmp_path)
    finally:
        mp.undo()


def test_home_summary_and_source_review_are_batched(nplusone_rows):
    round_trips = []
    db_reads = []
    for row in nplusone_rows:
        n = row["n"]
        snap = row["home"]["snap"]
        spy = row["home"]["spy"]
        calls = spy["calls"]
        events = spy["events"]
        assert snap.path_group == "/playground"
        assert _counter(snap, "playground_summary_reads") == 1
        assert calls.get("list_playground_summaries", 0) == 1
        scan_sizes = _source_scan_sizes(events)
        assert calls.get("list_source_scans", 0) == 1
        assert scan_sizes == [n]
        batched, per_law, change_sizes = _source_change_split(events)
        assert batched == 1
        assert per_law == 0
        assert change_sizes == [n]
        assert calls.get("get_item", 0) == 0
        assert calls.get("get_source_scan", 0) == 0
        assert _counter(snap, "bare_act_cache_misses") == 0
        round_trips.append(_counter(snap, "playground_repo_round_trips"))
        db_reads.append(_counter(snap, "playground_db_reads"))
    assert round_trips[0] == round_trips[1] == round_trips[2], (
        f"home playground_repo_round_trips must be equal, got {round_trips}"
    )
    assert db_reads[0] == db_reads[1] == db_reads[2], (
        f"home playground_db_reads must be equal, got {db_reads}"
    )
    _assert_constant_across_n(nplusone_rows, "home", "playground_device_lookups")
    _assert_constant_across_n(nplusone_rows, "home", "playground_entitlement_resolves")
    _assert_constant_across_n(nplusone_rows, "home", "playground_source_review_reads")


def test_today_due_list_is_batched_revision_mode_is_linear(nplusone_rows):
    for row in nplusone_rows:
        n = row["n"]
        expected_due = row["expected_due"]
        snap = row["today"]["snap"]
        spy = row["today"]["spy"]
        calls = spy["calls"]
        assert snap.path_group == "/dashboard"
        assert calls.get("list_due_revisions", 0) == 1
        follow_up = calls.get("list_revision_mode_progress", 0)
        assert follow_up == expected_due, (
            f"Today N={n} list_revision_mode_progress={follow_up} "
            f"exceeds or misses due facts {expected_due}"
        )
        assert follow_up <= expected_due
        assert _counter(snap, "bare_act_cache_misses") == 0
    _assert_constant_across_n(nplusone_rows, "today", "playground_device_lookups")
    _assert_constant_across_n(nplusone_rows, "today", "playground_entitlement_resolves")
    due_calls = [
        row["today"]["spy"]["calls"].get("list_due_revisions", 0)
        for row in nplusone_rows
    ]
    assert due_calls == [1, 1, 1]
    follow = [
        row["today"]["spy"]["calls"].get("list_revision_mode_progress", 0)
        for row in nplusone_rows
    ]
    assert follow == [4, 40, 120]


def test_calendar_schedule_is_batched_revision_mode_is_linear(nplusone_rows):
    for row in nplusone_rows:
        n = row["n"]
        expected_due = row["expected_due"]
        snap = row["calendar"]["snap"]
        spy = row["calendar"]["spy"]
        calls = spy["calls"]
        assert snap.path_group == "/calendar"
        assert calls.get("list_revision_schedule", 0) == 1
        follow_up = calls.get("list_revision_mode_progress", 0)
        assert follow_up == expected_due, (
            f"Calendar N={n} list_revision_mode_progress={follow_up} "
            f"exceeds or misses due facts {expected_due}"
        )
        assert follow_up <= expected_due
        assert _counter(snap, "bare_act_cache_misses") == 0
    _assert_constant_across_n(nplusone_rows, "calendar", "playground_device_lookups")
    _assert_constant_across_n(
        nplusone_rows, "calendar", "playground_entitlement_resolves"
    )
    schedule_calls = [
        row["calendar"]["spy"]["calls"].get("list_revision_schedule", 0)
        for row in nplusone_rows
    ]
    assert schedule_calls == [1, 1, 1]
    follow = [
        row["calendar"]["spy"]["calls"].get("list_revision_mode_progress", 0)
        for row in nplusone_rows
    ]
    assert follow == [4, 40, 120]


def test_device_and_entitlement_are_route_specific_not_global_one(nplusone_rows):
    homes = [
        _counter(row["home"]["snap"], "playground_device_lookups")
        for row in nplusone_rows
    ]
    todays = [
        _counter(row["today"]["snap"], "playground_device_lookups")
        for row in nplusone_rows
    ]
    calendars = [
        _counter(row["calendar"]["snap"], "playground_device_lookups")
        for row in nplusone_rows
    ]
    assert homes[0] == homes[1] == homes[2]
    assert todays[0] == todays[1] == todays[2]
    assert calendars[0] == calendars[1] == calendars[2]
    # T4 Plus/Pro home is inspect+ensure; Dashboard and Calendar inspect only.
    # Do not lock a global lookups == 1 across routes.
    assert homes[0] == 2
    assert todays[0] == 1
    assert calendars[0] == 1
    home_ent = [
        _counter(row["home"]["snap"], "playground_entitlement_resolves")
        for row in nplusone_rows
    ]
    today_ent = [
        _counter(row["today"]["snap"], "playground_entitlement_resolves")
        for row in nplusone_rows
    ]
    calendar_ent = [
        _counter(row["calendar"]["snap"], "playground_entitlement_resolves")
        for row in nplusone_rows
    ]
    assert home_ent[0] == home_ent[1] == home_ent[2]
    assert today_ent[0] == today_ent[1] == today_ent[2]
    assert calendar_ent[0] == calendar_ent[1] == calendar_ent[2]
    assert home_ent[0] >= 1
    assert today_ent[0] >= 1
    assert calendar_ent[0] >= 1


# --- T17 / WS9 repeated zero-hydration + Halted-home -----------------------

T17_REPEAT = 5
T17_SITEMAP_PATH = "/sitemap.xml"
T17_CALENDAR_PATH = "/calendar"
T17_ROSTER_PATH = "/playground/roster"
T17_ROSTER_NEXT_PATH = "/playground/roster/next"
T17_ACTIVE_ROUTES = (
    ("home", HOME_PATH),
    ("roster", T17_ROSTER_PATH),
    ("roster_next", T17_ROSTER_NEXT_PATH),
    ("today", TODAY_PATH),
    ("calendar", T17_CALENDAR_PATH),
)


class _T17DeviceCallCounter:
    """Test-only inspect/ensure counter. Does not change device policy."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.inspect_calls = 0
        self.ensure_calls = 0

    def inspect_current_device(self, *args, **kwargs):
        self.inspect_calls += 1
        return self.inner.inspect_current_device(*args, **kwargs)

    def ensure_current_device(self, *args, **kwargs):
        self.ensure_calls += 1
        return self.inner.ensure_current_device(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _seed_halted_subscription(app) -> None:
    """Direct halted current row. Does not flip an active subscriber mid-test."""

    app.state.subscriptions.create_subscription_record(
        BENCH_USER,
        tier="max",
        status="halted",
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _t17_current_status(app) -> str | None:
    row = app.state.subscriptions.get_current_subscription(BENCH_USER)
    if row is None:
        return None
    return str(getattr(row, "status", None) or "")


def _t17_fail_leak(
    *,
    route: str,
    phase: str,
    iteration: int,
    hydrated: list[str],
    snap,
    extra: str = "",
) -> None:
    notes = getattr(snap, "notes", None) or {}
    counters = getattr(snap, "counters", None) or {}
    timings = getattr(snap, "timings", None) or {}
    pytest.fail(
        "T17 hydration leak: "
        f"route={route} phase={phase} iteration={iteration} "
        f"slugs={list(hydrated)} spy_count={len(hydrated)} "
        f"misses={counters.get('bare_act_cache_misses', 0)} "
        f"bare_act_cache={notes.get('bare_act_cache')} "
        f"bare_act_load={'bare_act_load' in timings} "
        f"http={getattr(snap, 'status_code', None)} "
        f"access={notes.get('playground_access_result')} "
        f"{extra}".rstrip()
    )


def _assert_t17_zero_loader(
    hydrated: list[str],
    snap,
    *,
    route: str,
    phase: str,
    iteration: int,
) -> None:
    notes = snap.notes or {}
    counters = snap.counters or {}
    timings = snap.timings or {}
    if (
        hydrated
        or int(counters.get("bare_act_cache_misses") or 0) != 0
        or "bare_act_cache" in notes
        or "bare_act_load" in timings
    ):
        _t17_fail_leak(
            route=route,
            phase=phase,
            iteration=iteration,
            hydrated=hydrated,
            snap=snap,
        )


def _t17_positive_control_cold(hydrated: list[str]) -> None:
    clear_bare_act_cache()
    hydrated.clear()
    act = get_bare_act("ndps")
    assert act is not None
    assert hydrated == ["ndps"], (
        f"T17 cold positive control did not record get_bare_act('ndps'); "
        f"got {hydrated!r}"
    )
    hydrated.clear()
    clear_bare_act_cache()


def _t17_positive_control_warm(hydrated: list[str]) -> None:
    hydrated.clear()
    act = get_bare_act("ndps")
    assert act is not None
    assert "ndps" in hydrated, (
        f"T17 warm positive control (load) did not record ndps; got {hydrated!r}"
    )
    hydrated.clear()
    hit = get_bare_act("ndps")
    assert hit is not None
    assert hydrated == ["ndps"], (
        f"T17 warm positive control (lru_cache hit) did not record ndps; "
        f"got {hydrated!r}"
    )
    hydrated.clear()


async def _t17_get(client: AsyncClient, path: str):
    response = await client.get(path)
    snap = get_last_request_performance()
    return response, snap


def _assert_active_identity(label: str, path: str, response, snap, html: str) -> None:
    assert response.status_code == 200, (
        f"T17 active {label} HTTP {response.status_code} for {path}"
    )
    assert snap is not None, f"T17 active {label} missing request snapshot"
    assert snap.path_group == path.split("?", 1)[0]
    notes = snap.notes or {}
    counters = snap.counters or {}
    timings = snap.timings or {}
    assert notes.get("auth_state") == "authed"
    assert notes.get("playground_access_result") == "allowed"
    assert notes.get("playground_subscription_disposition") == "active"
    if label == "home":
        assert notes.get("playground_device_result") == "ok"
        assert int(counters.get("playground_device_lookups") or 0) == 2
        assert notes.get("playground_roster_result") == "ok"
        assert 'data-plus-playground="desktop"' in html
        assert 'data-halted-playground="desktop"' not in html
        assert "Payment retries have stopped" not in html
    elif label == "roster":
        assert notes.get("playground_device_result") == "ok"
        assert int(counters.get("playground_device_lookups") or 0) == 2
        assert 'data-playground-roster="current"' in html
        assert 'data-hard-gate="true"' not in html
        assert 'data-playground-gate="payment_halted"' not in html
    elif label == "roster_next":
        assert notes.get("playground_device_result") == "ok"
        assert int(counters.get("playground_device_lookups") or 0) == 2
        assert "playground_rollover_build" in timings
        assert 'data-playground-roster="next"' in html
        assert 'data-hard-gate="true"' not in html
        assert 'data-playground-gate="payment_halted"' not in html
    elif label == "today":
        assert notes.get("playground_device_result") == "skipped_unpaid"
        assert int(counters.get("playground_device_lookups") or 0) == 1
        assert snap.path_group == "/dashboard"
    elif label == "calendar":
        assert notes.get("playground_device_result") == "skipped_unpaid"
        assert int(counters.get("playground_device_lookups") or 0) == 1
        assert snap.path_group == "/calendar"
        assert path == "/calendar"


def _assert_halted_home_identity(response, snap, html: str) -> None:
    assert response.status_code == 200
    assert snap is not None
    notes = snap.notes or {}
    counters = snap.counters or {}
    assert snap.path_group == "/playground"
    assert notes.get("auth_state") == "authed"
    assert notes.get("playground_access_result") == "halted"
    assert notes.get("playground_subscription_disposition") == "halted"
    assert notes.get("playground_device_result") == "skipped_unpaid"
    assert int(counters.get("playground_device_lookups") or 0) == 1
    assert int(counters.get("playground_entitlement_resolves") or 0) == 1
    assert "playground_roster_result" not in notes
    assert 'data-halted-playground="desktop"' in html
    assert "Payment retries have stopped" in html
    assert 'data-plus-playground="desktop"' not in html
    assert 'data-hard-gate="true"' not in html
    assert "is-readonly" in html


def _assert_halted_denial_gate(label: str, path: str, response, snap, html: str) -> None:
    assert response.status_code == 200, (
        f"T17 Halted {label} HTTP {response.status_code}"
    )
    assert snap is not None
    notes = snap.notes or {}
    counters = snap.counters or {}
    assert snap.path_group == path
    assert notes.get("auth_state") == "authed"
    assert notes.get("playground_access_result") == "halted"
    assert notes.get("playground_subscription_disposition") == "halted"
    assert notes.get("playground_device_result") == "skipped_unpaid"
    assert int(counters.get("playground_device_lookups") or 0) == 1
    assert 'data-playground-gate="payment_halted"' in html
    assert 'data-hard-gate="true"' in html
    assert "Payment retries have stopped" in html
    assert 'data-playground-roster="current"' not in html
    assert 'data-playground-roster="next"' not in html
    assert 'data-halted-playground="desktop"' not in html


def _assert_sitemap_identity(response, snap) -> None:
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "xml" in content_type.lower()
    body = response.text
    assert "<sitemapindex" in body
    assert "sitemap-core.xml" in body
    assert "sitemap-laws.xml" in body
    assert snap is not None
    assert snap.path_group == T17_SITEMAP_PATH
    assert (snap.notes or {}).get("auth_state") == "guest"
    assert "playground_access_result" not in (snap.notes or {})


def test_t17_active_plus_repeated_zero_hydration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Active Plus: five routes × 5 cold + 5 warm. Real Acts. No syn-* patch."""

    install_nplusone_clock(monkeypatch)
    hydrated = _hydrate_spy(monkeypatch)
    app = create_benchmark_app(tmp_path / "t17-active.db")
    info = build_due_heavy_fixture(app)
    assert info["tier"] == "plus"
    assert info["roster_count"] == 3
    assert info["law_ids"] == ["bns", "bnss", "ndps"]

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            _t17_positive_control_cold(hydrated)
            for phase, control in (
                ("A", None),
                ("B", _t17_positive_control_warm),
            ):
                if control is not None:
                    control(hydrated)
                for label, path in T17_ACTIVE_ROUTES:
                    for iteration in range(1, T17_REPEAT + 1):
                        response, snap = await _t17_get(client, path)
                        _assert_active_identity(
                            label, path, response, snap, response.text
                        )
                        _assert_t17_zero_loader(
                            hydrated,
                            snap,
                            route=path,
                            phase=phase,
                            iteration=iteration,
                        )
            assert hydrated == []

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()
    assert hydrated == []


def test_t17_sitemap_unauthenticated_repeated_zero_hydration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Unauthenticated GET /sitemap.xml only. No child maps. No session cookie."""

    install_nplusone_clock(monkeypatch)
    hydrated = _hydrate_spy(monkeypatch)
    app = create_benchmark_app(tmp_path / "t17-sitemap.db")

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            assert not client.cookies
            _t17_positive_control_cold(hydrated)
            for phase, control in (
                ("A", None),
                ("B", _t17_positive_control_warm),
            ):
                if control is not None:
                    control(hydrated)
                for iteration in range(1, T17_REPEAT + 1):
                    response, snap = await _t17_get(client, T17_SITEMAP_PATH)
                    _assert_sitemap_identity(response, snap)
                    _assert_t17_zero_loader(
                        hydrated,
                        snap,
                        route=T17_SITEMAP_PATH,
                        phase=phase,
                        iteration=iteration,
                    )
                    assert not client.cookies.get("rtc_session")
            assert hydrated == []

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()
    assert hydrated == []


def test_t17_halted_home_repeated_zero_hydration_and_roster_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Halted subscriber GET /playground 5+5, then one-shot roster/next gates."""

    install_nplusone_clock(monkeypatch)
    hydrated = _hydrate_spy(monkeypatch)
    app = create_benchmark_app(tmp_path / "t17-halted.db")
    activate_law(app.state.playground, BENCH_USER, "ndps")
    _seed_halted_subscription(app)
    assert _t17_current_status(app) == "halted"
    device = _T17DeviceCallCounter(app.state.device_service)
    app.state.device_service = device

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            assert _t17_current_status(app) == "halted"
            _t17_positive_control_cold(hydrated)
            for phase, control in (
                ("A", None),
                ("B", _t17_positive_control_warm),
            ):
                if control is not None:
                    control(hydrated)
                for iteration in range(1, T17_REPEAT + 1):
                    response, snap = await _t17_get(client, HOME_PATH)
                    _assert_halted_home_identity(response, snap, response.text)
                    _assert_t17_zero_loader(
                        hydrated,
                        snap,
                        route=HOME_PATH,
                        phase=phase,
                        iteration=iteration,
                    )
                    assert device.ensure_calls == 0
                    assert _t17_current_status(app) == "halted"
            for label, path in (
                ("roster", T17_ROSTER_PATH),
                ("roster_next", T17_ROSTER_NEXT_PATH),
            ):
                response, snap = await _t17_get(client, path)
                _assert_halted_denial_gate(
                    label, path, response, snap, response.text
                )
                _assert_t17_zero_loader(
                    hydrated,
                    snap,
                    route=path,
                    phase="denial",
                    iteration=1,
                )
                assert device.ensure_calls == 0
                assert _t17_current_status(app) == "halted"
            assert hydrated == []
            assert device.ensure_calls == 0

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()
    assert _t17_current_status(app) == "halted"
    assert device.ensure_calls == 0
    assert hydrated == []


# --- T22 / WS12 observability + privacy consolidation ---

import json
import logging
import math
from dataclasses import asdict

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.devices.token import DEVICE_COOKIE_NAME, mint_installation_token
from constitution_memorizer.playground.benchmarking import BENCH_EMAIL
from constitution_memorizer.playground.repo_counters import _repo_counter_depth
from constitution_memorizer.web.request_context import (
    PLAYGROUND_ACCESS_RESULTS,
    PLAYGROUND_DEVICE_RESULTS,
    PLAYGROUND_LAW_STATES,
    PLAYGROUND_ROSTER_RESULTS,
    PLAYGROUND_SUBSCRIPTION_DISPOSITIONS,
    REQUEST_COUNTERS,
    REQUEST_NOTES,
    TIMING_STAGES,
    breakdown_includes_raw_path,
    wants_request_breakdown,
)

_T22_ROOT = Path(__file__).resolve().parents[1]
_T22_TRACKER = _T22_ROOT / "docs" / "PLAYGROUND_DELIVERY_TRACKER.md"
_T22_ALEMBIC_HEAD = "20260927_0027"
_T22_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_T22_LAW_SLUGS = ("bns", "bnss", "ndps", "uapa", "pss", "mtp")
_T22_AUTH_STATES = frozenset({"single_user", "authed", "guest"})
_T22_BARE_ACT_CACHE_NOTES = frozenset({"hit", "miss"})
_T22_NOTE_VALUES = {
    "playground_access_result": PLAYGROUND_ACCESS_RESULTS,
    "playground_subscription_disposition": PLAYGROUND_SUBSCRIPTION_DISPOSITIONS,
    "playground_device_result": PLAYGROUND_DEVICE_RESULTS,
    "playground_roster_result": PLAYGROUND_ROSTER_RESULTS,
    "playground_law_state": PLAYGROUND_LAW_STATES,
    "auth_state": _T22_AUTH_STATES,
    "bare_act_cache": _T22_BARE_ACT_CACHE_NOTES,
}
_T22_PLAYGROUND_STAGES = (
    "playground_entitlement",
    "playground_device",
    "playground_roster_access",
    "playground_home_build",
    "playground_home_summaries",
    "playground_source_presentations",
    "playground_workspace_build",
    "playground_selection_read",
    "playground_mode_progress",
    "playground_revision_progress",
    "playground_rollover_build",
    "playground_rollover_write",
    "playground_learning_build",
    "playground_learning_write",
    "playground_revision_build",
    "playground_revision_write",
    "playground_source_review",
    "playground_source_scan",
    "playground_today",
    "playground_calendar",
    "playground_admin_diagnostics",
)
_T22_PLAYGROUND_COUNTERS = (
    "playground_db_reads",
    "playground_db_writes",
    "playground_repo_round_trips",
    "playground_summary_reads",
    "playground_roster_reads",
    "playground_progress_reads",
    "playground_source_review_reads",
    "playground_revision_reads",
    "playground_entitlement_resolves",
    "playground_device_lookups",
)
_T22_PLAYGROUND_NOTES = (
    "playground_access_result",
    "playground_subscription_disposition",
    "playground_device_result",
    "playground_roster_result",
    "playground_law_state",
)
_T22_PLUS_ROUTES = (
    ("home", HOME_PATH, "/playground"),
    ("roster", T17_ROSTER_PATH, "/playground/roster"),
    ("roster_next", T17_ROSTER_NEXT_PATH, "/playground/roster/next"),
    ("today", TODAY_PATH, "/dashboard"),
    ("calendar", T17_CALENDAR_PATH, "/calendar"),
)
_T22_SIX_ROUTE_PATHS = (
    HOME_PATH,
    T17_ROSTER_PATH,
    T17_ROSTER_NEXT_PATH,
    TODAY_PATH,
    T17_CALENDAR_PATH,
    T17_SITEMAP_PATH,
)
_T22_PRIVACY_QUERY = (
    "/playground?email=bench@example.invalid&token=t22-secret-token&code=t22-oauth-code"
)
_T22_CALENDAR_QUERY = "/calendar?year=2026&month=9"
_T22_QUERY_SECRETS = (
    "bench@example.invalid",
    "t22-secret-token",
    "t22-oauth-code",
    "email=",
    "token=",
    "code=",
    "year=",
    "month=",
)


def _t22_force_sample_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", "1")


def _t22_breakdown_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]


def _t22_snapshot_text(snap) -> str:
    return json.dumps(asdict(snap), default=str, sort_keys=True)


def _t22_cookie_values(client: AsyncClient) -> dict[str, str]:
    values: dict[str, str] = {}
    session = client.cookies.get("rtc_session") or ""
    device = client.cookies.get(DEVICE_COOKIE_NAME) or ""
    if session:
        values["rtc_session"] = session
    if device:
        values[DEVICE_COOKIE_NAME] = device
    return values


async def _t22_request(client: AsyncClient, method: str, path: str, **kwargs):
    if method == "GET":
        response = await client.get(path, **kwargs)
    elif method == "POST":
        response = await client.post(path, **kwargs)
    else:
        raise AssertionError(f"T22 unsupported method {method}")
    snap = get_last_request_performance()
    if snap is None:
        pytest.fail(f"t22_missing_snapshot method={method} route={path}")
    return response, snap


def _t22_assert_shape(snap, *, route: str, method: str, status: int) -> None:
    assert snap.method == method, f"T22 method route={route}"
    assert snap.status_code == status, (
        f"T22 status route={route} expected={status} got={snap.status_code}"
    )
    assert isinstance(snap.total_ms, (int, float))
    assert snap.total_ms >= 0
    assert math.isfinite(float(snap.total_ms))


def _t22_assert_path_group(snap, expected: str, *, route: str) -> None:
    got = snap.path_group
    if got != expected:
        pytest.fail(f"T22 path_group route={route} expected={expected} got={got!r}")
    if "?" in got or "year=" in got or "month=" in got:
        pytest.fail(f"T22 query leaked into path_group route={route}")
    if _T22_UUID_RE.search(got):
        pytest.fail(f"T22 UUID leaked into path_group route={route}")
    if expected.startswith("/playground"):
        for slug in _T22_LAW_SLUGS:
            token = f"/{slug}"
            if token in got or got.endswith(slug):
                pytest.fail(f"T22 law id in path_group route={route}")


def _t22_assert_counters(snap, *, route: str, entitlement_exact: int | None) -> None:
    counters = snap.counters or {}
    for name, value in counters.items():
        if name not in REQUEST_COUNTERS:
            pytest.fail(f"T22 unexpected counter {name} route={route}")
        if type(value) is not int or value < 0:
            pytest.fail(f"T22 counter {name} not a nonnegative int route={route}")
    resolves = int(counters.get("playground_entitlement_resolves") or 0)
    if resolves > 1:
        pytest.fail(
            f"T22 playground_entitlement_resolves={resolves} > 1 route={route}"
        )
    if entitlement_exact is not None:
        assert resolves == entitlement_exact, (
            f"T22 playground_entitlement_resolves route={route} "
            f"expected={entitlement_exact} got={resolves}"
        )


def _t22_assert_notes(snap, *, route: str) -> None:
    notes = snap.notes or {}
    for name, value in notes.items():
        if name not in REQUEST_NOTES:
            pytest.fail(f"T22 unexpected note {name} route={route}")
        allowed = _T22_NOTE_VALUES.get(name)
        if allowed is None:
            continue
        if value not in allowed:
            pytest.fail(f"T22 note {name} outside closed set route={route}")


def _t22_assert_attribution(snap, *, route: str) -> None:
    counters = snap.counters or {}
    reads = int(counters.get("playground_db_reads") or 0)
    writes = int(counters.get("playground_db_writes") or 0)
    trips = int(counters.get("playground_repo_round_trips") or 0)
    summaries = int(counters.get("playground_summary_reads") or 0)
    if trips != reads + writes:
        pytest.fail(
            f"T22 round_trips={trips} != reads={reads}+writes={writes} route={route}"
        )
    if trips < summaries:
        pytest.fail(
            f"T22 round_trips={trips} < summary_reads={summaries} route={route}"
        )


def _t22_assert_hydration_zeros(snap, *, route: str) -> None:
    counters = snap.counters or {}
    notes = snap.notes or {}
    timings = snap.timings or {}
    misses = int(counters.get("bare_act_cache_misses") or 0)
    if misses != 0:
        pytest.fail(f"T22 bare_act_cache_misses={misses} route={route}")
    if "bare_act_cache" in notes:
        pytest.fail(f"T22 bare_act_cache note present route={route}")
    if "bare_act_load" in timings:
        pytest.fail(f"T22 bare_act_load timing present route={route}")


def _t22_assert_privacy(
    snap,
    breakdown_lines: list[str],
    *,
    route: str,
    cookies: dict[str, str],
    extra_needles: tuple[str, ...] = (),
) -> None:
    blob = _t22_snapshot_text(snap)
    playground = snap.path_group.startswith("/playground")
    needles = [
        ("email", BENCH_EMAIL),
        ("user_id", str(BENCH_USER)),
        ("bearer", "Bearer "),
        ("session_secret", "SESSION_SECRET"),
        ("database_url", "DATABASE_URL"),
        ("postgresql", "postgresql://"),
    ]
    for label, value in cookies.items():
        if value:
            needles.append((label, value))
    for secret in extra_needles:
        needles.append(("query", secret))
    for label, needle in needles:
        if needle and needle in blob:
            pytest.fail(f"T22 privacy leak ({label}) source=snapshot route={route}")
    if playground:
        _t22_assert_no_law_id_in_group(snap.path_group, route=route, source="snapshot")
    for line in breakdown_lines:
        for label, needle in needles:
            if needle and needle in line:
                pytest.fail(f"T22 privacy leak ({label}) source=log route={route}")
        if "?" in line or "year=" in line or "month=" in line:
            pytest.fail(f"T22 query leaked into request_breakdown route={route}")
        if _T22_UUID_RE.search(line):
            pytest.fail(f"T22 UUID leaked into request_breakdown route={route}")
        parts = line.split()
        raw_paths = [
            part for part in parts if part.startswith("path=") and not part.startswith("path_group=")
        ]
        if playground:
            if raw_paths:
                pytest.fail(f"T22 raw path= on playground request_breakdown route={route}")
            if not breakdown_includes_raw_path(route.split("?", 1)[0]):
                pass
            for slug in _T22_LAW_SLUGS:
                if slug in line:
                    pytest.fail(f"T22 law id in playground request_breakdown route={route}")
        else:
            for part in raw_paths:
                if "?" in part or "year=" in part or "month=" in part:
                    pytest.fail(f"T22 query in breakdown path= route={route}")


def _t22_assert_no_law_id_in_group(path_group: str, *, route: str, source: str) -> None:
    for slug in _T22_LAW_SLUGS:
        if f"/{slug}" in path_group or path_group.endswith(slug):
            pytest.fail(f"T22 law id in path_group source={source} route={route}")


def _t22_assert_repo_depth_clear(*, route: str) -> None:
    depth = _repo_counter_depth.get()
    if depth != 0:
        pytest.fail(f"T22 leaked _repo_counter_depth={depth} route={route}")


def _t22_subscribe_plus(app) -> None:
    app.state.subscriptions.create_subscription_record(
        BENCH_USER,
        tier="plus",
        status="active",
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _t22_seed_other_devices(app, n: int = 2) -> None:
    service = app.state.device_service
    inner = getattr(service, "inner", service)
    for index in range(n):
        access = inner.ensure_current_device(
            BENCH_USER,
            mint_installation_token(),
            auth_session_id=f"t22-seed-sess-{index}",
            commercially_eligible=True,
        )
        assert access.current_device_registered is True


def _t22_fill_plus_roster(app, monkeypatch: pytest.MonkeyPatch, n: int = 10) -> None:
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("slot-"):
            return True
        return real(law_id)

    monkeypatch.setattr(roster_service, "is_playground_eligible_law", wrapped)
    snap = app.state.entitlement_service.resolve(BENCH_USER)
    roster = app.state.roster
    for index in range(n):
        result = roster.confirm_add_law(
            BENCH_USER, f"slot-{index}", snap, can_consume_new_law=True
        )
        assert result.ok, result.status


def _t22_cell(
    snap,
    _response,
    *,
    route: str,
    expected_group: str,
    method: str,
    status: int,
    entitlement_exact: int | None,
    breakdown_lines: list[str],
    cookies: dict[str, str],
    extra_needles: tuple[str, ...] = (),
    expect_breakdown: bool,
    attribution: bool,
) -> None:
    _t22_assert_shape(snap, route=route, method=method, status=status)
    _t22_assert_path_group(snap, expected_group, route=route)
    _t22_assert_counters(snap, route=route, entitlement_exact=entitlement_exact)
    _t22_assert_notes(snap, route=route)
    _t22_assert_hydration_zeros(snap, route=route)
    _t22_assert_privacy(
        snap,
        breakdown_lines,
        route=route,
        cookies=cookies,
        extra_needles=extra_needles,
    )
    if expect_breakdown and not breakdown_lines:
        pytest.fail(f"T22 missing request_breakdown log route={route}")
    if attribution:
        _t22_assert_attribution(snap, route=route)
    _t22_assert_repo_depth_clear(route=route)


async def _t22_measured_get(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    path: str,
):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        response, snap = await _t22_request(client, "GET", path)
        lines = _t22_breakdown_messages(caplog)
    return response, snap, lines


def test_t22_playground_vocabulary_is_registered():
    for path in _T22_SIX_ROUTE_PATHS:
        assert wants_request_breakdown(path) is True, path
    assert wants_request_breakdown("/playground/laws/ndps/add") is True
    assert TIMING_STAGES[-len(_T22_PLAYGROUND_STAGES) :] == _T22_PLAYGROUND_STAGES
    assert REQUEST_COUNTERS[-len(_T22_PLAYGROUND_COUNTERS) :] == _T22_PLAYGROUND_COUNTERS
    assert REQUEST_NOTES[-len(_T22_PLAYGROUND_NOTES) :] == _T22_PLAYGROUND_NOTES
    playground_stages = tuple(name for name in TIMING_STAGES if name.startswith("playground_"))
    playground_counters = tuple(
        name for name in REQUEST_COUNTERS if name.startswith("playground_")
    )
    playground_notes = tuple(name for name in REQUEST_NOTES if name.startswith("playground_"))
    assert playground_stages == _T22_PLAYGROUND_STAGES
    assert playground_counters == _T22_PLAYGROUND_COUNTERS
    assert playground_notes == _T22_PLAYGROUND_NOTES
    for name in _T22_PLAYGROUND_STAGES:
        assert name in TIMING_STAGES
    for name in _T22_PLAYGROUND_COUNTERS:
        assert name in REQUEST_COUNTERS
    for name in _T22_PLAYGROUND_NOTES:
        assert name in REQUEST_NOTES
    assert "auth_state" in REQUEST_NOTES
    assert "bare_act_cache_misses" in REQUEST_COUNTERS
    assert "bare_act_load" in TIMING_STAGES


def test_t22_stage1_freeze_tracker_and_alembic_head():
    tracker = _T22_TRACKER.read_text(encoding="utf-8")
    assert "DONE — 100.0 / 100" in tracker
    assert "Stage 2 may begin only after" in tracker
    cfg = Config(str(_T22_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == [_T22_ALEMBIC_HEAD], heads


def test_t22_plus_five_route_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-plus.db")
    info = build_due_heavy_fixture(app)
    assert info["tier"] == "plus"

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            warmup, warmup_snap = await _t22_request(client, "GET", HOME_PATH)
            assert warmup.status_code == 200
            assert warmup_snap is not None
            for label, path, group in _T22_PLUS_ROUTES:
                response, snap, lines = await _t22_measured_get(client, caplog, path)
                assert response.status_code == 200, (
                    f"T22 plus {label} HTTP {response.status_code}"
                )
                entitlement_exact = 1 if label in {"home", "roster", "roster_next"} else None
                _t22_cell(
                    snap,
                    response,
                    route=path,
                    expected_group=group,
                    method="GET",
                    status=200,
                    entitlement_exact=entitlement_exact,
                    breakdown_lines=lines,
                    cookies=_t22_cookie_values(client),
                    expect_breakdown=True,
                    attribution=label in {"home", "roster"},
                )
                _assert_active_identity(label, path, response, snap, response.text)
                notes = snap.notes or {}
                assert notes.get("auth_state") == "authed"
                assert notes.get("playground_access_result") == "allowed"
            query_resp, query_snap, query_lines = await _t22_measured_get(
                client, caplog, _T22_PRIVACY_QUERY
            )
            assert query_resp.status_code == 200
            _t22_cell(
                query_snap,
                query_resp,
                route=_T22_PRIVACY_QUERY,
                expected_group="/playground",
                method="GET",
                status=200,
                entitlement_exact=1,
                breakdown_lines=query_lines,
                cookies=_t22_cookie_values(client),
                extra_needles=_T22_QUERY_SECRETS,
                expect_breakdown=True,
                attribution=True,
            )
            cal_resp, cal_snap, cal_lines = await _t22_measured_get(
                client, caplog, _T22_CALENDAR_QUERY
            )
            assert cal_resp.status_code == 200
            _t22_cell(
                cal_snap,
                cal_resp,
                route=_T22_CALENDAR_QUERY,
                expected_group="/calendar",
                method="GET",
                status=200,
                entitlement_exact=None,
                breakdown_lines=cal_lines,
                cookies=_t22_cookie_values(client),
                extra_needles=("year=", "month="),
                expect_breakdown=True,
                attribution=False,
            )

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()


def test_t22_guest_sitemap_and_playground(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-guest.db")

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            assert not client.cookies.get("rtc_session")
            site_resp, site_snap, site_lines = await _t22_measured_get(
                client, caplog, T17_SITEMAP_PATH
            )
            _assert_sitemap_identity(site_resp, site_snap)
            _t22_cell(
                site_snap,
                site_resp,
                route=T17_SITEMAP_PATH,
                expected_group="/sitemap.xml",
                method="GET",
                status=200,
                entitlement_exact=0,
                breakdown_lines=site_lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=False,
                attribution=False,
            )
            assert "playground_access_result" not in (site_snap.notes or {})
            assert (site_snap.notes or {}).get("auth_state") == "guest"
            assert int((site_snap.counters or {}).get("playground_entitlement_resolves") or 0) == 0
            home_resp, home_snap, home_lines = await _t22_measured_get(
                client, caplog, HOME_PATH
            )
            assert home_resp.status_code == 200
            notes = home_snap.notes or {}
            _t22_cell(
                home_snap,
                home_resp,
                route=HOME_PATH,
                expected_group="/playground",
                method="GET",
                status=200,
                entitlement_exact=1,
                breakdown_lines=home_lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=True,
                attribution=False,
            )
            assert notes.get("auth_state") == "guest"
            assert notes.get("playground_access_result") == "guest"
            assert notes.get("playground_device_result") == "skipped_unpaid"
            assert "playground_roster_result" not in notes
            assert int((home_snap.counters or {}).get("playground_device_lookups") or 0) == 0

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()


def test_t22_free_playground(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-free.db")

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            response, snap, lines = await _t22_measured_get(client, caplog, HOME_PATH)
            assert response.status_code == 200
            notes = snap.notes or {}
            _t22_cell(
                snap,
                response,
                route=HOME_PATH,
                expected_group="/playground",
                method="GET",
                status=200,
                entitlement_exact=1,
                breakdown_lines=lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=True,
                attribution=False,
            )
            assert notes.get("auth_state") == "authed"
            assert notes.get("playground_access_result") == "free"
            assert notes.get("playground_device_result") == "skipped_unpaid"
            assert int((snap.counters or {}).get("playground_device_lookups") or 0) == 1

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()


def test_t22_halted_playground_readonly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-halted.db")
    activate_law(app.state.playground, BENCH_USER, "ndps")
    _seed_halted_subscription(app)

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            response, snap, lines = await _t22_measured_get(client, caplog, HOME_PATH)
            _assert_halted_home_identity(response, snap, response.text)
            _t22_cell(
                snap,
                response,
                route=HOME_PATH,
                expected_group="/playground",
                method="GET",
                status=200,
                entitlement_exact=1,
                breakdown_lines=lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=True,
                attribution=False,
            )
            notes = snap.notes or {}
            assert notes.get("playground_access_result") == "halted"
            assert notes.get("playground_device_result") == "skipped_unpaid"
            assert "playground_roster_result" not in notes
            assert "is-readonly" in response.text

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()


def test_t22_device_limit_playground(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-device.db")
    _t22_subscribe_plus(app)

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            _t22_seed_other_devices(app, 2)
            response, snap, lines = await _t22_measured_get(client, caplog, HOME_PATH)
            assert response.status_code == 200
            _t22_cell(
                snap,
                response,
                route=HOME_PATH,
                expected_group="/playground",
                method="GET",
                status=200,
                entitlement_exact=1,
                breakdown_lines=lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=True,
                attribution=False,
            )
            notes = snap.notes or {}
            assert notes.get("auth_state") == "authed"
            assert notes.get("playground_access_result") == "device_limit"
            assert notes.get("playground_device_result") == "device_limit"
            assert int((snap.counters or {}).get("playground_device_lookups") or 0) == 2
            assert 'data-playground-gate="device_limit"' in response.text

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()


def test_t22_roster_full_add_denial_home_stays_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-roster-full.db")
    _t22_subscribe_plus(app)
    _t22_fill_plus_roster(app, monkeypatch)

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            home_resp, home_snap, home_lines = await _t22_measured_get(
                client, caplog, HOME_PATH
            )
            assert home_resp.status_code == 200
            _t22_cell(
                home_snap,
                home_resp,
                route=HOME_PATH,
                expected_group="/playground",
                method="GET",
                status=200,
                entitlement_exact=1,
                breakdown_lines=home_lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=True,
                attribution=True,
            )
            home_notes = home_snap.notes or {}
            assert home_notes.get("playground_access_result") == "allowed"
            assert home_notes.get("playground_roster_result") == "roster_full"
            csrf = client.cookies.get("rtc_csrf") or ""
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                add_resp, add_snap = await _t22_request(
                    client,
                    "POST",
                    "/playground/laws/ndps/add",
                    data={"csrf_token": csrf, "confirm": "add", "scope": "sections"},
                    headers={"Accept": "application/json"},
                )
                add_lines = _t22_breakdown_messages(caplog)
            assert add_resp.status_code in {200, 403}
            if add_resp.status_code == 403:
                assert add_resp.json()["error"] == "roster_full"
            else:
                assert "roster_full" in add_resp.text
            _t22_cell(
                add_snap,
                add_resp,
                route="/playground/laws/ndps/add",
                expected_group="/playground/laws/{law_id}/add",
                method="POST",
                status=add_resp.status_code,
                entitlement_exact=1,
                breakdown_lines=add_lines,
                cookies=_t22_cookie_values(client),
                expect_breakdown=True,
                attribution=False,
            )
            add_notes = add_snap.notes or {}
            assert add_notes.get("playground_access_result") == "roster_full"
            assert add_notes.get("playground_roster_result") == "roster_full"

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()


def test_t22_plus_home_request_local_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _t22_force_sample_rate(monkeypatch)
    install_nplusone_clock(monkeypatch)
    app = create_benchmark_app(tmp_path / "t22-isolation.db")
    info = build_due_heavy_fixture(app)
    assert info["tier"] == "plus"

    async def _go():
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            warmup, warmup_snap = await _t22_request(client, "GET", HOME_PATH)
            assert warmup.status_code == 200
            assert warmup_snap is not None
            _t22_assert_repo_depth_clear(route="warmup")
            a_resp, a_snap, a_lines = await _t22_measured_get(client, caplog, HOME_PATH)
            _t22_assert_repo_depth_clear(route="A")
            b_resp, b_snap, b_lines = await _t22_measured_get(client, caplog, HOME_PATH)
            _t22_assert_repo_depth_clear(route="B")
            assert a_resp.status_code == 200
            assert b_resp.status_code == 200
            cookies = _t22_cookie_values(client)
            for label, resp, snap, lines in (
                ("A", a_resp, a_snap, a_lines),
                ("B", b_resp, b_snap, b_lines),
            ):
                _t22_cell(
                    snap,
                    resp,
                    route=f"{HOME_PATH}#{label}",
                    expected_group="/playground",
                    method="GET",
                    status=200,
                    entitlement_exact=1,
                    breakdown_lines=lines,
                    cookies=cookies,
                    expect_breakdown=True,
                    attribution=True,
                )
                notes = snap.notes or {}
                assert notes.get("playground_access_result") == "allowed"
            a_ent = int((a_snap.counters or {}).get("playground_entitlement_resolves") or 0)
            b_ent = int((b_snap.counters or {}).get("playground_entitlement_resolves") or 0)
            assert a_ent == 1
            assert b_ent == 1
            a_trips = int((a_snap.counters or {}).get("playground_repo_round_trips") or 0)
            b_trips = int((b_snap.counters or {}).get("playground_repo_round_trips") or 0)
            assert b_trips == a_trips, (
                f"T22 isolation accumulated round_trips A={a_trips} B={b_trips}"
            )

    try:
        asyncio.run(_go())
    finally:
        clear_bare_act_cache()
