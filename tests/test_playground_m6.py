"""Milestone 6: Playground production UX/state integration. Presentation only."""

from __future__ import annotations

from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.devices.token import mint_installation_token
from constitution_memorizer.playground.source import canonical_body_text
from constitution_memorizer.playground.urls import (
    add_path,
    law_path,
    learn_path,
    remove_path,
    roster_next_path,
    sections_path,
)
from constitution_memorizer.web.bare_acts import clear_bare_act_cache, get_bare_act
from tests.test_devices_m4a import (
    _add_subscription as _m4_add_sub,
    _authed_client as _m4_authed,
)
from tests.test_entitlement_m3b import (
    PERIOD_END,
    PERIOD_START,
    _add_subscription as _m3_add_sub,
    _assert_subscribe_gate,
    _authed_client as _m3_authed,
    _guest_client,
)
from tests.test_roster_m5a import (
    NOW,
    USER,
    _authed_client,
    _confirm_add,
    _csrf,
    _hydrate_spy,
    _seed_overlay,
    _subscribe,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260917_0024"

FORBIDDEN_AI = (
    "AI-generated statute",
    "AI version",
    "generated law",
    "generated provision",
    "smart rewrite",
)


def _fill_used(client: TestClient, extra: int, monkeypatch: pytest.MonkeyPatch) -> None:
    roster = client.app.state.roster
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    monkeypatch.setattr(roster_service, "is_playground_eligible_law", wrapped)
    for i in range(extra):
        result = roster.confirm_add_law(USER, f"stub-{i}", snap, now=NOW)
        assert result.ok


def _tabbar(html: str) -> str:
    marker = 'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"'
    assert marker in html
    return html.split(marker, 1)[1].split("</nav>", 1)[0]


def test_signed_in_primary_nav_is_five_destinations(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    page = client.get("/playground")
    assert page.status_code == 200
    html = page.text
    nav = html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]
    for label, href in (
        ("Today", "/dashboard"),
        ("Browse", "/browse"),
        ("Playground", "/playground"),
        ("Calendar", "/calendar"),
        ("Profile", "/profile"),
    ):
        assert label in nav
        assert f'href="{href}"' in nav
    tabbar = _tabbar(html)
    assert 'href="/playground"' in tabbar
    assert 'aria-current="page"' in tabbar
    assert 'aria-hidden="true"' in tabbar
    assert "Design preview" not in html


def test_guest_nav_is_not_the_five_product_tabs(tmp_path: Path):
    client = _guest_client(tmp_path)
    home = client.get("/browse")
    assert home.status_code == 200
    assert 'class="mobile-tabbar is-guest"' in home.text
    guest_bar = home.text.split('class="mobile-tabbar is-guest"', 1)[1].split("</nav>", 1)[0]
    assert ">Playground<" not in guest_bar
    assert "Sign in" in guest_bar
    assert client.get("/playground", follow_redirects=False).status_code == 303


def test_today_calendar_profile_are_not_placeholders(tmp_path: Path):
    client = _authed_client(tmp_path)
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "this prototype does not design" not in dash.text.lower()
    cal = client.get("/calendar")
    assert cal.status_code == 200
    assert "calendar-grid" in cal.text or "cal-m-grid" in cal.text
    profile = client.get("/profile")
    assert profile.status_code == 200
    assert "Profile" in profile.text


def test_plus_home_8_of_10_capacity_and_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="plus")
    _confirm_add(client, "ndps")
    _confirm_add(client, "bns")
    _confirm_add(client, "bnss")
    _fill_used(client, 5, monkeypatch)
    home = client.get("/playground")
    assert home.status_code == 200
    assert "PlaygroundShell" in home.text
    assert "RosterCapacity" in home.text
    assert "8 of 10 laws" in home.text
    assert "2 spaces available" in home.text
    assert "8 /" not in home.text
    assert "My Playground" in home.text
    assert "September" in home.text
    assert "Verbatim, always." in home.text
    assert "Every provision you learn is the Bare Act text, word for word." in home.text
    assert "Browse laws" in home.text
    assert "Manage September" in home.text
    assert "Plan next month" in home.text
    assert "TrustMark" in home.text
    assert "LawCard" in home.text
    assert "In Playground this month" in home.text


def test_plus_home_full_10_of_10(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="plus")
    _confirm_add(client, "ndps")
    _fill_used(client, 9, monkeypatch)
    home = client.get("/playground")
    assert "10 of 10 laws" in home.text
    assert "Playground full for September" in home.text


