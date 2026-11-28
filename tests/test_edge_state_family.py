"""M8-Ra — subscription and device edge states: presentation under today's dispositions.

Every account state is seeded straight into a throwaway local database (no
payment provider). Each is tagged in ``STATES``:

  P  production-reachable: the application's own code can leave an account in
     this stored shape
  S  synthetic fixture: a shape the application does not produce, kept because
     the expired cohort tests pin it

Neither tag proves what the provider does.

  E01  the plans stage for a current subscriber: neutral title, Max card,
       pending account not offered a form the server refuses
  E02  ``?stage=plans`` for paused / halted / ended accounts goes to billing
  E03  a link is a sheet opener only when it leads to an Act's Add dialog
  E04  paused parity: header, Add sheet, Today and Calendar as Resume links
  E05  paused direct requests are refused and change no stored value
  E06  no month wording on Profile and billing under ``choices``;
       ``monthly`` strings unchanged
  E07  device copy: configured limit, the gate's own title on the Add sheet,
       the revoked gate, the Devices lede against the registration predicate
  K    ``test_known_defect_*`` — defects and held findings H1, H2, H3, H7.
       They pin what happens TODAY so a later change is visible. They are not
       desired behaviour and are never to be read as passes of a requirement.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.playground.urls import add_path, is_add_sheet_href, learn_complete_path, sections_path
from constitution_memorizer.web.app import create_app
from tests.conftest import PLAYGROUND_TEST_NOW

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
# The suite pins the entitlement and roster clocks (tests/conftest.py); every period
# and due date here is measured from that instant, never from the day the suite runs.
_TODAY = PLAYGROUND_TEST_NOW.replace(hour=0, minute=0, second=0, microsecond=0)
CALENDAR = f"/calendar?year={PLAYGROUND_TEST_NOW.year}&month={PLAYGROUND_TEST_NOW.month}"
OPEN = (_TODAY - timedelta(days=20), _TODAY + timedelta(days=10))
ELAPSED = (_TODAY - timedelta(days=40), _TODAY - timedelta(days=10))
ENTIRE, SECTIONED, REMOVED, OUTSIDE = "ndps", "bns", "uapa", "pss"
BILLING = "/billing/subscriptions"
DEVICES = "/profile/security/devices"
MODELS = ("monthly", "choices")

STATES: dict[str, dict] = {
    "free": {"reach": "P", "seed": None},
    "plus": {"reach": "P", "seed": "plus"},
    "max": {"reach": "P", "seed": "max"},
    "pending": {"reach": "P", "seed": "plus", "then": {"status": "pending"}},
    "paused": {"reach": "P", "seed": "plus", "then": {"status": "paused"}},
    "paused_elapsed": {"reach": "P", "seed": "plus", "then": {"status": "paused", "period": ELAPSED}},
    "halted": {"reach": "P", "seed": "plus", "then": {"status": "halted"}},
    "halted_elapsed": {"reach": "P", "seed": "plus", "then": {"status": "halted", "period": ELAPSED}},
    "expired_fixture": {"reach": "S", "seed": "plus", "then": {"status": "expired", "period": ELAPSED}},
    "ended_active": {"reach": "P", "seed": "plus", "then": {"period": ELAPSED}},
    "former_paid": {"reach": "P", "seed": "plus", "then": {"status": "expired", "period": ELAPSED, "not_current": True}},
    "abandoned": {"reach": "P", "seed": None, "then_new": {"tier": "plus", "status": "created"}},
}
RESUME_COHORTS = ("paused", "paused_elapsed", "halted", "halted_elapsed", "expired_fixture", "ended_active")


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _settings(tier_model: str, **extra: str) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
        ARTICLE_ENTITLEMENTS_ENABLED="false", **extra,
    )


def _app(tmp: Path, tier_model: str = "monthly", **extra: str):
    clear_settings_cache()
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    tmp.mkdir(parents=True, exist_ok=True)
    return create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                      multiuser_settings=_settings(tier_model, **extra), auth_provider=provider,
                      session_store=InMemorySessionStore(), study_materials_dir=tmp / "study-materials")


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _post(client: TestClient, path: str, data: dict | None = None):
    token = client.cookies.get("rtc_csrf") or ""
    return client.post(path, data=dict({"csrf_token": token} if token else {}, **(data or {})), follow_redirects=False)


def _populate(client: TestClient) -> None:
    """Through the application's own save points; one section learned yesterday so
    Today and the Calendar have a Playground item."""
    for law in (ENTIRE, REMOVED):
        _post(client, add_path(law), {"confirm": "add", "scope": "entire"})
    _post(client, add_path(SECTIONED), {"confirm": "add", "scope": "sections"})
    _post(client, sections_path(SECTIONED), {"section": ["1", "2"]})
    _post(client, f"/playground/roster/{REMOVED}/remove")
    if client.app.state.roster.is_law_active_this_period(USER, SECTIONED):
        for mode in PLAYGROUND_LEARN_MODES:
            client.app.state.playground.complete_mode(
                USER, SECTIONED, f"{SECTIONED}:section:1", mode, source_version="v", source_hash="h",
                as_of=_TODAY.date() - timedelta(days=1))


def _account(tmp_path: Path, state: str, tier_model: str = "monthly", **extra: str) -> TestClient:
    spec = STATES[state]
    client = TestClient(_app(tmp_path / state / tier_model, tier_model, **extra))
    _sign_in(client)
    client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    subs = client.app.state.subscriptions
    if spec.get("seed"):
        subs.create_subscription_record(USER, tier=spec["seed"], status="active", billing_period_start=OPEN[0],
                                        billing_period_end=OPEN[1], is_current=True)
    _populate(client)
    then = spec.get("then")
    if then:
        row = subs.get_current_subscription(USER)
        kwargs = {}
        if "status" in then:
            kwargs["status"] = then["status"]
        if "period" in then:
            kwargs["billing_period_start"], kwargs["billing_period_end"] = then["period"]
        subs.update_subscription_state(USER, row.id, **kwargs)
        if then.get("not_current"):
            subs.mark_not_current(USER, row.id)
    if spec.get("then_new"):
        subs.create_subscription_record(USER, tier=spec["then_new"]["tier"], status=spec["then_new"]["status"], is_current=True)
    return client


def _db(client: TestClient) -> Path:
    return Path(client.app.state.engine.repo.conn.execute("PRAGMA database_list").fetchone()[2])


def _stored(client: TestClient) -> dict[str, list[str]]:
    """Every row of every table the account's data lives in — learning progress,
    selections, overlay items, roster periods and items, the choice ledger,
    devices, device sessions, replacements, the subscription — as stored.
    A before / after comparison of this catches a modified row, not only an
    added or removed one."""

    out: dict[str, list[str]] = {}
    folder = _db(client).parent
    for path in sorted(folder.rglob("*.db")) + sorted(folder.rglob("*.sqlite3")):
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for (name,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
                rows = sorted(repr(row) for row in con.execute(f'select * from "{name}"'))
                if rows:
                    out[f"{path.name}:{name}"] = rows
        finally:
            con.close()
    return out


def _main(html: str) -> str:
    return html.split("<main", 1)[1].split("</main>", 1)[0] if "<main" in html else html


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<script\b.*?</script>", " ", re.sub(r"<[^>]+>", " ", fragment), flags=re.S)).strip()


def _header(html: str) -> str:
    return re.search(r'class="account-menu-btn-status">([^<]*)<', html).group(1).strip()


def _sheet(html: str) -> str:
    return html.split('data-pg-add', 1)[1].split("</section>", 1)[0]


def _openers(html: str) -> list[str]:
    """href of every link marked as a sheet opener."""
    out = []
    for tag in re.findall(r"<a\b[^>]*>", html):
        if re.search(r"\bdata-pg-sheet(?![-\w])", tag):
            out.append(re.search(r'href="([^"]*)"', tag).group(1))
    return out


def _links(html: str) -> list[tuple[str, str]]:
    return [(re.search(r'href="([^"]*)"', tag).group(1), _text(inner))
            for tag, inner in re.findall(r"(<a\b[^>]*href=[^>]*>)(.*?)</a>", html, flags=re.S)]


# --------------------------------------------------------------------------- #
# E01 — plans stage for a current subscriber                                   #
# --------------------------------------------------------------------------- #
FREE_GATE_TITLE = "Your RecallC account already includes the complete Constitution."
TIMING_WORDS = ("immediately", "right away", "applies", "effective", "end of", "billing cycle", "next billing", "1st", "prorat")


@pytest.mark.parametrize("tier_model", MODELS)
def test_e01_paid_holder_plans_stage_is_titled_for_a_plan_change(tmp_path: Path, tier_model: str) -> None:
    client = _account(tmp_path, "plus", tier_model)
    page = client.get("/playground?stage=plans")
    assert page.status_code == 200
    main = _main(page.text)
    assert re.findall(r"<h1[^>]*>(.*?)</h1>", main, flags=re.S) == ["Change your Playground plan"]
    assert "<title>Change your Playground plan · Playground" in page.text
    assert "You’re on RecallC Plus." in main
    assert FREE_GATE_TITLE not in page.text
    # neutral copy: nothing about when a change takes effect, on either clock
    text = _text(main).lower()
    for word in TIMING_WORDS:
        assert word not in text, word
    # the same form, the same route
    assert 'data-pg-plan-form="change"' in main and 'action="/billing/subscriptions/change"' in main
    current = re.search(r"<article[^>]*data-pg-plan-current[^>]*>(.*?)</article>", main, flags=re.S).group(1)
    assert "Plus" in current and "Current plan" in current


@pytest.mark.parametrize("tier_model", MODELS)
def test_e01_free_plans_stage_keeps_the_free_title_and_the_create_form(tmp_path: Path, tier_model: str) -> None:
    client = _account(tmp_path, "free", tier_model)
    main = _main(client.get("/playground?stage=plans").text)
    assert FREE_GATE_TITLE in main and "Change your Playground plan" not in main
    assert 'data-pg-plan-form="create"' in main


def test_e01_max_holder_sees_max_as_the_current_plan_with_no_price_or_promise(tmp_path: Path) -> None:
    client = _account(tmp_path, "max")
    main = _main(client.get("/playground?stage=plans").text)
    assert "You’re on RecallC Max." in main
    current = re.search(r"<article[^>]*data-pg-plan-current[^>]*>(.*?)</article>", main, flags=re.S).group(1)
    assert _text(current) == "Max Current plan"
    assert "₹" not in current
    # Max is not offered: the options are the purchasable plans only
    assert re.findall(r'name="tier" value="([^"]+)"', main) == ["plus", "pro"]


@pytest.mark.parametrize("tier_model", MODELS)
def test_e01_pending_holder_is_not_shown_a_form_the_server_refuses(tmp_path: Path, tier_model: str) -> None:
    """The one permitted exception to the billing-action boundary (owner
    2026-11-27): the unusable plan-change form is not rendered on the plans
    stage. Manage subscription stays; the server's rejection is unchanged."""

    client = _account(tmp_path, "pending", tier_model)
    main = _main(client.get("/playground?stage=plans").text)
    assert "Change your Playground plan" in main and "You’re on RecallC Plus." in main
    assert "data-pg-plan-form" not in main and "<form" not in main
    assert "Plan changes are not available while a payment retry is in progress." in main
    assert (BILLING, "Manage subscription") in _links(main)
    # a direct request is refused exactly as before, and nothing stored changes
    before = _stored(client)
    refused = _post(client, "/billing/subscriptions/change", {"tier": "pro"})
    assert refused.status_code == 303 and refused.headers["location"].startswith(f"{BILLING}?error=")
    assert _stored(client) == before
    row = client.app.state.subscriptions.get_current_subscription(USER)
    assert (row.tier, row.status) == ("plus", "pending")


