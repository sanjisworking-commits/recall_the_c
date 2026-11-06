"""M2-R — Act head and Add dialogs under ``PLAYGROUND_TIER_MODEL=choices``.

Plan §3.2: M2R-F01 (Free CTA states name the choices used; ``re_add`` from
the ledger also at three used; ``free_limit`` for a law outside the ledger),
M2R-F02 (sheet kinds ``free_confirm`` / ``free_readd`` / ``free_limit``; no
date promise, no price, no removal advice), M2R-F03 (the save-failure verdict
distinguishes a confirmed rollback from an unknown outcome; Retry re-reads),
M2R-F04 (the paid confirm step is unchanged), M2R-F05 (the chapterless MTP
head carries the same states), D31 and D32. The default model (``monthly``)
is asserted unchanged: a Free account still meets the subscribe sheet.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_LIMIT,
    BLOCK_SUBSCRIPTION_PAUSED,
)
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.playground.eligibility import playground_bare_act_spec
from constitution_memorizer.playground.roster.models import mark_save_rolled_back
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.playground.view import _gate_sentences, free_add_label, gate_view
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/constitution_memorizer/web/static"
PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
USER = UUID("a2a2a2a2-a2a2-4a2a-8a2a-a2a2a2a2a2a2")


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(tier_model: str | None) -> MultiUserSettings:
    kwargs = dict(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
    )
    if tier_model is not None:
        kwargs["PLAYGROUND_TIER_MODEL"] = tier_model
    return MultiUserSettings(**kwargs)


def _client(tmp_path: Path, *, tier_model: str | None = "choices", sign_in: bool = True) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="m2r@example.com", display_name="M2R")
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_settings(tier_model),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=ProgressRepository(open_progress_db(tmp_path / "progress.db")),
            study_materials_dir=tmp_path / "study-materials",
        )
    )
    if sign_in:
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    return client


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _subscribe(client: TestClient, *, tier: str = "plus", status: str = "active") -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _add_entire(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload.update({"confirm": "add", "scope": "entire"})
    return client.post(add_path(law_id), data=payload, follow_redirects=False)


def _remove(client: TestClient, law_id: str):
    return client.post(f"/playground/roster/{law_id}/remove", data=_csrf(client), follow_redirects=False)


def _cta(html: str) -> str:
    assert 'class="ActHead-cta LawPlaygroundCta"' in html
    return html.split('class="ActHead-cta LawPlaygroundCta"', 1)[1].split("</div>\n      </div>", 1)[0]


def _panel(html: str) -> str:
    assert 'class="pg-sheet-panel"' in html
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


def _reading(law_id: str) -> str:
    spec = playground_bare_act_spec(law_id)
    assert spec is not None
    return spec.short_name


def _ledger_count(client: TestClient) -> int:
    roster = client.app.state.roster
    return len(list(roster.choice_law_ids(USER)))


# ───────────────────────── M2R-F01 · Act-head CTA states ─────────────────────────


def test_free_add_label_counts_choices_used():
    assert free_add_label(0, 3) == "Add to Playground · 0 of 3 choices used"
    assert free_add_label(2, 3) == "Add to Playground · 2 of 3 choices used"
    assert free_add_label(0, None) == "Add to Playground · 0 of 3 choices used"


def test_free_act_head_counts_choices_and_closes_at_three(tmp_path: Path):
    client = _client(tmp_path / "f01")
    cta = _cta(client.get("/laws/ndps").text)
    assert 'data-pg-kind="eligible_to_add"' in cta
    assert ">Add to Playground · 0 of 3 choices used</a>" in cta
    assert "data-pg-sheet" in cta and f'href="{add_path("ndps")}"' in cta
    assert "Subscribe to use Playground" not in cta and 'data-pg-kind="subscribe"' not in cta

    assert _add_entire(client, "ndps").status_code == 303
    assert ">Add to Playground · 1 of 3 choices used</a>" in _cta(client.get("/laws/uapa").text)
    assert _add_entire(client, "uapa").status_code == 303
    assert ">Add to Playground · 2 of 3 choices used</a>" in _cta(client.get("/laws/pss").text)
    assert _add_entire(client, "pss").status_code == 303

    # P-NEW false at three used: a law outside the ledger meets free_limit …
    limit = _cta(client.get("/laws/bns").text)
    assert 'data-pg-kind="free_limit"' in limit
    assert ">All 3 law choices used</a>" in limit
    assert "data-pg-sheet" in limit
    assert "Choices used" in limit
    # … while the chosen laws stay active.
    active = _cta(client.get("/laws/ndps").text)
    assert 'data-pg-kind="already_active"' in active and "Already in Playground" in active
    assert _ledger_count(client) == 3


def test_free_readd_is_offered_from_the_ledger_even_at_three_used(tmp_path: Path):
    client = _client(tmp_path / "readd")
    for law in ("ndps", "uapa", "pss"):
        assert _add_entire(client, law).status_code == 303
    assert _remove(client, "ndps").status_code == 303
    cta = _cta(client.get("/laws/ndps").text)
    assert 'data-pg-kind="re_add"' in cta
    assert ">Add again</a>" in cta
    assert "Previously chosen" in cta
    assert "adding it again uses no choice" in cta
    assert "free_limit" not in cta
    # Re-adding consumes nothing.
    sheet = _panel(client.get(add_path("ndps")).text)
    assert 'data-pg-kind="free_readd"' in sheet
    assert _add_entire(client, "ndps").status_code == 303
    assert _ledger_count(client) == 3
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")


def test_free_historical_progress_note_has_no_month(tmp_path: Path):
    client = _client(tmp_path / "hist")
    assert _add_entire(client, "ndps").status_code == 303
    assert _remove(client, "ndps").status_code == 303
    cta = _cta(client.get("/laws/ndps").text)
    # Removed → ledger → re_add (not "Add to this month").
    assert "this month" not in cta
    assert 'data-pg-kind="re_add"' in cta


# ───────────────────────── M2R-F02 · sheet kinds ─────────────────────────


def test_free_confirm_sheet_is_the_permanent_choice_warning(tmp_path: Path):
    client = _client(tmp_path / "confirm")
    name = _reading("ndps")
    html = client.get(add_path("ndps")).text
    panel = _panel(html)
    assert 'data-pg-kind="free_confirm"' in panel
    assert f'data-pg-law-name="{name}"' in panel
    assert '<p class="pg-eyebrow">RecallC Free · permanent choice</p>' in panel
    assert '<h1 id="pg-add-title" class="pg-add-title">Add to Playground</h1>' in panel
    assert f"{name} becomes one of your Playground laws — learnable, verbatim." in panel
    assert (
        '<p class="pg-add-warning" data-pg-free-warning>This uses 1 of your 3 law choices — 2 will remain.</p>'
        in panel
    )
    assert "Removing it later will not restore the choice, though you can always add this law again." in panel
    # No month, no price, no revision-date promise (5-12), no removal advice.
    assert "joins this month" not in panel and "this month" not in panel
    assert "₹" not in panel and "revision" not in panel.lower() and "exactly as you left" not in panel
    assert '<button type="submit" class="pg-add-primary">Add to Playground</button>' in panel
    assert f'<a class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in panel
    assert 'data-step="confirm"' in panel
    # The failure banner slot sits on the scope step (M2R-F03).
    assert '<div class="pg-add-alert" role="alert" data-pg-add-alert hidden></div>' in panel

    # Confirm → scope step (the choice is not consumed by the confirm POST).
    step = client.post(add_path("ndps"), data={**_csrf(client), "confirm": "add"}, follow_redirects=False)
    assert step.status_code == 200
    scope = _panel(step.text)
    assert 'data-step="scope"' in scope and ">Entire Act<" in scope and ">Choose sections<" in scope
    assert _ledger_count(client) == 0

    # After one choice the remaining count follows the ledger.
    assert _add_entire(client, "ndps").status_code == 303
    second = _panel(client.get(add_path("uapa")).text)
    assert "This uses 1 of your 3 law choices — 1 will remain." in second


def test_free_readd_sheet_uses_no_choice_and_promises_no_dates(tmp_path: Path):
    client = _client(tmp_path / "readd-sheet")
    name = _reading("ndps")
    assert _add_entire(client, "ndps").status_code == 303
    assert _remove(client, "ndps").status_code == 303
    panel = _panel(client.get(add_path("ndps")).text)
    assert 'data-pg-kind="free_readd"' in panel
    assert f'<h1 id="pg-add-title" class="pg-add-title">Add {name} again?</h1>' in panel
    assert "One of your chosen laws — adding it again uses no choice." in panel
    assert "Your saved progress comes back with it." in panel
    assert "exactly as you left" not in panel and "revision" not in panel.lower()
    assert "pg-add-warning" not in panel and "this month" not in panel
    assert '<button type="submit" class="pg-add-primary">Add again</button>' in panel
    assert 'href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in panel


def test_free_limit_sheet_has_no_price_no_rollover_and_closes_to_the_act(tmp_path: Path):
    client = _client(tmp_path / "limit")
    for law in ("ndps", "uapa", "pss"):
        assert _add_entire(client, law).status_code == 303
    panel = _panel(client.get(add_path("bns")).text)
    assert 'data-pg-kind="free_limit"' in panel
    assert 'data-playground-gate="free_choices_exhausted"' in panel
    assert "₹" not in panel
    assert "Plan next month" not in panel and "/playground/roster/next" not in panel
    assert "Back to Playground" not in panel
    assert "Remov" not in panel  # no removal advice
    assert ">Subscribe to Plus</a>" in panel and ">Subscribe to Pro</a>" in panel
    assert "Max" not in panel
    assert '<a class="pg-add-secondary" href="/laws/bns" data-pg-sheet-close>Close</a>' in panel
    # A fourth distinct law is still refused by the save point itself.
    assert _add_entire(client, "bns").status_code == 200
    assert _ledger_count(client) == 3


def test_guest_sheet_stays_the_guest_kind_under_choices(tmp_path: Path):
    client = _client(tmp_path / "guest", sign_in=False)
    panel = _panel(client.get(add_path("ndps")).text)
    assert 'data-pg-kind="guest"' in panel
    assert "free_confirm" not in panel and "subscribe" not in panel.split("data-pg-kind", 1)[1][:40]


def test_monthly_model_keeps_free_on_the_subscribe_sheet(tmp_path: Path):
    client = _client(tmp_path / "monthly", tier_model=None)
    cta = _cta(client.get("/laws/ndps").text)
    assert 'data-pg-kind="subscribe"' in cta and ">Subscribe to use Playground</a>" in cta
    panel = _panel(client.get(add_path("ndps")).text)
    assert 'data-pg-kind="subscribe"' in panel
    assert "free_confirm" not in panel and "choices used" not in panel


# ───────────────────────── M2R-F04 · paid confirm unchanged ─────────────────────────


@pytest.mark.parametrize("tier", ("plus", "pro"))
def test_paid_confirm_step_is_unchanged_under_choices(tmp_path: Path, tier: str):
    client = _client(tmp_path / f"paid-{tier}")
    _subscribe(client, tier=tier)
    cta = _cta(client.get("/laws/ndps").text)
    assert 'data-pg-kind="eligible_to_add"' in cta and ">+ Add to Playground</a>" in cta
    assert "choices used" not in cta
    panel = _panel(client.get(add_path("ndps")).text)
    assert 'data-pg-kind="eligible_to_add"' in panel
    assert "joins this month's Playground — learnable, verbatim." in panel
    assert "pg-add-warning" not in panel and "free_confirm" not in panel
    assert 'data-step="confirm"' in panel  # 5-14 not approved: the confirm step stays


# ───────────────────────── M2R-F05 · MTP flat head ─────────────────────────


def test_chapterless_mtp_head_carries_the_free_states(tmp_path: Path):
    client = _client(tmp_path / "mtp")
    cta = _cta(client.get("/laws/mtp").text)
    assert 'data-pg-kind="eligible_to_add"' in cta
    assert ">Add to Playground · 0 of 3 choices used</a>" in cta
    for law in ("ndps", "uapa", "pss"):
        assert _add_entire(client, law).status_code == 303
    limit = _cta(client.get("/laws/mtp").text)
    assert 'data-pg-kind="free_limit"' in limit and ">All 3 law choices used</a>" in limit


# ───────────────────────── M2R-F03 · failure verdicts ─────────────────────────


def _post_entire_json(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload.update({"confirm": "add", "scope": "entire"})
    return client.post(
        add_path(law_id),
        data=payload,
        headers={"Accept": "application/json, text/html;q=0.9", "X-Requested-With": "pg-sheet"},
        follow_redirects=False,
    )


def test_confirmed_rollback_is_reported_as_rolled_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _client(tmp_path / "rb")
    roster = client.app.state.roster

    def boom(*args, **kwargs):
        raise mark_save_rolled_back(RuntimeError("disk full"))

    monkeypatch.setattr(roster, "confirm_add_law", boom)
    resp = _post_entire_json(client, "ndps")
    assert resp.status_code != 303
    assert resp.headers.get("content-type", "").startswith("application/json")
    body = resp.json()
    assert body == {"ok": False, "error": "save_failed", "outcome": "rolled_back"}
    assert _ledger_count(client) == 0


def test_failure_without_rollback_evidence_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _client(tmp_path / "unk")
    roster = client.app.state.roster

    def boom(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(roster, "confirm_add_law", boom)
    body = _post_entire_json(client, "ndps").json()
    assert body["ok"] is False and body["error"] == "save_failed"
    assert body["outcome"] == "unknown"


def test_retry_rereads_the_state_instead_of_reposting(tmp_path: Path):
    """The script's Retry fetches the sheet again; a save that did commit
    answers that GET with the already-active redirect, never a second add."""
    client = _client(tmp_path / "retry")
    assert _add_entire(client, "ndps").status_code == 303
    again = client.get(
        add_path("ndps") + "?step=scope",
        headers={"X-Requested-With": "pg-sheet"},
        follow_redirects=False,
    )
    assert again.status_code == 303 and "/playground/laws/ndps" in (again.headers.get("location") or "")
    assert _ledger_count(client) == 1
    js = (STATIC / "playground.js").read_text(encoding="utf-8")
    assert "[data-add-step='scope'] form" in js
    assert 'out.json.error === "save_failed"' in js
    assert 'out.json.outcome === "rolled_back" ? "rolled_back" : "unknown"' in js
    assert "Nothing was changed." in js and "may or may not have been added" in js
    assert 'showAddFailure(root, "unknown")' in js  # network failure → unknown, never "nothing changed"
    assert "rereadAddSheet(root)" in js and "step=scope" in js
    assert "pg-sheet:swap" in js
    assert "data-pg-add-retry" in js


def test_failure_banner_styles_and_pins():
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    for selector in (".pg-add-alert {", ".pg-add-alert-btn,\n.pg-add-alert-link {", ".pg-add-warning {"):
        assert selector in css
    btn = css.split(".pg-add-alert-btn,\n.pg-add-alert-link {", 1)[1].split("}", 1)[0]
    assert "min-height: 44px" in btn
    for rule in (".pg-add-alert {", ".pg-add-warning {"):
        block = css.split(rule, 1)[1].split("}", 1)[0]
        assert "var(--pg-" in block and "#" not in block  # tokens only: both themes
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg55" in base and "playground.js?v=pg13" in base
    panel = PANEL.read_text(encoding="utf-8")
    assert 'data-pg-add-alert hidden' in panel and 'role="alert"' in panel


# ───────────────────────── D31 / D32 ─────────────────────────


def test_pending_sheet_cancel_closes_the_sheet_onto_the_act():
    panel = PANEL.read_text(encoding="utf-8")
    pending = panel.split('{% elif blocked_pending or kind == "pending" %}', 1)[1].split("{% elif", 1)[0]
    assert '<a class="pg-add-secondary" href="{{ cancel_href }}" data-pg-sheet-close>Cancel</a>' in pending
    assert 'href="/playground">Cancel' not in panel


def test_device_blocked_and_resume_notes_are_punctuated():
    device = _gate_sentences(gate_view(reason=BLOCK_DEVICE_LIMIT))
    assert device.startswith("Device limit reached. ")
    assert re.search(r"[.!?] [A-Z]", device)
    paused = _gate_sentences(gate_view(reason=BLOCK_SUBSCRIPTION_PAUSED))
    assert ". " in paused or paused.endswith(".")
    assert "reached Your" not in device


def test_guest_sheet_offers_one_google_action_back_to_the_act(tmp_path: Path):
    """5-11 (owner, 2026-11-06): the guest Add sheet has one action, "Continue
    with Google"; signing in creates the account and ``next`` returns to this
    Act's Add dialog. No second button, no form."""
    client = _client(tmp_path, sign_in=False)
    html = client.get(add_path("ndps")).text
    panel = _panel(html)
    assert 'data-pg-kind="guest"' in html
    assert panel.count("data-guest-add-gate") == 1
    href = "/auth/google/start?next=%2Fplayground%2Flaws%2Fndps%2Fadd"
    assert (
        f'<a class="pg-add-primary" href="{href}" data-guest-add-gate data-guest-add-google>Continue with Google</a>'
    ) in panel
    for gone in ("Create an account", ">Sign in<", "pg-add-secondary", "/login?next=", "<form", "<button"):
        assert gone not in panel, gone


def test_upgrade_surfaces_print_no_price_until_pricing_is_approved(tmp_path: Path):
    """5-1 (owner, 2026-11-06): neither the Free subscribe sheet nor the
    Act-head Free note prints "from ₹…" under ``monthly``."""
    client = _client(tmp_path, tier_model="monthly")
    head = client.get("/laws/ndps").text
    assert '<p class="ActHead-note">Unlock Playground to add this law.</p>' in head
    assert "from ₹" not in head
    html = client.get(add_path("ndps")).text
    assert 'data-pg-kind="subscribe"' in html
    sheet = _panel(html)
    assert "Plus · Pro. Constitution learning stays free." in sheet
    assert "₹" not in sheet
