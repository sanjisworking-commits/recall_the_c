"""M7a — Playground home, Manage laws and Remove by tier and model.

Decisions Q1–Q11 of `docs/design/milestones/M7.md` (plan approved 2026-11-16).

F01 under ``choices`` the home, Manage laws, Remove and the Act badge print no
    month phrase and no link to the rollover route (5-23); the route itself
    still redirects to Manage laws.
F02 under ``monthly`` the same pages keep today's month copy and rollover
    links (Q6).
F03 RecallC Free under ``choices``: the counter follows the permanent choices
    0 → 3; the upgrade action and the limit paragraph appear only at 3 of 3,
    point at the plans stage and carry no price (5-1); removal keeps the
    choice, the law moves to "Previously chosen", re-adding consumes nothing.
F04 Plus / Pro / Max under ``choices``: "n laws" and "Unlimited · <tier>".
F05 markers: the shared open-Playground marker on every account whose
    Playground is open; the Plus marker on active Plus only (Q7).
F06 Manage laws copy per model and tier, including the page's own Add and
    re-add confirms (Q5).
F07 Remove copy per model and tier (Q5).
F08 GETs under ``choices`` write nothing to the period, roster or ledger.
F09 another account cannot open, learn or remove a law it has not added, and
    the owner's roster is untouched.
F10 stylesheet: the home rules key on the shared marker; the M7a block exists.
F11 `capacity_view` strings per model.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.playground.roster.period import playground_month_bounds, playground_month_name
from constitution_memorizer.playground.urls import add_path, law_path, roster_next_path, roster_path, sections_path
from constitution_memorizer.playground.view import (
    PLAYGROUND_PLANS_PATH,
    capacity_view,
    remove_page_copy,
    roster_page_copy,
)
from tests.conftest import PLAYGROUND_TEST_NOW
from tests.test_account_family import STATES, USER, USER_B, _app, _client, _csrf, _main, _sign_in, _subscribe, _text

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "constitution_memorizer" / "web" / "static"
TEMPLATES = ROOT / "src" / "constitution_memorizer" / "web" / "templates"
# conftest pins the Playground clock to PLAYGROUND_TEST_NOW; the month words to
# look for are that month and its neighbours.
_M = PLAYGROUND_TEST_NOW.month
MONTH_WORDS = "|".join(calendar.month_name[((_M - 1 + d) % 12) + 1] for d in (-1, 0, 1))
MONTH_RE = re.compile(
    rf"((?i:this month|next month|each month|last month|Playground month|your month|monthly Playground|law spaces?)|\b(?:{MONTH_WORDS})\b)"
)
THIS_MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
OPEN_UNDER_CHOICES = ["free", "plus", "pro", "max"]
PAID_OPEN = ["plus", "pro", "max"]


def _post(client: TestClient, path: str, **data):
    return client.post(path, data={"csrf_token": _csrf(client), **data}, follow_redirects=False)


def _add(client: TestClient, law: str):
    resp = _post(client, add_path(law), confirm="add", scope="entire")
    assert resp.status_code == 303 and resp.headers["location"].startswith("/playground/laws/"), (law, resp.headers)
    return resp


def _remove(client: TestClient, law: str):
    resp = _post(client, f"/playground/roster/{law}/remove")
    assert resp.status_code == 303 and resp.headers["location"] == roster_path()
    return resp


def _open(tmp_path: Path, state: str, tier_model: str) -> TestClient:
    client = _client(tmp_path, state, tier_model=tier_model)
    client.get("/playground")  # CSRF cookie
    return client


def _populated(tmp_path: Path, state: str, tier_model: str) -> TestClient:
    """Two active laws and one removed, through the application's own save points."""
    client = _open(tmp_path, state, tier_model)
    for law in ("ndps", "bns", "uapa"):
        _add(client, law)
    _remove(client, "uapa")
    return client


def _month_hits(html: str) -> list[str]:
    text = _text(re.sub(r"<script\b.*?</script>", " ", _main(html), flags=re.S))
    return sorted({text[max(0, m.start() - 24): m.end() + 24] for m in MONTH_RE.finditer(text)})


def _facts(client: TestClient) -> dict:
    conn = client.app.state.roster_repo._conn
    return {
        table: [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()]
        for table in ("user_playground_period", "user_playground_roster_item", "user_playground_choice")
    }


