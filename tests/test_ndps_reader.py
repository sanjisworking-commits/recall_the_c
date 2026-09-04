"""Bare Act pathway: Laws → the NDPS Act → chapters → a section reader.

The Act is reference material. Nothing on this path may claim a reader has
learned anything, so the assertions below care as much about what does *not*
happen — no progress, no revision, no calendar row — as about what renders.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import (
    BareActMissing,
    get_bare_act,
    split_on_footnotes,
    title_case_chapter,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _mu_settings(**overrides) -> MultiUserSettings:
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
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _mu_client(tmp_path: Path, *, signed_in: bool, **overrides) -> TestClient:
    provider = FakeAuthProvider()
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_mu_settings(**overrides),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
        )
    )
    if signed_in:
        provider.seed_google_user(
            user_id=USER_ID, email="a@example.com", display_name="A"
        )
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        client.get(
            f"/auth/callback?code=fake-google-code&state={state}",
            follow_redirects=False,
        )
    return client


# ── The Act itself ────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("ndps")
    assert act is not None
    assert act.title == (
        "The Narcotic Drugs and Psychotropic Substances Act, 1985"
    )
    assert len(act.chapters) == 8
    assert len(act.section_order) == 129
    assert act.meta_label == "8 Chapters · Sections 1–83"


def test_section_numbers_stay_strings():
    """7A, 25A, 68-I and 68Z are section numbers. Only some are integers."""
    act = get_bare_act("ndps")
    for number in ("1", "7A", "31A", "65", "68-I", "68Z", "83"):
        section = act.section(number)
        assert section is not None, number
        assert isinstance(section.number, str)
        assert section.number == number
    # The Act's own order, never a numeric sort.
    numbers = [s.number for s in act.section_order]
    assert numbers[:4] == ["1", "2", "3", "4"]
    assert numbers[numbers.index("7") + 1] == "7A"
    assert numbers[-1] == "83"


def test_chapter_titles_are_no_longer_shouted():
    act = get_bare_act("ndps")
    titles = [c.title for c in act.chapters]
    assert titles[0] == "Preliminary"
    assert titles[2] == "National Fund for Control of Drug Abuse"
    assert titles[3] == "Prohibition, Control and Regulation"
    assert titles[6] == "Forfeiture of Illegally Acquired Property"
    assert title_case_chapter("OFFENCES AND PENALTIES") == "Offences and Penalties"


def test_chapter_ranges_span_first_to_last_section():
    act = get_bare_act("ndps")
    ranges = [c.range_label for c in act.chapters]
    assert ranges[0] == "1–3"
    assert ranges[2] == "7A–7B"
    assert ranges[6] == "68A–68Z"


def test_neighbours_cross_chapter_boundaries():
    act = get_bare_act("ndps")
    # 7 ends Chapter II; 7A opens Chapter IIA.
    assert [s.number for s in act.neighbours("7")] == ["6", "7A"]
    # 68Z ends Chapter VA; 69 opens Chapter VI.
    assert [s.number for s in act.neighbours("68Z")] == ["68Y", "69"]
    # The Act has two ends, and neither has a neighbour past it.
    assert act.neighbours("1")[0] is None
    assert act.neighbours("83")[1] is None


def test_nesting_is_preserved_as_depth():
    act = get_bare_act("ndps")
    rows = act.section("1").rows
    # (1), (2), (2)(a), (2)(b), (3)
    assert [(r.depth, r.label) for r in rows] == [
        (0, "(1)"),
        (0, "(2)"),
        (1, "(a)"),
        (1, "(b)"),
        (0, "(3)"),
    ]
    # Section 9 nests four levels: subsection → clause → subclause → proviso.
    deep = act.section("9").rows
    assert max(r.depth for r in deep) == 3
    assert any(r.depth == 3 and r.kind == "proviso" for r in deep)


def test_section_65_is_omitted_not_missing():
    act = get_bare_act("ndps")
    section = act.section("65")
    assert section.is_omitted
    # The canonical title is the literal "[Omitted]" — brackets are a print
    # convention, and `status` already says this.
    assert section.title == "[Omitted]"
    assert section.list_title == "Omitted"
    assert section.former_title.startswith("Power to make rules")
    assert "1989" in section.omission_note


def test_the_31a_table_survives_as_a_table():
    act = get_bare_act("ndps")
    tables = [r for r in act.section("31A").rows if r.is_table]
    assert len(tables) == 1
    table = tables[0]
    assert table.table_columns == ("item", "particulars", "quantity")
    assert len(table.table_body) == 14
    assert table.table_body[0][0] == "(i)"
    assert table.table_body[-1][0] == "(xiv)"
    # Print leader dots are a column rule, not data.
    assert table.table_body[0][1] == "Opium"
    assert table.table_body[0][2] == "10 kgs."


def test_the_adapter_does_not_discard_canonical_fields():
    """View models expose what templates need; the file keeps everything."""
    act = get_bare_act("ndps")
    assert act.raw["schema_version"] == "2.5"
    assert len(act.raw["footnotes"]) == 108
    body = act.section("1").body
    assert body[1]["annotations"][0]["note_id"] == "footnote_p5_2"
    assert body[1]["source_pages"] == [5]
    assert act.section("1").body is not None


def test_a_missing_act_raises_rather_than_reading_as_empty(monkeypatch):
    monkeypatch.setattr(bare_acts, "_REPO_ROOT", Path("/nonexistent"))
    monkeypatch.setattr(bare_acts, "_WEB_DIR", Path("/nonexistent"))
    bare_acts._load_cached.cache_clear()
    with pytest.raises(BareActMissing):
        get_bare_act("ndps")
    bare_acts._load_cached.cache_clear()


def test_the_packaged_copy_alone_is_enough(monkeypatch):
    """An installed build ships no data/ directory."""
    monkeypatch.setattr(bare_acts, "_REPO_ROOT", Path("/nonexistent"))
    bare_acts._load_cached.cache_clear()
    try:
        assert len(get_bare_act("ndps").section_order) == 129
    finally:
        bare_acts._load_cached.cache_clear()


def test_packaged_copy_is_declared_as_package_data():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    assert '"web/ndps_act_final.json"' in pyproject


# ── Footnotes ─────────────────────────────────────────────────────────────


def test_the_act_and_its_patch_share_one_footnote_map():
    act = get_bare_act("ndps")
    # 108 from the Act, 12 from the Schedule patch, none overwriting another.
    assert len(act.footnotes) == 120
    assert act.footnotes["footnote_p5_1"].text.startswith("1. Ins. by Act 2 of 1989")
    assert act.footnotes["footnote_p50_1"].text.startswith("1. Ins. by S.O. 785(E)")


def test_a_colliding_patch_raises_rather_than_overwriting():
    """A silently replaced note prints the wrong amendment against a section."""
    from constitution_memorizer.web import bare_acts

    with pytest.raises(BareActMissing, match="appears twice"):
        bare_acts._collect_footnotes(
            [
                ("act.json", [{"id": "footnote_p5_1", "marker": "1", "text": "A"}]),
                ("patch.json", [{"id": "footnote_p5_1", "marker": "1", "text": "B"}]),
            ]
        )


def test_every_reference_resolves():
    act = get_bare_act("ndps")
    for section in act.section_order:
        for note_id in section.note_ids:
            assert note_id in act.footnotes, f"{section.number}: {note_id}"
    for schedule in act.schedules:
        for note_id in schedule.note_ids:
            assert note_id in act.footnotes, note_id


def test_segments_rejoin_to_the_stored_text():
    """The one guard that catches an offset drifting: nothing may be lost."""
    act = get_bare_act("ndps")
    checked = 0
    for section in act.section_order:
        for row in section.rows:
            if row.is_omission or row.is_table:
                continue
            assert "".join(s.text for s in row.segments) == row.text
            checked += 1
    assert checked > 400


def test_a_run_of_text_splits_into_plain_and_anchored():
    act = get_bare_act("ndps")
    rows = {r.label: r for r in act.section("1").rows}
    # "It shall come into force on such date as the Central Government may..."
    segments = rows["(3)"].segments
    assert [s.is_anchor for s in segments] == [False, True, False]
    assert segments[1].text == "date"
    assert segments[1].note_id == "footnote_p5_3"
    # A clause with no footnote is one plain span, never zero.
    assert [s.is_anchor for s in rows["(a)"].segments] == [False]


def test_a_node_can_carry_several_footnotes():
    act = get_bare_act("ndps")
    most = max(
        (r for s in act.section_order for r in s.rows),
        key=lambda r: sum(1 for x in r.segments if x.is_anchor),
    )
    anchors = [s for s in most.segments if s.is_anchor]
    assert len(anchors) == 4
    starts = [most.text.index(a.text) for a in anchors]
    assert starts == sorted(starts)


def test_malformed_spans_are_dropped_not_fatal():
    text = "alpha beta gamma"
    # end <= start, and an end past the string.
    spans = split_on_footnotes(
        text,
        [
            {"type": "footnote", "start": 5, "end": 5, "note_id": "x"},
            {"type": "footnote", "start": 6, "end": 999, "note_id": "y"},
        ],
    )
    assert "".join(s.text for s in spans) == text
    assert [s.note_id for s in spans if s.is_anchor] == ["y"]
    assert spans[-1].text == "beta gamma"


def test_labels_are_anchored_whole():
    act = get_bare_act("ndps")
    labelled = [r for r in act.section("2").rows if r.label_note_id]
    assert len(labelled) == 8
    assert labelled[0].label == "(i)"
    # Section 1 carries footnotes on its text, none on its labels.
    assert all(r.label_note_id is None for r in act.section("1").rows)


def test_omitted_provisions_carry_no_anchor():
    """We print "Omitted." where the source prints "* * * * *", so the stored
    offsets describe text that never reaches the page."""
    act = get_bare_act("ndps")
    omission = [r for r in act.section("63").rows if r.is_omission][0]
    assert omission.annotations  # the data does have one
    assert [s.is_anchor for s in omission.segments] == [False]
    assert omission.note_ids == ()


# ── The Schedule ──────────────────────────────────────────────────────────


def test_the_schedule_is_the_whole_list():
    act = get_bare_act("ndps")
    assert len(act.schedules) == 1
    schedule = act.schedules[0]
    assert schedule.slug == "psychotropic-substances"
    assert schedule.title == "THE SCHEDULE"
    assert schedule.reference == "[See clause (xxiii) of Section 2]"
    assert schedule.display_heading == "List of Psychotropic Substances"
    assert len(schedule.entries) == 162
    assert schedule.range_label == "1–110ZT"
    assert schedule.columns[0] == "Sl. No."
    assert len(schedule.columns) == 4


def test_schedule_serials_stay_strings():
    act = get_bare_act("ndps")
    serials = [e.serial_number for e in act.schedules[0].entries]
    assert serials[0] == "1"
    assert serials[-1] == "110ZT"
    for probe in ("105A", "110A", "110ZF"):
        assert probe in serials
    assert all(isinstance(s, str) for s in serials)


def test_amended_serials_are_the_schedule_anchors():
    act = get_bare_act("ndps")
    annotated = [
        e.serial_number for e in act.schedules[0].entries if e.serial_note_id
    ]
    assert annotated == [
        "77", "105A", "106", "110", "110A", "110B",
        "110C", "110K", "110P", "110Y", "110Z", "110ZF",
    ]


# ── The screens ───────────────────────────────────────────────────────────


def test_laws_lists_bare_acts_above_mapped_articles(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws").text
    assert ">Laws</h1>" in html
    assert "Bare Acts" in html
    assert "Mapped to Articles" in html
    assert 'href="/laws/ndps"' in html
    assert "8 Chapters · Sections 1–83" in html
    # The seeded mapped-law list is not displaced by the new group.
    assert 'href="/laws/rti-2005"' in html
    assert "Right to Information Act" in html
    # Reading an Act records nothing, so a progress label would never change.
    assert "Not started" not in html


def test_chapter_list_opens_on_chapter_one(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps").text
    assert 'data-mscreen="bareact"' in html
    assert html.count("<details") == 8
    # Exactly one chapter starts open, and it is the first.
    assert html.count('<details class="bareact-chapter" open>') == 1
    assert html.index('<details class="bareact-chapter" open>') < html.index(
        "Authorities and Officers"
    )
    assert "Chapter IIA" in html
    assert "7A–7B" in html
    assert 'href="/laws/ndps/section/68-I"' in html
    # Section 65 announces itself as omitted in the list, not as "[Omitted]".
    assert "[Omitted]" not in html


def test_one_chapter_open_at_a_time_is_enforced_in_js(tmp_path: Path):
    """<details> opens on its own; JS only adds the accordion rule."""
    client, _ = _client(tmp_path)
    js = client.get("/static/mobile.js").text
    body = js.split("function initActAccordion()", 1)[1].split("\n  }\n", 1)[0]
    assert "other.open = false" in body


def test_the_phone_rules_are_scoped_to_the_phone(tmp_path: Path):
    """mobile.css ends with a (min-width: 561px) block.

    Rules appended to the end of that file land in it and are scoped to
    desktop, where none of these screens use them — the page then falls back
    to the desktop styles and looks nothing like the design, with no error
    anywhere. Assert the block sits inside the phone query instead.
    """
    client, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    blocks = []
    for chunk in css.split("\n@media ")[1:]:
        condition, body = chunk.split(" {", 1)
        blocks.append((condition, body))
    phone = [b for c, b in blocks if c.strip() == "(max-width: 560px)"]
    assert phone, "no phone media block"
    scoped = "\n".join(phone)
    for selector in (
        'body[data-mscreen="bareact"] .bareact-chapter-row',
        'body[data-mscreen="bareact"] .bareact-section-row',
        'body[data-mscreen="bareactsection"] .bareact-row-text',
        'body[data-mscreen="laws"] .laws-bare-card',
    ):
        assert selector in scoped, selector
    # The chapter rows sit a shade off paper; the sections are on it.
    chapter = scoped.split(
        'body[data-mscreen="bareact"] .bareact-chapter-row {', 1
    )[1].split("}", 1)[0]
    assert "background: var(--rc-wash)" in chapter
    assert "padding: 10px var(--m-gutter)" in chapter
    section = scoped.split(
        'body[data-mscreen="bareact"] .bareact-section-row {', 1
    )[1].split("}", 1)[0]
    assert "background: var(--rc-paper)" in section


def test_section_reader_renders_the_provision_tree(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/1").text
    assert 'data-mscreen="bareactsection"' in html
    assert "Chapter I · Preliminary" in html
    assert ">Section 1</h1>" in html
    assert "Short title, extent and commencement" in html
    # Depth drives the indent, and the top level is marked differently.
    assert 'class="bareact-row is-root" style="--depth: 0"' in html
    assert 'style="--depth: 1"' in html
    assert "to all citizens of India outside India" in html
    # Internal plumbing never reaches the page.
    assert "source_pages" not in html
    assert "footnote_ids" not in html


def test_an_explanation_is_named_and_a_proviso_is_not(tmp_path: Path):
    """A proviso says "Provided that"; the parse drops "Explanation.—"."""
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/2").text
    assert '<span class="bareact-row-kind">Explanation</span>' in html
    assert "is-aside is-proviso" in html
    assert '<span class="bareact-row-kind">Proviso</span>' not in html


def test_section_31a_renders_a_scrollable_table(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/31A").text
    assert 'class="bareact-table-wrap"' in html
    assert html.count("<tr>") == 15  # one header row + 14 entries
    assert "Opium" in html and "Heroin" in html
    assert ">(xiv)</td>" in html
    css = client.get("/static/styles.css").text
    wrap = css.split(".bareact-table-wrap {", 1)[1].split("}", 1)[0]
    assert "overflow-x: auto" in wrap


def test_omitted_content_looks_deliberate(tmp_path: Path):
    client, _ = _client(tmp_path)
    whole = client.get("/laws/ndps/section/65").text
    assert 'class="bareact-omission"' in whole
    assert "Power to make rules" in whole
    assert "1989" in whole
    # An omission inside a live provision keeps its label.
    inner = client.get("/laws/ndps/section/63").text
    assert "bareact-row is-omission" in inner
    assert "* * * * *" not in inner


def test_prev_next_walk_the_whole_act(tmp_path: Path):
    client, _ = _client(tmp_path)
    across = client.get("/laws/ndps/section/68Z").text
    assert 'href="/laws/ndps/section/68Y"' in across
    assert 'href="/laws/ndps/section/69"' in across  # next chapter
    first = client.get("/laws/ndps/section/1").text
    assert "Previous" not in first
    assert 'href="/laws/ndps/section/2"' in first
    last = client.get("/laws/ndps/section/83").text
    assert "Next" not in last
    assert 'href="/laws/ndps/section/82"' in last


def test_unknown_slugs_and_sections_are_404(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert client.get("/laws/ndps/section/999").status_code == 404
    assert client.get("/laws/no-such-act").status_code == 404
    assert client.get("/laws/no-such-act/section/1").status_code == 404
    # The seeded acts still resolve on the same prefix.
    assert client.get("/laws/rti-2005").status_code == 200


def test_a_footnoted_section_carries_anchors_and_its_notes(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/1").text
    assert 'data-bareact-fn="footnote_p5_3"' in html
    assert 'aria-describedby="fn-footnote_p5_3"' in html
    # The note is in the page, in the accessibility tree, not just in JS.
    assert '<p id="fn-footnote_p5_3">' in html
    assert 'class="bareact-fn-notes visually-hidden"' in html
    assert "data-bareact-fn-card" in html
    # Every anchor points at a note that is actually on the page.
    for note_id in re.findall(r'data-bareact-fn="([^"]+)"', html):
        assert f'<p id="fn-{note_id}">' in html


def test_a_section_without_footnotes_has_no_apparatus(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/3").text
    assert "data-bareact-fn" not in html
    assert "bareact-fn-card" not in html


def test_a_clause_label_can_be_the_anchor(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/2").text
    label = html.split('<span class="bareact-row-label">', 1)[1].split("</span>", 1)[0]
    assert "bareact-fn" in label


def test_the_chapter_list_ends_with_the_schedule(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps").text
    assert 'href="/laws/ndps/schedule/psychotropic-substances"' in html
    assert "List of Psychotropic Substances" in html
    assert "[See clause (xxiii) of Section 2]" in html
    assert "1–110ZT" in html
    # A schedule is a link, not a ninth chapter.
    assert html.count("<details") == 8
    assert html.index("Miscellaneous") < html.index("bareact-schedule-row")


def test_the_schedule_screen_renders_every_entry(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/schedule/psychotropic-substances").text
    assert 'data-mscreen="bareactschedule"' in html
    assert html.count("<th ") == 4
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert body.count("<tr>") == 162
    assert ">110ZT</td>" in html or "110ZT" in body
    assert "N, N-Diethyltryptamine" in body
    # Amended serials anchor; untouched ones stay plain text.
    assert 'data-bareact-fn="footnote_p50_1"' in body
    first_row = body.split("<tr>", 2)[1]
    assert "bareact-fn" not in first_row


def test_the_schedule_table_holds_its_columns_without_panning(tmp_path: Path):
    """Four columns sized to fit a phone — the design shrinks type for this."""
    client, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    table = css.split(".bareact-schedule-table {", 1)[1].split("}", 1)[0]
    assert "table-layout: fixed" in table
    serial = css.split(".bareact-schedule-table col.is-serial {", 1)[1].split("}", 1)[0]
    assert "width: 34px" in serial
    wrap = css.split(".bareact-schedule-wrap {", 1)[1].split("}", 1)[0]
    assert "overflow-x" not in wrap


def test_footnote_colours_go_through_tokens(tmp_path: Path):
    """Hardcoding the handoff's hexes would leave a white smear in dark mode."""
    client, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    active = css.split(".bareact-fn.is-active {", 1)[1].split("}", 1)[0]
    assert "var(--" in active
    assert "#e9f3f1" not in active
    card = css.split(".bareact-fn-card {", 1)[1].split("}", 1)[0]
    assert "var(--rc-fn-card" in card
    assert "position: sticky" in card
    # And the dark theme actually redefines them.
    assert "--rc-fn-card: #17322c" in css


