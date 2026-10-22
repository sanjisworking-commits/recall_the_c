# M2 — Bare Act head family: contract for updating the screen tests

Worktree: `/Users/sanjwork/Desktop/memorize_the_c/.claude/worktrees/pg-m2` (branch `pg-m2-act-head`).
Run tests with:

```
cd /Users/sanjwork/Desktop/memorize_the_c/.claude/worktrees/pg-m2 && PYTHONPATH=src /Users/sanjwork/Desktop/memorize_the_c/.venv/bin/python -m pytest -m "not integration" -q -p no:cacheprovider --no-header -o addopts="" tests/<file>.py
```

Never `cd` anywhere else, never touch git (no commit, stash, checkout), never edit files under `src/` — if a test
cannot be satisfied without a source change, leave the test failing and report it. Playwright is not installed, so
browser tests in these files skip; leave them skipping, do not delete them, but update their selectors/expectations to
the new markup where they reference old markup.

## What M2 changed (source of truth: read the templates/CSS yourself)

- `src/constitution_memorizer/web/templates/bare_act.html` — ONE generated head for every Bare Act and every viewer.
  The fixture module `web/guest_bareact_head.py` (NDPS_GUEST_TITLE / KICKER / META / ROWS, ndps_guest_head,
  guest_add_reading_name, GUEST_ADD_TITLE) is DELETED. The `guest_screen4` template context no longer exists.
  Per-surface variants `[data-guest-bareact-desktop|phone]`, `[data-signed-in-bareact-desktop|phone]`,
  `[data-plus-bareact-phone]`, `data-plus-bareact="desktop"`, `data-expired-bareact="desktop"`,
  `data-halted-bareact="desktop"`, `[data-bareact-phone]`, and every `guest-bareact-*` / `signed-bareact-*` class are
  gone. The legacy Chapters/Schedules tab row (`data-bareact-tabs`, `data-bareact-tab`, `data-bareact-panel`) and the
  "This Act has no Schedules." line are gone. Chapter I no longer starts open.
- New head markup (same on both widths; CSS does the layout):
  - `<section class="panel ActHead bareact-page is-{profile}" data-act-head="{slug}" data-pg-kind="{kind}" data-membership="{badge}" [data-plus-bareact] [data-expired-bareact] [data-halted-bareact]>`
    (`data-plus-bareact` = active Plus subscriber, `data-expired-bareact`, `data-halted-bareact` are bare attributes,
    no value; present for every Act, not only NDPS).
  - `.ActHead-band` > `a.ActHead-back[href="/laws"]` "← Laws"; `.ActHead-row` > `.ActHead-copy` >
    `p.ActHead-kicker` "Bare Act · India Code" (uppercased by CSS; a `.bareact-status` pill follows when the catalogue
    has a status label), `h1.ActHead-title` = `act.title`, `p.ActHead-meta` = `act.head_meta_label`
    (new property: `meta_label` + " · Schedule" / " · Schedules" when the Act prints schedules, e.g. NDPS
    "8 Chapters · Sections 1–83 · Schedule", UAPA "7 Chapters · Sections 1–53 · Schedules", MTP "Sections 1–8").
  - `.ActHead-cta[data-law-id][data-pg-kind][data-membership]` renders only when `playground_state` is eligible:
    - kind `already_active`: `.ActHead-inpg` > `.ActHead-inpg-mark` + `status_badge` (`.LawStatusBadge` "Already in
      Playground") + `a.ActHead-inpg-sections[href=state.secondary_href]` "Sections" + `a.ActHead-inpg-continue[href=state.primary_href]`
      with the state's own primary label ("Continue" / "Start learning" for a subscriber; "Resume Playground" when
      expired; the halted recovery label, e.g. "Manage subscription", when halted). The old hard-coded
      `href="/playground"` Continue is gone: destinations are the live `LawPlaygroundState` values (M2-F04).
    - every other kind: `a.ActHead-btn[href=state.primary_href][data-pg-kind=kind]` with the state's primary label
      ("Sign in to use Playground" guest, "Subscribe to use Playground" Free, "+ Add to Playground" Plus/Pro/Max,
      "Resume Playground" expired resume, "Playground full this month", "Manage devices", …); `data-pg-sheet` is
      present iff `state.opens_sheet`; ghost modifier `.ActHead-btn--ghost` for roster_full / pending / device_blocked;
      optional `a.ActHead-link` for `secondary_href/label`; optional `p.ActHead-note` = `secondary_copy` (not for
      guest/subscribe).
  - About-this-act stays: `button.bareact-info-toggle.ActHead-about[data-bareact-info-toggle][aria-expanded=false]`
    + `#bareact-info[data-bareact-info hidden]`, now BELOW the title/CTA row inside the band.
  - The list: `<div class="bareact-chapters" data-bareact-accordion data-act-list>` containing, in order:
    MTP only: `<div class="bareact-section-list">` of `a.bareact-section-row` links (flat, no details);
    chaptered Acts: `<details class="bareact-chapter">` (none open) > `<summary class="bareact-chapter-row" aria-expanded="false">`
    > `span.bareact-chapter-tag` "Chapter I", `span.bareact-chapter-name`, `span.bareact-chapter-range` containing
    `<span class="ActHead-range-word">Sections </span>1–3`, `span.bareact-chapter-caret`; then
    `div.bareact-section-list` with the unchanged `a.bareact-section-row[href=/laws/{slug}/section/{n}]` rows;
    then schedule rows `<div class="bareact-schedule-row">` / `<div class="bareact-schedule-row is-unavailable">`
    exactly as before (overlay `a.bareact-schedule-row-link`, `.bareact-chapter-tag`, `.bareact-schedule-copy`,
    `.bareact-chapter-range` now "Entries 1–110ZT" via `<span class="ActHead-range-word">Entries </span>`).
  - NDPS now lists EIGHT chapters (I, II, IIA, III, IV, V, VA, VI) + 1 schedule; UAPA 7 + 4; BNS 20 + 0; BNSS 39 + 2;
    PSS 8 + 0; MTP 0 chapters, 9 flat sections. Counts come from the live model (`get_bare_act(slug)`).
