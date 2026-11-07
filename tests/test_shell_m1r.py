"""M1-R — shared shell revision (plan §3.3 / §4.2; owner criteria 2026-11-05).

One signed-in navigation surface per page, one five-tab phone bar driven by the
``shell_*`` flags (D33), the account-tier label from the entitlement snapshot
on every page (M1R-F01, DV-20), and one Google action on the guest gate
(M1R-F02, 5-11). The entitlement flag stays at its ``monthly`` default here:
labels depend on the snapshot, never on the flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.shell import FREE_LABEL, TIER_LABELS, account_status_for_snapshot

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "constitution_memorizer"
BASE = SRC / "web" / "templates" / "base.html"
STYLES = SRC / "web" / "static" / "styles.css"
MOBILE = SRC / "web" / "static" / "mobile.css"
PG_PARTIAL = SRC / "web" / "templates" / "partials" / "playground.html"
PG_CSS = SRC / "web" / "static" / "playground.css"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1")

SHARED_ROUTES = (
    "/dashboard", "/browse", "/browse/part/iii", "/laws", "/laws/ndps", "/laws/uapa",
    "/laws/ndps/section/8", "/playground", "/calendar", "/profile", "/settings",
    "/billing/subscriptions", "/tables", "/search", "/terms",
)
EXPECTED_ACTIVE = {
    "/dashboard": "/dashboard", "/browse": "/browse", "/browse/part/iii": "/browse", "/laws": "/browse",
    "/laws/ndps": "/browse", "/laws/uapa": "/browse", "/laws/ndps/section/8": "/browse",
    "/playground": "/playground", "/calendar": "/calendar", "/profile": "/profile", "/settings": "/profile",
    "/billing/subscriptions": "/playground", "/tables": "/browse", "/search": "/browse", "/terms": None,
}


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false",
        PLAYGROUND_DEVICE_HMAC_SECRET="m1r-test-hmac", PLAYGROUND_DEVICE_LIMIT="2",
    )


def _client(tmp_path: Path, *, sign_in: bool = True) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="m1r@example.com", display_name="Shell Tester")
    client = TestClient(
        create_app(
            units_path=MINI_UNITS, db_path=tmp_path / "unused.db", multiuser=True,
            multiuser_settings=_settings(), auth_provider=provider, session_store=InMemorySessionStore(),
            progress_repo=ProgressRepository(conn), study_materials_dir=tmp_path / "study-materials",
        )
    )
    if sign_in:
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    return client


def _subscribe(client: TestClient, tier: str, *, status: str = "active", start=None, end=None):
    return client.app.state.subscriptions.create_subscription_record(
        USER, tier=tier, status=status,
        billing_period_start=start or datetime(2026, 9, 1, tzinfo=timezone.utc),
        billing_period_end=end or datetime(2026, 10, 1, tzinfo=timezone.utc),
        is_current=True,
    )


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _status(html: str) -> str:
    return _header(html).split('class="account-menu-btn-status">', 1)[1].split("<", 1)[0]


def _bars(html: str) -> list[str]:
    return [chunk.split("</nav>", 1)[0] for chunk in html.split('<nav class="mobile-tabbar')[1:]]


def _active_hrefs(nav: str) -> list[str]:
    out = []
    for piece in nav.split('<a href="')[1:]:
        href = piece.split('"', 1)[0]
        tag = piece.split(">", 1)[0]
        if 'aria-current="page"' in tag:
            out.append(href)
    return out


# ------------------------------------------------------------- the label


class _Snap:
    def __init__(self, **kw):
        self.is_authenticated = True
        self.is_subscribed = False
        self.tier = None
        self.subscription_status = None
        self.playground_block_reason = None
        self.billing_period_end = None
        self.can_open_playground = False
        self.can_consume_new_playground_law = False
        self.__dict__.update(kw)


def test_account_status_label_matrix():
    assert account_status_for_snapshot(_Snap()) == FREE_LABEL == "RecallC Free"
    for tier in ("plus", "pro", "max"):
        snap = _Snap(is_subscribed=True, tier=tier, subscription_status="active", can_open_playground=True)
        assert account_status_for_snapshot(snap) == TIER_LABELS[tier] == f"RecallC {tier.capitalize()}"
    halted = _Snap(tier="plus", subscription_status="halted")
    assert account_status_for_snapshot(halted) == gate_view(reason=BLOCK_PAYMENT_HALTED).title
    expired = _Snap(
        tier="plus", subscription_status="active", playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
        billing_period_end=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    assert account_status_for_snapshot(expired) == gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
    assert "Free account" not in {FREE_LABEL, *TIER_LABELS.values()}


@pytest.mark.parametrize("tier,label", [(None, "RecallC Free"), ("plus", "RecallC Plus"), ("pro", "RecallC Pro"), ("max", "RecallC Max")])
def test_label_is_the_same_on_every_shared_shell_page(tmp_path: Path, tier, label):
    """DV-20 / M1R-F01: the slot reads the snapshot on every page — a Pro user
    is never 'Free account' on Browse, Laws, an Act page or Playground."""

    client = _client(tmp_path / f"label-{tier}")
    if tier:
        _subscribe(client, tier)
    for route in SHARED_ROUTES:
        html = client.get(route, follow_redirects=True).text
        assert _status(html) == label, (route, _status(html))
        assert "Free account" not in _header(html), route


def test_halted_and_expired_keep_their_status_titles(tmp_path: Path):
    halted = _client(tmp_path / "halted")
    _subscribe(halted, "plus", status="halted")
    assert _status(halted.get("/browse").text) == gate_view(reason=BLOCK_PAYMENT_HALTED).title
    expired = _client(tmp_path / "expired")
    _subscribe(expired, "plus", start=datetime(2026, 7, 1, tzinfo=timezone.utc), end=datetime(2026, 8, 1, tzinfo=timezone.utc))
    title = _status(expired.get("/browse").text)
    assert title == gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
    assert title not in {"RecallC Free", "RecallC Plus"}


# --------------------------------------------------------- one nav surface


@pytest.mark.parametrize("tier", [None, "plus", "pro"])
def test_signed_in_pages_render_one_top_nav_and_one_phone_bar(tmp_path: Path, tier):
    client = _client(tmp_path / f"nav-{tier}")
    if tier:
        _subscribe(client, tier)
    for route in SHARED_ROUTES:
        html = client.get(route, follow_redirects=True).text
        assert html.count('class="nav PrimaryTabs PrimaryTabs--top"') == 1, route
        bars = _bars(html)
        assert len(bars) == 1, (route, len(bars))
        assert "data-signed-in-phone-tabs" in bars[0], route
        for legacy in ("data-plus-bareact-phone-tabs", "data-expired-bareact-phone-tabs", "data-signed-in-bareact-phone-tabs", "data-guest-phone-tabs"):
            assert legacy not in html, (route, legacy)
        labels = [piece.split("</svg>", 1)[1].split("</a>", 1)[0].strip() for piece in bars[0].split('<a href="')[1:]]
        assert labels == ["Today", "Browse", "Playground", "Calendar", "Profile"], route
        expected = EXPECTED_ACTIVE[route]
        active = _active_hrefs(bars[0])
        assert active == ([expected] if expected else []), (route, active)
        top = html.split('class="nav PrimaryTabs PrimaryTabs--top"', 1)[1].split("</nav>", 1)[0]
        assert _active_hrefs(top) == ([expected] if expected else []), (route, _active_hrefs(top))


def test_d33_every_act_page_lights_browse_without_a_hardcoded_law(tmp_path: Path):
    client = _client(tmp_path / "d33")
    _subscribe(client, "plus")
    for law in ("ndps", "uapa", "bns", "mtp"):
        bars = _bars(client.get(f"/laws/{law}").text)
        assert len(bars) == 1 and _active_hrefs(bars[0]) == ["/browse"], law
    base = BASE.read_text(encoding="utf-8")
    assert "/laws/ndps" not in base
    assert "_status_gate" not in base and "signed_in_plus_bareact_phone" not in base
    assert "shell_account_status(request)" in base


def test_guest_pages_keep_the_m1_guest_bar(tmp_path: Path):
    client = _client(tmp_path / "guest", sign_in=False)
    for route in ("/browse", "/laws/ndps", "/playground", "/settings", "/search", "/terms"):
        html = client.get(route, follow_redirects=True).text
        bars = _bars(html)
        assert len(bars) == 1 and "data-guest-phone-tabs" in bars[0], route
        assert "data-signed-in-phone-tabs" not in html, route
        assert "account-menu-btn-status" not in html, route


def test_css_hides_every_phone_bar_once_the_desktop_header_exists():
    css = STYLES.read_text(encoding="utf-8")
    block = css.split("@media (min-width: 561px) {", 1)[1]
    rule = block.split(".mobile-tabbar {", 1)[1].split("}", 1)[0]
    assert "display: none !important" in rule
    assert "body.is-guest .mobile-tabbar {\n    display: none !important" not in css  # no longer guest-only
    mobile = MOBILE.read_text(encoding="utf-8")
    # # M1-R close (owner decision 2026-11-06): Settings shows the shared bar for everyone, not only guests.
    assert 'body[data-mscreen="settings"] .mobile-tabbar,\n  body[data-mscreen="search"] .mobile-tabbar {\n    display: grid;' in mobile
    assert 'body.is-guest[data-mscreen="settings"]' not in mobile
    base = BASE.read_text(encoding="utf-8")
    for pin in ("styles.css?v=main92", "mobile.css?v=mob111", "playground.css?v=pg55"):
        assert pin in base


# ---------------------------------------------------- 5-11 one Google action


def test_guest_gate_offers_one_google_action(tmp_path: Path):
    client = _client(tmp_path / "gate", sign_in=False)
    html = client.get("/playground").text
    gate = html.split('data-phone-pg-gate="guest"', 1)[1].split("</section>", 1)[0]
    assert gate.count("pg-guest-gate-signin") == 1
    assert 'href="/auth/google/start?next=%2Fplayground"' in gate
    assert "Continue with Google" in gate
    assert "Create an account" not in gate and "pg-guest-gate-create" not in gate
    assert "<button" not in gate.split("pg-guest-gate-signin", 1)[1].split("</a>", 1)[0]
    macro = PG_PARTIAL.read_text(encoding="utf-8").split("guest_phone_gate", 1)[1].split("{% macro how_it_works", 1)[0]
    assert macro.count("<a ") == 1 and "<form" not in macro and "/login" not in macro
    assert "pg-guest-gate-create" not in PG_CSS.read_text(encoding="utf-8")