def test_empty_plus_home(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="plus")
    home = client.get("/playground")
    assert "0 of 10 laws" in home.text
    assert "10 spaces available" in home.text
    assert "Your September Playground is empty" in home.text


def test_pro_and_max_capacity_copy(tmp_path: Path):
    pro = _authed_client(tmp_path / "pro")
    _subscribe(pro, tier="pro")
    _confirm_add(pro, "ndps")
    page = pro.get("/playground")
    assert "1 of 30 laws" in page.text
    assert "29 spaces available" in page.text
    mx = _authed_client(tmp_path / "max")
    _subscribe(mx, tier="max")
    _confirm_add(mx, "ndps")
    max_page = mx.get("/playground")
    assert "1 law this month" in max_page.text
    assert "Unlimited" in max_page.text
    assert "8 /" not in max_page.text


def test_removed_law_still_uses_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    _fill_used(client, 7, monkeypatch)
    client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    home = client.get("/playground")
    assert "8 of 10 laws" in home.text
    assert "Removed this month" in home.text
    assert "space still used" in home.text
    assert "Add back" in home.text
    assert "Progress saved" in home.text


def test_home_and_roster_hydrate_zero_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _seed_overlay(client, "ndps")
    _confirm_add(client, "ndps")
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client.get("/playground")
    client.get("/playground/roster")
    client.get(roster_next_path())
    client.get(add_path("bns"))
    assert hydrated == []


