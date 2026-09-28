"""Milestone 11: production hardening, legacy transition, release gate.

Cross-cutting invariants only. Earlier milestones keep their own unit tests.
Alembic head stays 20260927_0027. Legacy commercial tables are not dropped.
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.admin.playground_diagnostics import (
    commercial_config_status,
    log_commercial_startup_status,
    mask_provider_id,
)
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.devices.models import DEVICE_PLATFORMS, PLATFORM_IOS
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path, law_path, sections_path
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.subscriptions.errors import SubscriptionNetworkError
from constitution_memorizer.subscriptions.razorpay import ProviderSubscription
from constitution_memorizer.web import app as web_app
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import clear_bare_act_cache
from tests.test_playground import _hydrate_spy

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ADMIN = UUID("55555555-5555-4555-8555-555555555555")
USER_A = UUID("11111111-1111-4111-8111-111111111111")
USER_B = UUID("22222222-2222-4222-8222-222222222222")
MEMBER = UUID("66666666-6666-4666-8666-666666666666")

# Explicit review of every hosted state-changing route (M1–M10 + M11).
# protection is the live mechanism, not a wish. New mutations must be added
# here with their protection named; silent new POSTs fail this test.
MUTATION_ALLOWLIST: dict[tuple[str, str], str] = {
    ("POST", "/logout"): "require_csrf",
    ("POST", "/welcome"): "rtc_csrf cookie pair",
    ("POST", "/profile"): "rtc_csrf cookie pair",
    ("POST", "/auth/phone/send"): "rtc_csrf cookie pair",
    ("POST", "/auth/phone/verify"): "rtc_csrf cookie pair",
    ("POST", "/onboarding/plan"): "rtc_csrf cookie pair",
    ("POST", "/onboarding/state"): "rtc_csrf cookie pair",
    ("POST", "/settings"): "session + same-origin",
    ("POST", "/settings/learning-plan"): "session + same-origin",
    ("POST", "/api/theme"): "session cookie / guest no-op",
    ("POST", "/api/text-size"): "session cookie / guest no-op",
    ("POST", "/api/report-issue"): "signed-in + optional Turnstile",
    ("POST", "/api/contact"): "signed-in",
    ("POST", "/learn/{unit_id}/seen"): "session same-origin; Constitution",
    ("POST", "/learn/{unit_id}/quiz"): "session same-origin; Constitution",
    ("POST", "/learn/{unit_id}/done"): "session same-origin; Constitution",
    ("POST", "/learn/{unit_id}/again"): "session same-origin; Constitution",
    ("POST", "/learn/{unit_id}/skip"): "session same-origin; Constitution",
    ("POST", "/learn/{unit_id}/reset"): "session same-origin; Constitution",
    ("POST", "/learn/{clause_id}/choose"): "session same-origin; Constitution",
    ("POST", "/learn/{unit_id}/speech/transcribe"): "session same-origin; Constitution",
    ("POST", "/revision/start"): "session same-origin; Constitution",
    ("POST", "/learning/start"): "session same-origin; Constitution",
    ("POST", "/learning/plan-my-day"): "session same-origin; Constitution",
    ("POST", "/learning/plan-my-day/dismiss"): "session same-origin; Constitution",
    ("POST", "/reset"): "session same-origin; local/dev",
    ("PUT", "/browse/article/{article_number}/gloss"): "session same-origin",
    ("DELETE", "/browse/article/{article_number}/gloss"): "session same-origin",
    ("POST", "/memory"): "MEMORY_LOG_ENABLED 404 + session",
    ("POST", "/memory/{entry_id}/notes"): "MEMORY_LOG_ENABLED 404 + session",
    ("POST", "/memory/{entry_id}/done"): "MEMORY_LOG_ENABLED 404 + session",
    ("POST", "/memory/{entry_id}/photo"): "MEMORY_LOG_ENABLED 404 + session",
    ("POST", "/api/billing/order"): "PRICING_ENABLED 404; legacy N-day frozen",
    ("POST", "/api/billing/verify"): "PRICING_ENABLED 404; legacy N-day frozen",
    ("POST", "/billing/subscriptions/create"): "require_csrf_token",
    ("POST", "/billing/subscriptions/change"): "require_csrf_token",
    ("POST", "/billing/subscriptions/cancel"): "require_csrf_token",
    ("POST", "/billing/subscriptions/checkout/complete"): "require_csrf_token",
    ("POST", "/api/billing/subscriptions/webhook/razorpay"): "raw-body HMAC",
    ("POST", "/profile/security/devices/{device_id}/remove"): "require_csrf",
    ("POST", "/playground/roster/next"): "rtc_csrf fail-closed when session",
    ("POST", "/playground/laws/{law_id}/add"): "rtc_csrf fail-closed when session",
    ("POST", "/playground/roster/{law_id}/remove"): "rtc_csrf fail-closed when session",
    ("POST", "/playground/laws/{law_id}/sections"): "rtc_csrf fail-closed when session",
    (
        "POST",
        "/playground/laws/{law_id}/source-review/sections/{number}/reviewed",
    ): "rtc_csrf fail-closed when session",
    (
        "POST",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}/start",
    ): "rtc_csrf fail-closed when session",
    (
        "POST",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}/complete",
    ): "rtc_csrf fail-closed when session",
    (
        "POST",
        "/playground/laws/{law_id}/sections/{number}/learn/test/quiz",
    ): "rtc_csrf fail-closed when session",
    ("POST", "/admin/users/{user_id}/grants"): "require_admin + require_csrf",
    ("POST", "/admin/grants/{grant_id}/revoke"): "require_admin + require_csrf",
    ("POST", "/admin/users/{user_id}/devices/reset"): "require_admin + require_csrf",
    (
        "POST",
        "/admin/users/{user_id}/devices/clear-replacement-limit",
    ): "require_admin + require_csrf",
    (
        "POST",
        "/admin/users/{user_id}/subscription/reconcile",
    ): "require_admin + require_csrf",
    ("POST", "/admin/reports/{report_id}/status"): "require_admin + require_csrf",
    ("POST", "/admin/contact/{message_id}/status"): "require_admin + require_csrf",
    ("POST", "/admin/content"): "require_admin + require_csrf",
    ("POST", "/admin/preview"): "require_admin + require_csrf",
    ("POST", "/admin/preview/clear"): "require_admin + require_csrf",
    ("POST", "/calendar/google/disconnect"): "rtc_csrf cookie pair",
    ("POST", "/calendar/google/retry"): "rtc_csrf cookie pair",
    ("POST", "/calendar/google/preferences"): "rtc_csrf cookie pair",
}

DOC_FILES = (
    "docs/LEGACY_COMMERCIAL_TRANSITION.md",
    "docs/PLAYGROUND_PRODUCTION_ROLLOUT.md",
    "docs/PLAYGROUND_M11_REPORT.md",
    "docs/PLAYGROUND_DELIVERY_TRACKER.md",
    "docs/PLAYGROUND.md",
    "docs/PAYMENT_ENTITLEMENT_AUDIT.md",
    "docs/law-loading.md",
)


@pytest.fixture(autouse=True)
def _fresh_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(**overrides) -> MultiUserSettings:
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
        "ADMIN_ENABLED": "false",
        "PRICING_ENABLED": "false",
        "PLAYGROUND_ENABLED": "true",
        "ARTICLE_ENTITLEMENTS_ENABLED": "true",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _mu_app(tmp_path: Path, **setting_overrides):
    provider = FakeAuthProvider()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(**setting_overrides),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    return app, provider


def _sign_in(client: TestClient, provider: FakeAuthProvider, user_id: UUID, email: str):
    provider.seed_google_user(user_id=user_id, email=email, display_name=email)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    return client.cookies.get("rtc_csrf") or ""


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _subscribe(client: TestClient, user_id: UUID, *, tier: str = "plus", status: str = "active", **extra):
    return client.app.state.subscriptions.create_subscription_record(
        user_id,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
        **extra,
    )


def _admin_client(tmp_path: Path) -> tuple[TestClient, ProgressRepository]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=ADMIN, email="admin@recall.app", display_name="Sanjana"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(ADMIN_ENABLED="true"),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(ADMIN), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()
    return client, repo


def _seed_member(repo: ProgressRepository, user_id: UUID = MEMBER) -> None:
    now = datetime.now(timezone.utc).isoformat()
    repo.conn.execute(
        """
        INSERT INTO user_profile (
            user_id, display_name, avatar_url, created_at, updated_at,
            email, phone, last_sign_in_at
        ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?)
        """,
        (str(user_id), "Ananya Rao", now, now, "ananya@example.com", None, now),
    )
    repo.conn.commit()


def _mutation_routes(app) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.router.routes:
        inners = (
            list(route.original_router.routes)
            if type(route).__name__ == "_IncludedRouter"
            else [route]
        )
        for inner in inners:
            methods = set(getattr(inner, "methods", None) or [])
            path = getattr(inner, "path", "") or ""
            for method in sorted(methods & {"POST", "PUT", "PATCH", "DELETE"}):
                found.add((method, path))
    return found


def test_alembic_head_unchanged_and_one_head():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]
    versions = ROOT / "alembic" / "versions"
    assert not list(versions.glob("*0028*"))


def test_m11_does_not_drop_legacy_tables():
    versions = ROOT / "alembic" / "versions"
    forbidden = (
        "drop table user_free_articles",
        "drop table access_grants",
        "drop table billing_orders",
        "drop table if exists user_free_articles",
        "drop table if exists access_grants",
        "drop table if exists billing_orders",
    )
    for path in sorted(versions.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
                source = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
                lowered = source.lower()
                if EXPECTED_HEAD in path.name or "0027" in path.name:
                    for phrase in forbidden:
                        assert phrase not in lowered, path.name
                # Later additive revisions (none expected) also must not drop.
                if re.search(r"2026092[89]|2026093|_0028|_0029", path.name):
                    for phrase in forbidden:
                        assert phrase not in lowered, path.name


def test_ios_platform_remains_accepted():
    assert "ios" in DEVICE_PLATFORMS
    assert PLATFORM_IOS == "ios"


def test_authorization_order_hydrates_after_roster_gate():
    source = inspect.getsource(web_app.create_app)
    access_src = (ROOT / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    routes_src = (ROOT / "src/constitution_memorizer/playground/routes.py").read_text(
        encoding="utf-8"
    )
    assert "require_playground_open" in access_src
    assert "require_law_active_this_period" in access_src
    law_fn = routes_src.split("async def playground_law")[1].split("async def ")[0]
    assert law_fn.find("require_law_active_this_period") < law_fn.find(
        "require_playground_law"
    )
    gate = routes_src.split("def _gate_learn")[1].split("\n    @router.")[0]
    assert gate.find("require_law_active_this_period") < gate.find(
        "require_playground_law"
    )
    assert "create_playground_router" in source


def test_guest_and_free_blocked_playground_hydrates_zero_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    app, provider = _mu_app(tmp_path)
    guest = TestClient(app)
    assert guest.get("/playground", follow_redirects=False).status_code == 303
    assert hydrated == []
    _sign_in(guest, provider, USER_A, "a@example.com")
    blocked = guest.get("/playground")
    assert blocked.status_code == 200
    assert "data-playground-gate" in blocked.text
    law = guest.get(law_path("ndps"), follow_redirects=False)
    assert law.status_code in {200, 303}
    add = guest.post(add_path("ndps"), data=_csrf(guest), follow_redirects=False)
    assert add.status_code in {200, 303, 403}
    assert hydrated == []


def test_signed_in_free_has_full_constitution_despite_legacy_flag(tmp_path: Path):
    app, provider = _mu_app(tmp_path, ARTICLE_ENTITLEMENTS_ENABLED="true")
    client = TestClient(app)
    _sign_in(client, provider, USER_A, "a@example.com")
    page = client.get("/learn/clause-1")
    assert page.status_code == 200
    assert 'data-locked-modes=""' in page.text or "data-locked-modes=\"\"" in page.text
    for mode in ("read", "cloze", "letters", "type", "recite", "test"):
        resp = client.get(f"/learn/clause-1?mode={mode}")
        assert resp.status_code == 200
        assert 'class="locked-mode"' not in resp.text
    seen = client.post(
        "/learn/clause-1/seen",
        data={"mode": "type"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert seen.status_code == 200
    playground = client.get("/playground")
    assert "data-playground-gate" in playground.text
    assert "View Playground plans" in playground.text or "Subscribe" in playground.text or "billing/subscriptions" in playground.text


def test_historical_duration_buyer_is_not_auto_subscribed(tmp_path: Path):
    app, provider = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client, provider, USER_A, "a@example.com")
    repo = client.app.state.engine.repo
    ends = datetime.now(timezone.utc) + timedelta(days=300)
    repo.create_billing_order(
        USER_A, order_id="order_legacy", plan_days=365, amount_paise=99900
    )
    assert repo.mark_billing_order_paid(
        USER_A,
        order_id="order_legacy",
        payment_id="pay_legacy",
        grant_id="grant_legacy",
        access_ends_at=ends.isoformat(),
    )
    learn = client.get("/learn/clause-1?mode=type")
    assert learn.status_code == 200
    assert 'class="locked-mode"' not in learn.text
    recite = client.get("/learn/clause-1?mode=recite")
    assert recite.status_code == 200
    assert 'class="locked-mode"' not in recite.text
    playground = client.get("/playground")
    assert "data-playground-gate" in playground.text
    assert client.app.state.subscriptions.get_current_subscription(USER_A) is None
    add = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add"},
        follow_redirects=False,
    )
    assert add.status_code in {200, 303, 403}
    overlay = app.state.playground.list_selection(USER_A, "ndps")
    assert not overlay


def test_legacy_checkout_hidden_when_pricing_disabled(tmp_path: Path):
    app, provider = _mu_app(tmp_path, PRICING_ENABLED="false")
    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    assert 'href="/pricing"' not in home.text
    assert 'href="/subscribe' not in home.text
    assert client.get("/pricing").status_code == 404
    assert client.get("/subscribe/confirm").status_code == 404
    _sign_in(client, provider, USER_A, "a@example.com")
    dash = client.get("/dashboard")
    assert 'href="/pricing"' not in dash.text
    for path in ("/browse", "/learn", "/settings", "/profile", "/learn/clause-1"):
        page = client.get(path)
        assert page.status_code == 200, path
        assert 'href="/pricing"' not in page.text, path
        assert 'href="/subscribe' not in page.text, path
    billing = client.get("/billing/subscriptions")
    assert billing.status_code == 200
    text = billing.text.lower()
    assert "plus" in text and "pro" in text and "max" in text
    assert "₹199" in billing.text
    assert "365-day" not in billing.text
    assert "180-Day" not in billing.text


def test_kill_switch_404s_playground_and_preserves_constitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    app, provider = _mu_app(tmp_path, PLAYGROUND_ENABLED="false")
    client = TestClient(app)
    _sign_in(client, provider, USER_A, "a@example.com")
    _subscribe(client, USER_A)
    assert client.get("/playground").status_code == 404
    assert client.get("/playground/roster").status_code == 404
    assert client.get(law_path("ndps")).status_code == 404
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert 'href="/playground"' not in dash.text
    learn = client.get("/learn/clause-1")
    assert learn.status_code == 200
    laws = client.get("/laws")
    assert laws.status_code == 200
    assert client.get("/billing/subscriptions").status_code == 200
    assert hydrated == []
    row = client.app.state.subscriptions.get_current_subscription(USER_A)
    assert row is not None and row.status == "active"


def test_csrf_inventory_covers_every_mutation(tmp_path: Path):
    app, _provider = _mu_app(tmp_path, ADMIN_ENABLED="true")
    found = _mutation_routes(app)
    missing = found - set(MUTATION_ALLOWLIST)
    extra = set(MUTATION_ALLOWLIST) - found
    assert missing == set(), f"unreviewed mutations: {sorted(missing)}"
    assert extra == set(), f"stale allowlist entries: {sorted(extra)}"


def test_playground_mutation_rejects_missing_csrf(tmp_path: Path):
    app, provider = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client, provider, USER_A, "a@example.com")
    _subscribe(client, USER_A)
    client.cookies.pop("rtc_csrf", None)
    denied = client.post(
        add_path("ndps"),
        data={"confirm": "add"},
        follow_redirects=False,
    )
    assert denied.status_code == 403


def test_logout_requires_csrf(tmp_path: Path):
    app, provider = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client, provider, USER_A, "a@example.com")
    denied = client.post("/logout", follow_redirects=False)
    assert denied.status_code == 403
    ok = client.post("/logout", data=_csrf(client), follow_redirects=False)
    assert ok.status_code == 303


def test_cross_user_playground_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    app, provider = _mu_app(tmp_path)
    client_a = TestClient(app)
    client_b = TestClient(app)
    _sign_in(client_a, provider, USER_A, "a@example.com")
    _subscribe(client_a, USER_A)
    preview = client_a.post(add_path("ndps"), data=_csrf(client_a), follow_redirects=False)
    assert preview.status_code in {200, 303}
    added = client_a.post(
        add_path("ndps"),
        data={**_csrf(client_a), "confirm": "add"},
        follow_redirects=False,
    )
    assert added.status_code == 303
    selected = client_a.post(
        sections_path("ndps"),
        data={**_csrf(client_a), "section": "1"},
        follow_redirects=False,
    )
    assert selected.status_code == 303
    provider.google_users.clear()
    _sign_in(client_b, provider, USER_B, "b@example.com")
    _subscribe(client_b, USER_B)
    before = list(hydrated)
    other = client_b.get(law_path("ndps"), follow_redirects=False)
    assert other.status_code in {200, 303, 403}
    mutate = client_b.post(
        sections_path("ndps"),
        data={**_csrf(client_b), "section": "8"},
        follow_redirects=False,
    )
    assert mutate.status_code in {303, 403, 200}
    overlay = app.state.playground
    a_sel = overlay.list_selection(USER_A, "ndps")
    b_sel = overlay.list_selection(USER_B, "ndps")
    assert a_sel
    assert not b_sel
    devices_b = client_b.get("/profile/security/devices")
    assert devices_b.status_code == 200
    assert hydrated[len(before) :] == []


def test_admin_diagnostics_no_hydration_and_masks_provider_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    secret_id = "sub_LIVESECRETVALUE99"
    client.app.state.subscriptions.create_subscription_record(
        MEMBER,
        tier="plus",
        status="active",
        provider_subscription_id=secret_id,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )
    events = client.app.state.webhook_events
    events.reserve_event(
        provider_event_id="evt_1",
        event_name="subscription.charged",
        payload_sha256="abc",
        provider_subscription_id=secret_id,
    )
    page = client.get(f"/admin/users/{MEMBER}")
    assert page.status_code == 200
    assert "Playground commercial" in page.text
    assert "plus" in page.text
    assert secret_id not in page.text
    assert mask_provider_id(secret_id) in page.text
    assert "rtc_device" not in page.text.lower() or "never shown" in page.text
    assert "Reconcile from provider" in page.text
    assert "Playground roster" in page.text
    assert "Subscription webhooks" in page.text
    assert "evt_1" in page.text
    assert "HMAC" in page.text or "hmac" in page.text.lower()
    assert hydrated == []
    roster = client.app.state.roster
    original = roster.ensure_current_period

    def boom(*args, **kwargs):
        raise AssertionError("diagnostics must not create a period")

    roster.ensure_current_period = boom
    again = client.get(f"/admin/users/{MEMBER}")
    assert again.status_code == 200
    roster.ensure_current_period = original


def test_non_admin_diagnostics_404(tmp_path: Path):
    app, provider = _mu_app(tmp_path, ADMIN_ENABLED="true")
    client = TestClient(app)
    _sign_in(client, provider, USER_A, "a@example.com")
    missing = client.get(f"/admin/users/{USER_A}")
    assert missing.status_code == 404
    denied = client.post(
        f"/admin/users/{USER_A}/subscription/reconcile",
        data={**_csrf(client), "reason": "nope"},
        follow_redirects=False,
    )
    assert denied.status_code == 404


def test_reconcile_provider_outage_does_not_write(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    client.app.state.subscriptions.create_subscription_record(
        MEMBER,
        tier="plus",
        status="active",
        provider_subscription_id="sub_abc12345defg",
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )

    class Dead:
        def fetch_subscription(self, _sid):
            raise SubscriptionNetworkError("down")

    client.app.state.subscription_service._client = Dead()
    resp = client.post(
        f"/admin/users/{MEMBER}/subscription/reconcile",
        data={**_csrf(client), "reason": "dashboard mismatch"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from urllib.parse import unquote

    assert "Provider unavailable" in unquote(resp.headers.get("location") or "")
    row = client.app.state.subscriptions.get_current_subscription(MEMBER)
    assert row is not None
    assert row.status == "active"
    assert row.tier == "plus"
    audit = repo.conn.execute(
        "SELECT * FROM admin_audit_log WHERE action = 'reconcile_subscription'"
    ).fetchone()
    assert audit is None


def test_reconcile_success_audits_and_uses_existing_machine(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    stored = client.app.state.subscriptions.create_subscription_record(
        MEMBER,
        tier="plus",
        status="active",
        provider_subscription_id="sub_ok1234567890",
        provider_plan_id="plan_plus",
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )

    class Live:
        def fetch_subscription(self, sid):
            return ProviderSubscription(
                id=sid,
                plan_id="plan_plus",
                status="halted",
                current_start=int(stored.billing_period_start.timestamp()),
                current_end=int(stored.billing_period_end.timestamp()),
                customer_id="cust_1",
                short_url=None,
                has_scheduled_changes=False,
                raw={"id": sid, "status": "halted"},
            )

    client.app.state.subscription_service._client = Live()
    resp = client.post(
        f"/admin/users/{MEMBER}/subscription/reconcile",
        data={**_csrf(client), "reason": "retry halted mandate"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    row = client.app.state.subscriptions.get_current_subscription(MEMBER)
    assert row is not None
    assert row.status == "halted"
    audit = repo.conn.execute(
        "SELECT * FROM admin_audit_log WHERE action = 'reconcile_subscription'"
    ).fetchone()
    assert audit is not None
    assert audit["reason"] == "retry halted mandate"
    assert "sub_ok1234567890" not in (audit["after_state"] or "")


def test_concurrency_corpus_remains_collected():
    m8 = (ROOT / "tests/test_playground_m8.py").read_text(encoding="utf-8")
    assert "test_learned_transition_race" in m8
    assert "test_duplicate_revision_mode_does_not_double_advance" in m8
    for rel, needle in {
        "tests/test_devices_m4a.py": "test_concurrent_registrations_cannot_exceed_cap",
        "tests/test_devices_m4c.py": "test_concurrent_replacements_cannot_exceed_three",
        "tests/test_roster_m5a.py": "test_concurrent_finite_cap_one_roster_full",
        "tests/test_roster_m5b.py": "test_user_isolation_and_concurrency",
        "tests/test_subscription_webhooks.py": "test_concurrent_duplicate_event_id_fetches_once",
        "tests/test_playground_m9.py": "test_stale_review_does_not_mark_newer_version",
    }.items():
        assert needle in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_secret_redaction_and_config_status_are_presence_only():
    settings = _settings(
        RAZORPAY_KEY_SECRET="never-print-me",
        RAZORPAY_WEBHOOK_SECRET="whsec_never",
        SESSION_SECRET="session-never",
        SUPABASE_ANON_KEY="anon-never",
        RAZORPAY_KEY_ID="rzp_test_public",
        RAZORPAY_PLAN_ID_PLUS="plan_plus",
    )
    dumped = repr(settings)
    assert "never-print-me" not in dumped
    assert "whsec_never" not in dumped
    assert "session-never" not in dumped
    assert "anon-never" not in dumped
    status = commercial_config_status(settings)
    assert status["RAZORPAY_KEY_SECRET"] == "configured"
    assert status["RAZORPAY_KEY_ID"] == "configured"
    assert status["RAZORPAY_PLAN_ID_PLUS"] == "configured"
    assert status["RAZORPAY_PLAN_ID_PRO"] == "missing"
    assert status["PLAYGROUND_ENABLED"] == "true"
    assert "never-print-me" not in str(status)

    class _Capture:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def info(self, msg: str, *args: object) -> None:
            self.messages.append(msg % args if args else msg)

        def warning(self, msg: str, *args: object) -> None:
            self.messages.append(msg % args if args else msg)

    captured = _Capture()
    logged = log_commercial_startup_status(settings, captured)
    assert logged["RAZORPAY_KEY_SECRET"] == "configured"
    joined = " ".join(captured.messages)
    assert "never-print-me" not in joined
    assert "whsec_never" not in joined
    assert mask_provider_id("sub_LIVESECRETVALUE99") != "sub_LIVESECRETVALUE99"
    assert "SECRET" not in mask_provider_id("sub_LIVESECRETVALUE99")


def test_no_android_bootstrap_route_invented(tmp_path: Path):
    app, _provider = _mu_app(tmp_path)
    paths = []
    for route in app.router.routes:
        inners = (
            list(route.original_router.routes)
            if type(route).__name__ == "_IncludedRouter"
            else [route]
        )
        for inner in inners:
            paths.append(getattr(inner, "path", "") or "")
    assert "/api/v1/auth/bootstrap" not in paths
    assert "/me" not in paths
    assert "/auth/google/start" in paths


def test_release_docs_contract():
    for rel in DOC_FILES:
        path = ROOT / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        assert text.strip(), rel
    rollout = (ROOT / "docs/PLAYGROUND_PRODUCTION_ROLLOUT.md").read_text(encoding="utf-8")
    for needle in (
        "production database backup",
        "PLAYGROUND_ENABLED",
        "rollback",
        "N-day",
        "Plus",
        "webhook",
        "alembic",
        "20260927_0027",
    ):
        assert needle.lower() in rollout.lower(), needle
    legacy = (ROOT / "docs/LEGACY_COMMERCIAL_TRANSITION.md").read_text(encoding="utf-8")
    for needle in (
        "user_free_articles",
        "access_grants",
        "billing_orders",
        "ARTICLE_ENTITLEMENTS_ENABLED",
        "365",
        "Max",
        "category C",
        "proven unused",
    ):
        assert needle in legacy
    tracker = (ROOT / "docs/PLAYGROUND_DELIVERY_TRACKER.md").read_text(encoding="utf-8")
    assert "Milestone 11 = DONE" in tracker or "Milestone 11" in tracker
    assert "Stage 2 may begin only after" in tracker or "Stage 2 = NOT STARTED" in tracker
    assert "100.0" in tracker or "100 / 100" in tracker or "100.0 / 100" in tracker


def test_access_chain_comment_is_the_only_model():
    access = (ROOT / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    assert "commercial entitlement → allowed device → active current-period law" in access
    assert "Never calls a payment provider" in access


def test_playground_enabled_defaults_true():
    settings = MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        SESSION_SECRET="x",
    )
    assert settings.playground_enabled is True
