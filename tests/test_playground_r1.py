"""R1 — shared Playground design system and shells.

Closes U1 rows D1–D10, D12–D21, D24–D25, T33–T35, T38–T39, T41.
Does not cover later-batch screens (clause picker, Today merge, speech).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from tests.test_roster_m5a import _authed_client, _subscribe

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
STATIC = ROOT / "src/constitution_memorizer/web/static"
INVENTORY = ROOT / "docs/design/PLAYGROUND_DESIGN_INVENTORY.md"
PLAYGROUND_CSS = STATIC / "playground.css"
PLAYGROUND_JS = STATIC / "playground.js"
MOBILE_CSS = STATIC / "mobile.css"
BASE = TEMPLATES / "base.html"

LIGHT_TOKENS = (
    "--pg-ink",
    "--pg-paper",
    "--pg-page",
    "--pg-hairline",
    "--pg-muted",
    "--pg-faint",
    "--pg-teal",
    "--pg-teal-dark",
    "--pg-teal-tint",
    "--pg-teal-border",
    "--pg-teal-done",
    "--pg-teal-on-dark",
    "--pg-amber",
    "--pg-amber-tint",
    "--pg-destructive",
    "--pg-destructive-tint",
    "--pg-radius-sheet",
    "--pg-radius-card",
    "--pg-radius-row",
    "--pg-radius-button",
    "--pg-radius-chip",
    "--pg-shadow-press",
    "--pg-shadow-sheet",
    "--pg-shadow-dialog",
    "--pg-shadow-menu",
    "--pg-font-display",
    "--pg-font-ui",
    "--pg-label-size",
    "--pg-focus-ring",
    "--pg-tap",
    "--pg-scrim",
)

# Prototype / demo strings that must never ship in runtime templates or
# Playground static assets. Historical docs/ and design prototypes are
# excluded — T35 is a production-asset test, not a documentation test.
MUST_NOT_SHIP = (
    ("X1", "₹149"),
    ("X1", "₹299"),
    ("X1", "₹499"),
    ("X1", "Core / Deep / Infinite"),
    ("X2", "offical"),
    ("X3", "1 spaces remaining"),
    ("X5", "Devices 2 of 3"),
    ("X6", "Study archive"),
    ("X6", "Streak chip"),
    ("X8", "36% learned"),
    ("X8", "geodesic-dome"),
)

CLASS_C_NAMED = {
    "devices.html",
    "playground_source_review.html",
    "playground_source_review_section.html",
    "subscription_checkout.html",
}
CLASS_E_DELETED = {"playground_cloze.html"}


def _css() -> str:
    return PLAYGROUND_CSS.read_text()


def _token_block(css: str, prelude: str) -> str:
    idx = css.find(prelude)
    assert idx != -1, prelude
    rest = css[idx:]
    depth = 0
    start = rest.find("{")
    for i, ch in enumerate(rest[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return rest[: i + 1]
    raise AssertionError(f"unclosed block for {prelude}")


def test_t41_every_active_template_is_classified():
    inventory = INVENTORY.read_text()
    section = re.search(
        r"## 2\. Production template inventory.*?(?=## 3\.)",
        inventory,
        re.S,
    )
    assert section, "inventory §2 missing"
    named = set(re.findall(r"`([^`]+?\.html)`", section.group(0)))
    named |= CLASS_C_NAMED
    named -= CLASS_E_DELETED
    disk = {
        path.relative_to(TEMPLATES).as_posix()
        for path in TEMPLATES.rglob("*.html")
    }
    unclassified = sorted(disk - named)
    missing = sorted(named - disk)
    assert len(disk) == 81, f"active templates changed: {len(disk)}"
    assert unclassified == [], f"unclassified templates: {unclassified}"
    assert missing == [], f"inventory names missing on disk: {missing}"
    assert "Unclassified templates" in inventory
    assert "**0**" in inventory.split("Unclassified templates", 1)[1][:200]
    assert not (TEMPLATES / "playground_cloze.html").exists()


def test_t33_r1_asset_versions_are_pinned():
    html = BASE.read_text()
    assert "styles.css?v=main84" in html
    assert "mobile.css?v=mob98" in html
    assert "playground.css?v=pg26" in html
    assert "playground.js?v=pg8" in html
    assert "playground-select.js?v=pg1" in html
    assert "playground.css?v=pg25" not in html
    assert "playground.css?v=pg24" not in html
    assert "playground.css?v=pg23" not in html
    assert "playground.css?v=pg22" not in html
    assert "playground.css?v=pg21" not in html
    assert "playground.css?v=pg20" not in html
    assert "playground.css?v=pg19" not in html
    assert "playground.css?v=pg18" not in html
    assert "playground.css?v=pg17" not in html
    assert "playground.css?v=pg16" not in html
    assert "playground.css?v=pg15" not in html
    assert "playground.css?v=pg14" not in html
    assert "playground.css?v=pg13" not in html
    assert "playground.js?v=pg7" not in html
    assert "mobile.css?v=mob94" not in html
    assert "mobile.css?v=mob95" not in html
    assert "mobile.css?v=mob96" not in html
    assert "mobile.css?v=mob97" not in html


def test_t34_light_and_dark_tokens_and_fixed_dark_surface():
    css = _css()
    light = _token_block(css, "html[data-theme=\"light\"]")
    dark = _token_block(css, "html[data-theme=\"dark\"]")
    for token in LIGHT_TOKENS:
        assert token in light, token
        assert token in dark, token
    assert ".pg-surface--fixed-dark" in css
    fixed = _token_block(css, ".pg-surface--fixed-dark")
    for token in (
        "--pg-ink",
        "--pg-paper",
        "--pg-page",
        "--pg-teal",
        "--pg-amber",
        "--pg-destructive",
    ):
        assert token in fixed, token


def test_d1_d16_design_system_primitives_in_css():
    css = _css()
    for needle in (
        "--pg-ink",
        "--pg-teal-on-dark",
        "--pg-amber",
        "--pg-destructive-tint",
        "--pg-font-display",
        "--pg-font-ui",
        "--pg-label-size: 10.5px",
        "--pg-radius-sheet: 22px",
        "--pg-radius-card: 16px",
        "--pg-radius-row: 14px",
        "--pg-radius-button: 12px",
        "--pg-radius-chip: 999px",
        "--pg-shadow-press",
        "--pg-shadow-sheet",
        "--pg-shadow-dialog",
        "--pg-shadow-menu",
        ".pg-btn--teal",
        ".pg-btn--outline",
        ".pg-btn--destructive",
        ".pg-btn:disabled",
        ".LawCard--emphasised",
        ".pg-card--saved",
        ".pg-chip",
        ".pg-chip--verbatim",
        ".pg-chip--teal",
        ".pg-progress-ring",
        ".pg-progress-bar",
        ".pg-waffle",
        ".pg-rung",
        ".pg-field",
        "--pg-focus-ring: 2px solid",
        "@keyframes pg-rise",
        "@keyframes pg-pop",
        "@keyframes pg-sheet-rise",
        "@keyframes pg-grow",
        "@keyframes pg-fade",
        "prefers-reduced-motion",
        "html:not(.rtc-anim)",
        "env(safe-area-inset-bottom",
        "min-height: var(--pg-tap)",
        ".pg-sheet-panel::before",
        "max-width: 460px",
        ".pg-surface--fixed-dark",
        "--pg-shell-max",
        "min-width: 561px",
        "min-width: 900px",
        "min-width: 1040px",
        "min-width: 1280px",
        ".pg-back",
        ".pg-sticky-cta",
        ".pg-columns",
    ):
        assert needle in css, needle
    assert "PlaygroundShell" in css
    assert "RosterCapacity" in css
    assert "LawCard" in css
    assert "EntitlementGate" in css


def test_no_uncontrolled_hex_outside_token_blocks():
    css = _css()
    remainder = css
    for prelude in (
        ":root,",
        "html[data-theme=\"dark\"]",
        ".pg-surface--fixed-dark",
    ):
        block = _token_block(css, prelude)
        remainder = remainder.replace(block, "", 1)
    remainder = re.sub(r"/\*.*?\*/", "", remainder, flags=re.S)
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}", remainder)
    assert hexes == [], f"uncontrolled hex in rules: {hexes}"


def test_t35_must_not_ship_strings_absent_from_runtime_assets():
    roots = [TEMPLATES, STATIC]
    skip_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2"}
    hits: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() in skip_suffixes:
                continue
            text = path.read_text(errors="ignore")
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith("docs/"):
                continue
            for code, needle in MUST_NOT_SHIP:
                if needle in text:
                    hits.append(f"{code} {needle!r} in {rel}")
    assert hits == [], hits
    # Runtime templates must not import prototype machinery.
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text()
        assert "support.js" not in text
        assert "<sc-if" not in text
        assert "<sc-for" not in text
        assert "DCLogic" not in text
        assert "Playground.dc.html" not in text
    js = PLAYGROUND_JS.read_text()
    assert "support.js" not in js
    assert "DCLogic" not in js


def test_t38_sheet_enhancement_focus_trap_and_fallback():
    js = PLAYGROUND_JS.read_text()
    assert "function enhanceSheets" in js
    assert "lastOpener" in js
    assert 'event.key === "Escape"' in js
    assert "showModal" in js
    assert "aria-labelledby" in js
    assert "data-pg-sheet-close" in js
    assert "dialog.close()" in js
    assert 'event.key !== "Tab"' in js
    assert "window.location.href = href" in js
    add = (TEMPLATES / "playground_add.html").read_text()
    assert 'role="dialog"' in add
    assert "pg-sheet-panel" in add
    css = _css()
    assert "max-width: 460px" in css
    assert ".pg-sheet::backdrop" in css
    assert "var(--pg-scrim)" in css


def test_t39_tabbar_hide_and_sticky_offset_are_playground_scoped():
    mobile = MOBILE_CSS.read_text()
    assert 'body[data-mscreen="playground"]:has(.pg-learn) .mobile-tabbar' in mobile
    assert 'body[data-mscreen="playground"]:has(.pg-complete) .mobile-tabbar' in mobile
    assert 'body[data-mscreen="playground"]:has(.RolloverPlanner) .mobile-tabbar' in mobile
    assert "body[data-mscreen=\"playground\"] .pg-sticky-cta" in mobile
    assert "var(--m-tabbar" in mobile.split(
        'body[data-mscreen="playground"] .pg-sticky-cta', 1
    )[1][:800]
    # Constitution Learn must not pick up Playground hide rules.
    assert 'body[data-mscreen="learn"]:has(.pg-learn)' not in mobile
    assert 'body[data-mscreen="settings"] .mobile-tabbar' in mobile


def test_d18_d20_desktop_and_phone_shell_markup():
    html = BASE.read_text()
    assert 'class="brand-mark"' in html
    assert "nav-icon" in html
    assert "account-menu-btn-copy" in html
    assert "account-menu-logout" in html
    primary = html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]
    assert "account-menu" not in primary
    assert 'data-account-menu' in html
    tabbar = html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]
    for label in ("Today", "Browse", "Playground", "Calendar", "Profile"):
        assert label in tabbar
    styles = (STATIC / "styles.css").read_text()
    shell = styles.split("/* R1 desktop shell", 1)[1]
    assert ".PrimaryTabs--top .nav-icon" in styles
    assert "height: 60px" in styles
    assert "border-radius: 9px" in styles
    assert "account-menu-btn-copy" in styles
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in shell
    assert "position: absolute" not in shell
    assert "left: 50%" not in shell
    assert "white-space: nowrap" in shell


def test_d21_playground_learn_hides_tabbar_without_touching_constitution(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-mscreen="playground"' in home.text
    assert "PlaygroundShell" in home.text
    assert "class=\"pg-learn\"" not in home.text
    css = client.get("/static/playground.css?v=pg26").text
    assert "--pg-teal:" in css
    mobile = client.get("/static/mobile.css?v=mob98").text
    assert 'body[data-mscreen="playground"] .mobile-tab.is-active' in mobile


def test_d24_back_link_primitive_on_existing_pages():
    select = (TEMPLATES / "playground_select.html").read_text()
    law = (TEMPLATES / "playground_law.html").read_text()
    assert 'class="pg-back"' in select
    assert "← {{ act.short_name }}" in select
    assert 'class="pg-back"' in law
    assert "← Playground" in law
    css = _css()
    assert ".pg-back" in css
    assert "min-height: var(--pg-tap)" in css


def test_constitution_learn_is_not_playground_mscreen(tmp_path: Path):
    app = create_app(
        units_path=ROOT / "tests/fixtures/learning/mini_units.json",
        db_path=tmp_path / "progress.db",
    )
    html = TestClient(app).get("/learn/clause-1").text
    assert 'data-mscreen="learn"' in html
    assert 'data-mscreen="playground"' not in html
    assert "body[data-mscreen=\"playground\"]" not in html
