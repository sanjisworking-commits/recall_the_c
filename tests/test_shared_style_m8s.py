"""M8-S — shared style: label contrast, back link, close controls.

The contrast figures are computed here from the stylesheet's own token values
(WCAG relative-luminance ratio), so a later colour change that drops below the
margin fails this module rather than waiting for a browser probe.

  S01  every Playground label grey clears 5.0:1 on every surface of its theme
  S02  the disabled colour is its own token and only disabled controls use it
  S03  "Current plan" is information: it keeps the label colour
  S04  the back link has no 32 px desktop override; the base rule gives 44 px
  S05  close controls are 44 px (Playground sheet; Calendar dialogs)
  S06  Learn hints and the unselected practice-style option use the label colour
  S07  the Playground error page loads the same stylesheet pin as every page
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_playground_r1 import _token_block

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "constitution_memorizer" / "web" / "static"
TEMPLATES = ROOT / "src" / "constitution_memorizer" / "web" / "templates"
PLAYGROUND_CSS = (STATIC / "playground.css").read_text(encoding="utf-8")
STYLES_CSS = (STATIC / "styles.css").read_text(encoding="utf-8")

MARGIN = 5.0  # the batch's rule: some room above the 4.5:1 requirement
LABEL_TOKENS = ("--pg-muted", "--pg-mid", "--pg-faint")
SURFACE_TOKENS = ("--pg-page", "--pg-paper", "--pg-subtle", "--pg-wash")
BLOCKS = {
    "light": ":root,",
    "dark": 'html[data-theme="dark"]',
    "fixed-dark": ".pg-surface--fixed-dark",
}


def _contrast(fg: str, bg: str) -> float:
    def lum(hex_colour: str) -> float:
        h = hex_colour.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(block: str) -> dict[str, str]:
    return {name: value for name, value in re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})\s*;", block)}


def _site_tokens(prelude: str) -> dict[str, str]:
    """`--page` / `--paper` of the site stylesheet's theme block: Playground
    labels also sit on those surfaces on the account and billing pages."""

    idx = STYLES_CSS.find(prelude)
    assert idx != -1, prelude
    return _tokens(STYLES_CSS[idx:STYLES_CSS.find("}", idx)])


def _rule(css: str, selector: str) -> str:
    """Body of the first rule whose selector list is exactly ``selector``."""

    match = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, selector
    return match.group(1)


# ── S01 ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("theme", sorted(BLOCKS))
def test_s01_label_greys_clear_the_margin_on_every_surface(theme: str) -> None:
    tokens = _tokens(_token_block(PLAYGROUND_CSS, BLOCKS[theme]))
    surfaces = {name: tokens[name] for name in SURFACE_TOKENS}
    if theme == "light":
        surfaces.update({f"site {k}": v for k, v in _site_tokens(":root {").items() if k in ("--page", "--paper")})
    if theme == "dark":
        site = _site_tokens('[data-theme="dark"]')
        surfaces.update({f"site {k}": v for k, v in site.items() if k in ("--page", "--paper")})
        assert {"site --page", "site --paper"} <= set(surfaces)
    for label in LABEL_TOKENS:
        for name, surface in surfaces.items():
            ratio = _contrast(tokens[label], surface)
            assert ratio >= MARGIN, f"{theme}: {label} {tokens[label]} on {name} {surface} is {ratio:.2f}:1"


def test_s01_light_greys_are_one_value_so_none_reads_lighter_than_muted() -> None:
    light = _tokens(_token_block(PLAYGROUND_CSS, BLOCKS["light"]))
    assert light["--pg-muted"] == light["--pg-mid"] == light["--pg-faint"]
    # the values the baseline measured as failing are gone from the label tokens
    for theme, old in (("light", {"#9a9a9a", "#8f8f8d", "#6b6b6b"}), ("dark", {"#7d7a73"})):
        tokens = _tokens(_token_block(PLAYGROUND_CSS, BLOCKS[theme]))
        assert not ({tokens[t] for t in LABEL_TOKENS} & old), theme


# ── S02 ─────────────────────────────────────────────────────────────────────
def test_s02_disabled_colour_is_its_own_token_used_only_by_disabled_controls() -> None:
    for theme, prelude in BLOCKS.items():
        assert "--pg-disabled" in _tokens(_token_block(PLAYGROUND_CSS, prelude)), theme
    rules = re.findall(r"([^{}]+)\{([^{}]*var\(--pg-disabled\)[^{}]*)\}", PLAYGROUND_CSS)
    assert rules, "no rule uses the disabled token"
    for selectors, body in rules:
        for selector in (s.strip() for s in selectors.split(",")):
            assert ":disabled" in selector or ".is-disabled" in selector, selector
        assert "color: var(--pg-disabled);" in body
    # `.is-disabled` on a Playground button stays an inert state, never a link:
    # no template renders an anchor carrying both classes
    for template in TEMPLATES.rglob("*.html"):
        for tag in re.findall(r"<a\b[^>]*>", template.read_text(encoding="utf-8")):
            assert not ("pg-btn" in tag and "is-disabled" in tag), (template.name, tag)


# ── S03 ─────────────────────────────────────────────────────────────────────
def test_s03_current_plan_keeps_the_label_colour() -> None:
    both = re.search(r"\.plus-sub-cta\.is-current,\s*\.plus-sub-cta:disabled\s*\{([^}]*)\}", PLAYGROUND_CSS)
    assert both and "color: var(--pg-mid);" in both.group(1)
    other = re.search(r"\.plus-sub-cta:disabled:not\(\.is-current\)\s*\{([^}]*)\}", PLAYGROUND_CSS)
    assert other and "color: var(--pg-disabled);" in other.group(1)


# ── S04 ─────────────────────────────────────────────────────────────────────
def test_s04_back_link_is_44px_at_every_width() -> None:
    base = _rule(PLAYGROUND_CSS, ".pg-back")
    assert "min-height: var(--pg-tap);" in base
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", PLAYGROUND_CSS):
        if ".pg-back" not in selectors:
            continue
        for height in re.findall(r"min-height:\s*([^;]+);", body):
            assert height.strip() in {"var(--pg-tap)", "var(--pg-tap, 44px)"}, (selectors.strip(), height)
        assert not re.search(r"(?<!min-)(?<!line-)height:\s*\d", body), selectors.strip()
    light = _tokens(_token_block(PLAYGROUND_CSS, BLOCKS["light"]))
    assert "--pg-tap: 44px;" in _token_block(PLAYGROUND_CSS, BLOCKS["light"]) and light


# ── S05 ─────────────────────────────────────────────────────────────────────
def test_s05_close_controls_are_44px() -> None:
    sheet = _rule(PLAYGROUND_CSS, ".pg-sheet-close")
    for needle in ("width: 44px;", "height: 44px;", "min-width: 44px;", "min-height: 44px;"):
        assert needle in sheet
    dialog = re.search(r"\.cal-si-dialog-head button\s*\{([^}]*)\}", STYLES_CSS)
    assert dialog
    body = dialog.group(1)
    assert "width: 44px;" in body and "height: 44px;" in body and "flex: 0 0 auto;" in body
    assert "36px" not in body


# ── S06 ─────────────────────────────────────────────────────────────────────
def test_s06_learn_hints_follow_the_playground_label_colour() -> None:
    hints = re.search(r"\.pg-learn \.learn-hint,[^{}]*\{([^}]*)\}", PLAYGROUND_CSS)
    assert hints and "color: var(--pg-muted);" in hints.group(1)
    selectors = PLAYGROUND_CSS[hints.start():hints.start(1)]
    for needle in (".pg-learn .learn-hint", ".pg-learn .learn-recite-hint", ".pg-learn .learn-stem"):
        assert needle in selectors
    option = re.search(r"\.pg-learn \.learn-letters-view-btn:not\(\.is-active\)\s*\{([^}]*)\}", PLAYGROUND_CSS)
    assert option and "color: var(--pg-muted);" in option.group(1)
    # scoped: the site-wide greys themselves are not changed by this batch
    assert re.search(r"\.learn-hint\s*\{[^}]*color: var\(--faint\);", STYLES_CSS)


# ── S07 ─────────────────────────────────────────────────────────────────────
def test_s07_error_page_uses_the_current_stylesheet_pin() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    pin = re.search(r"/static/playground\.css\?v=(pg\d+)", base).group(1)
    errors = (ROOT / "src" / "constitution_memorizer" / "playground" / "errors.py").read_text(encoding="utf-8")
    assert f"/static/playground.css?v={pin}" in errors
    assert pin == "pg61"