# --------------------------------------------------------------------------- #
# F01 — no month model under ``choices``                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", OPEN_UNDER_CHOICES)
def test_f01_choices_pages_print_no_month_and_no_rollover_link(tmp_path: Path, state: str) -> None:
    empty = _open(tmp_path / "empty", state, "choices").get("/playground").text
    assert _month_hits(empty) == []
    assert roster_next_path() not in _main(empty)
    assert "Your Playground is empty" in _main(empty)

    client = _populated(tmp_path / "full", state, "choices")
    pages = {
        "home": client.get("/playground").text,
        "roster": client.get(roster_path()).text,
        "readd": client.get(roster_path() + "?add=uapa").text,
        "remove": client.get("/playground/roster/ndps/remove").text,
        "law": client.get(law_path("ndps")).text,
    }
    for key, html in pages.items():
        assert _month_hits(html) == [], (state, key, _month_hits(html))
        assert roster_next_path() not in _main(html), (state, key)
    home = _main(pages["home"])
    assert ">Laws</h1>" in home and ">Playground</h1>" in home
    assert "<h2>In Playground</h2>" in home
    assert "<h2>Previously chosen — add again anytime</h2>" in home
    assert ">Manage laws<" in home
    assert 'data-law-id="uapa" data-membership="removed_this_month"' in home
    card = home.split('data-law-id="uapa"', 1)[1].split("</article>", 1)[0]
    assert "Previously chosen" in card and ">Add again<" in card and "Add back" not in card
    assert "In Playground" in _text(_main(pages["law"]))
    # the rollover route stays, unlinked, and only redirects (5-23)
    rollover = client.get(roster_next_path(), follow_redirects=False)
    assert rollover.status_code == 303 and rollover.headers["location"] == roster_path()


# --------------------------------------------------------------------------- #
# F02 — ``monthly`` keeps today's copy                                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", PAID_OPEN)
def test_f02_monthly_pages_keep_the_month_model(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "monthly")
    home = _main(client.get("/playground").text)
    assert f">{THIS_MONTH}</h1>" in home
    assert f">Manage {THIS_MONTH}<" in home
    assert "Playground month" in home
    assert "<h2>In Playground this month</h2>" in home
    assert "<h2>Removed this month</h2>" in home
    assert "Plan next month" in home and home.count(roster_next_path()) == 3
    assert ">Add back<" in home and "Add again" not in home
    assert "data-pg-strip-note" not in home and "data-pg-upgrade" not in home
    roster = _main(client.get(roster_path()).text)
    assert f"<h1>{THIS_MONTH} Playground</h1>" in roster
    assert "It doesn’t free a space this month, and adding it back doesn’t use another one." in roster
    assert "<h2>Active this month</h2>" in roster and "<h2>Removed this month</h2>" in roster
    assert roster.count(roster_next_path()) == 1
    remove = _main(client.get("/playground/roster/ndps/remove").text)
    assert f"Remove from {THIS_MONTH}" in remove
    assert "This does not free a law space this month." in remove
    assert f"In {THIS_MONTH} Playground" in _text(_main(client.get(law_path("ndps")).text))
    assert client.get(roster_next_path(), follow_redirects=False).status_code == 200


# --------------------------------------------------------------------------- #
# F03 — RecallC Free counter under ``choices``                                 #
# --------------------------------------------------------------------------- #
def test_f03_free_counter_follows_the_permanent_choices(tmp_path: Path) -> None:
    client = _open(tmp_path, "free", "choices")
    for used, law in enumerate(("ndps", "bns", "uapa"), start=0):
        home = _main(client.get("/playground").text)
        assert f"{used} of 3 law choices used" in home
        assert f"{3 - used} left · removal never restores a choice" in home
        assert f'data-roster-used="{used}" data-roster-limit="3"' in home
        assert "data-pg-upgrade" not in home and "data-pg-limit-note" not in home
        assert f"{used} of 3 law choices used · Free" in home  # phone strip
        assert "Removing a law never restores a choice" in home
        _add(client, law)
    home = _main(client.get("/playground").text)
    assert "3 of 3 law choices used" in home
    assert "All three used · removal never restores a choice" in home
    assert "0 choices left" in home
    note = home.split("data-pg-limit-note>", 1)[1].split("</p>", 1)[0]
    assert note == (
        "All three choices are used. Each chosen law stays fully learnable, and any you remove can be "
        "added again without using a choice. For more laws, upgrade to Plus."
    )
    upgrade = re.search(r'<a class="pg-btn pg-btn--teal" href="([^"]+)" data-pg-upgrade>([^<]+)</a>', home)
    assert upgrade and upgrade.group(1) == PLAYGROUND_PLANS_PATH
    assert upgrade.group(2) == "Upgrade to Plus · unlimited laws"
    assert home.count("data-pg-upgrade") == 1
    assert "₹" not in home and "/ month" not in home


