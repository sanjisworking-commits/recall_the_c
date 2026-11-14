"""M6 — Calendar (classic) by tier (owner decisions of 2026-11-11).

F01 guest `/calendar` stays the sign-in gate (locked).
F02 legends: the desktop month base legend lists the roadmap's six items and
    the Auto Plan "Review" (capacity) item only when the month draws such a
    chip; the week and phone legends are unchanged.
F03 markers per state and model: the shared paid marker on active Plus / Pro /
    Max (and pending, which is subscribed), Plus keeps its own; expired and
    halted markers; Free and paused none.
F04 personal-material create entry points render iff
    `can_add_personal_calendar_tasks`; otherwise the upgrade sheet with one
    "See plans ›" action and no price; the API gate is unchanged (403 on
    create without the capability); GET is mutation-free.
F05 "Continue today's Recall →" → /dashboard on both widths.
F06 the footnote states both ladders.
F07 the week view and Playground chips are untouched (carried by
    `test_calendar_week` and `test_playground_r6`; one smoke row here).
F08 halted phone CSS: the halted block mirrors the expired block.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from constitution_memorizer.web.calendar_view import CalendarChip, CalendarDay, CalendarMonth
import base64

from tests.test_account_family import STATES, USER, _client

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "constitution_memorizer" / "web" / "templates" / "calendar.html"
PG_CSS = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "playground.css"
SIGNED_IN = [s for s in STATES if s != "guest"]
ROADMAP_LEGEND = ["Memorized", "Review done", "Review due", "Scheduled", "New", "Overdue"]
PAID = {"plus", "pro", "max", "pending"}
# Under `choices`, the personal-material capability is a paid capability
# (`entitlements/service.py:248, 261`); under `monthly` it is True for every
# signed-in account (the gate is inert, B1 §4.6).
NO_CAPABILITY_UNDER_CHOICES = {"free", "paused", "expired", "halted"}


def _main(html: str) -> str:
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _legend(html: str, cls: str) -> list[str]:
    block = html.split(f'class="{cls}"', 1)[1].split("</div>", 1)[0] if f'class="{cls}"' in html else ""
    return [t for t in (_text(x) for x in re.findall(r"</span>([^<]+)</span>", block)) if t]


def _section_tag(html: str) -> str:
    main = _main(html)
    return main.split("<section", 1)[1].split(">", 1)[0]


# --------------------------------------------------------------------------- #
# F01 — guest gate                                                             #
# --------------------------------------------------------------------------- #
def test_f01_guest_calendar_is_the_sign_in_gate(tmp_path: Path) -> None:
    client = _client(tmp_path, "guest")
    resp = client.get("/calendar", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?next=%2Fcalendar")
    week = client.get(f"/calendar?view=week&date={date.today().isoformat()}", follow_redirects=False)
    assert week.status_code == 303


# --------------------------------------------------------------------------- #
# F02 — legends                                                                #
# --------------------------------------------------------------------------- #
VISIBLE_LEGEND = ["My material", "Due today", *ROADMAP_LEGEND]


def test_f02_desktop_month_legend_is_the_roadmap_list_without_capacity_chips(tmp_path: Path) -> None:
    html = _client(tmp_path, "free").get("/calendar").text
    main = _main(html)
    # the legend a signed-in account sees is the toolbar legend; the base legend
    # is hidden for signed-in month views by styles.css and keeps the same six items
    assert _legend(main, "cal-si-legend") == VISIBLE_LEGEND
    assert _legend(main, "calendar-legend") == ROADMAP_LEGEND
    css = (ROOT / "src" / "constitution_memorizer" / "web" / "static" / "styles.css").read_text(encoding="utf-8")
    assert "[data-signed-in-calendar]:not(.is-week) .calendar-legend {\n    display: none;" in css
    toolbar = main.split('class="cal-si-legend"', 1)[1].split("</div>", 1)[0]
    assert "is-review-capacity" not in toolbar
    assert "is-review-capacity" not in main.split('class="calendar-legend"', 1)[1].split("</div>", 1)[0]
    assert _legend(main, "cal-m-legend") == ["Today", "Overdue", "Scheduled", "Done", "New"]
    week = _main(_client(tmp_path, "free").get(f"/calendar?view=week&date={date.today().isoformat()}").text)
    assert _legend(week, "calendar-week-legend") == ROADMAP_LEGEND


def test_f02_legend_adds_the_review_capacity_item_only_when_drawn(tmp_path: Path) -> None:
    template_src = TEMPLATE.read_text(encoding="utf-8")
    assert template_src.count("{% if calendar.has_review_capacity %}") == 2  # toolbar legend + base legend
    today = date.today()
    day = CalendarDay(day=today.day, iso=today.isoformat(), is_today=True, is_past=False,
                      chips=[CalendarChip(kind="review_capacity", unit_id="", label="REVIEW · 1", title="1 revision on this day")])
    assert day.chips[0].kind == "review_capacity"
    month = CalendarMonth(year=today.year, month=today.month, title="x", today=today, prev_year=today.year, prev_month=1,
                          next_year=today.year, next_month=12, summary="", weekdays=("S",), days=[day],
                          memorized_count=0, review_done_count=0, scheduled_count=0, has_review_capacity=True)
    assert month.has_review_capacity is True
    assert CalendarMonth.__dataclass_fields__["has_review_capacity"].default is False


# --------------------------------------------------------------------------- #
# F03 — markers                                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
@pytest.mark.parametrize("state", SIGNED_IN)
def test_f03_markers_by_state(tmp_path: Path, state: str, tier_model: str) -> None:
    tag = _section_tag(_client(tmp_path, state, tier_model=tier_model).get("/calendar").text)
    assert "data-signed-in-calendar" in tag
    assert ('data-paid-calendar="desktop"' in tag) is (state in PAID), (state, tag)
    assert ('data-plus-calendar="desktop"' in tag) is (state == "plus")
    assert ('data-expired-calendar="desktop"' in tag) is (state == "expired")
    assert ('data-halted-calendar="desktop"' in tag) is (state == "halted")


# --------------------------------------------------------------------------- #
# F04 — personal-material entry points and the upgrade sheet                   #
# --------------------------------------------------------------------------- #
def _entry_points(html: str) -> dict:
    main = _main(html)
    return {
        "add_task": "data-study-add" in main,
        "cells": main.count("cal-si-cell-add"),
        "day_add": "data-cal-day-add" in main,
        "editor": 'id="cal-si-editor"' in html,
        "gated": len(re.findall(r"data-cal-upgrade(?![-\w])", main)),
        "sheet": 'id="cal-si-upgrade"' in html,
    }


@pytest.mark.parametrize("entitlements", [False, True])
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
@pytest.mark.parametrize("state", SIGNED_IN)
def test_f04_create_entry_points_follow_the_capability(tmp_path: Path, state: str, tier_model: str, entitlements: bool) -> None:
    client = _client(tmp_path, state, tier_model=tier_model, entitlements=entitlements)
    html = client.get("/calendar").text
    pts = _entry_points(html)
    allowed = not (tier_model == "choices" and state in NO_CAPABILITY_UNDER_CHOICES)
    if allowed:
        assert pts["add_task"] and pts["cells"] >= 1 and pts["day_add"] and pts["editor"], (state, tier_model, pts)
        assert pts["gated"] == 0 and not pts["sheet"]
    else:
        assert not pts["add_task"] and pts["cells"] == 0 and not pts["day_add"] and not pts["editor"], (state, tier_model, pts)
        assert pts["gated"] == 2 and pts["sheet"]  # toolbar entry + day-panel entry
        sheet = html.split('id="cal-si-upgrade"', 1)[1].split("</dialog>", 1)[0]
        assert "Personal tasks are part of Plus" in sheet
        assert 'href="/playground?stage=plans">See plans ›</a>' in sheet
        assert "₹" not in sheet and "/billing" not in sheet and "/pricing" not in sheet
        assert 'aria-labelledby="cal-si-upgrade-title"' in sheet and "data-study-close" in sheet
        assert 'aria-haspopup="dialog" aria-controls="cal-si-upgrade"' in _main(html)
    # existing material stays readable regardless (5-6a): the viewer dialog and the script render for every signed-in account
    assert 'id="cal-si-viewer"' in html and "calendar-signed.js?v=cal3" in html
    assert client.get("/api/study-materials/does-not-exist", follow_redirects=False).status_code in (404, 403)


def test_f04_api_gate_is_unchanged_and_get_is_mutation_free(tmp_path: Path) -> None:
    free = _client(tmp_path, "free", tier_model="choices")
    before = free.get("/calendar").text
    token = re.search(r'data-study-token="([^"]+)"', before)
    assert token
    create = free.post("/api/study-materials", data={"title": "x", "studied_on": date.today().isoformat(), "activity": "Studied"},
                       headers={"X-Study-Token": token.group(1)}, follow_redirects=False)
    assert create.status_code == 403
    assert "Personal tasks are part of Plus" in create.text
    assert free.get("/calendar").text.replace(token.group(1), "T") == before.replace(token.group(1), "T")
    plus = _client(tmp_path, "plus", tier_model="choices")
    html = plus.get("/calendar").text
    token2 = re.search(r'data-study-token="([^"]+)"', html).group(1)
    ok = plus.post("/api/study-materials", data={"title": "Notes", "studied_on": date.today().isoformat(), "activity": "Studied"},
                   headers={"X-Study-Token": token2}, follow_redirects=False)
    assert ok.status_code in (200, 201), ok.text[:200]


# --------------------------------------------------------------------------- #
# F05 / F06 — CTA target and footnote                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", ["free", "plus", "expired", "halted"])
def test_f05_continue_today_targets_today_on_both_widths(tmp_path: Path, state: str) -> None:
    html = _client(tmp_path, state).get("/calendar").text
    main = _main(html)
    assert 'data-cal-continue-recall href="/dashboard"' in main
    assert 'href="/playground">Continue today' not in main
    src = TEMPLATE.read_text(encoding="utf-8")
    assert src.count("Continue today’s Recall →") == 2
    assert 'class="cal-m-today-continue" href="/dashboard"' in src


def test_f06_footnote_states_both_ladders(tmp_path: Path) -> None:
    main = _main(_client(tmp_path, "free").get("/calendar").text)
    note = _text(main.split("data-calendar-gcal-footnote>", 1)[1].split("</p>", 1)[0])
    assert "1 → 3 → 7 → 15 → 30 → 60 days (your own study material: 3 → 7 → 15 → 30 → 60)" in note
    assert "Playground due work as the pending rung only" in note


# --------------------------------------------------------------------------- #
# F07 — week and chips untouched (smoke)                                       #
# --------------------------------------------------------------------------- #
def test_f07_week_view_smoke(tmp_path: Path) -> None:
    client = _client(tmp_path, "free")
    today = date.today()
    html = client.get(f"/calendar?view=week&date={today.isoformat()}").text
    assert "is-week" in _section_tag(html)
    assert 'class="calendar-week"' in html
    bad = client.get("/calendar?view=week&date=2026-13-40", follow_redirects=False)
    assert bad.status_code == 400


# --------------------------------------------------------------------------- #
# F08 — halted phone CSS                                                       #
# --------------------------------------------------------------------------- #
def test_f08_halted_phone_block_mirrors_the_expired_block() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    halted = css.split("/* ── M6 · Calendar", 1)[1].split("/* Q1:", 1)[0]
    assert '[data-halted-calendar="desktop"]' in halted
    assert "@media (max-width: 560px)" in halted
    assert "@media (min-width: 561px)" not in halted
    expired = css.split("/* Phone Expired Calendar is expired/05-screen", 1)[1].split("/* Plus desktop /profile", 1)[0]

    def normalise(block: str) -> str:
        block = block.split("*/", 1)[1]  # both slices begin inside their header comment
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        return block.replace('data-halted-calendar="desktop"', "MARK").replace('data-expired-calendar="desktop"', "MARK").strip()

    assert normalise(halted) == normalise(expired)
    # the Plus rules key on the shared paid marker
    plus = css.split("Plus desktop /calendar month view", 1)[1].split("Expired and Halted desktop /calendar", 1)[0]
    assert '[data-paid-calendar="desktop"]' in plus and '[data-plus-calendar="desktop"]' not in plus
    # and the generic Free phone block (mobile.css) excludes every paid account, not only Plus
    mob = (ROOT / "src" / "constitution_memorizer" / "web" / "static" / "mobile.css").read_text(encoding="utf-8")
    assert ":not([data-plus-calendar])" not in mob
    assert mob.count("[data-signed-in-calendar]:not([data-paid-calendar]):not([data-expired-calendar]):not([data-halted-calendar])") >= 30


# --------------------------------------------------------------------------- #
# F09 — 5-6a: a gated account keeps its existing material; writes stay 403     #
# --------------------------------------------------------------------------- #
def _token(client) -> str:
    match = re.search(r'data-study-token="([^"]+)"', client.get("/calendar").text)
    assert match
    return match.group(1)


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _save_entry(client, token: str, title: str = "Preamble notes") -> dict:
    resp = client.post(
        "/api/study-materials",
        # studied three days ago so the first rung (3 days) is due today and can be marked revised
        data={"title": title, "studied_on": (date.today() - timedelta(days=3)).isoformat(), "activity": "Studied", "notes": "mine"},
        files=[("files", ("notes.png", PNG, "image/png"))],
        headers={"X-Study-Token": token},
    )
    assert resp.status_code == 200, resp.text[:200]
    entry = resp.json()
    assert entry["id"] and entry["assets"], entry
    return entry


def test_f09_gated_account_reads_its_material_but_cannot_create_or_edit(tmp_path: Path) -> None:
    # The material is saved while the account is Plus, then the subscription is halted:
    # under `choices` the create capability is gone, the material is not.
    client = _client(tmp_path, "plus", tier_model="choices")
    token = _token(client)
    entry = _save_entry(client, token)
    asset_id = next(a["id"] for a in entry["assets"] if a.get("name") == "notes.png")
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    client.app.state.subscriptions.update_subscription_state(USER, stored.id, status="halted")
    html = client.get("/calendar").text
    assert 'data-halted-calendar="desktop"' in html and 'id="cal-si-upgrade"' in html and 'id="cal-si-editor"' not in html
    # read: the day chip, the detail, the attachment
    assert f'data-study-id="{entry["id"]}"' in html
    detail = client.get(f"/api/study-materials/{entry['id']}")
    assert detail.status_code == 200 and detail.json()["title"] == "Preamble notes"
    media = client.get(f"/api/study-materials/files/{asset_id}")
    assert media.status_code == 200 and media.content == PNG and media.headers["content-type"].startswith("image/png")
    assert media.headers["content-disposition"].startswith("inline")
    # mark revised (not gated by 5-6a)
    done = client.post(f"/api/study-materials/{entry['id']}/reviews/3", data={"done": "true"}, headers={"X-Study-Token": token})
    assert done.status_code == 200
    # create and edit: 403 and nothing changes
    create = client.post("/api/study-materials", data={"title": "New", "studied_on": date.today().isoformat(), "activity": "Studied"},
                         headers={"X-Study-Token": token})
    assert create.status_code == 403 and "Personal tasks are part of Plus" in create.text
    edit = client.post(f"/api/study-materials/{entry['id']}", data={"title": "Renamed", "notes": "changed"}, headers={"X-Study-Token": token})
    assert edit.status_code == 403
    after = client.get(f"/api/study-materials/{entry['id']}").json()
    assert after["title"] == "Preamble notes" and after["notes"] == "mine"
    assert len(client.get("/calendar").text.split('data-study-id="')) == len(html.split('data-study-id="'))
    # the viewer's Edit control is not offered to a gated account (the API would answer 403)
    assert 'id="cal-si-edit"' not in html
    assert 'id="cal-si-edit"' in _client(tmp_path, "pro", tier_model="choices").get("/calendar").text


# --------------------------------------------------------------------------- #
# F10 — another account cannot reach those entries or attachments              #
# --------------------------------------------------------------------------- #
def test_f10_material_and_attachments_are_private_to_their_account(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from constitution_memorizer.auth.fake_provider import FakeAuthProvider
    from constitution_memorizer.auth.sessions import InMemorySessionStore
    from constitution_memorizer.multiuser.settings import clear_settings_cache
    from constitution_memorizer.web.app import create_app
    from tests.test_account_family import USER_B, _settings, _sign_in, _subscribe
    from tests.test_browse_laws_family import UNITS

    clear_settings_cache()
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="A", avatar_url=None)
    app = create_app(units_path=UNITS, db_path=tmp_path / "progress.db", multiuser=True,
                     multiuser_settings=_settings(), auth_provider=provider, session_store=InMemorySessionStore())
    a = TestClient(app)
    _sign_in(a)
    _subscribe(a, STATES["plus"])
    entry = _save_entry(a, _token(a), title="A's notes")
    asset_id = next(x["id"] for x in entry["assets"] if x.get("name") == "notes.png")
    # the fake provider signs in its first seeded Google user: swap in B for the second session
    provider.google_users.clear()
    provider.seed_google_user(user_id=USER_B, email="b@example.com", display_name="B", avatar_url=None)
    b = TestClient(app)
    _sign_in(b)
    _subscribe(b, STATES["plus"], user=USER_B)
    html_b = b.get("/calendar").text
    assert "A's notes" not in html_b and f'data-study-id="{entry["id"]}"' not in html_b
    assert b.get(f"/api/study-materials/{entry['id']}").status_code == 404
    assert b.get(f"/api/study-materials/files/{asset_id}").status_code == 404
    token_b = _token(b)
    assert b.post(f"/api/study-materials/{entry['id']}", data={"title": "B edits A"}, headers={"X-Study-Token": token_b}).status_code == 404
    assert b.post(f"/api/study-materials/{entry['id']}/reviews/3", data={"done": "true"}, headers={"X-Study-Token": token_b}).status_code == 404
    # a stale or missing token is refused before any write, for either account
    assert b.post("/api/study-materials", data={"title": "x", "studied_on": date.today().isoformat()}).status_code == 403
    # A's entry is untouched
    still = a.get(f"/api/study-materials/{entry['id']}")
    assert still.status_code == 200 and still.json()["title"] == "A's notes"
    # signed-out requests are refused outright
    anon = TestClient(app)
    assert anon.get(f"/api/study-materials/files/{asset_id}", follow_redirects=False).status_code == 401


# --------------------------------------------------------------------------- #
# F11 — the Overdue legend item matches what the month grid renders            #
# --------------------------------------------------------------------------- #
def test_f11_overdue_legend_matches_the_month_grid(tmp_path: Path) -> None:
    today = date.today()
    if today.day < 3:
        pytest.skip("needs a past day in the current month")
    client = _client(tmp_path, "free")
    eng = client.app.state.engine.for_user(USER)
    eng.repo.upsert_progress(USER, unit_id="article-14", status="review", times_completed=1,
                             last_completed=today - timedelta(days=5), next_revision=today - timedelta(days=2), interval_days=3)
    eng.repo.upsert_progress(USER, unit_id="article-21", status="review", times_completed=1,
                             last_completed=today - timedelta(days=1), next_revision=today, interval_days=1)
    eng._invalidate_progress_cache()
    html = client.get("/calendar").text
    main = _main(html)
    grid = main.split('class="calendar-grid"', 1)[1].split("cal-si-panel", 1)[0]
    chips = re.findall(r'<a\s+class="calendar-chip ([^"]+)"[^>]*href="/learn/(article-14|article-21)"', grid)
    classes: dict[str, list[str]] = {}
    for cls, unit in chips:  # a row draws its memorized chip, its due chip and the projected rungs
        classes.setdefault(unit, []).append(cls)
    assert "is-due is-overdue" in classes["article-14"], classes
    assert "is-due" in classes["article-21"] and not any("is-overdue" in c for c in classes["article-21"]), classes
    legend = main.split('class="cal-si-legend"', 1)[1].split("</div>", 1)[0]
    assert 'calendar-swatch is-overdue' in legend and 'calendar-swatch is-due"' in legend
    # the Auto Plan "Review" item is listed exactly when the grid draws a review-capacity chip
    assert ("is-review-capacity" in legend) is ("is-review-capacity" in grid)
    css = (ROOT / "src" / "constitution_memorizer" / "web" / "static" / "styles.css").read_text(encoding="utf-8")
    assert ".calendar-chip.is-overdue {" in css and ".calendar-swatch.is-overdue {" in css
    # the week view names the same day Overdue
    week = client.get(f"/calendar?view=week&date={today.isoformat()}").text
    assert "calendar-week-card is-overdue" in week or 'is-overdue"' in week.split('class="calendar-week"', 1)[1]
    # the phone grid's single bar is the overdue state on that day
    phone = html.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]
    assert "is-overdue" in phone


# --------------------------------------------------------------------------- #
# F12 — the script tolerates a page without the editor                        #
# --------------------------------------------------------------------------- #
def test_f12_script_guards_every_editor_reference() -> None:
    js = (ROOT / "src" / "constitution_memorizer" / "web" / "static" / "calendar-signed.js").read_text(encoding="utf-8")
    assert 'const editor = document.getElementById("cal-si-editor");' in js
    assert "if (!editor || !form || !token) return;" in js  # openEditor
    assert "if (!form) return;" in js  # hint()
    assert "if (!el) return;" in js  # error()
    for optional in ('document.getElementById("cal-si-edit")?.', "form?.elements.studied_on?.", "form?.addEventListener", "viewer?.addEventListener", 'document.getElementById("cal-si-preview")?.'):
        assert optional in js, optional
    assert "if (!upgrade) return;" in js
    # editor-only elements are read only inside functions that return first when the editor is absent
    blocks = re.split(r"\n  (?:async )?function ", js)
    guards = ("if (!editor || !form || !token) return;", "if (!form) return;")
    for editor_only in ("cal-si-editor-title", "cal-si-schedule-hint"):
        assert editor_only not in blocks[0], editor_only  # not at module scope
        owners = [b for b in blocks[1:] if editor_only in b]
        assert owners, editor_only
        for block in owners:
            head = block.split("{", 1)[1].lstrip()
            assert head.startswith(guards), (editor_only, head[:60])
    # the form error slot is only ever reached through the null-guarded error() helper
    assert all(m.group(1) == "error" for m in re.finditer(r'(\w+)\("cal-si-form-error"', js))
