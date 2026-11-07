# M3 — test changes (PR #237, `pg-m3-browse-laws`)

Every existing test touched by M3, with its reason. No behaviour test was weakened: an assertion that pinned a retired element (the phone Part rail, the Marks sheet, the per-card Playground CTA, the Laws search toggle, the guest Laws fixture, the Free banner reaching Pro / Max) was replaced by the assertion of the new behaviour at the same strength; copy pins were re-pointed to the owner's copy of 2026-11-06.

## A. Integration re-pins (commit `149047a`, before any M3 edit)
The merge of `main` @ `ea15591` changed the Browse lede ("…then the twelve Schedules…"), the Tables card line ("Parts, writs, amendments") and added `browse_schedule.html`.

| Test | Was | Now |
|---|---|---|
| `test_expired_browse_screen2.py`, `test_halted_browse_screen2.py`, `test_plus_browse_screen2.py`, `test_signed_in_browse_screen2.py` (lede pins) | "The Constitution, Part by Part. Open an Article, then learn any clause from inside it." | main's lede |
| `test_guest_browse_screen2.py:132`, `test_signed_in_browse_screen2.py:141` | "Schedules, Parts, writs" | "Parts, writs, amendments" |
| `test_playground_r1.py::test_t41_every_active_template_is_classified` | 82 templates | 83; `browse_schedule.html` classified in `PLAYGROUND_DESIGN_INVENTORY.md` §2 / §3 |

## B. Mechanical asset re-pins (commit `08f2055`)
`styles.css?v=main90 → main91`, `mobile.css?v=mob109 → mob110`, `mobile.js?v=mob30 → mob31`, `app.js?v=main62 → main63` in `base.html` and 44 test modules (string replacement only; the list is `git show 08f2055 --stat -- tests`).

## C. Schema / catalogue pins (commit `94a5aa3`)
| Test | Change | Reason |
|---|---|---|
| `test_bare_act_sitemap.py::test_builder_emits_explicit_slug_and_source_version` | schema `2 → 3`; every entry carries `head_meta_label == act.head_meta_label` | manifest extension (Q3 / F06) |
| `test_law_catalog.py::test_index_html_always_contains_every_production_law` | `"Bare Acts" not in html` → `html.count("Bare Acts") == 1` (the shared lede) | one Laws body for every viewer; the legacy section label is still absent |

## D. New module (commit `4a3b0fd`)
`tests/test_browse_laws_family.py` — M3-F01, F02, F03 (+ the Free-predicate / shell-label invariant and the handler/template source pins), gate 1 (both tier models), F04, F05, F06, F07 across guest, Free, Plus, Pro, Max, paused, pending, expired and halted.

## E. Existing screen tests re-pinned to the new Browse / Laws markup (18 files)

Pass run on the candidate: changed files 211 passed, 23 skipped (Playwright, not installed locally); guard set 203 passed unchanged. Every changed block carries `# M3 (<tag>): …`.

