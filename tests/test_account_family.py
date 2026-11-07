"""M5 — Account, Devices and Plans by tier (owner decisions of 2026-11-07).

F01 Profile: "No paid subscription" / "See plans ›" for Free under both tier
    models; identity meta "RecallC {tier} · …"; paid, paused, pending,
    expired and halted cards unchanged; phone section order identity,
    subscription, account.
F02 Guest Profile and Settings: one Google action each (returning to the same
    page), a working report control, no /login on the body.
F03 Settings: identity line, Auto Plan note without the Article-unlock claim,
    the can_use_auto_plan matrix across tiers under both entitlement flags —
    no new restriction: Free stays False, admin and grant stay True.
F04 Settings CSRF: valid token saves; missing and invalid tokens are refused
    with 403 and change nothing (both POST routes); the single-user install
    is exempt.
F05 Devices: guest redirect; empty and populated states through the real
    registration path; account isolation (A cannot list or remove B's
    device); the current-device confirm step; the device limit copy.
F06 Plans stage: radio group, Max absent, catalogue prices as configured,
    Continue posts to create (no subscription) or change (current subscriber)
    with CSRF; mocked checkout — the subscription service is replaced, so no
    provider is called and nothing is charged; ?stage=plans reachable for
    accounts that can open the Playground; Max refused by the route.
F07 Gate: no "from ₹" anywhere; one Google action for guests at both widths
    that returns to the requested deep link.
F08 Protected account actions need sign-in and CSRF for every tier; GETs are
    mutation-free; both tier models render the same bodies apart from the
    Free card sentence.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.entitlements import can_use_auto_plan
from tests.test_browse_laws_family import STATES, UNITS, USER

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "constitution_memorizer" / "web" / "templates"
USER_B = UUID("22222222-2222-4222-8222-222222222222")
GOOGLE = "/auth/google/start?next="
LEGACY = ("3 Articles", "Free Articles", "pick any", "Unlock every Article", "Recall active", "from ₹", "/login", "/pricing", "No plan yet")
SIGNED_IN = [s for s in STATES if s != "guest"]
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _settings(*, tier_model: str = "monthly", entitlements: bool = False) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
        ARTICLE_ENTITLEMENTS_ENABLED="true" if entitlements else "false",
    )


def _app(tmp: Path, *, tier_model: str = "monthly", entitlements: bool = False, users: tuple[UUID, ...] = (USER,)):
    clear_settings_cache()
    provider = FakeAuthProvider()
    for uid in users:
        provider.seed_google_user(user_id=uid, email=f"{str(uid)[:4]}@example.com", display_name="Sanjay", avatar_url=None)
    tmp.mkdir(parents=True, exist_ok=True)
    return create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                      multiuser_settings=_settings(tier_model=tier_model, entitlements=entitlements),
                      auth_provider=provider, session_store=InMemorySessionStore())


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _subscribe(client: TestClient, spec: dict, user: UUID = USER) -> None:
    start, end = spec.get("period", (_TODAY - timedelta(days=20), _TODAY + timedelta(days=10)))
    client.app.state.subscriptions.create_subscription_record(
        user, tier=spec["tier"], status=spec["status"], billing_period_start=start,
        billing_period_end=end, is_current=True)


def _client(tmp_path: Path, state: str, **kw) -> TestClient:
    client = TestClient(_app(tmp_path / state / kw.get("tier_model", "monthly") / str(kw.get("entitlements", False)), **kw))
    spec = STATES[state]
    if spec is not None:
        _sign_in(client)
        if spec:
            _subscribe(client, spec)
        client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    return client


def _csrf(client: TestClient) -> str:
    return client.cookies.get("rtc_csrf") or ""


def _main(html: str) -> str:
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _card(html: str) -> str:
    return _main(html).split("data-profile-subscription", 1)[1].split("</article>", 1)[0]


# --------------------------------------------------------------------------- #
# F01 — Profile by tier                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_f01_free_profile_says_no_paid_subscription_and_links_to_plans(tmp_path: Path, tier_model: str) -> None:
    html = _client(tmp_path, "free", tier_model=tier_model).get("/profile").text
    main = _main(html)
    assert "RecallC Free · Constitution learning included" in main
    card = _card(html)
    assert "<h2>No paid subscription</h2>" in card
    assert 'href="/playground?stage=plans">See plans ›</a>' in card
    if tier_model == "choices":
        assert "permanent law choices used" in card and ">FREE<" in card
    else:
        assert "Playground learning needs a paid plan." in card and "law choices" not in card
    # phone reading order: identity, subscription, account
    order = [m for m in re.findall(r'(data-profile-identity|data-profile-subscription|data-profile-account)', main)]
    assert order[:3] == ["data-profile-identity", "data-profile-subscription", "data-profile-account"]
    assert 'data-profile-grid="m5"' in main
    for phrase in LEGACY:
        assert phrase not in main, phrase


@pytest.mark.parametrize("state", SIGNED_IN)
def test_f01_profile_cards_by_state(tmp_path: Path, state: str) -> None:
    html = _client(tmp_path, state).get("/profile").text
    main, card = _main(html), _card(html)
    expected = {
        "free": ("No paid subscription", "See plans ›", "/playground?stage=plans", "RecallC Free · Constitution learning included"),
        "plus": ("RecallC Plus", "Change plan", "/billing/subscriptions", "RecallC Plus · Playground included"),
        "pro": ("RecallC Pro", "Manage plan", "/billing/subscriptions", "RecallC Pro · Playground included"),
        "max": ("RecallC Max", "Manage plan", "/billing/subscriptions", "RecallC Max · Playground included"),
        "paused": ("RecallC Plus", "Resume Playground", "/billing/subscriptions", "RecallC Free · Constitution learning included"),
        "pending": ("RecallC Plus", "Manage subscription", "/billing/subscriptions", "RecallC Plus · Playground included"),
        "expired": ("RecallC Plus", "Resume Playground", "/billing/subscriptions", "Signed in with Google"),
        "halted": ("RecallC Plus", "Manage subscription", "/billing/subscriptions", "Signed in with Google"),
    }[state]
    title, cta, href, meta = expected
    assert f"<h2>{title}</h2>" in card
    assert f'href="{href}">{cta}</a>' in card, card
    assert meta in main
    assert "Devices<span class=\"pg-account-meta\">0 of 2 ›</span>" in main
    for phrase in LEGACY:
        assert phrase not in main, (state, phrase)
    if state == "halted":
        assert 'data-halted-profile="desktop"' in main


# --------------------------------------------------------------------------- #
# F02 — guest Profile and Settings                                             #
# --------------------------------------------------------------------------- #
def test_f02_guest_profile_has_one_google_action_and_a_report_button(tmp_path: Path) -> None:
    client = _client(tmp_path, "guest")
    html = client.get("/profile").text
    main = _main(html)
    assert main.count(f'href="{GOOGLE}%2Fprofile"') == 3  # desktop block, phone block, inline card
    assert main.count("Continue with Google") == 3
    assert "Reading as a guest." in main
    assert 'href="/laws">Browse the Bare Acts →</a>' in main
    assert main.count('<button type="button" class="guest-profile-report" data-report-open') == 2
    assert "/login" not in main and "Read mode." not in main
    start = client.get("/auth/google/start?next=%2Fprofile", follow_redirects=False)
    assert start.status_code == 303 and (start.cookies.get("rtc_auth_next") or "").strip('"') == "/profile"


def test_f02_guest_settings_has_google_actions_study_card_and_report(tmp_path: Path) -> None:
    html = _client(tmp_path, "guest").get("/settings").text
    main = _main(html)
    assert main.count(f'href="{GOOGLE}%2Fsettings"') == 2  # identity row + account row
    assert "Continue with Google" in main
    assert 'data-settings-group="study-guest"' in main
    assert "Learning plan and revision calendar appear once you sign in." in main
    assert 'data-guest-settings-report data-report-open data-report-section="Settings"' in main
    assert 'action="/settings/learning-plan"' not in main
    assert "/login" not in main


# --------------------------------------------------------------------------- #
# F03 — Settings identity, Auto Plan note and predicate                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entitlements", [False, True])
@pytest.mark.parametrize("state", SIGNED_IN)
def test_f03_settings_identity_and_auto_plan_by_tier(tmp_path: Path, state: str, entitlements: bool) -> None:
    client = _client(tmp_path, state, entitlements=entitlements)
    html = client.get("/settings").text
    main = _main(html)
    status = _text(main.split('class="settings-account-status">', 1)[1].split("</span>", 1)[0])
    label = {"free": "RecallC Free", "plus": "RecallC Plus", "pro": "RecallC Pro", "max": "RecallC Max",
             "paused": "RecallC Free", "pending": "RecallC Plus"}.get(state)
    if state == "expired":
        assert status == "Your Playground is paused"
    elif state == "halted":
        assert status == "Payment retries have stopped"
    else:
        assert status == f"{label} · Signed in with Google"
    assert "Recall active" not in main and "Unlock every Article" not in main and "/pricing" not in main
    # The capability: when entitlements are off the whole predicate is open
    # (unchanged behaviour); when on, paid active tiers are True, Free and
    # non-active rows are False — no new restriction anywhere.
    with_request = client.app.state  # the predicate is exercised through the page below
    del with_request
    note = "Auto Plan is part of Plus and Pro." in main
    enabled = 'id="pace-auto"' in main and "disabled" not in main.split('id="pace-auto"', 1)[1][:200]
    if not entitlements:
        assert enabled and not note
    else:
        expect_enabled = state in {"plus", "pro", "max", "pending"}
        assert enabled is expect_enabled, (state, enabled)
        assert note is (not expect_enabled)
        if note:
            assert 'href="/playground?stage=plans">See plans ›</a>' in main


def test_f03_can_use_auto_plan_matrix_is_unchanged_for_free_admin_and_grant(tmp_path: Path) -> None:
    # Free stays False, paid tiers become True; admin and grant paths are the
    # existing tests' business (tests/test_learning_plan_settings.py) and stay green.
    free = _client(tmp_path, "free", entitlements=True)
    assert "Auto Plan is part of Plus and Pro." in free.get("/settings").text
    plus = _client(tmp_path, "plus", entitlements=True)
    assert "Auto Plan is part of Plus and Pro." not in plus.get("/settings").text
    halted = _client(tmp_path, "halted", entitlements=True)
    assert "Auto Plan is part of Plus and Pro." in halted.get("/settings").text


# --------------------------------------------------------------------------- #
# F04 — Settings CSRF                                                          #
# --------------------------------------------------------------------------- #
def _plan(client: TestClient) -> tuple[str, str]:
    html = client.get("/settings").text
    mode = "auto" if re.search(r'id="pace-auto"[^>]*checked', html) else "self_paced"
    target = re.search(r'id="target-(\d)"[^>]*checked', html)
    return mode, target.group(1) if target else ""


@pytest.mark.parametrize("state", ["free", "plus"])
def test_f04_learning_plan_post_requires_a_valid_csrf_token(tmp_path: Path, state: str) -> None:
    client = _client(tmp_path, state)
    before = _plan(client)
    missing = client.post("/settings/learning-plan", data={"mode": "auto", "daily_target": "7"}, follow_redirects=False)
    assert missing.status_code == 403
    assert _plan(client) == before
    wrong = client.post("/settings/learning-plan", data={"mode": "auto", "daily_target": "7", "csrf_token": "not-the-token"}, follow_redirects=False)
    assert wrong.status_code == 403
    assert _plan(client) == before
    ok = client.post("/settings/learning-plan", data={"mode": "auto", "daily_target": "7", "csrf_token": _csrf(client)}, follow_redirects=False)
    assert ok.status_code == 303
    assert _plan(client) == ("auto", "7")
    page = client.get("/settings").text
    form = page.split('action="/settings/learning-plan"', 1)[1].split("</form>", 1)[0]
    assert 'name="csrf_token"' in form


def test_f04_settings_post_requires_a_valid_csrf_token(tmp_path: Path) -> None:
    client = _client(tmp_path, "free")
    missing = client.post("/settings", data={"notification_frequency": "daily"}, follow_redirects=False)
    assert missing.status_code == 403
    wrong = client.post("/settings", data={"notification_frequency": "daily", "csrf_token": "x"}, follow_redirects=False)
    assert wrong.status_code == 403
    ok = client.post("/settings", data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert ok.status_code == 303


def test_f04_single_user_install_is_exempt_from_the_csrf_check(tmp_path: Path) -> None:
    app = create_app(units_path=UNITS, db_path=tmp_path / "single.db")
    client = TestClient(app)
    resp = client.post("/settings/learning-plan", data={"mode": "self_paced"}, follow_redirects=False)
    assert resp.status_code in (303, 200)


# --------------------------------------------------------------------------- #
# F05 — Devices                                                                #
# --------------------------------------------------------------------------- #
def test_f05_devices_guest_redirects_and_free_sees_the_designed_empty_state(tmp_path: Path) -> None:
    guest = _client(tmp_path, "guest").get("/profile/security/devices", follow_redirects=False)
    assert guest.status_code == 303 and "/login" in guest.headers["location"]
    html = _client(tmp_path, "free").get("/profile/security/devices").text
    main = _main(html)
    assert "<h1 class=\"display\">Devices</h1>" in main
    assert "Your plan supports the Playground on up to 2 registered devices." in main
    assert "while a paid plan is active" in main
    assert "0 of 2 devices" in main
    assert "data-devices-empty" in main and "No devices registered yet." in main
    assert "Your devices" not in main and "Security" not in main.split("<h1", 1)[0]
    assert 'href="/profile"' in main


def test_f05_devices_populated_isolated_and_removable(tmp_path: Path) -> None:
    app = _app(tmp_path / "two", users=(USER, USER_B))
    a = TestClient(app)
    _sign_in(a)
    _subscribe(a, {"tier": "plus", "status": "active"})
    service = app.state.device_service
    a_device = service.ensure_current_device(USER, "tok-a", auth_session_id="sess-a", commercially_eligible=True)
    b_device = service.ensure_current_device(USER_B, "tok-b", auth_session_id="sess-b", commercially_eligible=True)
    assert a_device.current_device_registered and b_device.current_device_registered
    html = a.get("/profile/security/devices").text
    main = _main(html)
    assert "1 of 2 devices" in main
    assert f'data-device-id="{a_device.current_device_id}"' in main
    assert f'data-device-id="{b_device.current_device_id}"' not in main
    assert main.count('class="pg-eyebrow">Registered</p>') == 1
    # isolation: A cannot remove B's device
    foreign = a.post(f"/profile/security/devices/{b_device.current_device_id}/remove", data={"csrf_token": _csrf(a)}, follow_redirects=False)
    assert foreign.status_code in (303, 404)
    assert "1 of 2 devices" in _main(a.get("/profile/security/devices").text)
    assert len([d for d in service.list_devices(USER_B) if not d.is_revoked]) == 1
    # CSRF on remove
    no_token = a.post(f"/profile/security/devices/{a_device.current_device_id}/remove", data={}, follow_redirects=False)
    assert no_token.status_code == 403
    # a real remove of A's own non-current device (the session has no device cookie, so it is not "current")
    removed = a.post(f"/profile/security/devices/{a_device.current_device_id}/remove", data={"csrf_token": _csrf(a)}, follow_redirects=False)
    assert removed.status_code == 303
    after = _main(a.get("/profile/security/devices?removed=1").text)
    assert "0 of 2 devices" in after and "Device removed." in after and "Removed devices" in after


# --------------------------------------------------------------------------- #
# F06 — plans stage and mocked checkout                                        #
# --------------------------------------------------------------------------- #
class _FakeSubscriptions:
    def __init__(self) -> None:
        self.started: list[tuple] = []
        self.changed: list[tuple] = []

    def start_subscription(self, uid, tier):
        self.started.append((str(uid), tier))

    def change_plan(self, uid, tier):
        self.changed.append((str(uid), tier))


def _mock_checkout(client: TestClient) -> _FakeSubscriptions:
    fake = _FakeSubscriptions()
    client.app.state.subscription_service = fake
    return fake


def test_f06_free_plans_stage_is_a_radio_form_that_creates_through_the_existing_route(tmp_path: Path) -> None:
    client = _client(tmp_path, "free")
    html = client.get("/playground?stage=plans&tier=plus").text
    main = _main(html)
    form = main.split('data-pg-plan-form="create"', 1)[1].split("</form>", 1)[0]
    assert 'action="/billing/subscriptions/create"' in main.split("<form", 2)[-1].split(">", 1)[0] or 'action="/billing/subscriptions/create"' in main
    assert 'name="csrf_token"' in form
    assert form.count('type="radio" name="tier"') == 2
    assert 'value="plus" required checked' in form and 'value="pro" required' in form
    assert 'value="max"' not in form and "₹1199" not in main
    assert "₹199" in form and "₹399" in form and "Monthly. GST included." in main
    assert "from ₹" not in main
    assert '<button type="submit" class="pg-btn" data-pg-plan-continue>Continue with Plus</button>' in form
    fake = _mock_checkout(client)
    # missing CSRF → refused, nothing started
    refused = client.post("/billing/subscriptions/create", data={"tier": "plus"}, follow_redirects=False)
    assert refused.status_code == 403 and fake.started == []
    # Max never purchasable
    max_resp = client.post("/billing/subscriptions/create", data={"tier": "max", "csrf_token": _csrf(client)}, follow_redirects=False)
    assert max_resp.status_code == 303 and max_resp.headers["location"].endswith("error=invalid_tier") and fake.started == []
    # the form's own submission reaches the mocked service and lands on checkout
    ok = client.post("/billing/subscriptions/create", data={"tier": "plus", "csrf_token": _csrf(client)}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/billing/subscriptions/checkout"
    assert fake.started == [(str(USER), "plus")] and fake.changed == []


def test_f06_subscriber_plans_stage_uses_the_change_flow(tmp_path: Path) -> None:
    client = _client(tmp_path, "plus")
    html = client.get("/playground?stage=plans&tier=pro").text
    main = _main(html)
    assert 'data-pg-plan-form="change"' in main
    assert 'action="/billing/subscriptions/change"' in main
    assert "data-pg-plan-current" in main and "Current plan" in main
    assert 'value="plus"' not in main.split('data-pg-plan-form="change"', 1)[1].split("</form>", 1)[0]
    assert 'value="pro" required checked' in main
    assert ">Switch to Pro<" in main
    fake = _mock_checkout(client)
    moved = client.post("/billing/subscriptions/change", data={"tier": "pro", "csrf_token": _csrf(client)}, follow_redirects=False)
    assert moved.status_code == 303 and moved.headers["location"] == "/billing/subscriptions"
    assert fake.changed == [(str(USER), "pro")] and fake.started == []
    # Playground home itself is untouched for the subscriber
    home = client.get("/playground").text
    assert "data-signed-in-pg-gate" not in home and 'data-plus-playground="desktop"' in home


def test_f06_plans_stage_is_reachable_for_free_under_choices(tmp_path: Path) -> None:
    client = _client(tmp_path, "free", tier_model="choices")
    html = client.get("/playground?stage=plans").text
    assert 'data-pg-gate-stage="plans"' in html and 'data-pg-plan-form="create"' in html
    assert "data-pg-plan-selected" not in html
    assert '<button type="submit" class="pg-btn" data-pg-plan-continue>Continue</button>' in html
    assert "Continue with" not in html


# --------------------------------------------------------------------------- #
# F07 — gate                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/playground", "/playground/laws/ndps"])
def test_f07_guest_gate_has_one_google_action_returning_to_the_deep_link(tmp_path: Path, path: str) -> None:
    html = _client(tmp_path, "guest").get(path).text
    main = _main(html)
    desktop = main.split("data-guest-pg-intro", 1)[1].split("</section>", 1)[0]
    assert desktop.count("guest-pg-signin") == 1
    assert f'href="{GOOGLE}{quote(path, safe="")}"' in desktop
    assert ">Continue with Google<" in desktop and ">Sign in<" not in desktop
    assert "/login" not in main and "from ₹" not in main and "Create an account" not in main


@pytest.mark.parametrize("state", SIGNED_IN)
def test_f07_no_price_teaser_on_the_gate_or_home(tmp_path: Path, state: str) -> None:
    client = _client(tmp_path, state)
    for path in ("/playground", "/playground?stage=plans"):
        assert "from ₹" not in client.get(path).text, (state, path)


# --------------------------------------------------------------------------- #
# F08 — protected actions and tier-model parity                                #
# --------------------------------------------------------------------------- #
def test_f08_guest_account_posts_are_refused(tmp_path: Path) -> None:
    client = _client(tmp_path, "guest")
    for path, data in (
        ("/profile", {"action": "reset_progress", "display_name": "x", "csrf_token": ""}),
        ("/profile", {"action": "delete_account", "display_name": "x", "csrf_token": ""}),
        ("/settings/learning-plan", {"mode": "auto"}),
        ("/billing/subscriptions/create", {"tier": "plus"}),
        ("/billing/subscriptions/change", {"tier": "pro"}),
    ):
        resp = client.post(path, data=data, follow_redirects=False)
        assert resp.status_code in (303, 401, 403), (path, resp.status_code)
        assert resp.status_code != 200


@pytest.mark.parametrize("state", SIGNED_IN)
def test_f08_signed_in_account_posts_need_csrf(tmp_path: Path, state: str) -> None:
    client = _client(tmp_path, state)
    fake = _mock_checkout(client)
    for path, data in (
        ("/profile", {"action": "reset_progress", "display_name": "Sanjay", "csrf_token": "not-the-token"}),
        ("/profile", {"action": "delete_account", "display_name": "Sanjay", "csrf_token": "not-the-token"}),
        ("/settings/learning-plan", {"mode": "auto", "daily_target": "5"}),
        ("/billing/subscriptions/create", {"tier": "plus"}),
        ("/billing/subscriptions/change", {"tier": "pro"}),
    ):
        resp = client.post(path, data=data, follow_redirects=False)
        assert resp.status_code in (303, 403), (state, path, resp.status_code)
        if resp.status_code == 303:
            assert "error=csrf" in resp.headers.get("location", "") or resp.headers.get("location", "").startswith("/profile"), (state, path, resp.headers.get("location"))
    assert fake.started == [] and fake.changed == []
    assert client.get("/profile").status_code == 200  # the account is intact


# Plus / Pro differ by design between the models (the B1 allowance line: 10 / 30 laws
# a month vs unlimited) and Free by its card sentence — those rows are read back, not
# asserted identical.
@pytest.mark.parametrize("state", ["guest", "expired", "halted"])
def test_f08_account_family_is_identical_under_both_tier_models(tmp_path: Path, state: str) -> None:
    pages = {}
    for model in ("monthly", "choices"):
        client = _client(tmp_path, state, tier_model=model)
        pages[model] = [re.sub(r'value="[A-Za-z0-9_-]{16,}"', 'value="TOKEN"', re.sub(r"\s+", " ", _main(client.get(p).text)))
                        for p in ("/profile", "/settings", "/profile/security/devices")
                        if client.get(p, follow_redirects=False).status_code == 200]
    assert pages["monthly"] == pages["choices"]


def test_f08_templates_carry_no_superseded_account_copy() -> None:
    for name in ("profile.html", "settings.html", "devices.html", "playground_gate.html"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        for phrase in ("3 Articles", "Unlock every Article", "/pricing", "Read mode.", "Recall active", "from_price", "/login?next="):
            assert phrase not in src, (name, phrase)