- `src/constitution_memorizer/web/templates/playground_add.html` — ONE sheet per state (no desktop/phone twins).
  It now `{% extends "bare_act.html" %}` and fills `{% block act_dialog %}` with
  `<dialog class="pg-sheet" data-pg-sheet-host data-pg-sheet-direct data-pg-sheet-return="{cancel_href}" … open>`
  wrapping `<section class="pg-sheet-panel" data-pg-add data-pg-kind="{kind}" data-step data-skip-confirm data-roster-confirm [data-expired-add] [data-halted-add] role="dialog" aria-modal="true" aria-labelledby="pg-add-title">`.
  So a GET of `/playground/laws/{id}/add` returns the FULL Act page (head + list) with the sheet inside the open
  dialog; `playground_base.html` / `.PlaygroundShell[data-hard-gate]` are no longer used by this page; the page's
  `data-mscreen` is `bareact`. In-page opening is unchanged: playground.js fetches the URL and lifts `.pg-sheet-panel`
  into its own dialog. Old markers `data-guest-add-desktop|phone`, `data-signed-in-add-desktop|phone`,
  `data-plus-add="desktop"`, `data-plus-add-desktop|phone`, `data-expired-add="desktop"`, `data-halted-add="desktop"`
  and classes `guest-add-*`, `signed-add-*`, `plus-add-*`, `expired-add-*`, `halted-add-*` are gone.
  Copy and classes per kind (read the template for exact text):
    - guest: `h1#pg-add-title.pg-add-title` "Add to Playground"; `p.pg-add-lede` "Playground needs an account. Reading
      {reading_name} stays free — sign in and you’ll come right back here."; `a.pg-add-primary[href=login_href][data-guest-add-gate]`
      "Sign in"; `a.pg-add-secondary[href=login_href][data-guest-add-gate]` "Create an account" (both real links now;
      the phone twin's inert buttons are gone).
    - subscribe (Free): title "Add to Playground"; lede "Turning {reading_name} into a learning experience needs a
      plan. Reading it stays free."; `a.pg-add-primary[href="/playground"]` "Unlock Playground"; `p.pg-add-note`
      "Plus · Pro · Max — from ₹199 / month. Constitution learning stays free." (tiers from `catalogue_plans`, price
      from `from_price`). No Cancel button (the dialog close ✕ / Escape / scrim close it).
    - resume (expired/halted): title + lede lines from the gate; `a.pg-add-primary` with the gate CTA
      (`resume_cta_href/label` when halted, `state.primary_href/label` when expired, else `/billing/subscriptions`
      "Resume Playground"); `a.pg-add-secondary[href=cancel_href][data-pg-sheet-close]` "Cancel".
    - device_blocked / pending / roster_full: same shape as before with `.pg-add-*` classes (roster_full keeps
      `.pg-plan-list` and the two `.pg-btn--ghost` links).
    - eligible_to_add / re_add (Plus, Pro, Max): `[data-add-step="confirm"]` has `p.pg-eyebrow` (month),
      title "Add to Playground", `p.pg-add-lede` "{reading_name} joins {month}’s Playground — learnable, verbatim. The
      reader itself never changes.", the existing confirm `lines` as `p.pg-add-note.pg-add-note--left`, the unchanged
      `<form method="post" action="/playground/laws/{id}/add" data-pg-add-confirm>` with hidden `csrf_token` and
      `confirm`, `button.pg-add-primary` = `action_label` ("Add to Playground" / "Add back"), then
      `a.pg-add-secondary[data-pg-sheet-close]` Cancel. `[data-add-step="scope"]` is unchanged except class names
      (`.pg-add-title`, `.pg-add-lede`, `.pg-add-note--left`, Cancel as `a.pg-add-secondary`) and uses `reading_name`.
      The NDPS-only `plus_add` copy variant (`plus_add_title/lede/space/footer`) is no longer rendered.
    - `reading_name` is now the registry spec's `short_name` for every Act ("The NDPS Act, 1985", "The UAPA, 1967",
      "The BNS, 2023", "The MTP Act, 1971" …) — `playground_bare_act_spec(law_id).short_name`.
