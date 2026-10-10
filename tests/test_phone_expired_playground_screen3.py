"""Phone Expired Playground home Screen 03 (CTA map expired/03-screen).

Authorized: ChatGPT. Authenticated expired GET /playground at 390x844.
Desktop Expired Screen 06 is the functional contract. Live heading, live
month_count_label, live paused banner, live Resume Playground → billing.
Empty and enrolled are both real. Map "2 laws" / "Plan ended 12 August" /
Learn are presentation losses. Guest, Free, Plus, Halted, Pro, Expired 01–02,
and desktop 06 stay unchanged.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.access import PlaygroundAccess
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
    playground_today,
)
from constitution_memorizer.playground.urls import (
    add_path,
    home_path,
    law_path,
    roster_path,
    sections_path,
)
from constitution_memorizer.playground.view import (
    CONSTITUTION_HOME_PATH,
    PLAYGROUND_BILLING_PATH,
    build_home_view,
    gate_view,
)
from constitution_memorizer.web.app import create_app
from tests.conftest import PLAYGROUND_TEST_NOW
from tests.test_playground_m8 import _seed_progress

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
PARTIALS = ROOT / "src/constitution_memorizer/web/templates/partials/playground.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
LIVE_COPY = LIVE_GATE.lines
LOCATOR = "ndps:section:8:clause:a"
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlimited",
    "Unlock all",
    "Free plan",
    "All 3 slots",
    "2 laws",
    "12 Aug",
    "Plan ended",
    "Your September Playground is empty",
    "Add laws you want to learn this month.",
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
    )


def _mu_app(tmp_path: Path, *, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _subscribe(
    client: TestClient,
    *,
    tier: str = "plus",
    status: str = "active",
    period_start: datetime = ACTIVE_START,
    period_end: datetime = ACTIVE_END,
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        is_current=True,
    )


def _expire(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )


def _seed_roster(client: TestClient, *law_ids: str) -> None:
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    for law_id in law_ids:
        result = roster._repo.consume_law(
            USER,
            period_start=start,
            law_id=law_id,
            law_limit=10,
            allow_new=True,
        )
        assert result.ok, result.status
        assert roster.is_law_active_this_period(USER, law_id) is True


def _confirm_add(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "sections"
    preview = client.post(add_path(law_id), data=_csrf(client), follow_redirects=False)
    if preview.status_code == 303 and "/playground/roster" in (
        preview.headers.get("location") or ""
    ):
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    if preview.status_code == 200:
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    return preview


def _seed_ndps_progress_then_expire(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    selected = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "unit": LOCATOR, "section": "8"},
        follow_redirects=False,
    )
    assert selected.status_code in {200, 303}
    overlay = client.app.state.playground
    locators = [s.source_locator for s in overlay.list_selection(USER, "ndps")]
    assert locators, "section selection did not persist"
    seed_locator = LOCATOR if LOCATOR in locators else locators[0]
    day = playground_today()
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        seed_locator,
        status="review",
        interval_days=1,
        next_revision=day.isoformat(),
        times_completed=1,
        learned_at=day.isoformat(),
    )
    _expire(client)


def _expired_empty(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _expire(client)
    return client


def _expired_enrolled(tmp_path: Path, *law_ids: str) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _seed_roster(client, *law_ids)
    _expire(client)
    return client


def _phone(html: str) -> str:
    return html.split("data-expired-pg-phone", 1)[1].split("<aside", 1)[0]


def _desk(html: str) -> str:
    return html.split("data-expired-pg-desktop", 1)[1].split(
        "data-expired-pg-phone", 1
    )[0]


def _tabs(html: str) -> str:
    start = html.find('class="mobile-tabbar')
    assert start != -1
    return html[start:].split("</nav>", 1)[0]


def _home_view(client: TestClient):
    snap = client.app.state.entitlement_service.resolve(USER)
    access = PlaygroundAccess(
        user_id=USER,
        snapshot=snap,
        can_open=snap.can_open_playground,
        can_consume_new_law=snap.can_consume_new_playground_law,
        local_owner=False,
        can_view_home=True,
    )
    return build_home_view(
        access=access,
        roster=client.app.state.roster,
        overlay=client.app.state.playground,
    )


def _facts(client: TestClient) -> dict:
    roster = client.app.state.roster
    overlay = client.app.state.playground
    start, _end = playground_month_bounds()
    period = roster._repo.get_period(USER, start)
    cap = roster.peek_capacity(USER, client.app.state.entitlement_service.resolve(USER))
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "status": getattr(
            client.app.state.subscriptions.get_current_subscription(USER),
            "status",
            None,
        ),
        "period": None if period is None else (period.period_start, period.law_limit),
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status, p.times_completed, p.next_revision)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
    }


def _assert_generic_playground_tabs(html: str) -> None:
    assert "data-expired-pg-phone-tabs" not in html
    assert "data-expired-bareact-phone-tabs" not in html
    assert "data-plus-playground-phone-tabs" not in html
    assert html.count('class="mobile-tabbar') == 1
    tabs = _tabs(html)
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label in tabs
    playground = tabs.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in playground
    assert 'aria-current="page"' in playground
    assert tabs.count("is-active") == 1


def test_phone_expired_empty_home_is_readonly_not_gate(tmp_path: Path) -> None:
    client = _expired_empty(tmp_path)
    start, _end = playground_month_bounds()
    assert client.app.state.roster._repo.get_period(USER, start) is None
    before = _facts(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    home = _home_view(client)
    assert home.read_only is True
    assert home.empty is True
    assert home.month_count_label == f"0 of 10 · {MONTH}"
    page = client.get("/playground")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-hard-gate="true"' not in html
    assert "is-readonly" in html
    assert 'data-expired-playground="desktop"' in html
    assert "data-expired-pg-phone" in html
    assert "data-signed-in-pg-gate" not in html
    assert "data-guest-pg-intro" not in html
    assert "data-plus-playground-phone" not in html
    phone = unescape(_phone(html))
    assert 'class="pg-home-title' in html
    assert ">Playground<" in phone
    assert f"0 of 10 · {MONTH}" in phone
    assert home.month_count_label in phone
    assert f">{LIVE_HEADING}<" in phone or f"<strong>{LIVE_HEADING}</strong>" in phone
    for line in LIVE_COPY:
        assert line in phone
    assert ">Resume Playground<" in phone
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in phone
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert phone.count("PaymentStateBanner") == 1
    assert 'data-state="expired"' in phone
    assert "LawCard" not in phone
    assert 'data-law-id="' not in phone
    assert ">Learn<" not in phone
    assert ">Continue<" not in phone
    assert ">Start learning<" not in phone
    assert ">Add a law<" not in phone
    assert "Manage " + MONTH not in phone
    assert 'data-pg-sheet' not in phone
    for phrase in INVENTED:
        assert phrase not in phone, phrase
    _assert_generic_playground_tabs(html)
    assert _facts(client) == before
    assert client.app.state.roster._repo.get_period(USER, start) is None
    assert html.find("pg-home-title") < html.find("PaymentStateBanner")
    assert html.find("pg-home-month") < html.find("PaymentStateBanner")


def test_phone_expired_ndps_only_uses_live_resume_card(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_progress_then_expire(client)
    before = _facts(client)
    assert before["active"] == ("ndps",)
    assert before["progress"]
    home = _home_view(client)
    assert home.read_only is True
    assert home.empty is False
    assert home.month_count_label == f"1 of 10 · {MONTH}"
    html = unescape(client.get("/playground").text)
    phone = unescape(_phone(html))
    assert f"1 of 10 · {MONTH}" in phone
    assert home.month_count_label in phone
    assert 'data-law-id="ndps"' in phone
    assert 'data-law-id="bns"' not in html
    ndps = phone.split('data-law-id="ndps"', 1)[1].split("</article>", 1)[0]
    actions = ndps.split("pg-card-actions--phone", 1)[1].split(
        "pg-card-actions--desktop", 1
    )[0]
    assert ">Resume Playground<" in actions
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in actions
    assert "data-pg-sheet" not in actions
    assert ">Learn<" not in actions
    assert ">Continue<" not in actions
    assert ">Start learning<" not in actions
    assert _facts(client) == before
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections.text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in workspace.text
    posted = client.post(
        add_path("bns"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    assert _facts(client) == before


def test_phone_expired_ndps_bns_enrolled_cards_are_real(tmp_path: Path) -> None:
    client = _expired_enrolled(tmp_path, "ndps", "bns")
    before = _facts(client)
    assert before["active"] == ("bns", "ndps")
    home = _home_view(client)
    assert home.month_count_label == f"2 of 10 · {MONTH}"
    html = unescape(client.get("/playground").text)
    phone = unescape(_phone(html))
    assert home.month_count_label in phone
    assert f"2 of 10 · {MONTH}" in phone
    assert 'data-law-id="ndps"' in phone
    assert 'data-law-id="bns"' in phone
    for law_id in ("ndps", "bns"):
        card = phone.split(f'data-law-id="{law_id}"', 1)[1].split("</article>", 1)[0]
        actions = card.split("pg-card-actions--phone", 1)[1].split(
            "pg-card-actions--desktop", 1
        )[0]
        assert ">Resume Playground<" in actions
        assert f'href="{PLAYGROUND_BILLING_PATH}"' in actions
        assert "data-pg-sheet" not in actions
        assert ">Learn<" not in actions
        assert ">Continue<" not in actions
        assert ">Start learning<" not in actions
    assert _facts(client) == before
    _assert_generic_playground_tabs(html)


def test_phone_expired_month_count_is_label_not_visible_cards(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _seed_roster(client, "ndps", "bns")
    start, _end = playground_month_bounds()
    removed = client.app.state.roster._repo.remove_law(
        USER, period_start=start, law_id="bns"
    )
    assert removed is not None
    _expire(client)
    home = _home_view(client)
    facts = _facts(client)
    assert facts["active"] == ("ndps",)
    assert facts["removed"] == ("bns",)
    assert facts["used"] == 2
    assert home.month_count_label == f"1 of 10 · {MONTH}"
    html = unescape(client.get("/playground").text)
    phone = unescape(_phone(html))
    assert home.month_count_label in phone
    assert "2 of 10 ·" not in phone
    assert 'data-law-id="ndps"' in phone
    assert 'data-law-id="bns"' in phone
    assert "LawCard--saved" in phone
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in phone.split(
        'data-law-id="bns"', 1
    )[1].split("</article>", 1)[0]
    assert _facts(client) == facts


def test_guest_free_plus_halted_pro_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in guest
    assert "data-expired-pg-phone" not in guest
    assert 'data-expired-playground="desktop"' not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/playground").text
    assert "data-signed-in-pg-gate" in free_html
    assert "data-expired-pg-phone" not in free_html
    assert 'data-expired-playground="desktop"' not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/playground").text)
    assert "data-plus-playground-phone" in plus_html
    assert "data-expired-pg-phone" not in plus_html
    assert 'data-expired-playground="desktop"' not in plus_html
    assert LIVE_HEADING not in plus_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    _seed_roster(halted, "ndps")
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/playground").text
    assert 'data-halted-playground="desktop"' in halted_html
    assert "data-halted-pg-phone" in halted_html
    assert "data-expired-pg-phone" not in halted_html
    assert 'data-expired-playground="desktop"' not in halted_html
    assert LIVE_HEADING not in halted_html
    assert "Payment retries have stopped" in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/playground").text
    assert "data-expired-pg-phone" not in pro_html
    assert 'data-expired-playground="desktop"' not in pro_html


def test_phone_expired_css_scope_pins_banner_once_and_desktop_06_untouched() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/03-screen:" in css
    phone_block = css.split("is expired/03-screen:", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "[data-expired-pg-phone]" in phone_block
    assert '[data-expired-playground="desktop"]' in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "min-height: 44px" in phone_block
    assert "LawCard--saved" in phone_block
    assert "PaymentStateBanner" in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "[data-halted-pg-phone]" not in phone_block
    assert "[data-plus-playground-phone]" not in phone_block
    assert "[data-signed-in-pg-gate]" not in phone_block
    plus_block = css.split("is plus/03-screen:", 1)[1].split(
        "Expired and Halted desktop Playground home", 1
    )[0]
    assert "is expired/03-screen" not in plus_block
    desk_title = css.split(".expired-pg-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 34px" in desk_title
    hide_desk = css.split("[data-expired-pg-desktop],", 1)[1].split("}", 1)[0]
    assert "display: none" in hide_desk
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "is expired/03-screen" not in mobile
    assert "data-expired-pg-phone" not in STYLES.read_text(encoding="utf-8")
    assert "data-expired-pg-phone" not in PG_JS.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    assert home.count("{{ banner(home.banner) }}") == 3
    pre_grid, _, column = home.partition("class=\"pg-home-grid")
    assert "{% elif not expired_pg %}" in pre_grid
    assert "{{ banner(home.banner) }}" in pre_grid
    expired_top = pre_grid.split("{% elif not expired_pg %}", 1)[0]
    assert "{{ banner(home.banner) }}" in expired_top
    assert "data-halted-pg-phone" in expired_top
    assert "{% elif expired_pg %}" not in pre_grid
    phone_col = column.split("data-expired-pg-phone", 1)[1]
    assert "{{ banner(home.banner) }}" in phone_col.split("<aside", 1)[0]
    assert phone_col.find("home.heading") < phone_col.find("{{ banner(home.banner) }}")
    assert phone_col.find("month_count_label") < phone_col.find(
        "{{ banner(home.banner) }}"
    )
    assert "September" not in home
    assert "12 Aug" not in home
    assert "2 laws" not in home
    partials = PARTIALS.read_text(encoding="utf-8")
    assert "data-expired-pg-phone" not in partials
    assert "def build_home_view" in VIEW.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    assert "require_playground_home" in routes
    assert '"expired_playground": expired_playground' in routes
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg44" in base
    assert "playground.css?v=pg42" not in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "data-expired-pg-phone-tabs" not in base
    assert "data-expired-bareact-phone-tabs" in base


def _screenshot(page, path: Path, *, attempts: int = 5) -> None:
    last: OSError | None = None
    for index in range(attempts):
        try:
            page.screenshot(path=str(path), full_page=False)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.4 * (index + 1))
    assert last is not None
    raise last


def _serve(app, host: str = "127.0.0.1") -> tuple[int, object]:
    import uvicorn

    sock = socket.socket()
    sock.bind((host, 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(80):
        probe = socket.socket()
        probe.settimeout(0.1)
        ready = probe.connect_ex((host, port)) == 0
        probe.close()
        if ready:
            break
        time.sleep(0.05)
    else:
        pytest.fail("server did not bind")
    return port, server


def _playwright_session(app):
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert session
    return client, session, csrf


def _cookie_list(origin: str, session: str, csrf: str | None) -> list[dict]:
    cookies = [
        {
            "name": SESSION_COOKIE_NAME,
            "value": session,
            "url": origin,
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }
    ]
    if csrf:
        cookies.append(
            {
                "name": CSRF_COOKIE_NAME,
                "value": csrf,
                "url": origin,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        )
    return cookies


def test_phone_expired_playground_screen03_captures(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    empty_path = artifact_dir / "phone_expired_playground_screen03_empty_390x844.png"
    enrolled_path = artifact_dir / "phone_expired_playground_screen03_390x844.png"
    desk_path = artifact_dir / "phone_expired_playground_screen03_desktop_regression_1280.png"

    empty_app = _mu_app(tmp_path / "empty")
    empty_client, empty_session, empty_csrf = _playwright_session(empty_app)
    _subscribe(empty_client)
    _expire(empty_client)

    enrolled_app = _mu_app(tmp_path / "enrolled")
    enrolled_client, enrolled_session, enrolled_csrf = _playwright_session(enrolled_app)
    _subscribe(enrolled_client)
    _seed_roster(enrolled_client, "ndps", "bns")
    _expire(enrolled_client)
    enrolled_home = _home_view(enrolled_client)

    desk_app = _mu_app(tmp_path / "desk")
    desk_client, desk_session, desk_csrf = _playwright_session(desk_app)
    _seed_ndps_progress_then_expire(desk_client)
    desk_home = _home_view(desk_client)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])

        def open_home(app, session, csrf, *, width: int, height: int):
            port, _server = _serve(app)
            origin = f"http://127.0.0.1:{port}"
            context = browser.new_context(
                viewport={"width": width, "height": height}, device_scale_factor=1
            )
            context.add_cookies(_cookie_list(origin, session, csrf))
            page = context.new_page()
            page.emulate_media(color_scheme="light")
            page.add_init_script(
                """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
            )
            page.goto(f"{origin}/playground", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.wait_for_selector(
                '[data-expired-playground="desktop"]', timeout=8000
            )
            page.wait_for_timeout(250)
            return page, context

        page, context = open_home(
            empty_app, empty_session, empty_csrf, width=390, height=844
        )
        empty_geo = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-expired-pg-phone]');
              const desk = document.querySelector('[data-expired-pg-desktop]');
              const banner = phone && phone.querySelector('.PaymentStateBanner[data-state="expired"]');
              const title = phone && phone.querySelector('.pg-home-title');
              const count = phone && phone.querySelector('.pg-home-month');
              const cards = phone ? [...phone.querySelectorAll('.pg-law-grid .LawCard')] : [];
              const strip = phone && phone.querySelector('.pg-month-strip');
              const actions = phone && phone.querySelector(':scope > p.pg-actions');
              const resume = banner && banner.querySelector('a.pg-btn');
              const tabs = [...document.querySelectorAll('.mobile-tabbar .mobile-tab')];
              const active = document.querySelector('.mobile-tabbar .mobile-tab.is-active');
              const banners = [...document.querySelectorAll('.PaymentStateBanner[data-state="expired"]')];
              const box = resume && resume.getBoundingClientRect();
              return {
                marker: Boolean(document.querySelector('[data-expired-playground="desktop"]')),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                plus: Boolean(document.querySelector('[data-plus-playground-phone]')),
                gate: Boolean(document.querySelector('[data-signed-in-pg-gate]')),
                title: title && title.textContent.trim(),
                count: count && count.textContent.trim(),
                bannerTitle: banner && banner.querySelector('strong')
                  && banner.querySelector('strong').textContent.trim(),
                bannerBody: banner && banner.querySelector('.pg-lede')
                  && banner.querySelector('.pg-lede').textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                resumeHeight: box && box.height,
                banners: banners.length,
                cards: cards.length,
                stripDisplay: strip ? getComputedStyle(strip).display : 'missing',
                actionsDisplay: actions ? getComputedStyle(actions).display : 'missing',
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabLabels: tabs.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabs.map((el) => el.getAttribute('href')),
                activeTab: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                dedicatedTabs: Boolean(document.querySelector('[data-expired-pg-phone-tabs]')),
                bareactTabs: Boolean(document.querySelector('[data-expired-bareact-phone-tabs]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, empty_path)
        context.close()

        page, context = open_home(
            enrolled_app, enrolled_session, enrolled_csrf, width=390, height=844
        )
        enrolled_geo = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-expired-pg-phone]');
              const cards = [...phone.querySelectorAll('.pg-law-grid .LawCard')];
              const primaries = cards.map((card) => {
                const btn = card.querySelector('.pg-card-actions--phone .pg-btn');
                const box = btn && btn.getBoundingClientRect();
                return {
                  id: card.getAttribute('data-law-id'),
                  title: card.querySelector('.LawCard-title')
                    && card.querySelector('.LawCard-title').textContent.trim(),
                  text: btn && btn.textContent.trim(),
                  href: btn && btn.getAttribute('href'),
                  height: box && box.height,
                  sheet: btn && btn.hasAttribute('data-pg-sheet'),
                };
              });
              const count = phone.querySelector('.pg-home-month');
              const banner = phone.querySelector('.PaymentStateBanner[data-state="expired"]');
              const resume = banner && banner.querySelector('a.pg-btn');
              const visibleSheet = [...phone.querySelectorAll('[data-pg-sheet]')].filter((el) => {
                let node = el;
                while (node) {
                  const cs = getComputedStyle(node);
                  if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                  node = node.parentElement;
                }
                return true;
              });
              const learnExact = [...phone.querySelectorAll('a, button')].some(
                (el) => el.textContent.trim() === 'Learn'
              );
              const sectionHead = phone.querySelector('.pg-section-head');
              return {
                count: count && count.textContent.trim(),
                countDisplay: count && getComputedStyle(count).display,
                sectionHeadDisplay: sectionHead ? getComputedStyle(sectionHead).display : 'missing',
                bannerHref: resume && resume.getAttribute('href'),
                ids: cards.map((el) => el.getAttribute('data-law-id')),
                primaries,
                visibleSheet: visibleSheet.length,
                learnExact,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, enrolled_path)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-expired-pg-phone]');
              const btn = [...phone.querySelectorAll('.pg-card-actions--phone .pg-btn')].at(-1);
              btn.scrollIntoView();
              const tabsEl = document.querySelector('.mobile-tabbar');
              let box = btn.getBoundingClientRect();
              const tabTop = tabsEl.getBoundingClientRect().top;
              if (box.bottom > tabTop) {
                window.scrollBy(0, box.bottom - tabTop + 12);
                box = btn.getBoundingClientRect();
              }
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                height: box.height,
                width: box.width,
                inView: box.bottom <= tabsEl.getBoundingClientRect().top + 2 && box.top >= 0,
              };
            }"""
        )
        context.close()

        page, context = open_home(
            desk_app, desk_session, desk_csrf, width=1280, height=800
        )
        desk_geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-expired-pg-desktop]');
              const phone = document.querySelector('[data-expired-pg-phone]');
              const primary = desk && desk.querySelector('.expired-pg-primary');
              const secondary = desk && desk.querySelector('.expired-pg-secondary');
              const tiles = desk ? [...desk.querySelectorAll('.ProgressSummary-cell')] : [];
              const lawGrid = document.querySelector('.pg-law-grid');
              const bannerInDesk = Boolean(desk && desk.querySelector('.PaymentStateBanner'));
              const banners = [...document.querySelectorAll('.PaymentStateBanner[data-state="expired"]')];
              const visibleBanners = banners.filter((el) => el.getBoundingClientRect().height > 1);
              return {
                marker: Boolean(document.querySelector('[data-expired-playground="desktop"]')),
                plus: Boolean(document.querySelector('[data-plus-playground="desktop"]')),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                title: desk && desk.querySelector('.expired-pg-title')
                  && desk.querySelector('.expired-pg-title').textContent.trim(),
                primaryText: primary && primary.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                secondaryText: secondary && secondary.textContent.trim(),
                secondaryHref: secondary && secondary.getAttribute('href'),
                tileLabels: tiles.map((el) => el.querySelector('.ProgressSummary-label').textContent.trim()),
                tileValues: tiles.map((el) => el.querySelector('.ProgressSummary-value').textContent.trim()),
                lawGridVisible: Boolean(lawGrid && lawGrid.getBoundingClientRect().height > 1),
                bannerInDesk,
                bannerCount: banners.length,
                visibleBanners: visibleBanners.length,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, desk_path)
        context.close()
        browser.close()

    assert empty_geo["marker"] is True
    assert empty_geo["deskDisplay"] == "none"
    assert empty_geo["phoneDisplay"] != "none"
    assert empty_geo["plus"] is False
    assert empty_geo["gate"] is False
    assert empty_geo["title"] == "Playground"
    assert empty_geo["count"] == f"0 of 10 · {MONTH}"
    assert empty_geo["bannerTitle"] == LIVE_HEADING
    assert empty_geo["bannerBody"] == LIVE_COPY[0]
    assert empty_geo["resumeText"] == "Resume Playground"
    assert empty_geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert empty_geo["resumeHeight"] >= 44
    assert empty_geo["banners"] == 1
    assert empty_geo["cards"] == 0
    assert empty_geo["stripDisplay"] == "none"
    assert empty_geo["actionsDisplay"] == "none"
    assert empty_geo["overflow"] is False
    assert empty_geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert empty_geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert empty_geo["activeTab"] == "Playground"
    assert empty_geo["dedicatedTabs"] is False
    assert empty_geo["bareactTabs"] is False

    assert enrolled_geo["count"] == enrolled_home.month_count_label
    assert enrolled_geo["count"] == f"2 of 10 · {MONTH}"
    assert enrolled_geo["countDisplay"] != "none"
    assert enrolled_geo["sectionHeadDisplay"] == "none"
    assert enrolled_geo["bannerHref"] == PLAYGROUND_BILLING_PATH
    assert set(enrolled_geo["ids"]) == {"ndps", "bns"}
    by_id = {row["id"]: row for row in enrolled_geo["primaries"]}
    assert by_id["ndps"]["title"] == "NDPS Act"
    assert by_id["bns"]["title"] == "BNS"
    assert by_id["ndps"]["text"] == "Resume Playground"
    assert by_id["bns"]["text"] == "Resume Playground"
    assert by_id["ndps"]["href"] == PLAYGROUND_BILLING_PATH
    assert by_id["bns"]["href"] == PLAYGROUND_BILLING_PATH
    assert by_id["ndps"]["sheet"] is False
    assert by_id["ndps"]["height"] >= 44
    assert enrolled_geo["visibleSheet"] == 0
    assert enrolled_geo["learnExact"] is False
    assert enrolled_geo["overflow"] is False

    assert short["overflow"] is False
    assert short["height"] >= 44
    assert short["inView"] is True

    assert desk_geo["marker"] is True
    assert desk_geo["plus"] is False
    assert desk_geo["deskDisplay"] != "none"
    assert desk_geo["phoneDisplay"] == "none"
    assert desk_geo["title"] == LIVE_HEADING
    assert desk_geo["primaryText"] == "View Playground plans"
    assert desk_geo["primaryHref"] == PLAYGROUND_BILLING_PATH
    assert desk_geo["secondaryText"] == "Back to Constitution"
    assert desk_geo["secondaryHref"] == CONSTITUTION_HOME_PATH
    assert desk_geo["tileLabels"] == ["Due today", "Overdue", "Sections learned"]
    assert desk_geo["tileValues"] == [
        str(desk_home.due_today),
        str(desk_home.overdue),
        str(desk_home.sections_learned),
    ]
    assert desk_geo["lawGridVisible"] is False
    assert desk_geo["bannerInDesk"] is False
    assert desk_geo["bannerCount"] == 1
    assert desk_geo["visibleBanners"] == 0

    for path in (empty_path, enrolled_path, desk_path):
        assert path.is_file() and path.stat().st_size > 1000
