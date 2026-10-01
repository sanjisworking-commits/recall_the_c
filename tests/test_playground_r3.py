"""R3 — Add flow, Act header, home, and gates.

Closes U2 leftover rows D27–D40, T17–T18 and U3 rows D22, D51–D63,
D101, D104–D106, D125–D127, D140, D142, T19–T21.

Three non-optional invariants:

1. Entire Act persistence recovery after roster consume.
2. ``can_view_home`` is GET ``/playground`` only and does not authorize
   Learn, Add, Remove, selection, or roster writes.
3. D142 is one atomic row: Playground-scoped HTML 404 + 403 + 500, without
   hijacking global exception handlers. Partial implementation scores zero.

Does not start R4 or R5. Programme score stays provisional until the
post-closeout read-only persistence and unexpected-failure corrections
pass locally and in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.playground.access import PLAYGROUND_BILLING_PATH
from constitution_memorizer.playground.service import persist_entire_act_selection
from constitution_memorizer.playground.source import locators_for_act
from constitution_memorizer.playground.urls import (
    add_path,
    learn_complete_path,
    learn_path,
    remove_path,
    roster_path,
    sections_path,
)
from tests.test_entitlement_m3b import (
    PERIOD_END,
    PERIOD_START,
    _add_subscription,
    _assert_subscribe_gate,
    _authed_client as _m3_authed,
    _guest_client,
    _seed_ndps_overlay,
    USER as M3_USER,
)
from tests.test_playground_m11 import USER_A, _mu_app, _sign_in, _subscribe as _m11_subscribe
from tests.test_playground_m6 import _fill_used
from tests.test_roster_m5a import (
    NOW,
    USER,
    _authed_client,
    _confirm_add,
    _csrf,
    _seed_overlay,
    _subscribe,
)

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "src/constitution_memorizer/web/app.py"
PLAYGROUND_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PLAYGROUND_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
ACCESS_PY = ROOT / "src/constitution_memorizer/playground/access.py"
ROUTES_PY = ROOT / "src/constitution_memorizer/playground/routes.py"
ERRORS_PY = ROOT / "src/constitution_memorizer/playground/errors.py"


def _used(client: TestClient) -> int:
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    return client.app.state.roster.peek_capacity(USER, snap, now=NOW).used


def _roster_consume_state(client: TestClient, user_id=USER) -> tuple:
    """Consumed membership only. Period ensure is allowed on can_open POSTs."""

    roster = client.app.state.roster
    items = []
    for period in roster.list_periods(user_id):
        for item in roster.list_items_for_period(user_id, period.period_start):
            items.append(
                (
                    item.law_id,
                    item.origin,
                    item.consumed_at is not None,
                    item.removed_at is not None,
                )
            )
    used = roster.peek_capacity(user_id, None, now=NOW).used
    return tuple(items), used


def _roster_persistence(client: TestClient, user_id=USER) -> tuple:
    """Byte-stable roster rows. Includes updated_at so silent UPDATEs fail."""

    roster = client.app.state.roster
    periods = tuple(
        (
            row.id,
            row.period_start,
            row.period_end,
            row.status,
            row.tier_snapshot,
            row.law_limit,
            row.confirmed_at,
            row.created_at,
            row.updated_at,
        )
        for row in roster.list_periods(user_id)
    )
    items = []
    for period in roster.list_periods(user_id):
        for item in roster.list_items_for_period(user_id, period.period_start):
            items.append(
                (
                    item.id,
                    item.period_start,
                    item.law_id,
                    item.origin,
                    item.consumed_at,
                    item.removed_at,
                    item.created_at,
                    item.updated_at,
                )
            )
    current = roster.get_current_period(user_id, now=NOW)
    used = (
        roster.peek_capacity(user_id, None, now=NOW).used if current is not None else 0
    )
    return periods, tuple(items), used


def _progress_fingerprint(client: TestClient, law_id: str = "ndps") -> tuple:
    playground = client.app.state.playground
    lifecycle = tuple(
        (row.source_locator, row.times_completed, row.source_hash, row.status)
        for row in playground.list_progress(USER, law_id)
    )
    modes = tuple(
        (row.source_locator, row.mode, row.status, row.attempt_count)
        for row in playground.list_mode_progress(USER, law_id)
    )
    return lifecycle, modes


def test_t17_confirm_without_scope_shows_scope_and_does_not_consume(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    page = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add"},
        follow_redirects=False,
    )
    assert page.status_code == 200
    assert "Entire Act" in page.text
    assert "Choose sections" in page.text
    assert "Nothing is scheduled yet" in page.text
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert client.app.state.playground.get_item(USER, "ndps") is None


def test_t17_max_skips_confirm_and_opens_on_scope(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="max")
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    assert 'data-skip-confirm="true"' in page.text
    assert 'data-step="scope"' in page.text
    assert "Entire Act" in page.text
    assert "Choose sections" in page.text
    assert "1 of your" not in page.text


def test_choose_sections_consumes_and_opens_empty_picker(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    added = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert added.status_code == 303
    assert added.headers["location"] == sections_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    assert _used(client) == 1
    overlay = client.app.state.playground
    assert overlay.get_item(USER, "ndps") is not None
    assert overlay.list_selection(USER, "ndps") == []
    picker = client.get(sections_path("ndps"))
    assert picker.status_code == 200
    assert "Choose what to learn" in picker.text
    assert 'aria-checked="true"' not in picker.text
    assert 'aria-checked="mixed"' not in picker.text


def test_entire_act_persist_recovers_after_overlay_failure_without_second_slot(
    tmp_path: Path,
):
    """Invariant 1: consume-then-overlay-fail does not eat another slot.

    Retry finishes the intended Entire Act selection and does not reset
    progress/history rows.
    """

    client = _authed_client(tmp_path)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    saved = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert client.get(learn_path("ndps", "1")).status_code == 200
    done = client.post(learn_complete_path("ndps", "1"), data=_csrf(client))
    assert done.status_code == 200
    assert done.json()["ok"] is True
    before_progress = _progress_fingerprint(client)
    assert before_progress[0] or before_progress[1]
    used_before = _used(client)
    assert used_before == 1
    before_selection = [
        row.source_locator
        for row in client.app.state.playground.list_selection(USER, "ndps")
    ]
    assert before_selection == ["ndps:section:1"]

    overlay = client.app.state.playground
    real_replace = overlay.replace_selection
    calls = {"n": 0}

    def boom(user_id, law_id, rows):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("forced overlay write failure")
        return real_replace(user_id, law_id, rows)

    overlay.replace_selection = boom
    try:
        client.raise_server_exceptions = False
        failed = client.post(
            add_path("ndps"),
            data={**_csrf(client), "confirm": "add", "scope": "entire"},
            follow_redirects=False,
        )
        assert failed.status_code == 500
        assert "Playground hit a problem" in failed.text
        assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
        assert _used(client) == used_before
        assert [
            row.source_locator
            for row in overlay.list_selection(USER, "ndps")
        ] == before_selection
        assert _progress_fingerprint(client) == before_progress

        recovered = client.post(
            add_path("ndps"),
            data={**_csrf(client), "confirm": "add", "scope": "entire"},
            follow_redirects=False,
        )
        assert recovered.status_code == 303
        assert recovered.headers["location"].endswith("/playground/laws/ndps")
        assert _used(client) == used_before
        expected = {loc.value for loc in locators_for_act("ndps")}
        got = {
            row.source_locator
            for row in overlay.list_selection(USER, "ndps")
        }
        assert got == expected
        assert len(got) > 1
        assert _progress_fingerprint(client) == before_progress
    finally:
        overlay.replace_selection = real_replace
        client.raise_server_exceptions = True
    assert calls["n"] >= 2


def test_persist_entire_act_selection_is_idempotent(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    overlay = client.app.state.playground
    first = persist_entire_act_selection(overlay, USER, "ndps")
    second = persist_entire_act_selection(overlay, USER, "ndps")
    assert {row[0] for row in first} == {row[0] for row in second}
    assert _used(client) == 1


def test_can_view_home_does_not_leak_learn_or_mutations(tmp_path: Path):
    """Invariant 2: paused home is read-only. Learn and writes stay blocked."""

    client = _authed_client(tmp_path)
    sub = _subscribe(client, tier="pro", status="active")
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    client.app.state.subscriptions.update_subscription_state(USER, sub.id, status="paused")
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.can_open_playground is False

    home = client.get("/playground")
    assert home.status_code == 200
    assert "Playground subscription paused" in home.text
    assert "Resume Playground" in home.text
    assert 'data-hard-gate="true"' not in home.text
    assert "My Playground" in home.text or "Playground" in home.text

    learn = client.get(learn_path("ndps", "1"), follow_redirects=False)
    assert learn.status_code == 200
    assert 'data-pg-learn-panel="cloze"' not in learn.text
    assert "data-playground-gate" in learn.text or "paused" in learn.text.lower()

    learn_json = client.get(
        learn_path("ndps", "1"),
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert learn_json.status_code == 403
    payload = learn_json.json()
    assert payload["ok"] is False
    assert payload["error"]

    done = client.post(learn_complete_path("ndps", "1"), data=_csrf(client))
    assert done.status_code == 403
    assert done.json()["ok"] is False

    added = client.post(
        add_path("bns"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert added.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False

    selected = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "2"},
        follow_redirects=False,
    )
    assert selected.status_code == 303
    locators = [
        row.source_locator
        for row in client.app.state.playground.list_selection(USER, "ndps")
    ]
    assert "ndps:section:2" not in locators

    removed = client.post(
        remove_path("ndps"),
        data=_csrf(client),
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True

    roster = client.get(roster_path(), follow_redirects=False)
    assert roster.status_code == 200
    assert "data-playground-gate" in roster.text or "paused" in roster.text.lower()

    routes = ROUTES_PY.read_text()
    assert routes.count("require_playground_home(") == 1


def test_can_view_home_does_not_apply_to_guest_free_or_device(tmp_path: Path):
    guest = _guest_client(tmp_path / "g")
    guest_home = guest.get("/playground", follow_redirects=False)
    assert guest_home.status_code == 200
    assert "Sign in to use Playground" in guest_home.text
    assert 'data-hard-gate="true"' in guest_home.text
    assert "In Playground this month" not in guest_home.text

    free, _repo = _m3_authed(tmp_path / "free")
    _assert_subscribe_gate(free.get("/playground"))
    assert "Resume Playground" not in free.get("/playground").text


def test_d142_playground_html_404_403_500_without_global_handlers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Invariant 3 / D142 atomic row. All three statuses must pass together."""

    app_src = APP_PY.read_text()
    assert "@app.exception_handler" not in app_src
    assert "add_exception_handler" not in app_src
    errors_src = ERRORS_PY.read_text()
    assert "playground_error_middleware" in errors_src
    assert "is_playground_path" in errors_src
    assert "HTTPException" not in errors_src

    client = _authed_client(tmp_path)
    _subscribe(client)

    missing = client.get("/playground/this-page-does-not-exist", follow_redirects=False)
    assert missing.status_code == 404, missing.text
    assert "This Playground page was not found" in missing.text
    assert 'data-playground-error="404"' in missing.text
    assert 'data-hard-gate="true"' in missing.text

    other_404 = client.get("/this-page-does-not-exist", follow_redirects=False)
    assert other_404.status_code == 404
    assert "This Playground page was not found" not in other_404.text
    assert "data-playground-error" not in other_404.text

    client.cookies.pop("rtc_csrf", None)
    forbidden = client.post(
        add_path("ndps"),
        data={"confirm": "add", "scope": "entire"},
        follow_redirects=False,
    )
    assert forbidden.status_code == 403
    assert "You can’t do that in Playground" in forbidden.text
    assert 'data-playground-error="403"' in forbidden.text
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    client = _authed_client(tmp_path / "five")
    _subscribe(client)
    import constitution_memorizer.playground.routes as pg_routes

    def boom(*_a, **_k):
        raise RuntimeError("forced playground 500")

    monkeypatch.setattr(pg_routes, "build_home_view", boom)
    client.raise_server_exceptions = False
    try:
        crashed = client.get("/playground")
    finally:
        client.raise_server_exceptions = True
    assert crashed.status_code == 500
    assert "Playground hit a problem" in crashed.text
    assert 'data-playground-error="500"' in crashed.text
    assert "Constitution Learn is separate" in crashed.text

    other_500 = client.get("/dashboard")
    assert "Playground hit a problem" not in other_500.text
    assert 'data-playground-error="500"' not in other_500.text

    kill_dir = tmp_path / "kill"
    kill_dir.mkdir()
    app, provider = _mu_app(kill_dir, PLAYGROUND_ENABLED="false")
    killed = TestClient(app)
    _sign_in(killed, provider, USER_A, "d142@example.com")
    _m11_subscribe(killed, USER_A)
    off = killed.get("/playground")
    assert off.status_code == 404
    assert "Playground is unavailable" in off.text or "turned off" in off.text
    assert 'data-playground-gate="unavailable"' in off.text
    dash = killed.get("/dashboard")
    assert dash.status_code == 200
    assert "Playground is unavailable" not in dash.text