def test_the_footnote_card_clears_the_tab_bar(tmp_path: Path):
    client, _ = _client(tmp_path)
    css = client.get("/static/mobile.css").text
    phone = [
        body
        for chunk in css.split("\n@media ")[1:]
        for condition, body in [chunk.split(" {", 1)]
        if condition.strip() == "(max-width: 560px)"
    ]
    scoped = "\n".join(phone)
    card = scoped.split(".bareact-fn-card {", 1)[1].split("}", 1)[0]
    assert "calc(var(--m-tabbar) + 8px)" in card


def test_an_unknown_schedule_is_404(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert client.get("/laws/ndps/schedule/nope").status_code == 404
    assert client.get("/laws/rti-2005/schedule/anything").status_code == 404


# ── Access ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("signed_in", [False, True])
def test_the_act_is_free_to_read(tmp_path: Path, signed_in: bool):
    client = _mu_client(tmp_path, signed_in=signed_in)
    for path in (
        "/laws",
        "/laws/ndps",
        "/laws/ndps/section/83",
        "/laws/ndps/schedule/psychotropic-substances",
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, path


def test_free_tier_caps_do_not_reach_the_act(tmp_path: Path):
    client = _mu_client(
        tmp_path, signed_in=True, ARTICLE_ENTITLEMENTS_ENABLED="true"
    )
    html = client.get("/laws/ndps/section/31A").text
    assert "Sign in" not in html.split("<main", 1)[-1]
    assert "Unlock" not in html
    assert client.get("/laws/ndps/section/1").status_code == 200


def test_laws_is_on_without_being_asked_for():
    """The middleware 404s /laws before auth runs when this is off."""
    assert MultiUserSettings(_env_file=None, APP_ENV="test").relevant_laws_enabled


def test_reading_the_act_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in (
        "/laws",
        "/laws/ndps",
        "/laws/ndps/section/1",
        "/laws/ndps/section/31A",
        "/laws/ndps/section/65",
        "/laws/ndps/schedule/psychotropic-substances",
    ):
        assert client.get(path).status_code == 200
    assert engine.stats() == before
    assert engine.due_today() == []