def test_f03_removal_keeps_the_choice_and_readd_consumes_nothing(tmp_path: Path) -> None:
    client = _populated(tmp_path, "free", "choices")
    ledger = _facts(client)["user_playground_choice"]
    assert len(ledger) == 3
    home = _main(client.get("/playground").text)
    assert "3 of 3 law choices used" in home
    assert "2 in Playground" in home
    assert "1 previously chosen · add again anytime · choice still used" in home
    # a fourth distinct law stays refused; the previously chosen one can come back
    fourth = client.get(roster_path() + "?add=pss")
    assert 'data-playground-gate="free_choices_exhausted"' in fourth.text
    confirm = _main(client.get(roster_path() + "?add=uapa").text)
    dialog = confirm.split('data-roster-confirm="uapa"', 1)[1].split("</article>", 1)[0]
    assert "Add UAPA again?" in dialog
    assert "adding it again uses no choice" in dialog
    assert ">Add again</button>" in dialog
    assert "No extra space used" not in dialog
    back = _post(client, add_path("uapa"), confirm="add", scope="entire")
    assert back.status_code == 303 and "notice=readded" in back.headers["location"]
    assert _facts(client)["user_playground_choice"] == ledger
    notice = _main(client.get(back.headers["location"]).text)
    assert "UAPA is back in your Playground. No choice used." in notice
    assert "3 in Playground" in _main(client.get("/playground").text)


def test_f03_free_roster_add_confirm_states_the_permanent_choice(tmp_path: Path) -> None:
    client = _open(tmp_path, "free", "choices")
    _add(client, "ndps")
    _add(client, "bns")
    confirm = _main(client.get(roster_path() + "?add=uapa").text)
    dialog = confirm.split('data-roster-confirm="uapa"', 1)[1].split("</article>", 1)[0]
    assert "This uses 1 of your 3 law choices — 0 will remain." in dialog
    assert "Removing it later will not restore the choice" in dialog
    assert MONTH_RE.search(_text(dialog)) is None


# --------------------------------------------------------------------------- #
# F04 — paid tiers under ``choices``                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", PAID_OPEN)
def test_f04_paid_home_is_unlimited_without_a_month(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "choices")
    home = _main(client.get("/playground").text)
    word = state.capitalize()
    assert 'data-roster-used="3" data-roster-limit="unlimited"' in home
    assert "<span>3 laws</span>" in home
    assert f"Unlimited · {word}" in home
    assert f"Unlimited laws · {word}" in home  # phone strip
    assert "Every law, whenever you want it" in home
    assert "1 previously chosen · add again anytime" in home and "choice still used" not in home
    assert "law choices used" not in home
    assert "data-pg-upgrade" not in home and "data-pg-limit-note" not in home
    assert ">2 laws<" in home  # phone sub-title counts the active laws


# --------------------------------------------------------------------------- #
# F05 — markers                                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
@pytest.mark.parametrize("state", [s for s in STATES if s != "guest"])
def test_f05_home_markers_by_state(tmp_path: Path, state: str, tier_model: str) -> None:
    html = _client(tmp_path, state, tier_model=tier_model).get("/playground").text
    open_states = {"plus", "pro", "max", "pending"} | ({"free"} if tier_model == "choices" else set())
    assert ('data-open-playground="desktop"' in html) is (state in open_states), state
    assert ("data-open-playground-phone" in html) is (state in open_states), state
    assert ('data-plus-playground="desktop"' in html) is (state == "plus"), state
    assert ("data-plus-playground-phone" in html) is (state == "plus"), state
    if state in open_states:
        assert html.count('class="RosterCapacity"') == 1
    if state in {"expired", "halted"}:
        assert f'data-{state}-playground="desktop"' in html


