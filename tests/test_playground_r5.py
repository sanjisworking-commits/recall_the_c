"""R5 — Roster/rollover restyle plus Profile, Settings, and account surfaces.

Closes U3 leftover D93–D100, D130 and U7 D107–D114, D137–D138, T26–T27.

Restyle only for roster/rollover: Keep / Remove / Undecided and slot
consumption stay Stage 1. Entitlement snapshot is the subscription
authority; device counts come from the device service. No Razorpay calls
at render time. Alembic head remains 20260927_0027.

Does not start R6, reopen R4, or touch T22–T25 / T42.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

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
)
from tests.test_calendar_routes import USER as GCAL_USER
from tests.test_calendar_routes import _client as _gcal_client
from tests.test_calendar_routes import _connect as _gcal_connect
from tests.test_entitlement_m3b import _add_subscription, _authed_client as _m3_authed
from tests.test_entitlement_m3b import _guest_client
from tests.test_roster_m5a import USER, _authed_client, _confirm_add, _csrf, _subscribe

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
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_alembic_head_unchanged():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]


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
    assert ">Done<" in html
    assert "Browse laws" in html
    assert "RolloverPlanner-aside" in html
    assert "pg-sticky-cta" in html
    assert "data-key=\"keep\"" in html


def test_d100_downgrade_banner(tmp_path: Path):
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


def test_d110_guest_profile_card(tmp_path: Path):
    client = _guest_client(tmp_path)
    page = client.get("/profile", follow_redirects=False)
    assert page.status_code == 200
    assert "data-guest-profile" in page.text
    assert "Guest · Reading only" in page.text
    assert "Sign in" in page.text
    assert "Browse the Bare Acts" in page.text
    posted = client.post("/profile", follow_redirects=False)
    assert posted.status_code in {303, 401, 403}


def test_d111_d113_settings_phone_groups_keep_controls(tmp_path: Path):
    client = _authed_client(tmp_path)
    html = client.get("/settings").text
    assert 'data-settings-group="study"' in html
    assert 'data-settings-group="app"' in html
    assert 'data-settings-group="account"' in html
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


def test_r5_assets_and_no_r6_routes():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    mobile = (STATIC / "mobile.css").read_text(encoding="utf-8")
    assert "playground.css?v=pg15" in base
    assert "mobile.css?v=mob95" in base
    assert ".RosterRow" in css
    assert ".RolloverPlanner-aside" in css
    assert ".pg-sub-chip" in css
    assert "RolloverPlanner" in mobile
    roster_js = (STATIC / "playground.js").read_text(encoding="utf-8")
    assert "data-rollover-form" in roster_js
    assert "value=\"keep\"" in (TEMPLATES / "playground_roster_next.html").read_text(
        encoding="utf-8"
    )