def test_never_added_add_to_playground(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    page = client.get("/laws/ndps")
    assert "Add to Playground" in page.text
    assert add_path("ndps") in page.text
    assert "LawPlaygroundCta" in page.text


def test_active_not_started_and_continue(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get("/laws/ndps")
    assert "In Playground" in page.text
    assert "Start learning" in page.text
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    again = client.get("/laws/ndps")
    assert "Continue" in again.text


def test_historical_saved_progress_copy(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _seed_overlay(client, "bns")
    page = client.get("/laws/bns")
    assert "Progress saved" in page.text
    assert "You studied this law previously." in page.text
    assert "Add it to September to continue where you left off." in page.text
    assert "Add to this month" in page.text
    assert "Unlock again" not in page.text
    assert "Repurchase" not in page.text


def test_full_roster_inactive_plan_next_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="plus")
    _confirm_add(client, "ndps")
    _fill_used(client, 9, monkeypatch)
    page = client.get("/laws/bns")
    assert "Playground full this month" in page.text
    assert "Plan next month" in page.text


def test_guest_law_cta_is_sign_in_not_checkout(tmp_path: Path):
    client = _guest_client(tmp_path)
    page = client.get("/laws/ndps")
    assert "Sign in" in page.text
    assert "/login?next=/laws/ndps" in page.text
    chunk = page.text.split("LawPlaygroundCta", 1)[-1][:800]
    assert "/billing/subscriptions" not in chunk


def test_free_account_law_cta_is_plans_not_constitution_lock(tmp_path: Path):
    client, _repo = _m3_authed(tmp_path)
    page = client.get("/laws/ndps")
    assert "View Playground plans" in page.text
    assert "complete Constitution" in page.text
    assert "free articles" not in page.text.lower()


def test_add_confirm_get_does_not_write_and_requires_post(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    preview = client.get(add_path("ndps"))
    assert preview.status_code == 200
    assert "Add NDPS Act to September?" in preview.text
    assert "This will use 1 of your 10 law spaces for September." in preview.text
    assert "You'll have 9 spaces remaining." in unescape(preview.text)
    assert 'name="csrf_token"' in preview.text
    assert 'role="dialog"' in preview.text
    assert 'aria-modal="true"' in preview.text
    assert client.app.state.playground.get_item(USER, "ndps") is None
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    unconfirmed = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert unconfirmed.status_code == 303
    assert "/playground/roster" in (unconfirmed.headers.get("location") or "")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True


def test_add_confirm_historical_max_full_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    hist = _authed_client(tmp_path / "hist")
    _subscribe(hist)
    _seed_overlay(hist, "bns")
    page = hist.get(add_path("bns"))
    assert "Your saved progress comes with it." in page.text
    mx = _authed_client(tmp_path / "max")
    _subscribe(mx, tier="max")
    max_page = mx.get(add_path("ndps"))
    assert "Add NDPS Act to September Playground?" in max_page.text
    assert "1 of your" not in max_page.text
    full = _authed_client(tmp_path / "full")
    _subscribe(full, tier="plus")
    _confirm_add(full, "ndps")
    _fill_used(full, 9, monkeypatch)
    full_page = full.get(add_path("bns"))
    assert "Playground full this month" in full_page.text
    assert "Plan next month" in full_page.text
    pending = _authed_client(tmp_path / "pending")
    _subscribe(pending, status="pending")
    blocked = pending.get(add_path("ndps"))
    assert "Adding new laws is temporarily unavailable" in blocked.text
    assert "Manage subscription" in blocked.text


def test_remove_confirm_does_not_remove_until_post(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    _seed_overlay(client, "ndps")
    page = client.get(remove_path("ndps"))
    assert page.status_code == 200
    assert "Remove from September" in page.text
    assert "Your progress will be saved." in page.text
    assert "This does not free a law space this month." in page.text
    assert 'role="dialog"' in page.text
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    used_before = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    ).used
    removed = client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert removed.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    used_after = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    ).used
    assert used_after == used_before
    assert client.app.state.playground.get_item(USER, "ndps") is not None
    back = _confirm_add(client, "ndps")
    assert back.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    notice = client.get("/playground/roster?notice=readded&add=ndps")
    assert "NDPS Act is back in September" in notice.text
    assert "No extra space used." in notice.text


def test_pending_permits_same_month_add_back(tmp_path: Path):
    client = _authed_client(tmp_path)
    sub = _subscribe(client, status="active")
    _confirm_add(client, "ndps")
    client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    client.app.state.subscriptions.update_subscription_state(USER, sub.id, status="pending")
    page = client.get(add_path("ndps"))
    assert "Adding new laws is temporarily unavailable" not in page.text
    assert "No extra space used." in page.text
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True


def test_roster_manager_copy_and_sections(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get("/playground/roster")
    assert "RosterManager" in page.text
    assert "September Playground" in page.text
    assert "1 of 10 used" in page.text
    assert "9 remaining" in page.text
    assert "Removing a law saves its progress." in page.text
    assert "Active this month" in page.text
    assert "Plan next month" in page.text
    assert "Manage October" in page.text


def test_rollover_keep_remove_undecided_and_browse(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get(roster_next_path())
    assert page.status_code == 200
    assert "Your October Playground" in page.text
    assert "Keep" in page.text
    assert "Remove" in page.text
    assert "Undecided" in page.text
    assert 'role="radiogroup"' in page.text
    assert 'value="undecided"' in page.text
    assert "Browse laws" in page.text
    assert "RolloverCandidate" in page.text
    assert "No October space. Progress stays saved." in page.text
    assert "Not chosen yet." in page.text


def test_hard_gates_copy_and_ctas(tmp_path: Path):
    guest = _guest_client(tmp_path / "g")
    assert guest.get("/playground", follow_redirects=False).status_code == 303
    free, _repo = _m3_authed(tmp_path / "free")
    _assert_subscribe_gate(free.get("/playground"))
    halted, _r2 = _m3_authed(tmp_path / "halted")
    _m3_add_sub(halted, tier="max", status="halted")
    halted_page = halted.get("/playground")
    assert 'data-playground-gate="payment_halted"' in halted_page.text
    assert "Payment retries have stopped" in halted_page.text
    assert "EntitlementGate" in halted_page.text
    assert "Manage subscription" in halted_page.text
    paused, _r3 = _m3_authed(tmp_path / "paused")
    _m3_add_sub(paused, tier="pro", status="paused")
    paused_page = paused.get("/playground")
    assert "Playground subscription paused" in paused_page.text
    expired, _r4 = _m3_authed(tmp_path / "expired")
    sub = _m3_add_sub(expired, tier="plus", status="active")
    expired.app.state.subscription_charges.upsert_charge(
        provider_payment_id="pay_m6_refund",
        user_subscription_id=sub.id,
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        refund_status="full",
    )
    expired_page = expired.get("/playground")
    assert 'data-playground-gate="paid_period_ended"' in expired_page.text
    assert "Your Playground is paused" in expired_page.text
    assert "View Playground plans" in expired_page.text
    assert "Back to Constitution" in expired_page.text


def test_device_gates_do_not_offer_subscribe(tmp_path: Path):
    client, _repo = _m4_authed(tmp_path)
    _m4_add_sub(client)
    assert client.get("/playground").status_code == 200
    token_b = mint_installation_token()
    token_c = mint_installation_token()
    second = TestClient(client.app)
    start = second.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    second.cookies.set("rtc_device", token_b)
    second.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    second.get("/playground")
    third = TestClient(client.app)
    start3 = third.get("/auth/google/start", follow_redirects=False)
    state3 = start3.cookies.get("rtc_oauth_state")
    third.cookies.set("rtc_device", token_c)
    third.get(
        f"/auth/callback?code=fake-google-code&state={state3}",
        follow_redirects=False,
    )
    blocked = third.get("/playground")
    assert 'data-playground-gate="device_limit"' in blocked.text
    assert "Device limit reached" in blocked.text
    assert "Manage devices" in blocked.text
    assert "Subscribe" not in blocked.text
    assert "Upgrade" not in blocked.text
    assert "Buy Max" not in blocked.text


def test_cancel_upgrade_welcome_banners(tmp_path: Path):
    client = _authed_client(tmp_path)
    sub = _subscribe(client, status="active")
    client.app.state.subscriptions.update_subscription_state(
        USER, sub.id, cancel_at_period_end=True
    )
    home = client.get("/playground")
    assert "Plan ends" in home.text or "Cancels at period end" in home.text
    upgrade = client.get("/playground?notice=upgrade")
    assert "Your Playground now supports" in upgrade.text
    client.app.state.subscriptions.update_subscription_state(
        USER, sub.id, cancel_at_period_end=False, tier="pro",
        provider_metadata={"scheduled_tier": "plus"},
    )
    down = client.get("/playground")
    assert "Pro until" in down.text
    assert "Changes to Plus next billing cycle" in down.text
    _seed_overlay(client, "bns")
    welcome = client.get("/playground?notice=welcome")
    assert "Welcome back" in welcome.text


def test_pending_banner_blocks_new_and_keeps_roster(tmp_path: Path):
    client = _authed_client(tmp_path)
    sub = _subscribe(client, status="active")
    _confirm_add(client, "ndps")
    client.app.state.subscriptions.update_subscription_state(USER, sub.id, status="pending")
    home = client.get("/playground")
    assert "Payment retry in progress" in home.text
    assert "PaymentStateBanner" in home.text
    assert "Continue" in home.text or "Start learning" in home.text
    assert "LawCard" in home.text
    blocked = client.get("/laws/bns")
    assert "Adding new laws is temporarily unavailable" in blocked.text
    assert "Manage subscription" in blocked.text
    assert "Add to Playground" not in blocked.text.split("LawPlaygroundCta", 1)[-1][:800]


def test_canonical_reveal_matches_source_and_has_no_ai_copy(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    workspace = client.get(law_path("ndps"))
    assert "Verbatim, always." in workspace.text
    assert "VERBATIM TEXT" in workspace.text
    assert "CanonicalText" in workspace.text
    assert 'aria-expanded="true"' in workspace.text
    act = get_bare_act("ndps")
    assert act is not None
    section = act.section("1")
    assert section is not None
    assert canonical_body_text(section) in workspace.text
    learn = client.get(learn_path("ndps", "1"))
    assert "VERBATIM TEXT" in learn.text
    for phrase in FORBIDDEN_AI:
        assert phrase.lower() not in workspace.text.lower()
        assert phrase.lower() not in learn.text.lower()


def test_semantic_classes_and_reduced_motion_contract():
    css = (ROOT / "src/constitution_memorizer/web/static/playground.css").read_text()
    for name in (
        "PlaygroundShell",
        "PrimaryTabs",
        "RosterCapacity",
        "LawCard",
        "LawStatusBadge",
        "RolloverCandidate",
        "EntitlementGate",
        "TrustMark",
        "--pg-ink",
    ):
        assert name in css
    assert "prefers-reduced-motion" in css
    assert ".PlaygroundShell a.pg-btn" in css
    assert "color: var(--pg-paper)" in css
    runtime = (ROOT / "src/constitution_memorizer/web/templates/playground_base.html").read_text()
    assert "Playground.dc.html" not in runtime
    assert "support.js" not in runtime


def test_badge_facts_are_not_product_learned():
    src = (ROOT / "src/constitution_memorizer/playground/view.py").read_text()
    assert "Cloze-complete" in src
    assert "not as final Learned" in src


def test_alembic_head_unchanged():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]


def test_no_design_preview_in_runtime_templates():
    templates = ROOT / "src/constitution_memorizer/web/templates"
    for path in templates.rglob("*.html"):
        text = path.read_text()
        assert "Design preview — not part of the product" not in text