@pytest.mark.parametrize("state", ["paused", "expired", "halted"])
def test_f05_read_only_homes_change_only_their_month_phrases_under_choices(tmp_path: Path, state: str) -> None:
    monthly_html = _client(tmp_path / "m", state, tier_model="monthly").get("/playground").text
    choices_html = _client(tmp_path / "c", state, tier_model="choices").get("/playground").text
    assert _month_hits(choices_html) == [] and _month_hits(monthly_html) != []
    monthly, choices = _main(monthly_html), _main(choices_html)
    assert "is-readonly" in monthly and "is-readonly" in choices
    # the read-only capacity line stays the plain one: no tier word is promised
    assert "Unlimited · " not in choices
    assert ">Resume Playground<" in choices and ">Resume Playground<" in monthly
    assert roster_next_path() not in choices and roster_next_path() not in monthly


def test_f05_guest_home_is_the_gate(tmp_path: Path) -> None:
    html = _client(tmp_path, "guest").get("/playground").text
    assert "data-open-playground" not in html and "data-guest-pg-intro" in html


# --------------------------------------------------------------------------- #
# F06 / F07 — Manage laws and Remove                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", OPEN_UNDER_CHOICES)
def test_f06_manage_laws_under_choices(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "choices")
    html = client.get(roster_path()).text
    assert "<title>Manage laws ·" in html
    roster = _main(html)
    assert "<h1>Manage laws</h1>" in roster
    rule = _text(roster.split('class="RosterManager-rules">', 1)[1].split("</p>", 1)[0])
    if state == "free":
        assert rule == (
            "Removing a law saves its progress. It does not restore a law choice or allow a different "
            "law instead; adding the same law again uses no choice."
        )
        assert "3 of 3 choices used" in roster and "0 left · never restored by removal" in roster
    else:
        assert rule == "Removing a law saves its progress. You can add it again anytime."
        assert "3 laws" in roster and f"Unlimited · {state.capitalize()}" in roster
    assert "<h2>Active</h2>" in roster
    assert "<h2>Previously chosen — add again anytime</h2>" in roster
    removed = roster.split('data-roster-removed="uapa"', 1)[1].split("</article>", 1)[0]
    assert "Previously chosen" in removed and "Progress saved" in removed
    assert ">Add again</a>" in removed
    assert 'class="pg-plan-row"' not in roster


def test_f06_paid_readd_confirm_under_choices(tmp_path: Path) -> None:
    client = _populated(tmp_path, "plus", "choices")
    dialog = _main(client.get(roster_path() + "?add=uapa").text).split('data-roster-confirm="uapa"', 1)[1].split("</article>", 1)[0]
    assert "Add UAPA again?" in dialog
    assert "Your saved progress comes back with it." in dialog
    assert ">Add again</button>" in dialog and "uses no choice" not in dialog
    back = _post(client, add_path("uapa"), confirm="add", scope="entire")
    assert "UAPA is back in your Playground." in _main(client.get(back.headers["location"]).text)


@pytest.mark.parametrize("state", OPEN_UNDER_CHOICES)
def test_f07_remove_page_under_choices(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "choices")
    html = client.get("/playground/roster/ndps/remove").text
    assert "<title>Remove from Playground · Playground</title>" in html
    page = _main(html)
    assert '<h1 id="pg-remove-title">Remove from Playground</h1>' in page
    assert ">Remove from Playground</button>" in page
    assert "Your progress will be saved." in page
    if state == "free":
        assert "This does not restore a law choice. You can add this law again without using one." in page
    else:
        assert "You can add it again anytime." in page and "law choice" not in page


def test_f06_f07_copy_tables() -> None:
    monthly = roster_page_copy(month_name="September", month_model=True, permanent=False)
    assert monthly["title"] == "September Playground" and monthly["readd_label"] == "Add back"
    assert monthly["removed_heading"] == monthly["removed_badge"] == "Removed this month"
    assert monthly["readd_note"] == "Your saved progress comes with it. No extra space used."
    for permanent in (True, False):
        copy = roster_page_copy(month_name="September", month_model=False, permanent=permanent)
        assert not any(MONTH_RE.search(v) or "September" in v for v in copy.values()), copy
        gone = remove_page_copy(month_name="September", month_model=False, permanent=permanent)
        assert gone["title"] == "Remove from Playground" and "September" not in gone["consequence"]
    assert remove_page_copy(month_name="September", month_model=True, permanent=False) == {
        "title": "Remove from September",
        "consequence": "This does not free a law space this month.",
    }