- CSS: the per-surface blocks were deleted from `styles.css`, `mobile.css`, `playground.css`; new head rules live in
  `styles.css` under the comment "Bare Act head (M2)" (`.ActHead*`, `.ActHead .bareact-*` overrides, phone block at
  `@media (max-width: 560px)`); new sheet rules in `playground.css` under "Add sheet (M2)" (`.pg-add-*`). The legacy
  `body[data-mscreen="bareact"] .bareact-chapter-row` / `.bareact-section-row` rules in `mobile.css` are kept.
  Cache pins in `base.html`: `styles.css?v=main88`, `mobile.css?v=mob107`, `playground.css?v=pg50`,
  `playground.js?v=pg9`, `mobile.js?v=mob30`.
- JS: `mobile.js` syncs `aria-expanded` on chapter summaries; `playground.js` re-opens a server-rendered
  `[data-pg-sheet-direct]` dialog with `showModal()` and, on close, `history.replaceState` to `data-pg-sheet-return`.
- Python: `web/bare_act_page.py` (new) holds `bare_act_page_context(request, bare)` and `halted_law_presentation`
  (moved from app.py); the Laws route and the Add route both use it. `BareAct.head_meta_label` is new.

## Rules for the rewrite

1. Keep every BEHAVIOUR assertion: status codes, redirect targets, hrefs, form actions and hidden fields, CSRF,
   roster/entitlement outcomes, cohort separation (e.g. "Pro is not Plus", "Free/guest unchanged"), "no invented
   copy" lists, and the pins on OTHER accepted screens. Translate them to the new markup; do not delete them.
   If a behaviour genuinely changed (listed above: live hrefs for Continue, Chapter I closed, tabs gone, one sheet,
   reading names, eight NDPS chapters), update the expectation and record it.
2. Assertions that existed only to pin the deleted fixture or the deleted per-surface twins (three fixed rows,
   "6 Chapters", `guest-bareact-*` classes, "desktop block ≠ phone block") are replaced by equivalent assertions on
   the generated head: meta text == `get_bare_act(slug).head_meta_label`, chapter row count == `act.chapter_count`,
   schedule rows == `len(act.schedules)`, every row is a `<summary>`/link, CTA label/href per kind.
3. Do NOT loosen: no `assert True`, no `pytest.skip` for convenience, no deleting a test because it is hard. A test
   may be removed only when its subject no longer exists (e.g. "desktop twin hidden on phone"); say so in the log.
4. Every test file you change must end green (except Playwright skips). Run the file after editing.
5. Write a changelog at the path given in your task: one line per test — `file::test — change — reason` — plus a
   short list of tests removed with reasons. Do not write anything else outside your assigned files and that log.

Prototype/decision references for reasons: M2 §2.1 (one head, one sheet), §4 Q1 (eight NDPS chapters from canonical
data), Q2 (About below the CTA), Q3 (chapter rows expand into section links; schedules open readers), Q4 (direct Add
URL = Act page with the dialog open; close returns to the Act), §4a (CTA wording), M2-F04 (live state destinations).
