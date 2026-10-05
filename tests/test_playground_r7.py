"""R7 — U8 responsive / a11y / parity closeout.

Does not reopen Stage 1, R5, or R6 semantics. T40 rewrites live in
``test_playground_m8.py`` and ``test_pota_reader.py`` and are authorized by
``docs/PLAYGROUND_UI_REDESIGN_R7_LEDGER.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REPLACEMENT_LIMIT,
    BLOCK_DEVICE_REVOKED,
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.web.app import create_app

from tests.test_guest_first_ux import _client as _guest_client
from tests.test_roster_m5a import _authed_client, _subscribe

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
STATIC = ROOT / "src/constitution_memorizer/web/static"
LEDGER = ROOT / "docs/PLAYGROUND_UI_REDESIGN_R7_LEDGER.md"
INVENTORY = ROOT / "docs/design/PLAYGROUND_DESIGN_INVENTORY.md"
BASE = TEMPLATES / "base.html"

CLASS_B = (
    "browse_part.html",
    "browse_article.html",
    "learn.html",
    "choose.html",
    "incomplete.html",
    "search.html",
    "tables.html",
    "memory.html",
    "memory_detail.html",
    "law_detail.html",
    "bare_act_section.html",
    "bare_act_schedule.html",
    "progress.html",
    "progress_mastered.html",
    "guest_gate.html",
    "welcome.html",
    "onboarding_plan.html",
    "plan_my_day.html",
    "home.html",
    "pricing.html",
    "purchase_confirm.html",
    "purchase_result.html",
    "login.html",
    "signed_out.html",
    "session_expired.html",
    "auth_transition.html",
    "auth_callback.html",
    "landing.html",
    "landing_light.html",
    "legal/base.html",
    "legal/terms.html",
    "legal/privacy.html",
    "legal/grievance.html",
    "legal/_macros.html",
    "visual_explainer.html",
    "visual_explainer_trigger.html",
    "_completion_banner.html",
    "_locked_mode.html",
    "partials/auth_shell.html",
    "partials/bare_act_footnotes.html",
    "partials/bare_act_macros.html",
    "partials/guest_modal.html",
    "partials/mode_help_modal.html",
    "partials/report_dialog.html",
    "partials/revision_exit_modal.html",
)

CLASS_C_STATES = (
    "D102",
    "D133",
    "D134",
    "D135",
    "D136",
    "D137",
    "D138",
    "D139",
    "D140",
    "D141",
    "D142",
)


def test_t33_r7_asset_pins() -> None:
    html = BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main84" in html
    assert "mobile.css?v=mob98" in html
    assert "playground.css?v=pg19" in html
    assert "playground.js?v=pg8" in html
    assert "styles.css?v=main76" not in html
    assert "mobile.css?v=mob97" not in html
    assert "playground.css?v=pg18" not in html


def test_r7_ledger_inventory_and_class_b() -> None:
    ledger = LEDGER.read_text(encoding="utf-8")
    inventory = INVENTORY.read_text(encoding="utf-8")
    assert "Approved work order" in ledger
    assert "T40 execution" in ledger
    assert "V16 / V17 / V18" in ledger
    assert ledger.find("T40 execution") < ledger.find("V16 / V17 / V18")
    assert "do not claim V23 DONE" in ledger or "do not claim V23 done" in ledger.lower()
    assert "V11 cannot close via" in ledger or "cannot be passed via" in ledger.lower() or "cannot close via `APPROVED DEVIATION`" in ledger
    assert "Not screenshotted must not mean not inspected" in ledger
    assert "Calendar week is desktop-only" in ledger
    assert "Legal stays Class B" in ledger
    stop = ledger.split("## Stop log", 1)[1]
    assert "V23" in stop
    assert "landing.html" in stop
    assert "login.html" in stop
    assert "new" in stop.lower() and "D row" in stop
    assert "V23 closed via D143" in stop
    assert len(CLASS_B) == 45
    for name in CLASS_B:
        assert f"`{name}`" in ledger, name
        assert (TEMPLATES / name).exists(), name
    for state in CLASS_C_STATES:
        assert state in ledger, state
    assert "sign-in gate" in inventory
    assert "read-only home" in inventory


def test_r7_t40_ledger_authorizes_pending_rewrites() -> None:
    ledger = LEDGER.read_text(encoding="utf-8")
    m8 = (ROOT / "tests/test_playground_m8.py").read_text(encoding="utf-8")
    pota = (ROOT / "tests/test_pota_reader.py").read_text(encoding="utf-8")
    assert "T40-4" in ledger
    assert "T40-5" in ledger
    assert "test_today_queue_current_roster_only" in ledger
    assert "data-today-path-card" in m8
    assert "Day 3 → 7 · Playground" in m8
    assert "Day 1 → 3 · Playground" in m8
    assert "Start revision →" in m8
    assert "list_playground_eligible_laws" in pota
    assert 'for slug in ("ndps", "bns", "bnss"):' not in pota


def test_v15_d_row_ledger_covers_d1_d142() -> None:
    ledger = LEDGER.read_text(encoding="utf-8")
    assert "MATCHED" in ledger
    assert "APPROVED DEVIATION" in ledger
    assert "D113" in ledger
    assert "D102" in ledger
    for i in range(1, 143):
        token = f"D{i}"
        if token in {
            "D4",
            "D18",
            "D20",
            "D36",
            "D51",
            "D60",
            "D92",
            "D104",
            "D105",
            "D109",
            "D113",
        }:
            assert token in ledger, token
    assert "All other D1–D142" in ledger or "all other D1–D142" in ledger


def _walk_paths(routes, prefix: str = "") -> list[str]:
    found: list[str] = []
    for route in routes:
        nested = getattr(route, "routes", None)
        original = getattr(route, "original_router", None)
        path = getattr(route, "path", None) or ""
        methods = getattr(route, "methods", None)
        full = f"{prefix}{path}" if path else prefix
        if methods and "GET" in methods and full:
            found.append(full)
        if nested:
            found.extend(_walk_paths(nested, full))
        if original is not None:
            found.extend(_walk_paths(original.routes, prefix))
    return found


def test_v24_html_get_routes_are_classified(tmp_path: Path) -> None:
    inventory = INVENTORY.read_text(encoding="utf-8")
    ledger = LEDGER.read_text(encoding="utf-8")
    blob = inventory + "\n" + ledger
    required = (
        "/playground",
        "/dashboard",
        "/calendar",
        "/profile",
        "/settings",
        "/browse",
        "/laws",
        "/learn",
        "/login",
        "/terms",
        "/privacy",
        "/grievance",
        "/profile/security/devices",
        "/billing/subscriptions",
        "/admin",
        "/calendar?view=week",
    )
    for path in required:
        assert path in blob, path
    app = create_app(
        units_path=ROOT / "tests/fixtures/learning/mini_units.json",
        db_path=tmp_path / "progress.db",
    )
    html_gets = _walk_paths(app.router.routes)
    assert "/playground" in html_gets
    assert "/dashboard" in html_gets
    assert "/calendar" in html_gets
    assert any(path.startswith("/admin") for path in html_gets)


def test_r7_css_reconciliation_contracts() -> None:
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    mobile = (STATIC / "mobile.css").read_text(encoding="utf-8")
    playground = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert "R7 closeout" in styles
    assert "R7 closeout" in mobile
    assert "R7 closeout" in playground
    assert "overflow-x: hidden" in styles
    assert "@media (max-width: 899px)" in styles
    assert "@media (min-width: 900px) and (max-width: 1039px)" in styles
    assert "@media (min-width: 900px) and (max-width: 1039px)" in playground
    assert "a:focus-visible" in styles
    assert "min-height: 44px" in styles.split("R7 closeout", 1)[1]
    assert "min-height: 44px" in mobile.split("learn-letters-viewswitch", 1)[1][:400]
    assert "prefers-reduced-motion: reduce" in styles
    assert "PlaygroundShell" in playground
    assert ".calendar.is-week .calendar-week" in styles
    assert "@media (min-width: 900px)" in styles.split(".calendar-week,", 1)[1][:500]


def test_d102_gate_variants_remain_distinct() -> None:
    reasons = (
        BLOCK_NOT_SUBSCRIBED,
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_REPLACEMENT_LIMIT,
        BLOCK_DEVICE_CONFIG_ERROR,
        BLOCK_PAYMENT_HALTED,
    )
    views = [gate_view(reason=reason) for reason in reasons]
    titles = [view.title for view in views]
    assert len(set(titles)) == len(reasons)
    assert "Unlock Playground" in titles
    assert "Device limit reached" in titles
    gate = (TEMPLATES / "playground_gate.html").read_text(encoding="utf-8")
    assert 'data-playground-gate="{{ gate.reason }}"' in gate


def test_class_c_templates_and_status_not_colour_only() -> None:
    for name in (
        "playground_source_review.html",
        "playground_source_review_section.html",
        "devices.html",
        "subscription_checkout.html",
        "playground_gate.html",
    ):
        assert (TEMPLATES / name).exists(), name
    learn = (TEMPLATES / "playground_learn.html").read_text(encoding="utf-8")
    js = (STATIC / "playground-learn.js").read_text(encoding="utf-8")
    assert "not due" in learn.lower() or "not due" in js.lower() or "This revision is not due yet." in js
    calendar = (TEMPLATES / "calendar.html").read_text(encoding="utf-8")
    assert 'role="radiogroup"' in calendar
    roster = (TEMPLATES / "playground_roster_next.html").read_text(encoding="utf-8")
    assert 'role="radiogroup"' in roster
    picker = (TEMPLATES / "playground_select.html").read_text(encoding="utf-8")
    assert "aria-checked" in picker


def test_v11_settings_styling_frozen_hit_area_corrected() -> None:
    settings = (TEMPLATES / "settings.html").read_text(encoding="utf-8")
    assert "segmented-btn" in settings
    mobile = (STATIC / "mobile.css").read_text(encoding="utf-8")
    settings_css = mobile.split('body[data-mscreen="settings"] .segmented-btn', 1)[1][:500]
    assert "min-height: 44px" in settings_css
    assert "height: 30px" not in settings_css.split("}", 1)[0]
    toggle = mobile.split(".settings-toggle {", 1)[1][:700]
    assert "min-height: 44px" in toggle
    assert "height: 28px" in mobile
    assert "settings-toggle::before" in mobile


def test_r7_shell_still_has_phone_and_desktop_breakpoints(tmp_path: Path) -> None:
    client = _authed_client(tmp_path)
    _subscribe(client)
    home = client.get("/playground")
    assert home.status_code == 200
    assert "PlaygroundShell" in home.text
    css = client.get("/static/playground.css?v=pg19").text
    assert "--pg-tap: 44px" in css or "--pg-tap:" in css
    styles = client.get("/static/styles.css?v=main84").text
    assert "R7 closeout" in styles
    week = client.get("/calendar?view=week")
    assert week.status_code == 200
    assert "calendar-week" in week.text or "calendar.is-week" in week.text or "is-week" in week.text


D143_SURFACES = (
    TEMPLATES / "landing.html",
    TEMPLATES / "landing_light.html",
    TEMPLATES / "login.html",
    STATIC / "landing.js",
)
D143_TOKENS = {
    "--page",
    "--paper",
    "--wash",
    "--ink",
    "--muted",
    "--faint",
    "--hairline",
    "--control-border",
    "--hover",
    "--accent",
    "--accent-hover",
    "--on-accent",
    "--destructive",
    "--shadow",
    "--font-display",
    "--font-body",
}
_HEX = re.compile(r"(?<!&)#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b")
_RGB = re.compile(
    r"rgba?\(\s*(?:110\s*,\s*130\s*,\s*200|244\s*,\s*241\s*,\s*234)\b",
    re.I,
)
_VAR = re.compile(r"var\(\s*(--[A-Za-z0-9-]+)")
_SPLASH = (
    "6E82C8",
    "0E7569",
    "f4f1ea",
    "fdfcfa",
    "4C5C9E",
    "F59022",
)
_FORBIDDEN = ("--browse-due", "--pg-", "--letters-correct")


def test_d143_tracker_row_is_not_folded_into_u1() -> None:
    tracker = (ROOT / "docs/PLAYGROUND_UI_REDESIGN_TRACKER.md").read_text(encoding="utf-8")
    assert "### D143 — Splash/auth palette reconciliation" in tracker
    assert "| D143 |" in tracker
    assert "not in frozen U1 28" in tracker or "Not folded into frozen U1" in tracker
    assert "U8 25 / 25" in tracker or "U8 **25 / 25**" in tracker or "25/25" in tracker
    assert "208 scored" in tracker


def test_d143_surfaces_use_u1_tokens_only() -> None:
    for path in D143_SURFACES:
        text = path.read_text(encoding="utf-8")
        hexes = _HEX.findall(text)
        assert hexes == [], f"{path.name} still has hex: {hexes}"
        assert _RGB.search(text) is None, f"{path.name} still has splash rgb"
        lowered = text.lower()
        for splash in _SPLASH:
            assert splash.lower() not in lowered, f"{path.name} still mentions {splash}"
        for token in _FORBIDDEN:
            assert token not in text, f"{path.name} uses forbidden {token}"
        unknown = sorted({name for name in _VAR.findall(text) if name not in D143_TOKENS})
        assert unknown == [], f"{path.name} uses tokens outside D143: {unknown}"
    landing = (TEMPLATES / "landing.html").read_text(encoding="utf-8")
    light = (TEMPLATES / "landing_light.html").read_text(encoding="utf-8")
    login = (TEMPLATES / "login.html").read_text(encoding="utf-8")
    js = (STATIC / "landing.js").read_text(encoding="utf-8")
    for html in (landing, light, login):
        assert "styles.css?v=main84" in html
        assert html.find("styles.css?v=main84") < html.find("<style>")
        assert "a:hover" in html
    assert 'data-theme="dark"' in landing
    assert 'data-theme="light"' in light
    assert 'data-theme="light"' in login
    assert "landing.js?v=landing2" in landing
    assert "tokenRgb" in js
    assert "getComputedStyle" in js
    assert "lerpToken" in js


def test_d143_does_not_change_ia_auth_or_light_route(tmp_path: Path) -> None:
    login = (TEMPLATES / "login.html").read_text(encoding="utf-8")
    assert "Continue with Google" in login
    assert "data-phone-form" in login
    assert "data-otp-form" in login
    assert "j-legal-nav" in login
    assert "auth_shell" not in login
    app_src = (ROOT / "src/constitution_memorizer/web/app.py").read_text(encoding="utf-8")
    assert '"landing.html"' in app_src
    landing_serve = app_src.split("landing_light.html", 1)[1][:400]
    assert '"landing.html"' in landing_serve
    client = _guest_client(tmp_path)
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    assert "rc-launch" in home.text
    assert "landing.js?v=landing2" in home.text
    assert "landing-light.js" not in home.text
    signin = client.get("/login")
    assert signin.status_code == 200
    assert "Continue with Google" in signin.text or "data-google-signin" in signin.text
    assert "j-legal-nav" in signin.text