# --------------------------------------------------------------------------- #
# F12 — "How Playground works" and the guest line (Q9d)                        #
# --------------------------------------------------------------------------- #
GUEST_MONTHLY = "Add laws to your month — up to your plan’s spaces."
GUEST_CHOICES = "Add the laws you want to learn to your Playground."


def test_f12_guest_line_follows_the_period_model(tmp_path: Path) -> None:
    monthly = _client(tmp_path / "m", "guest", tier_model="monthly").get("/playground").text
    choices = _client(tmp_path / "c", "guest", tier_model="choices").get("/playground").text
    assert GUEST_MONTHLY in monthly and GUEST_CHOICES not in monthly
    assert GUEST_CHOICES in choices and GUEST_MONTHLY not in choices
    assert _month_hits(choices) == []
    # nothing is promised to a guest: no count of choices, no price
    intro = choices.split("data-guest-pg-intro", 1)[1].split("</section>", 1)[0]
    assert "choice" not in intro.lower() and "₹" not in intro
    assert "Learn each section verbatim through six recall modes." in intro  # the other steps are unchanged


def test_f12_how_it_works_follows_the_period_model(tmp_path: Path) -> None:
    # the block is printed by gates that have no step list of their own; render the macro itself
    env = _client(tmp_path, "guest").app.state.templates.env
    macro = env.from_string('{% from "partials/playground.html" import how_it_works %}{{ how_it_works(m) }}')
    monthly, choices = macro.render(m=True), macro.render(m=False)
    assert monthly == env.from_string('{% from "partials/playground.html" import how_it_works %}{{ how_it_works() }}').render()
    assert "<strong>Choose your laws each month</strong>" in monthly
    assert "Your Playground holds them for the calendar month." in monthly
    assert "<strong>Next month, decide what to keep</strong>" in monthly
    assert "<strong>Choose your laws</strong>" in choices
    assert "They stay in your Playground until you remove them." in choices
    assert "<strong>Remove and add back anytime</strong>" in choices
    assert "Your saved progress comes back with the law." in choices
    assert "<strong>Progress never disappears</strong>" in choices  # step 2 unchanged
    assert MONTH_RE.search(_text(choices)) is None and choices.count("HowPlaygroundWorks-row") == monthly.count("HowPlaygroundWorks-row")


@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_f12_signed_in_account_reads_its_snapshot(tmp_path: Path, tier_model: str) -> None:
    from starlette.requests import Request

    from constitution_memorizer.web.shell import shell_playground_month_model

    client = _client(tmp_path, "plus", tier_model=tier_model)
    seen: list[bool] = []
    original = client.app.state.templates.env.globals["playground_month_model"]
    assert original is shell_playground_month_model

    def spy(request: Request) -> bool:
        value = original(request)
        seen.append(value)
        return value

    client.app.state.templates.env.globals["playground_month_model"] = spy
    try:
        client.get("/playground?stage=plans")
    finally:
        client.app.state.templates.env.globals["playground_month_model"] = original
    assert seen and all(v is (tier_model == "monthly") for v in seen)


def test_f12_templates_read_the_snapshot_helper_not_the_flag() -> None:
    gate = (TEMPLATES / "playground_gate.html").read_text(encoding="utf-8")
    assert "playground_month_model(request)" in gate
    assert "tier_model" not in gate and "choices_model" not in gate
    partial = (TEMPLATES / "partials" / "playground.html").read_text(encoding="utf-8")
    assert "{% macro how_it_works(month_model=true) %}" in partial


# --------------------------------------------------------------------------- #
# F13 — the paid Add sheet names no month under ``choices`` (W15)              #
# --------------------------------------------------------------------------- #
def _panel(html: str) -> str:
    return html.split("data-pg-add", 1)[1].split("</form>", 1)[0]


@pytest.mark.parametrize("state", ["plus", "pro"])
def test_f13_paid_add_sheet_under_choices(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "choices")
    for law, kind in (("pss", "eligible_to_add"), ("uapa", "re_add")):
        html = client.get(add_path(law)).text
        assert f'data-pg-kind="{kind}"' in html
        panel = _panel(html)
        assert '<p class="pg-eyebrow">Playground</p>' in panel
        assert "joins your Playground — learnable, verbatim. The reader itself never changes." in panel
        assert "this month" not in panel and THIS_MONTH not in _text(panel)
        # the confirmation step is preserved (5-14 not approved)
        assert 'data-step="confirm"' in html and 'data-skip-confirm="false"' in html
        assert "data-pg-add-confirm" in html and 'name="confirm"' in panel
        assert "₹" not in panel