def test_e01_active_holder_change_request_still_reaches_the_change_route(tmp_path: Path) -> None:
    """The form on the plans stage posts where it always did; this batch adds no
    billing behaviour. (The fixture row has no provider subscription, so the
    route answers with its own error redirect.)"""

    client = _account(tmp_path, "plus")
    answer = _post(client, "/billing/subscriptions/change", {"tier": "pro"})
    assert answer.status_code == 303 and answer.headers["location"].startswith(BILLING)


# --------------------------------------------------------------------------- #
# E02 — ?stage=plans for accounts that cannot open the Playground              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("state", RESUME_COHORTS)
def test_e02_plans_request_goes_to_billing_instead_of_being_ignored(tmp_path: Path, state: str, tier_model: str) -> None:
    client = _account(tmp_path, state, tier_model)
    answer = client.get("/playground?stage=plans", follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == BILLING
    assert client.get(BILLING).status_code == 200
    # the read-only home itself is still served, and still has no plans stage
    home = client.get("/playground", follow_redirects=False)
    assert home.status_code == 200 and "data-pg-plan-form" not in home.text


@pytest.mark.parametrize("state", ["paused", "halted", "expired_fixture"])
def test_e02_calendar_locked_entry_names_the_accounts_own_action_under_choices(tmp_path: Path, state: str) -> None:
    client = _account(tmp_path, state, "choices")
    html = client.get("/calendar").text
    sheet = html.split('id="cal-si-upgrade"', 1)[1].split("</dialog>", 1)[0]
    assert "Personal tasks need an active subscription" in sheet
    assert "Personal tasks are part of Plus" not in sheet and "stage=plans" not in sheet
    label = "Manage subscription" if state == "halted" else "Resume Playground"
    assert (BILLING, label) in _links(sheet)


def test_e02_calendar_locked_entry_is_unchanged_for_free_and_absent_under_monthly(tmp_path: Path) -> None:
    free = _account(tmp_path, "free", "choices").get("/calendar").text
    sheet = free.split('id="cal-si-upgrade"', 1)[1].split("</dialog>", 1)[0]
    assert "Personal tasks are part of Plus" in sheet and 'href="/playground?stage=plans"' in sheet
    for state in ("paused", "halted", "expired_fixture"):
        assert 'id="cal-si-upgrade"' not in _account(tmp_path, state, "monthly").get("/calendar").text


# --------------------------------------------------------------------------- #
# E03 — sheet openers                                                          #
# --------------------------------------------------------------------------- #
def test_e03_only_an_add_dialog_is_a_sheet_target() -> None:
    assert is_add_sheet_href("/playground/laws/ndps/add")
    assert is_add_sheet_href("/playground/laws/ndps/add?scope=sections")
    for href in (BILLING, "/playground?stage=plans", "/playground", DEVICES, "/playground/laws/ndps",
                 "/playground/laws/ndps/sections/1/add", "/playground/laws//add", "", None):
        assert not is_add_sheet_href(href), href


@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("state", sorted(STATES))
def test_e03_no_billing_plans_or_devices_link_is_marked_as_a_sheet_opener(tmp_path: Path, state: str, tier_model: str) -> None:
    client = _account(tmp_path, state, tier_model)
    for path in ("/playground", f"/laws/{ENTIRE}", f"/laws/{OUTSIDE}", f"/laws/{REMOVED}", add_path(OUTSIDE)):
        page = client.get(path, follow_redirects=False)
        if page.status_code != 200:
            continue
        for href in _openers(page.text):
            assert is_add_sheet_href(href), (state, tier_model, path, href)


def test_e03_resume_links_are_plain_links_and_add_links_still_open_the_sheet(tmp_path: Path) -> None:
    for state in ("paused", "expired_fixture", "ended_active"):
        client = _account(tmp_path, state)
        for law in (ENTIRE, OUTSIDE):
            head = client.get(f"/laws/{law}").text
            # the head's action for this account leads to billing, as a plain link
            billing_tags = [tag for tag in re.findall(r"<a\b[^>]*>", _main(head)) if f'href="{BILLING}"' in tag]
            assert billing_tags, (state, law)
            assert not [tag for tag in billing_tags if re.search(r"\bdata-pg-sheet(?![-\w])", tag)], (state, law)
            assert _openers(head) == [], (state, law)
        # the read-only home: cards rewritten to billing carry no opener
        assert _openers(client.get("/playground").text) == []
    plus = _account(tmp_path, "plus")
    tag = re.search(r'<a\s[^>]*class="ActHead-btn[^"]*"[^>]*>', plus.get(f"/laws/{OUTSIDE}").text, flags=re.S).group(0)
    assert f'href="{add_path(OUTSIDE)}"' in tag and "data-pg-sheet" in tag
    # a removed law's "Add back" on the home still opens its Add dialog
    assert add_path(REMOVED) in _openers(plus.get("/playground").text)


# --------------------------------------------------------------------------- #
# E04 — paused parity                                                          #
# --------------------------------------------------------------------------- #
PAUSED_TITLE = "Playground subscription paused"


@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("state", ["paused", "paused_elapsed"])
def test_e04_paused_header_names_the_paused_subscription(tmp_path: Path, state: str, tier_model: str) -> None:
    client = _account(tmp_path, state, tier_model)
    for path in ("/dashboard", "/profile", "/calendar", "/playground"):
        assert _header(client.get(path).text) == PAUSED_TITLE, path
    # the Profile card and the header no longer disagree
    assert "PAUSED" in _text(_main(client.get("/profile").text))


def test_e04_other_header_labels_are_unchanged(tmp_path: Path) -> None:
    expected = {"free": "RecallC Free", "plus": "RecallC Plus", "pending": "RecallC Plus", "max": "RecallC Max",
                "halted": "Payment retries have stopped", "halted_elapsed": "Payment retries have stopped",
                "expired_fixture": "Your Playground is paused", "ended_active": "Your Playground is paused",
                "former_paid": "RecallC Free"}
    for state, label in expected.items():
        assert _header(_account(tmp_path, state).get("/profile").text) == label, state


@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("law", [ENTIRE, OUTSIDE])
def test_e04_paused_add_sheet_states_the_pause_not_an_add_confirmation(tmp_path: Path, law: str, tier_model: str) -> None:
    client = _account(tmp_path, "paused", tier_model)
    sheet = _sheet(client.get(add_path(law)).text)
    assert re.search(r'id="pg-add-title"[^>]*>(.*?)</h1>', sheet, flags=re.S).group(1).strip() == PAUSED_TITLE
    text = _text(sheet)
    assert "Your laws and learning progress are saved." in text
    for stale in ("Add ", "law space", "choice", "?"):
        assert stale not in text.replace("Resume Playground", ""), stale
    assert (BILLING, "Resume Playground") in _links(sheet)
    # no add form is offered
    assert "<form" not in sheet


@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("state", ["paused", "paused_elapsed"])
def test_e04_paused_today_and_calendar_show_playground_items_as_resume_links_only(tmp_path: Path, state: str, tier_model: str) -> None:
    client = _account(tmp_path, state, tier_model)
    for path in ("/dashboard", CALENDAR):
        main = _main(client.get(path).text)
        assert re.search(r"\bBNS\b", _text(main)), path  # the due Playground revision is shown
        hrefs = [h for h, _ in _links(main)]
        # ...only as a link to the existing Resume flow: no Learn link, no opener, no form to Learn
        assert BILLING in hrefs, path
        assert not [h for h in hrefs if h.startswith("/playground/laws/")], path
        assert _openers(main) == [], path
        assert not re.search(r'<form\b[^>]*action="/playground', main), path
    today = _main(client.get("/dashboard").text)
    assert (BILLING, "Resume Playground") in _links(today)


def test_e04_paused_matches_expired_and_differs_from_an_account_with_no_items(tmp_path: Path) -> None:
    """Parity is with the expired cohort's binder; an account that cannot see the
    Playground at all (device limit aside) still shows nothing."""

    expired = _main(_account(tmp_path, "expired_fixture").get(CALENDAR).text)
    paused = _main(_account(tmp_path, "paused").get(CALENDAR).text)
    chip = lambda main: sorted({h for h, t in _links(main) if "BNS" in t})
    assert chip(paused) == chip(expired) == [BILLING]
    assert not re.search(r"\bBNS\b", _text(_main(_account(tmp_path, "former_paid").get(CALENDAR).text)))


# --------------------------------------------------------------------------- #
# E05 — paused: direct requests are refused and nothing stored changes         #
# --------------------------------------------------------------------------- #
def _direct_requests() -> list[tuple[str, str, dict]]:
    stem = f"/playground/laws/{SECTIONED}/sections/1"
    return [
        ("GET", f"{stem}/learn/read", {}),
        ("GET", f"{stem}/learn/read?revision=1", {}),
        ("GET", f"{stem}/learned", {}),
        ("GET", sections_path(SECTIONED), {}),
        ("GET", "/playground/roster", {}),
        ("POST", learn_complete_path(SECTIONED, "1", "read"), {}),
        ("POST", learn_complete_path(SECTIONED, "2", "cloze"), {}),
        ("POST", sections_path(SECTIONED), {"section": ["1", "2", "3"]}),
        ("POST", add_path(OUTSIDE), {"confirm": "add", "scope": "entire"}),
        ("POST", add_path(REMOVED), {"confirm": "add", "scope": "entire"}),
        ("POST", f"/playground/roster/{ENTIRE}/remove", {}),
    ]


@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("state", ["paused", "paused_elapsed"])
def test_e05_paused_direct_requests_are_refused_and_change_no_stored_value(tmp_path: Path, state: str, tier_model: str) -> None:
    client = _account(tmp_path, state, tier_model)
    before = _stored(client)
    assert any(name.endswith(":user_playground_progress") for name in before)  # there is something to protect
    for method, path, data in _direct_requests():
        answer = client.get(path, follow_redirects=False) if method == "GET" else _post(client, path, data)
        # refused: the commercial gate, never the Learn page or a save redirect
        assert "data-pg-learn" not in answer.text, (method, path)
        if answer.status_code in (302, 303):
            assert not answer.headers["location"].startswith("/playground/laws/"), (method, path, answer.headers["location"])
        else:
            assert answer.status_code in (200, 403), (method, path, answer.status_code)
            # the gate page, or the JSON refusal a script-driven save point returns
            refused_json = answer.status_code == 403 and '"ok":false' in answer.text.replace(" ", "")
            assert refused_json or 'data-playground-gate="' in answer.text, (method, path, answer.text[:80])
        # every stored value is what it was: progress, roster, ledger, devices, subscription
        assert _stored(client) == before, (method, path)


@pytest.mark.parametrize("tier_model", MODELS)
def test_e05_paused_page_views_write_nothing(tmp_path: Path, tier_model: str) -> None:
    client = _account(tmp_path, "paused", tier_model)
    before = _stored(client)
    for path in ("/dashboard", "/calendar", CALENDAR, "/calendar?view=week", "/playground", "/playground?stage=plans",
                 f"/laws/{ENTIRE}", add_path(OUTSIDE), "/profile", "/settings", BILLING, DEVICES):
        client.get(path, follow_redirects=False)
        assert _stored(client) == before, path


def test_e05_the_stored_value_dump_detects_a_modified_row(tmp_path: Path) -> None:
    """Guards the guard: a completion by an active account changes an existing
    progress row without adding one, and the dump sees it."""

    client = _account(tmp_path, "plus")
    before = _stored(client)
    saved = _post(client, learn_complete_path(SECTIONED, "2", "read"))
    assert saved.status_code in (200, 303)
    after = _stored(client)
    assert after != before
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert any("playground" in name for name in changed), changed


# --------------------------------------------------------------------------- #
# E06 — month wording under ``choices``                                        #
# --------------------------------------------------------------------------- #
def _card(html: str) -> str:
    return _text(_main(html).split("data-profile-subscription", 1)[1].split("</article>", 1)[0])


def test_e06_profile_card_has_no_month_under_choices_and_is_unchanged_under_monthly(tmp_path: Path) -> None:
    monthly = _card(_account(tmp_path, "plus", "monthly").get("/profile").text)
    assert "This month’s Playground is open." in monthly and "new spaces open" in monthly
    choices = _card(_account(tmp_path, "plus", "choices").get("/profile").text)
    assert "Your Playground is open." in choices and "in your Playground" in choices
    # (the card still names the date the paid period ends: a billing date, not a Playground month)
    for stale in ("This month", "this month", "new spaces open", "laws in " + _TODAY.strftime("%B")):
        assert stale not in choices, stale
    assert "laws in " + _TODAY.strftime("%B") in monthly


def test_e06_paused_card_body_by_model(tmp_path: Path) -> None:
    assert "Resume to keep learning this month’s laws." in _card(_account(tmp_path, "paused", "monthly").get("/profile").text)
    choices = _card(_account(tmp_path, "paused", "choices").get("/profile").text)
    assert "Resume to keep learning your laws." in choices and "month" not in choices.lower()


def test_e06_billing_labels_by_model(tmp_path: Path) -> None:
    monthly = _text(_main(_account(tmp_path, "plus", "monthly").get(BILLING).text))
    assert "active in your Playground each calendar month" in monthly
    choices = _text(_main(_account(tmp_path, "plus", "choices").get(BILLING).text))
    for stale in ("per monthly Playground period", "calendar month", "opens on the 1st"):
        assert stale not in choices, stale
    assert "your progress is never deleted" in choices
    # labels only: the same actions on both
    forms = lambda client: sorted(set(re.findall(r'<form\b[^>]*action="(/billing[^"]*)"', client.get(BILLING).text)))
    assert forms(_account(tmp_path / "f", "plus", "monthly")) == forms(_account(tmp_path / "f", "plus", "choices"))


# --------------------------------------------------------------------------- #
# E07 — devices                                                                #
# --------------------------------------------------------------------------- #
def _plus_app(tmp: Path, **extra: str):
    app = _app(tmp, "monthly", **extra)
    app.state.subscriptions.create_subscription_record(USER, tier="plus", status="active", billing_period_start=OPEN[0],
                                                       billing_period_end=OPEN[1], is_current=True)
    return app


def _browser(app) -> TestClient:
    client = TestClient(app)
    _sign_in(client)
    return client


@pytest.mark.parametrize("limit", [1, 2])
def test_e07_device_limit_gate_and_sheet_state_the_configured_limit(tmp_path: Path, limit: int) -> None:
    app = _plus_app(tmp_path / str(limit), PLAYGROUND_DEVICE_LIMIT=str(limit))
    app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    for _ in range(limit):
        _browser(app).get("/playground")
    extra = _browser(app)
    sentence = f"Your subscription supports Playground on up to {limit} registered devices."
    gate = extra.get("/playground").text
    assert 'data-playground-gate="device_limit"' in gate and sentence in gate
    sheet = _sheet(extra.get(add_path(OUTSIDE)).text)
    # the sheet is the gate's, not an add confirmation with a Manage devices button
    assert re.search(r'id="pg-add-title"[^>]*>(.*?)</h1>', sheet, flags=re.S).group(1).strip() == "Device limit reached"
    assert sentence in sheet and "law space" not in sheet and f"Add {OUTSIDE.upper()}" not in sheet
    assert (DEVICES, "Manage devices") in _links(sheet)
    assert sentence in _text(extra.get(f"/laws/{OUTSIDE}").text)


def _revoke_own_device(client: TestClient) -> None:
    device = re.search(rf"{DEVICES}\?confirm=([0-9a-f-]{{8,}})", client.get(DEVICES).text).group(1)
    assert _post(client, f"{DEVICES}/{device}/remove").headers["location"].startswith("/signed-out")
    _sign_in(client)


@pytest.mark.parametrize("support", ["", "help@example.com"])
def test_e07_revoked_gate_says_what_happened_and_promises_nothing(tmp_path: Path, support: str) -> None:
    app = _plus_app(tmp_path / (support or "none"), **({"SUPPORT_EMAIL": support} if support else {}))
    app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    client = _browser(app)
    client.get("/playground")
    _revoke_own_device(client)
    gate = client.get("/playground").text
    assert 'data-playground-gate="device_revoked"' in gate
    text = _text(_main(gate))
    assert "This device no longer has Playground access." in text
    assert "It was removed from this account’s registered devices." in text
    assert "Your Constitution access and saved progress are unaffected." in text
    for promise in ("register again", "re-register", "restore", "clear", "cookie", "browser data"):
        assert promise not in text.lower(), promise
    links = _links(_main(gate))
    assert (DEVICES, "Manage devices") in links
    if support:
        assert any(href.startswith("mailto:help@example.com") and label == "Contact support" for href, label in links)
    else:
        assert any(label == "Back to Constitution" for _, label in links) and not any(h.startswith("mailto:") for h, _ in links)
    # the Devices page lists it as removed; it offers no way to bring it back
    devices = _main(client.get(DEVICES).text)
    assert "data-device-revoked" in devices and "restore" not in devices.lower()


PAID_LEDE = ("A device is registered the first time you use the Playground on it while your subscription gives "
             "Playground access, including while a payment is being retried.")
UNSUBSCRIBED_LEDE = "This account has no such subscription now, so no device is being registered."


@pytest.mark.parametrize("tier_model", MODELS)
@pytest.mark.parametrize("state", ["free", "plus", "pending", "paused", "halted", "expired_fixture", "former_paid"])
def test_e07_devices_lede_says_what_the_registry_does_for_this_account(tmp_path: Path, state: str, tier_model: str) -> None:
    """The copy is generated from the registration predicate, so the two cannot
    disagree: an account that reads the paid lede is registered on Playground
    use (active or pending), and no other account is."""

    client = _account(tmp_path, state, tier_model)
    rows_before = len(client.app.state.device_service.list_device_summaries(USER, None))
    client.get("/playground", follow_redirects=False)
    registered = len(client.app.state.device_service.list_device_summaries(USER, None))
    main = _main(client.get(DEVICES).text)
    lede = _text(re.search(r"data-device-lede>(.*?)</p>", main, flags=re.S).group(1))
    if state in ("plus", "pending"):
        assert registered == 1, state
        assert lede.endswith(PAID_LEDE) and "up to 2 registered devices" in lede
        assert "1 of 2 devices" in _text(main)
    else:
        assert registered == rows_before, state
        assert UNSUBSCRIBED_LEDE in lede and "Your plan supports" not in lede
    assert "while a paid plan is active" not in main


def test_e07_free_devices_page_shows_no_allowance_count(tmp_path: Path) -> None:
    main = _main(_account(tmp_path, "free").get(DEVICES).text)
    assert "data-device-count" not in main and "of 2 devices" not in main
    assert "No devices registered yet." in main


def test_e07_an_unsubscribed_account_with_a_listed_device_still_sees_the_count_and_can_remove_it(tmp_path: Path) -> None:
    client = _account(tmp_path, "plus")
    client.get("/playground")  # registers this browser
    row = client.app.state.subscriptions.get_current_subscription(USER)
    client.app.state.subscriptions.update_subscription_state(USER, row.id, status="paused")
    main = _main(client.get(DEVICES).text)
    assert "data-device-count" in main and "1 of 2 devices" in _text(main)
    assert UNSUBSCRIBED_LEDE in _text(main) and "Remove" in main


# --------------------------------------------------------------------------- #
# K — known defects and held findings. Not desired behaviour.                  #
# --------------------------------------------------------------------------- #
def test_known_defect_h1_the_pinned_expired_state_is_a_shape_the_service_does_not_keep(tmp_path: Path) -> None:
    """H1. The expired cohort tests seed a terminal status on a row that is
    still current. The service marks a terminal row not-current
    (``_persist_provider``; pinned by ``test_subscription_webhooks``), and in
    that shape the account is simply one without a subscription: under
    ``monthly`` it meets the Free gate and never the read-only "Your
    Playground is paused" home. Decision 5-20 will say what an ended
    subscription becomes; until then this records that the two shapes differ.
    Reverse or delete when 5-20 is implemented."""

    fixture = _account(tmp_path, "expired_fixture")
    assert "Your Playground is paused" in _main(fixture.get("/playground").text)
    assert 'data-playground-gate="not_subscribed"' not in fixture.get("/playground").text
    service_shape = _account(tmp_path, "former_paid")
    home = service_shape.get("/playground").text
    assert 'data-playground-gate="not_subscribed"' in home and "Your Playground is paused" not in home
    assert _header(service_shape.get("/profile").text) == "RecallC Free"


def test_known_defect_h2_former_paid_account_under_choices_keeps_every_law_and_three_fresh_choices(tmp_path: Path) -> None:
    """H2 — ACTIVATION BLOCKER. Approved 5-4 (2026-11-02): on paid → Free the
    original Free choices are preserved, the user explicitly selects any
    remaining allowance, and other laws keep their data without staying
    learnable. Today, under ``choices``, a former paid account has 0 of 3
    choices used, every paid-era law still learnable, and can add more. This
    test pins the DEFECT so it stays visible; it must be reversed when the
    paid → Free selection is built."""

    client = _account(tmp_path, "former_paid", "choices")
    assert client.app.state.subscriptions.get_current_subscription(USER) is None
    home = _text(_main(client.get("/playground").text))
    assert "0 of 3 law choices used" in home
    # both paid-era laws are still in the Playground and learnable
    learn = client.get(f"/playground/laws/{SECTIONED}/sections/1/learn/read")
    assert learn.status_code == 200 and "data-pg-learn" in learn.text
    assert client.app.state.roster.is_law_active_this_period(USER, ENTIRE)
    # and a further law can be added on top of them
    added = _post(client, add_path(OUTSIDE), {"confirm": "add", "scope": "entire"})
    assert added.status_code == 303 and added.headers["location"].startswith("/playground/laws/")


def test_known_defect_h3_an_abandoned_checkout_removes_free_access_under_choices(tmp_path: Path) -> None:
    """H3 — ACTIVATION BLOCKER. A checkout that is started and left stores a
    ``created`` subscription row that stays current. Under ``choices`` the
    account stops being RecallC Free: the Playground it had with its permanent
    choices is hard-gated until the provider expires the row (5-20 row 1 is
    undecided). Pins the DEFECT; reverse when 5-20 row 1 is implemented."""

    client = _account(tmp_path, "free", "choices")
    assert client.get(f"/playground/laws/{SECTIONED}/sections/1/learn/read").status_code == 200
    assert "law choices used" in _text(_main(client.get("/playground").text))
    client.app.state.subscriptions.create_subscription_record(USER, tier="plus", status="created", is_current=True)
    gated = client.get("/playground").text
    assert 'data-playground-gate="not_subscribed"' in gated
    assert "data-pg-learn" not in client.get(f"/playground/laws/{SECTIONED}/sections/1/learn/read").text
    # the choices themselves are still in the ledger; it is the access that is gone
    assert client.app.state.roster.is_law_active_this_period(USER, ENTIRE)


@pytest.mark.parametrize("tier_model", MODELS)
def test_known_defect_h7_billing_page_for_an_elapsed_period_with_an_active_row_is_unchanged(tmp_path: Path, tier_model: str) -> None:
    """H7 — HELD. With the stored period elapsed and the provider row still
    ``active`` the Playground is read-only, while the billing page shows the
    ordinary current-plan actions. An elapsed stored date does not establish
    that the provider subscription has ended, so M8-Ra changes nothing here
    (owner, 2026-11-27): no "Subscribe" treatment, no hidden action. This
    pins the page as it is, pending a reviewed state / action matrix."""

    client = _account(tmp_path, "ended_active", tier_model)
    assert "Your Playground is paused" in _main(client.get("/playground").text)
    billing = client.get(BILLING).text
    forms = sorted(set(re.findall(r'<form\b[^>]*action="(/billing[^"]*)"', billing)))
    assert forms == ["/billing/subscriptions/change"]
    assert "/billing/subscriptions/create" not in billing
    assert "data-expired-subscription" not in billing


def test_e07_replacement_limit_gate_is_reached_and_its_copy_is_unchanged(tmp_path: Path) -> None:
    """Read-back of the third device state: after three replacements inside the
    rolling window, a further new browser meets the replacement-limit gate.
    M8-Ra changes nothing about it; this pins that the state is reachable through
    the application's own registry and still reads as it did."""

    app = _plus_app(tmp_path)
    app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    service = app.state.device_service
    first, second = _browser(app), _browser(app)
    first.get("/playground"), second.get("/playground")
    gate = ""
    for _ in range(6):
        active = [row for row in service.list_device_summaries(USER, None) if row.is_active]
        service.revoke_device(USER, active[0].id)
        gate = _browser(app).get("/playground").text
        if 'data-playground-gate="device_replacement_limit"' in gate:
            break
    assert 'data-playground-gate="device_replacement_limit"' in gate
    text = _text(_main(gate))
    assert "Too many recent device changes" in text
    assert "For account security, new Playground devices are temporarily limited after several replacements." in text
    assert "Your Constitution access and saved progress are unaffected." in text