def test_d140_playground_service_error_is_styled_503(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    client.app.state.playground = None
    page = client.get("/playground")
    assert page.status_code == 503
    assert "Playground is unavailable" in page.text
    assert 'data-playground-error="503"' in page.text
    dash = client.get("/dashboard")
    assert dash.status_code == 200


def test_t18_act_head_kinds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    guest = _guest_client(tmp_path / "g")
    guest_law = guest.get("/laws/ndps")
    assert 'data-pg-kind="guest"' in guest_law.text
    assert "Sign in to use Playground" in guest_law.text

    free, _repo = _m3_authed(tmp_path / "free")
    free_law = free.get("/laws/ndps")
    assert 'data-pg-kind="subscribe"' in free_law.text
    assert "Subscribe to use Playground" in free_law.text

    paused, _p = _m3_authed(tmp_path / "paused")
    _add_subscription(paused, tier="pro", status="paused")
    paused_law = paused.get("/laws/ndps")
    assert 'data-pg-kind="resume"' in paused_law.text
    assert "Resume Playground" in paused_law.text

    client = _authed_client(tmp_path / "plus")
    _subscribe(client)
    eligible = client.get("/laws/ndps")
    assert 'data-pg-kind="eligible_to_add"' in eligible.text
    assert "+ Add to Playground" in eligible.text

    _confirm_add(client, "ndps")
    active = client.get("/laws/ndps")
    assert 'data-pg-kind="already_active"' in active.text
    assert "Already in Playground" in active.text
    assert "Sections" in active.text
    assert "Start learning" in active.text

    full = _authed_client(tmp_path / "full")
    _subscribe(full, tier="plus")
    _confirm_add(full, "ndps")
    _fill_used(full, 9, monkeypatch)
    full_law = full.get("/laws/bns")
    assert 'data-pg-kind="roster_full"' in full_law.text
    assert "Playground full this month" in full_law.text
    assert "Plan next month" in full_law.text

    pending = _authed_client(tmp_path / "pending")
    _subscribe(pending, status="pending")
    pending_law = pending.get("/laws/ndps")
    assert 'data-pg-kind="pending"' in pending_law.text
    assert "temporarily unavailable" in pending_law.text.lower()

    hist = _authed_client(tmp_path / "hist")
    _subscribe(hist)
    _seed_overlay(hist, "bns")
    saved = hist.get("/laws/bns")
    assert 'data-pg-kind="eligible_to_add"' in saved.text
    assert "Progress saved" in saved.text
    assert "Add to this month" in saved.text


def test_d35_guest_add_sheet_preserves_next(tmp_path: Path):
    client = _guest_client(tmp_path)
    page = client.get(add_path("ndps"), follow_redirects=False)
    assert page.status_code == 200
    assert 'data-pg-kind="guest"' in page.text
    assert "Sign in to use Playground" in page.text
    assert f"/login?next={add_path('ndps')}" in page.text
    assert 'data-hard-gate="true"' in page.text


def test_t20_guest_json_stays_401_on_home_and_learn(tmp_path: Path):
    client = _guest_client(tmp_path)
    home = client.get(
        "/playground", headers={"Accept": "application/json"}, follow_redirects=False
    )
    assert home.status_code == 401
    assert home.json() == {"ok": False, "error": "auth_required"}
    learn = client.get(
        learn_path("ndps", "8"),
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert learn.status_code == 401
    assert learn.json()["error"] == "auth_required"


def test_t21_subscribe_gate_plans_come_from_catalogue(tmp_path: Path):
    client, _repo = _m3_authed(tmp_path)
    home = client.get("/playground")
    _assert_subscribe_gate(home)
    assert "₹199" in home.text
    assert "₹399" in home.text
    assert "₹1199" in home.text
    assert "10 laws / month" in home.text
    assert "30 laws / month" in home.text
    assert "Unlimited laws / month" in home.text
    assert "Plus" in home.text and "Pro" in home.text and "Max" in home.text
    assert "₹149" not in home.text
    assert PLAYGROUND_BILLING_PATH in home.text


def test_t19_halted_and_expired_home_are_read_only(tmp_path: Path):
    halted, _h = _m3_authed(tmp_path / "halted")
    _add_subscription(halted, tier="max", status="halted")
    halted_home = halted.get("/playground")
    assert halted_home.status_code == 200
    assert "Payment retries have stopped" in halted_home.text
    assert "Resume Playground" in halted_home.text
    assert 'data-hard-gate="true"' not in halted_home.text
    halted_learn = halted.get(learn_path("ndps", "8"), follow_redirects=False)
    assert 'data-pg-learn-panel="cloze"' not in halted_learn.text

    expired, _e = _m3_authed(tmp_path / "expired")
    _seed_ndps_overlay(expired)
    sub = _add_subscription(expired, tier="plus", status="active")
    expired.app.state.subscription_charges.upsert_charge(
        provider_payment_id="pay_r3_refund",
        user_subscription_id=sub.id,
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        refund_status="full",
    )
    expired_home = expired.get("/playground")
    assert "Your Playground is paused" in expired_home.text
    assert "Resume Playground" in expired_home.text
    assert 'data-hard-gate="true"' not in expired_home.text


def test_d22_d29_d40_assets(tmp_path: Path):
    css = PLAYGROUND_CSS.read_text()
    assert 'body:has(.PlaygroundShell[data-hard-gate="true"])' in css
    assert "minmax(0, 1fr) 380px" in css
    assert "@media (min-width: 1024px)" in css
    js = PLAYGROUND_JS.read_text()
    assert "function enhanceAddFlow" in js
    assert "[data-pg-add-confirm]" in js
    add = (ROOT / "src/constitution_memorizer/web/templates/playground_add.html").read_text()
    assert 'role="dialog"' in add
    assert 'name="scope" value="entire"' in add
    assert 'name="scope" value="sections"' in add


def test_home_copy_provisions_and_empty_state(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    empty = client.get("/playground")
    assert empty.status_code == 200
    assert "<h1 class=\"pg-home-title\">Playground</h1>" in empty.text or ">Playground<" in empty.text
    assert "Your September Playground is empty" in empty.text
    assert "Add a law" in empty.text
    _confirm_add(client, "ndps")
    home = client.get("/playground")
    assert "In Playground this month" in home.text
    assert "provisions" in home.text.lower() or "Start learning" in home.text
    assert "Verbatim, always." in home.text
    assert PLAYGROUND_BILLING_PATH not in home.text.split("pg-home-title", 1)[-1][:400]


def test_re_add_uses_no_extra_space(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    page = client.get(add_path("ndps"))
    assert "No extra space used." in page.text
    assert 'data-pg-kind="re_add"' in page.text
    used = _used(client)
    back = _confirm_add(client, "ndps")
    assert back.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    assert _used(client) == used


def test_structured_playground_json_is_not_restyled_to_html(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client, status="paused")
    denied = client.post(
        learn_complete_path("ndps", "1"),
        data=_csrf(client),
        headers={"Accept": "application/json"},
    )
    assert denied.status_code == 403
    body = denied.json()
    assert body["ok"] is False
    assert "error" in body
    assert "Playground hit a problem" not in denied.text


def test_access_chain_comment_names_can_view_home_as_home_only():
    src = ACCESS_PY.read_text()
    assert "can_view_home" in src
    assert "GET-home-only" in src or "GET ``/playground`` home only" in src
    assert "require_playground_home" in src
    assert "not access.can_open" in src
    routes = ROUTES_PY.read_text()
    assert "require_playground_open" in routes
    assert "persist_entire_act_selection" in routes
    assert (
        'except Exception:\n                raise HTTPException(status_code=400, detail="invalid_selection")'
        not in routes
    )
    view = (ROOT / "src/constitution_memorizer/playground/view.py").read_text()
    assert "peek_capacity" in view
    service = (
        ROOT / "src/constitution_memorizer/playground/roster/service.py"
    ).read_text()
    assert "def peek_capacity" in service


def test_paused_home_get_does_not_create_or_update_roster_period(tmp_path: Path):
    """Invariant 2: paused GET /playground is persistence-read-only.

    Covers missing current period and an already-created period.
    """

    missing = _authed_client(tmp_path / "missing")
    _subscribe(missing, status="paused")
    assert missing.app.state.roster.get_current_period(USER, now=NOW) is None
    before = _roster_persistence(missing)
    home = missing.get("/playground")
    assert home.status_code == 200
    assert "Resume Playground" in home.text
    assert _roster_persistence(missing) == before
    assert missing.app.state.roster.get_current_period(USER, now=NOW) is None

    existing = _authed_client(tmp_path / "existing")
    sub = _subscribe(existing)
    added = _confirm_add(existing, "ndps")
    assert added.status_code == 303
    existing.app.state.subscriptions.update_subscription_state(
        USER, sub.id, status="paused"
    )
    before_existing = _roster_persistence(existing)
    assert before_existing[0]
    paused_home = existing.get("/playground")
    assert paused_home.status_code == 200
    assert "Playground subscription paused" in paused_home.text
    assert _roster_persistence(existing) == before_existing


def test_halted_and_expired_home_get_do_not_write_roster(tmp_path: Path):
    halted, _h = _m3_authed(tmp_path / "halted")
    _add_subscription(halted, tier="max", status="halted")
    before_halted = _roster_persistence(halted, M3_USER)
    halted_home = halted.get("/playground")
    assert halted_home.status_code == 200
    assert "Payment retries have stopped" in halted_home.text
    assert _roster_persistence(halted, M3_USER) == before_halted
    assert halted.app.state.roster.get_current_period(M3_USER, now=NOW) is None

    expired, _e = _m3_authed(tmp_path / "expired")
    _seed_ndps_overlay(expired)
    sub = _add_subscription(expired, tier="plus", status="active")
    expired.app.state.subscription_charges.upsert_charge(
        provider_payment_id="pay_r3_readonly",
        user_subscription_id=sub.id,
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        refund_status="full",
    )
    before_expired = _roster_persistence(expired, M3_USER)
    expired_home = expired.get("/playground")
    assert "Your Playground is paused" in expired_home.text
    assert _roster_persistence(expired, M3_USER) == before_expired


def test_unsubscribed_public_law_get_does_not_write_roster(tmp_path: Path):
    client, _repo = _m3_authed(tmp_path)
    assert client.app.state.roster.get_current_period(M3_USER, now=NOW) is None
    before = _roster_persistence(client, M3_USER)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    assert 'data-pg-kind="subscribe"' in page.text
    assert _roster_persistence(client, M3_USER) == before
    assert client.app.state.roster.get_current_period(M3_USER, now=NOW) is None
    assert client.app.state.roster.list_periods(M3_USER) == []


def test_peek_capacity_does_not_call_ensure(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    roster = client.app.state.roster
    calls = {"n": 0}
    real = roster.ensure_current_period

    def boom(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("peek_capacity must not ensure_current_period")

    roster.ensure_current_period = boom
    try:
        cap = roster.peek_capacity(USER, None, now=NOW)
    finally:
        roster.ensure_current_period = real
    assert calls["n"] == 0
    assert cap.used == 0
    assert roster.get_current_period(USER, now=NOW) is None


def test_entire_act_unexpected_error_is_playground_500_without_consume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client)
    import constitution_memorizer.playground.routes as pg_routes

    def boom(*_a, **_k):
        raise RuntimeError("forced entire-act prep failure")

    monkeypatch.setattr(pg_routes, "require_playground_law", boom)
    overlay = client.app.state.playground
    before = _roster_consume_state(client)
    client.raise_server_exceptions = False
    try:
        failed = client.post(
            add_path("ndps"),
            data={**_csrf(client), "confirm": "add", "scope": "entire"},
            follow_redirects=False,
        )
    finally:
        client.raise_server_exceptions = True
    assert failed.status_code == 500
    assert "Playground hit a problem" in failed.text
    assert 'data-playground-error="500"' in failed.text
    assert _roster_consume_state(client) == before
    assert overlay.get_item(USER, "ndps") is None
    assert overlay.list_selection(USER, "ndps") == []
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_entire_act_selection_rejected_is_400_without_consume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client)
    import constitution_memorizer.playground.routes as pg_routes

    monkeypatch.setattr(pg_routes, "selection_rows", lambda *_a, **_k: [])
    overlay = client.app.state.playground
    before = _roster_consume_state(client)
    rejected = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add", "scope": "entire"},
        follow_redirects=False,
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "invalid_selection"
    assert _roster_consume_state(client) == before
    assert overlay.get_item(USER, "ndps") is None