@pytest.mark.parametrize("state", ["plus", "pro"])
def test_f13_paid_add_sheet_under_monthly_is_unchanged(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "monthly")
    panel = _panel(client.get(add_path("pss")).text)
    assert f'<p class="pg-eyebrow">{THIS_MONTH}</p>' in panel
    assert "joins this month's Playground — learnable, verbatim. The reader itself never changes." in panel
    assert "joins your Playground" not in panel


# --------------------------------------------------------------------------- #
# F14 — paid re-add wording on the Act head and in the sheet (W18)             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", ["plus", "pro"])
def test_f14_paid_readd_under_choices_uses_the_home_wording(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "choices")
    head = _text(_main(client.get("/laws/uapa").text))
    assert "Previously chosen" in head and "Add again" in head
    assert "Your saved progress comes back with it." in head
    for gone in ("Removed this month", "Add back", "No extra space used"):
        assert gone not in head, gone
    html = client.get(add_path("uapa")).text
    assert 'data-pg-kind="re_add"' in html
    panel = _panel(html)
    assert "Your saved progress comes back with it." in panel
    assert ">Add again</button>" in panel
    for gone in ("Add back", "No extra space used", "Your progress will be saved."):
        assert gone not in panel, gone
    # a paid account is told nothing about choices
    assert "uses no choice" not in panel and "uses no choice" not in head
    assert 'data-step="confirm"' in html  # the confirmation step stays


@pytest.mark.parametrize("state", ["plus", "pro"])
def test_f14_paid_readd_under_monthly_is_unchanged(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "monthly")
    head = _text(_main(client.get("/laws/uapa").text))
    assert "Removed this month" in head and "Add back" in head and "No extra space used." in head
    assert "Previously chosen" not in head and "Add again" not in head
    panel = _panel(client.get(add_path("uapa")).text)
    assert "Your progress will be saved." in panel and "No extra space used." in panel
    assert ">Add back</button>" in panel


def test_f14_free_readd_keeps_the_m2r_wording(tmp_path: Path) -> None:
    client = _populated(tmp_path, "free", "choices")
    head = _text(_main(client.get("/laws/uapa").text))
    assert "Previously chosen" in head and "Add again" in head
    assert "One of your chosen laws — adding it again uses no choice." in head
    panel = _panel(client.get(add_path("uapa")).text)
    assert "adding it again uses no choice" in panel and ">Add again</button>" in panel


# --------------------------------------------------------------------------- #
# F08 — GETs write nothing under ``choices``                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", ["free", "plus"])
def test_f08_get_walk_writes_nothing_under_choices(tmp_path: Path, state: str) -> None:
    client = _populated(tmp_path, state, "choices")
    before = _facts(client)
    for path in ("/playground", roster_path(), roster_path() + "?add=uapa", "/playground/roster/ndps/remove",
                 roster_next_path(), law_path("ndps"), sections_path("ndps"), add_path("uapa")):
        assert client.get(path, follow_redirects=False).status_code in {200, 303}, path
    assert _facts(client) == before


# --------------------------------------------------------------------------- #
# F09 — another account                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_f09_another_account_cannot_reach_a_law_it_has_not_added(tmp_path: Path, tier_model: str) -> None:
    app = _app(tmp_path / tier_model, tier_model=tier_model, users=(USER,))
    a = TestClient(app)
    _sign_in(a)
    _subscribe(a, STATES["plus"])
    a.get("/playground")
    _add(a, "ndps")
    provider = app.state.auth_provider
    # the fake provider signs in its first seeded Google user: swap in B for the second session
    provider.google_users.clear()
    provider.seed_google_user(user_id=USER_B, email="b@example.com", display_name="B", avatar_url=None)
    b = TestClient(app)
    _sign_in(b)
    _subscribe(b, STATES["plus"], user=USER_B)
    home_b = _main(b.get("/playground").text)
    assert 'data-law-id="ndps"' not in home_b
    assert 'data-roster-active="ndps"' not in _main(b.get(roster_path()).text)
    for path in (law_path("ndps"), "/playground/laws/ndps/sections/1/learn/read",
                 "/playground/laws/ndps/sections/1/learned", "/playground/roster/ndps/remove"):
        resp = b.get(path, follow_redirects=False)
        assert resp.status_code == 303, (path, resp.status_code)
    removed = b.post("/playground/roster/ndps/remove", data={"csrf_token": _csrf(b)}, follow_redirects=False)
    assert removed.status_code in {303, 404}
    # A's law is untouched
    assert app.state.roster.is_law_active_this_period(USER, "ndps")
    assert not app.state.roster.is_law_active_this_period(USER_B, "ndps")
    assert 'data-law-id="ndps" data-membership="in_playground"' in _main(a.get("/playground").text)


