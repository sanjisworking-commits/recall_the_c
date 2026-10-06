"""R5 — Roster/rollover restyle plus Profile, Settings, and account surfaces.

Closes U3 leftover D93–D100, D130 and U7 D107–D114, D137–D138, T26–T27.

Restyle only for roster/rollover: Keep / Remove / Undecided and slot
consumption stay Stage 1. Entitlement snapshot is the subscription
authority; device counts come from the device service. No Razorpay calls
at render time. Alembic head remains 20260927_0027.

Does not start R6, reopen R4, or touch T22–T25 / T42.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from re import findall
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SUBSCRIPTION_PAUSED,
)
from constitution_memorizer.playground.urls import (
    add_path,
    remove_path,
    roster_next_path,
)
from constitution_memorizer.playground.view import (
    device_count_copy,
    playground_subscription_card,
    rollover_submit_label,
)
from tests.test_calendar_routes import USER as GCAL_USER
from tests.test_calendar_routes import _client as _gcal_client
from tests.test_calendar_routes import _connect as _gcal_connect
from tests.test_entitlement_m3b import NOW as M3_NOW
from tests.test_entitlement_m3b import USER as M3_USER
from tests.test_entitlement_m3b import _add_subscription, _authed_client as _m3_authed
from tests.test_entitlement_m3b import _consume_on_roster
from tests.test_entitlement_m3b import _guest_client
from tests.test_entitlement_m3b import _mutate, _seed_legacy, _set_status
from tests.test_roster_m5a import _authed_client, _confirm_add, _csrf, _subscribe

LEGACY_PROFILE_PHRASES = (
    "3 Free Articles",
    "Back on Free",
    "Unlock every Article",
    "Recall pass",
    "subscription.plan_days",
    "Free Articles you have claimed",
)


def _rollover_cta_labels(html: str) -> list[str]:
    return findall(r"data-rollover-submit[^>]*>([^<]+)<", html)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
STATIC = ROOT / "src/constitution_memorizer/web/static"


def _snapshot(**overrides) -> SimpleNamespace:
    base = dict(
        is_authenticated=True,
        is_subscribed=True,
        admin_override=False,
        tier="plus",
        playground_block_reason=None,
        playground_law_limit=10,
        billing_period_end=None,
        registered_device_count=1,
        device_limit=2,
        subscription_status="active",
        cancel_at_period_end=False,
        scheduled_tier=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_alembic_head_unchanged():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]


def test_create_app_import_does_not_cycle():
    from constitution_memorizer.web.app import create_app

    assert callable(create_app)


def test_t26_subscription_card_chips_and_device_copy():
    active = playground_subscription_card(_snapshot())
    assert active.show is True
    assert active.chip == "ACTIVE"
    assert active.stat_big == "10"
    paused = playground_subscription_card(
        _snapshot(
            playground_block_reason=BLOCK_SUBSCRIPTION_PAUSED,
            is_subscribed=False,
        )
    )
    assert paused.chip == "PAUSED"
    hold = playground_subscription_card(
        _snapshot(
            playground_block_reason=BLOCK_PAYMENT_HALTED,
            is_subscribed=False,
        )
    )
    assert hold.chip == "ON HOLD"
    ended = playground_subscription_card(
        _snapshot(
            playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
            is_subscribed=False,
        )
    )
    assert ended.chip == "PAUSED"
    free = playground_subscription_card(
        _snapshot(
            is_subscribed=False,
            playground_block_reason=BLOCK_NOT_SUBSCRIBED,
            tier=None,
        )
    )
    assert free.chip == ""
    assert free.cta_label == "Subscribe"
    guest = playground_subscription_card(
        _snapshot(is_authenticated=False, is_subscribed=False)
    )
    assert guest.show is False
    pending = playground_subscription_card(
        _snapshot(
            subscription_status="pending",
            playground_block_reason=None,
            is_subscribed=True,
        )
    )
    assert pending.chip == "PENDING"
    assert pending.chip != "ACTIVE"
    assert pending.chip_kind == "pending"
    assert "temporarily unavailable" in pending.body.lower()
    assert "existing playground" in pending.body.lower()
    cancel = playground_subscription_card(
        _snapshot(subscription_status="active", cancel_at_period_end=True)
    )
    assert cancel.chip == "ACTIVE"
    assert "Cancels at the end of the current paid period" in cancel.body
    down = playground_subscription_card(
        _snapshot(
            tier="pro",
            subscription_status="active",
            scheduled_tier="plus",
        )
    )
    assert down.chip == "ACTIVE"
    assert "Changes to Plus at the end of the current paid period" in down.body
    up = playground_subscription_card(
        _snapshot(
            tier="plus",
            subscription_status="active",
            scheduled_tier="max",
        )
    )
    assert up.chip == "ACTIVE"
    assert "Changes to Max at the end of the current paid period" in up.body
    assert device_count_copy(1, 2) == "1 of 2"
    assert device_count_copy(0, 2) == "0 of 2"
    assert "2 of 3" not in device_count_copy(2, 2)


def test_d93_d94_roster_manager_chrome_and_rows(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get("/playground/roster")
    assert page.status_code == 200
    html = page.text
    assert "RosterManager-head" in html
    assert "My Playground" in html
    assert "September Playground" in html
    assert "1 of 10 used" in html
    assert "9 remaining" in html
    assert "Removing a law saves its progress." in html
    assert "Active this month" in html
    assert 'data-roster-active="ndps"' in html
    assert ">Continue<" in html or ">Start learning<" in html
    assert ">Read<" in html
    assert ">Remove<" in html
    assert 'data-pg-sheet' in html
    assert "Removed this month" in html
    assert "Nothing removed this month." in html
    assert "Plan next month" in html
    assert "Manage October" in html
    assert "← Playground" in html


def test_d95_remove_dialog_is_sheet(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get(remove_path("ndps"))
    assert page.status_code == 200
    assert 'data-roster-remove="ndps"' in page.text
    assert 'role="dialog"' in page.text
    assert "Your progress will be saved." in page.text
    assert "does not free a law space" in page.text
    assert "pg-sheet-panel" in page.text
    posted = client.post(
        remove_path("ndps"),
        data=_csrf(client),
        follow_redirects=False,
    )
    assert posted.status_code == 303
    roster = client.get("/playground/roster")
    assert 'data-roster-removed="ndps"' in roster.text
    assert "Add back" in roster.text
    assert "Progress saved" in roster.text


def test_d95_sheet_responsive_class_contract():
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    js = (STATIC / "playground.js").read_text(encoding="utf-8")
    roster = (TEMPLATES / "playground_roster.html").read_text(encoding="utf-8")
    remove = (TEMPLATES / "playground_remove.html").read_text(encoding="utf-8")
    assert "--pg-sheet-anchor: bottom" in css
    assert "max-width: 460px" in css
    assert "safe-area-inset-bottom" in css
    assert "dialog.pg-sheet" in css
    assert "data-pg-sheet" in roster
    assert 'href="/playground/roster/{{ law.law_id }}/remove" data-pg-sheet' in roster
    assert "pg-sheet-panel" in remove
    assert "data-pg-sheet" in js
    assert ".pg-sheet-panel" in js
    assert "showModal" in js
    assert "data-pg-sheet-host" in js
    assert "data-pg-sheet-close" in js


def test_d96_add_law_dialog_has_meter_and_saved_line(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    page = client.get("/playground/roster?add=ndps")
    assert page.status_code == 200
    assert 'data-roster-confirm="ndps"' in page.text
    assert "RosterCapacity" in page.text
    assert "No extra space used." in page.text
    assert "data-saved-progress" in page.text or "saved progress" in page.text.lower()


def test_d97_d100_d130_rollover_key_states_and_copy(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get(roster_next_path())
    assert page.status_code == 200
    html = page.text
    assert "RolloverPlanner" in html
    assert "Your October Playground" in html
    assert "Continue with last month’s laws" in html or "Continue with last month" in html
    assert "RolloverKey" in html
    assert "Keep" in html
    assert "Remove" in html
    assert "Undecided" in html
    assert 'role="radiogroup"' in html
    assert 'value="undecided"' in html
    assert "Continue with these" in html
    assert _rollover_cta_labels(html) == ["Continue with these", "Continue with these"]
    assert "Browse laws" in html
    assert "RolloverPlanner-aside" in html
    assert "pg-sticky-cta" in html
    assert "data-key=\"keep\"" in html


def test_d100_downgrade_banner(tmp_path: Path):
    next_src = (TEMPLATES / "playground_roster_next.html").read_text(encoding="utf-8")
    assert 'data-playground-gate="rollover_adjustment_required"' in next_src
    assert 'data-state="scheduled_downgrade"' in next_src
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    page = client.get(roster_next_path())
    html = page.text
    assert "data-playground-gate=" in html or "RolloverPlanner" in html
    blocked = client.get(roster_next_path(blocked="roster_full"))
    assert 'data-playground-gate="roster_full"' in blocked.text
    locked = client.get(roster_next_path(blocked="active_slot_locked"))
    assert 'data-playground-gate="active_slot_locked"' in locked.text


def test_d130_submit_label_helper():
    assert rollover_submit_label([]) == "Done"
    assert rollover_submit_label([{"target_decision": None}]) == "Continue with these"
    assert rollover_submit_label([{"target_decision": "undecided"}]) == "Continue with these"
    assert (
        rollover_submit_label(
            [{"target_decision": "keep"}, {"target_decision": None}]
        )
        == "Continue with these"
    )
    assert (
        rollover_submit_label(
            [{"target_decision": "keep"}, {"target_decision": "decline"}]
        )
        == "Done"
    )
    assert (
        rollover_submit_label(
            [{"target_decision": "keep"}],
            adjustment_required=True,
        )
        == "Continue with these"
    )


def test_d130_unresolved_has_continue_not_done(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    empty = client.get(roster_next_path())
    assert empty.status_code == 200
    assert "No carry-forward candidates" in empty.text
    assert _rollover_cta_labels(empty.text) == []
    assert "← Playground" in empty.text
    _confirm_add(client, "ndps")
    page = client.get(roster_next_path())
    html = page.text
    labels = _rollover_cta_labels(html)
    assert labels
    assert set(labels) == {"Continue with these"}
    assert "Done" not in labels
    assert html.count("data-rollover-submit") >= 1
    assert 'value="undecided"' in html


def test_d130_mixed_keep_undecided_has_continue_not_done(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    _confirm_add(client, "bns")
    posted = client.post(
        roster_next_path(),
        data={**_csrf(client), "choice_ndps": "keep", "choice_bns": "undecided"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    html = client.get(roster_next_path()).text
    labels = _rollover_cta_labels(html)
    assert labels
    assert set(labels) == {"Continue with these"}
    assert "Done" not in labels
    assert 'data-rollover-candidate="ndps"' in html
    assert 'data-rollover-candidate="bns"' in html


def test_d130_all_resolved_is_done(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    _confirm_add(client, "bns")
    posted = client.post(
        roster_next_path(),
        data={**_csrf(client), "choice_ndps": "keep", "choice_bns": "decline"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    html = client.get(roster_next_path()).text
    labels = _rollover_cta_labels(html)
    assert labels
    assert set(labels) == {"Done"}
    assert "Continue with these" not in labels


def test_d107_d109_profile_subscription_and_devices(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    page = client.get("/profile")
    assert page.status_code == 200
    html = page.text
    assert "data-profile-identity" in html
    assert "data-profile-subscription" in html
    assert 'data-chip="active"' in html
    assert ">ACTIVE<" in html
    assert "data-profile-account" in html
    assert "Learning preferences" in html
    assert "/profile/security/devices" in html
    assert " of " in html
    assert "2 of 3" not in html
    assert "rtc_device" not in html
    assert "current_device_id" not in html
    devices = client.get("/profile/security/devices")
    assert devices.status_code == 200
    assert "data-device-count" in devices.text
    assert " of " in devices.text
    assert "Active devices" in devices.text


def test_d108_paused_and_hold_chips(tmp_path: Path):
    paused, _ = _m3_authed(tmp_path / "paused")
    _add_subscription(paused, tier="pro", status="paused")
    html = paused.get("/profile").text
    assert 'data-chip="paused"' in html
    assert ">PAUSED<" in html
    halted, _ = _m3_authed(tmp_path / "halted")
    _add_subscription(halted, tier="max", status="halted")
    hold = halted.get("/profile").text
    assert 'data-chip="hold"' in hold
    assert ">ON HOLD<" in hold


def test_d108_t26_pending_profile_card(tmp_path: Path):
    client, _repo = _m3_authed(tmp_path / "pending")
    _add_subscription(client, tier="plus", status="active")
    _consume_on_roster(client, "ndps")
    sub = client.app.state.subscriptions.get_current_subscription(M3_USER)
    _set_status(client, sub.id, "pending")
    page = client.get("/profile")
    html = page.text
    assert page.status_code == 200
    assert ">ACTIVE<" not in html
    assert 'data-chip="pending"' in html
    assert ">PENDING<" in html
    assert "temporarily unavailable" in html.lower()
    assert "/billing/subscriptions" in html
    home = client.get("/playground")
    assert home.status_code == 200
    assert "Playground" in home.text
    _mutate(client, add_path("bns"), confirm="add", scope="sections")
    assert client.app.state.playground.get_item(M3_USER, "bns") is None
    snap = client.app.state.entitlement_service.resolve(M3_USER, now=M3_NOW)
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason is None


def test_d108_t26_cancel_and_scheduled_profile_cards(tmp_path: Path):
    cancel_c, _ = _m3_authed(tmp_path / "cancel")
    _add_subscription(cancel_c, tier="plus", status="active", cancel_at_period_end=True)
    cancel_html = cancel_c.get("/profile").text
    assert ">ACTIVE<" in cancel_html
    assert "Cancels at the end of the current paid period" in cancel_html

    down_c, _ = _m3_authed(tmp_path / "down")
    down_sub = _add_subscription(down_c, tier="pro", status="active")
    down_c.app.state.subscriptions.update_subscription_state(
        M3_USER, down_sub.id, provider_metadata={"scheduled_tier": "plus"}
    )
    down_html = down_c.get("/profile").text
    assert ">ACTIVE<" in down_html
    assert "Changes to Plus at the end of the current paid period" in down_html
    assert "RecallC Pro" in down_html

    up_c, _ = _m3_authed(tmp_path / "up")
    up_sub = _add_subscription(up_c, tier="plus", status="active")
    up_c.app.state.subscriptions.update_subscription_state(
        M3_USER, up_sub.id, provider_metadata={"scheduled_tier": "max"}
    )
    up_html = up_c.get("/profile").text
    assert ">ACTIVE<" in up_html
    assert "Changes to Max at the end of the current paid period" in up_html
    assert "RecallC Plus" in up_html


def test_d108_legacy_commercial_profile_ui_absent(tmp_path: Path):
    profile_src = (TEMPLATES / "profile.html").read_text(encoding="utf-8")
    for phrase in LEGACY_PROFILE_PHRASES:
        assert phrase not in profile_src, phrase
    routes = (ROOT / "src/constitution_memorizer/auth/routes.py").read_text(
        encoding="utf-8"
    )
    assert '"subscription": subscription_status(request, eng)' not in routes
    assert "free_article_slots" not in routes
    client, repo = _m3_authed(tmp_path / "legacy")
    _add_subscription(client, tier="plus", status="active")
    _seed_legacy(repo, ends_at=M3_NOW + timedelta(days=30))
    html = client.get("/profile").text
    for phrase in LEGACY_PROFILE_PHRASES:
        assert phrase not in html, phrase
    assert "data-profile-subscription" in html
    assert "Your account and subscription" in html
    assert "Your Recall access, and the Free Articles you have claimed" not in html


def test_d110_guest_profile_card(tmp_path: Path):
    client = _guest_client(tmp_path)
    page = client.get("/profile", follow_redirects=False)
    assert page.status_code == 200
    assert "data-guest-profile" in page.text
    assert "Guest · Reading only" in page.text
    assert "Sign in" in page.text
    assert "Browse the Bare Acts" in page.text
    assert 'name="robots" content="noindex, nofollow"' in page.text
    posted = client.post("/profile", follow_redirects=False)
    assert posted.status_code in {303, 401, 403}


def test_d111_d113_settings_phone_groups_keep_controls(tmp_path: Path):
    settings_src = (TEMPLATES / "settings.html").read_text(encoding="utf-8")
    assert 'data-settings-group="calendar"' in settings_src
    assert "settings-account-row" in settings_src
    assert 'class="settings-group settings-phone-only" data-settings-group="account"' in settings_src
    client = _authed_client(tmp_path)
    html = client.get("/settings").text
    assert 'data-settings-group="study"' in html
    assert 'data-settings-group="app"' in html
    assert 'data-settings-group="account"' in html
    assert "settings-phone-only" in html
    assert "settings-account-row" in html
    assert "settings-verbatim" in html
    assert "data-theme-set" in html
    assert "segmented-btn" in html
    assert "data-plan-autosubmit" in html


def test_t27_d112_d114_reminders_row_and_first_connect_sheet(tmp_path: Path):
    settings = (TEMPLATES / "settings.html").read_text(encoding="utf-8")
    assert "data-settings-reminders" in settings
    assert 'name="reminder_cadence"' in settings
    assert 'action="/calendar/google/preferences"' in settings
    assert "data-gcal-reminder-modal" in settings
    assert 'role="dialog"' in settings
    client, _store, fake, repo = _gcal_client(tmp_path)
    fake.calendar_exists = False
    location = _gcal_connect(client, fake)
    connected = client.get(location)
    assert connected.status_code == 200
    assert "data-settings-reminders" in connected.text
    assert "gcal-reminder-modal" in connected.text
    csrf = client.cookies.get("rtc_csrf")
    saved = client.post(
        "/calendar/google/preferences",
        data={"csrf_token": csrf, "reminder_cadence": "twice"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert repo.get_setting(GCAL_USER, "gcal_reminder_cadence") == "twice"


def test_d137_d138_devices_and_checkout_markup():
    devices = (TEMPLATES / "devices.html").read_text(encoding="utf-8")
    assert "data-device-count" in devices
    assert "data-device-confirm" in devices
    assert "data-device-revoked" in devices
    assert "Remove this device?" in devices
    checkout = (TEMPLATES / "subscription_checkout.html").read_text(encoding="utf-8")
    assert "data-subscription-checkout" in checkout
    assert "Opening secure checkout" in checkout
    assert "Razorpay" in checkout
    assert "GST included" in checkout


def test_r5_assets_and_r6_today_calendar_fields():
    from constitution_memorizer.web.dashboard import TodayUnit

    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    mobile = (STATIC / "mobile.css").read_text(encoding="utf-8")
    assert "playground.css?v=pg24" in base
    assert "playground.js?v=pg8" in base
    assert "mobile.css?v=mob98" in base
    assert ".RosterRow" in css
    assert ".RolloverPlanner-aside" in css
    assert ".RolloverPlanner .pg-sticky-cta" in css
    assert ".pg-sub-chip" in css
    assert "--pg-sheet-anchor: bottom" in css
    assert ".panel.profile-panel" in css
    assert "RolloverPlanner" in mobile
    roster_js = (STATIC / "playground.js").read_text(encoding="utf-8")
    assert "data-rollover-form" in roster_js
    assert "syncRolloverAction" in roster_js
    assert "data-rollover-submit" in (
        TEMPLATES / "playground_roster_next.html"
    ).read_text(encoding="utf-8")
    assert "value=\"keep\"" in (TEMPLATES / "playground_roster_next.html").read_text(
        encoding="utf-8"
    )
    fields = set(TodayUnit.__dataclass_fields__)
    assert "source" in fields
    assert "eyebrow" in fields
    assert "cta_label" in fields
    calendar = (TEMPLATES / "calendar.html").read_text(encoding="utf-8")
    assert "view=week" in calendar
