"""T16 / WS9 N+1 scaling locks and T17 repeated zero-hydration + Halted-home.

Integer query counts and loader-call locks only; no millisecond asserts.
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