| File | Tests | Was | Now | Tag |
|---|---|---|---|---|
| `test_guest_browse_screen2.py` | strip copy, strip sign-in, only desktop sign-in entry, part heading rows, phone body (renamed `test_screen2_phone_browse_is_the_one_body`), 1280 screenshot (Playwright) | "save 3 Articles", `/login` + `data-guest-gate`, heading `div`, Part rail / `.part-card-track` | exact new copy; one `/auth/google/start?next=%2Fbrowse` (GET → 303 + `rtc_auth_next=/browse`); `<h2>` + `button.browse-part-toggle[aria-expanded][aria-controls]` with matching body id; no rail / sheet / chips; toggle + two-column grid rules in mobile.css; none of `.display/.lede/.browse-legend/.browse-part` hidden | 5-11 / Q1 / Q5 |
| `test_signed_in_browse_screen2.py` | Free strip copy + gate, part rows (renamed `…_are_collapse_toggles_not_links`), desktop chrome, phone/landing, 1280 shot (Playwright) | "pick any 3 Articles … Unlock all"; summary hidden < 561; rail css | exact Free copy + `View Playground`; `app.js` handler pinned (`aria-expanded`, `getElementById(aria-controls)`, `body.hidden`, no `localStorage`); summary laid out `display:flex` on phone | Q4 / Q1 |
| `test_plus_browse_screen2.py` | Free (renamed `…_keeps_free_summary_and_view_playground`), **Pro / Max not Plus**, template marker, 1280 shot | old copy; **Pro received the strip** | new copy; Pro **and Max**: no `data-signed-in-browse-strip`, no "Free plan", own label; template `{% elif free_browse %}`, no `not plus_browse`, no "Unlock all" | Q4 / **F03** |
| `test_expired_browse_screen2.py` | Free copy, shared predicate, phone (renamed `…_is_the_one_body`), 1280 / Free regression (Playwright) | old copy; `not expired_browse` in template | new copy; `free_browse` flag; `request_is_free_account` in `app.py`; predicate excludes expired | Q4 / Q1 |
| `test_halted_browse_screen2.py` | cohort separation, shared predicate, 1280 (Playwright) | Free copy; paused / pending / Pro / Max only "not halted" | paused → Free summary + `RecallC Free`; pending → no strip + `RecallC Plus` (a pending row resolves `is_subscribed`, as the shell label does); Pro / Max → no strip, own label; predicate excludes halted | Q4 / F03 |
| `test_mobile_screens.py` | Part links, phone cards (renamed `test_browse_index_phone_is_the_one_body`) | rail + `.part-card*` | toggles == bodies == Parts, each with its id and `data-browse-part`; every `/browse/part/{slug}` 200 and linked from its first article page; mobile.css toggle 44 px, grid `repeat(2, minmax(0, 1fr))`, no `.part-card` | Q1 / Q5 |
| `test_guest_first_ux.py::test_browse_free_plan_banner` | old Free copy | new copy + View Playground; no "slots" / "Preview only" / `browse-access-label` | Q4 |
| `test_guest_laws_screen3.py` (module rewritten; fixture import removed; three tests renamed) | `GUEST_LAWS_CARDS/CHIPS`, `data-guest-laws-desktop`, `data-laws-phone`, `#laws-q-guest`, "Commercial", "6 Chapters" | one `data-laws-index data-laws-body`; chips == All + `visible_subjects` + Repealed; cards == `load_catalog().laws` (ids, hrefs, titles, `card_meta_label`); every full Act href → 200 with `data-act-head`; visible labelled `#laws-q`; no toggle / `laws-index-head` / `mobile-back`; CSS without `is-guest` / `is-authed` Laws rules; guest cards: empty badge wrappers, no `LawStatusBadge`, no button; single-user app unchanged | Q3 / Q5 / F04 |
| `test_signed_in_laws_screen3.py` | back link, desktop chrome, phone / landing / browse, cards (strengthened), 1280 (Playwright) | `mobile-back`, `body.is-authed[data-mscreen="laws"]`, `.laws-index-head` | one `laws-back-link` (44 px on phone); same desktop values under `body[data-mscreen="laws"]`; hero / search phone rules; badge-only wrappers, zero `pg-btn` / `pg-lede` / `data-pg-sheet` | Q5 / Q3 / F04 |
| `test_plus_laws_screen3.py` | guest unchanged, Plus index (strengthened), 1280 (Playwright) | `data-guest-laws-desktop` | one `data-laws-index`; no per-card CTA on Plus or guest | Q3 / F04 |
| `test_expired_laws_screen3.py` | live Playground state, cohort separation, shared predicate, phone (renamed `…_is_the_one_body`), 1280 (Playwright) | `_cta_kind` on `class="LawPlaygroundCta"`; Plus card "+ Add to Playground" | regex on the badge wrapper; three `already_active` badges, `pss` `resume` wrapper without badge or button; **the Add CTA lives on `/laws/bns`'s head**, not the card; `playground_status_badge(pg_state)` in the template | F04 / Q3 |
| `test_halted_laws_screen3.py` | live tags, cohort separation, shared predicate, 1280 (Playwright) | `_cta_kind`; `playground_cta(` | badge regex; halted "IN PLAYGROUND" labels; no CTA copy; Pro / Max own label | F04 / F03 |
| `test_guest_bareact_screen4.py` (2), `test_phone_guest_bare_act_screen1.py` (1), `test_guest_add_screen5.py` (1), `test_guest_playground_screen6.py` (1), `test_guest_profile_screen10.py` (1), `test_signed_in_bareact_screen4.py` (3) | "other screens untouched" guards on `data-guest-laws-desktop` / `is-authed` Laws css / "Unlock all" | `laws.count("data-laws-index") == 1`, no `data-laws-search-toggle`; `body[data-mscreen="laws"]` title 30 px; "View Playground" | Q3 / Q5 / Q4 |

Notes from the pass: (1) the Playwright-driven tests were updated on paper and are **NOT RUN locally**; the guest Laws screenshot fixture `tests/fixtures/guest_laws/03-screen.jpg` still shows the retired fixture catalogue and will need re-capture when those tests next run; (2) the agent's finding that a guest card rendered a whitespace-only badge wrapper (8 px per phone card) is fixed in the source commit that follows (`|trim` so the `:empty` rule applies).