# --------------------------------------------------------------------------- #
# F10 — stylesheet and templates                                               #
# --------------------------------------------------------------------------- #
def test_f10_home_rules_key_on_the_shared_marker() -> None:
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert '[data-open-playground="desktop"]' in css and "[data-open-playground-phone]" in css
    assert "[data-plus-playground" not in css
    block = css.split("/* ── M7a · Playground home without the month model", 1)[1]
    for selector in (".pg-strip-note", ".pg-limit-note", ".pg-upgrade-actions"):
        assert selector in block
    # W12: inside the aside card the capacity cells may shrink, so a 30-space bar fits
    assert ".plus-pg-aside-card .RosterCapacity-cell {\n  min-width: 0;\n}" in block
    home = (TEMPLATES / "playground.html").read_text(encoding="utf-8")
    assert "{% if home.month_model %}" in home
    assert "{% if not home.read_only and home.month_model %}" in home
    assert home.count("home.plan_next_href") == 3  # every rollover link sits behind the month model
    roster = (TEMPLATES / "playground_roster.html").read_text(encoding="utf-8")
    assert '{% if month_model %}\n  <a class="pg-plan-row" href="/playground/roster/next">' in roster
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "playground.css?v=pg59" in base
    # templates read the view, never the flag
    for name in ("playground.html", "playground_roster.html", "playground_remove.html", "playground_law.html"):
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "tier_model" not in source and "choices_model" not in source, name


# --------------------------------------------------------------------------- #
# F11 — capacity strings                                                       #
# --------------------------------------------------------------------------- #
def _cap(**kw):
    base = dict(period_start=date(2026, 9, 1), used=3, law_limit=None, remaining=None,
                active_count=2, removed_consumed_count=1)
    base.update(kw)
    return capacity_view(**base)


def test_f11_capacity_strings_per_model() -> None:
    monthly_unlimited = _cap()
    assert monthly_unlimited.used_label == "3 laws this month" and monthly_unlimited.remaining_label == "Unlimited"
    assert monthly_unlimited.month_model is True
    limited = _cap(law_limit=10, remaining=7)
    assert limited.used_label == "3 of 10 laws" and limited.remaining_label == "7 spaces available"
    assert limited.legend_removed == "1 removed this month · space still used"
    paid = _cap(month_model=False, tier_label="Pro")
    assert (paid.used_label, paid.remaining_label) == ("3 laws", "Unlimited · Pro")
    assert paid.legend_removed == "1 previously chosen · add again anytime"
    assert paid.aria_label == "3 laws, unlimited." and paid.month_model is False
    assert _cap(month_model=False, used=1, active_count=1, removed_consumed_count=0).used_label == "1 law"
    free = _cap(law_limit=3, remaining=0, permanent=True, month_model=False)
    assert free.used_label == "3 of 3 law choices used"
    assert free.remaining_label == "All three used · removal never restores a choice"
    assert free.legend_removed == "1 previously chosen · add again anytime · choice still used"
    assert free.legend_available == "0 choices left"
    part = _cap(law_limit=3, used=1, remaining=2, active_count=1, removed_consumed_count=0, permanent=True, month_model=False)
    assert part.remaining_label == "2 left · removal never restores a choice" and part.legend_available == "2 choices left"
    on_roster = _cap(law_limit=3, remaining=0, permanent=True, month_model=False, surface="roster")
    assert (on_roster.used_label, on_roster.remaining_label) == ("3 of 3 choices used", "0 left · never restored by removal")
    for view in (paid, free, part, on_roster):
        joined = " ".join((view.used_label, view.remaining_label, view.legend_in, view.legend_removed,
                           view.legend_available, view.aria_label))
        assert MONTH_RE.search(joined) is None, joined
