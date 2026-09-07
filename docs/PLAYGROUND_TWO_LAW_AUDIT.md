# Playground two-law audit (NDPS + BNS)

**Date:** 2026-09-06  
**Corpus:** the two Bare Acts already on `main`. No other statutes.  
**Central question:** What is the minimum new user-state architecture required to let a canonical provision in the existing NDPS/BNS verbatim JSON enter Playground, acquire a RecallC learning state, progress through learning and later revision, while leaving both the law source and Constitution system unchanged?

---

## Review gate (answers)

### 1. Canonical source locator

**`{law_id}:section:{number}`**

Examples: `ndps:section:8`, `bns:section:103`, `ndps:section:7A`.

- Reconstructable: walk `chapters[].sections[]` and match the JSON `number` field (string, never int).
- Matches the public reader: `GET /laws/{law_id}/section/{number}`.
- JSON `id` (`section_8`, `section_7a`) exists on both files but is **not** the runtime key: `BareAct.section()` and `ActSection` use `number` only.
- Nested body nodes (`subsection`, `clause`, `proviso`, …) have **no** `id`. MVP grain is the **section**. Optional later path: `{law_id}:section:{number}:subsection:1:clause:a`.
- Not a database UUID.

### 2. Source-version / hash strategy

Do **not** copy statutory text into user rows.

Per selected/learned section store:

| Field | Meaning |
|--------|---------|
| `source_locator` | `{law_id}:section:{number}` |
| `source_version` | `{schema_version}\|{act_number}\|{last_update or enactment_date}` from `document` |
| `source_hash` | SHA-256 of **canonical section text** (see §9) |

Law-level item row also stores `source_version` + `law_source_hash` (SHA-256 of the **main** JSON file bytes). NDPS schedule patch does not change section bodies.

On load: recompute `source_hash` from live JSON. Mismatch → provision changed; do not silently rewrite; do not wipe other sections.

### 3. Minimum user-owned DB state + RLS

All Playground tables are **user-owned**. No global generated module table.

Guests **cannot** persist Playground (redirect to `/login?next=…`), matching Constitution.

`user_id`: UUID (Postgres) / TEXT (SQLite), same as `learning_unit_progress`. Alembic `ENABLE ROW LEVEL SECURITY` with **no policies** (app `postgres` role bypasses RLS; isolation is application `WHERE user_id = ?`). Admin bypass: none for Playground.

### 4. First Cloze against both laws

Playground Cloze (new files, not `learn.html` / `quiz.py`) loads canonical section text from JSON, blanks words (same density idea as Constitution Cloze), reveal restores **that same string**. Persist completion on Playground progress/revision rows. Integrity test: revealed == canonical JSON-derived text.

### 5. Constitution-specific architecture untouched

No edits to Constitution models, Article JSON, `learning_units.json`, `ReminderEngine` completion/ladder, `learning_unit_progress`, `learn.html`, `quiz.py`, or Constitution progress templates. Shared `app.py` / `base.html` / CSS may gain **additive** `/playground` routes and a footer/head link.

---

## 1. Name of each existing law

| Slug | Title | Act number |
|------|--------|------------|
| `ndps` | The Narcotic Drugs and Psychotropic Substances Act, 1985 | 61 OF 1985 |
| `bns` | The Bharatiya Nyaya Sanhita, 2023 | 45 OF 2023 |

---

## 2. Exact files

| Law | Canonical JSON | Patch | Registry |
|-----|----------------|-------|----------|
| NDPS | `src/constitution_memorizer/web/ndps_act_final.json` | `src/constitution_memorizer/web/ndps_schedule_patch.json` | `BARE_ACTS["ndps"]` in `bare_acts.py` |
| BNS | `src/constitution_memorizer/web/bns_runtime_v1.json` | none | `BARE_ACTS["bns"]` |

Loader: `get_bare_act(slug)` → `_load_cached` → `_parse`. Non-destructive: `BareAct.raw` keeps the parsed dict; view models do not rewrite files.

Catalogue (index only): `data/reference/law_catalog.seed.json` lists NDPS and BNS as full Bare Acts (`primary_content: "full_act"`).

**Out of scope:** `data/reference/laws.seed.json` mapped extracts.

---

## 3. JSON structure of each

**Shared:**

```text
document { title, act_number, enactment_date, source, … }
long_title, enacting_formula
chapters[] {
  id, number, title
  sections[] {
    id, number, title, status?
    body[] { type, label, text, children[], source_pages, … }
  }
}
footnotes[]
```

**NDPS extras:** `schema_version` 2.5; `document.last_update`; `title_annotations`; body `annotations` / tables; schedule via **patch** (`schedules[]`).

**BNS extras:** `schema_version` 1.0; `document.source_type: as_enacted_gazette`; chapter `divisions[]`; section `division_id` / `division_title`; body types include `exception`, `illustration(s)`.

Nested `body` nodes generally have **no** `id`.

---

## 4. Rendering path

`get_bare_act` → `BareAct` / `ActChapter` / `ActSection` → `flatten_body(section.body)` → Jinja.

- Chapter list: `templates/bare_act.html` (`data-mscreen="bareact"`)
- Section: `templates/bare_act_section.html` (`bareactsection`)
- Schedule: `templates/bare_act_schedule.html`
- CSS: `styles.css` + `mobile.css` scoped to those `data-mscreen` values
- Accordion: `mobile.js` `initActAccordion`

`title_case_chapter` is **display-only** (ALL-CAPS headings). Statutory `text` on body nodes is unchanged.

---

## 5. Existing routes

| Method | Path | Auth | Progress |
|--------|------|------|----------|
| GET | `/laws` | optional | none (catalogue metadata) |
| GET | `/laws/{law_id}` | optional | none |
| GET | `/laws/{law_id}/section/{number}` | optional | none (commented as reference-only) |
| GET | `/laws/{law_id}/schedule/{slug}` | optional | none |

Feature flag `relevant_laws_enabled` 404s `/laws*` when off.

---

## 6. Existing backend services

- `web/bare_acts.py` — registry, parse, flatten, neighbours
- `web/law_catalog.py` — index metadata (must not parse Act JSON)
- `web/laws_data.py` — mapped extracts (not Playground source)
- `web/app.py` — HTML routes above
- Constitution Learn (`ReminderEngine`, `quiz.py`, `/learn/{unit_id}`) — **not** used for laws today

---

## 7. Stable identifiers and canonical locator

| Level | Identifier | Stable? |
|-------|------------|---------|
| Act | `BARE_ACTS` slug `ndps` / `bns` | yes |
| Chapter | JSON `id` (`chapter_i`) + roman `number` | yes |
| Section | JSON `number` (public); JSON `id` (`section_1`) also present | **locator uses `number`** |
| Nested body | `type` + `label` + tree order | no `id`; not MVP locators |
| Footnotes | `note_id` | yes |

**Canonical Playground locator:** `{law_id}:section:{number}`.

Ordering: `BareAct.section_order` is chapter-then-section file order (the Act’s own order).

---

## 8. Differences between the two structures

| | NDPS | BNS |
|--|------|-----|
| schema_version | 2.5 | 1.0 |
| Provenance | India Code + `last_update` | Gazette `as_enacted_gazette` |
| Divisions | no | yes (between chapter and section) |
| Schedule | patch file | none in reader |
| Catalogue | listed | not listed |
| Render profile | `ndps` | `bns` |
| Empty-text nodes | fewer | illustrations containers, some labelled wrappers |

Playground must not hard-code NDPS-only fields. Locator + `get_bare_act` + `section(number)` work for both.

**Chapter selection:** both have `chapters[]`, but BNS divisions mean a “chapter” checkbox is not the same UI as NDPS. **Batch 1: Entire Act or individual sections only.** Chapter selection later.

---

## 9. Referencing without modifying JSON

Playground **reads** `get_bare_act` / `section.body`. Canonical section text for Cloze and hashing:

```text
DFS flatten of body nodes (same order as flatten_body)
join each node's `text` with a single space
(no labels, no title-casing, no paraphrase)
```

Reveal and `source_hash` use this string. Labels stay in the **reader**, not in the Cloze source, so hiding words does not hide `(1)` as if it were statutory prose. Title is metadata, not hashed into the cloze string (hash includes title separately: `number + "\n" + title + "\n" + body_text` so a title-only amendment still flags).

JSON files are never rewritten.

---

## 10. Minimum new DB state + ownership/RLS

**Global:** none (law JSON on disk).

**User-owned:**

```text
user_playground_item
  PK (user_id, law_id)
  status TEXT  -- in_playground | learning | revising | mastered
  added_at, last_activity_at
  source_version, law_source_hash

user_playground_selection
  PK (user_id, law_id, source_locator)
  selected_at
  source_version, source_hash

user_playground_progress
  PK (user_id, law_id, source_locator)
  status TEXT  -- new | review | mastered
  cloze_done INTEGER
  times_completed, last_completed, next_revision, interval_days
  source_version, source_hash
  updated_at
```

Progress row **is** revision state (no fourth table). Ladder `(1, 3, 7, 15, 30, 60)` in `playground/revision.py` — copy of ideology, not `ReminderEngine`.

**Uniques:** PKs above. One activation per user per law.

**RLS:** `ENABLE ROW LEVEL SECURITY` on all three; no PostgREST policies. App filters `user_id`.

**Guests:** no writes. Sign-in required.

**SQLite:** apply same DDL when opening the local progress DB (additive; do not alter Constitution table definitions).

**Postgres:** new Alembic revision after `20260828_0016`.

---

## 11. Add to Playground flow

1. Signed-in user on `/laws/ndps` or `/laws/bns` sees **Add to Playground**.
2. `POST /playground/{law_id}/add` → upsert `user_playground_item`. Idempotent.
3. Redirect to `/playground/{law_id}/select` (choose sections) or `/playground` if already selected.
4. Guest: `303 /login?next=/laws/{law_id}`.
5. Law JSON unchanged. Reader unchanged except the button.

---

## 12. Selection flow

Activation ≠ selection.

- **Entire Act:** insert a selection row per `section_order` entry (skip omitted if no learnable text).
- **Individual sections:** checkbox list from `section_order`.
- Not Batch 1: chapters, divisions, nested clauses, schedules.

Changing selection updates `user_playground_selection`; does not delete progress for deselected locators (keep history; hide from Continue until re-selected). MVP may treat deselect as delete of selection only.

---

## 13. First learning-mode implementation (Cloze)

**Status:** Batch 1 Cloze is the **architectural proof** (verbatim JSON → hide words → reveal equals source → persist). It is **not** the finished Playground learning engine.

**Not** Read auto-seen. Official “Learned” (later in the finished train): all required RecallC-style modes complete, **then** Day 1 revision. Cloze-only must not remain the mastery trigger.

New `GET /playground/{law_id}/learn/{locator}` (locator URL-safe: `section/8`).

- Load section from JSON; canonical text; if no cloze-able word (≥4 ASCII letters), show that Cloze is unavailable (same rule as `has_cloze_blanks`).
- New template + `playground.js` (fork density/blank/reveal behaviour; do not edit `app.js` Learn Cloze).
- On all blanks tapped: `POST` complete → set `cloze_done`, first completion starts ladder day 1.
- Integrity tests for one NDPS section and one BNS section: `canonical_text(json) == revealed_source`.

Prototype sections (short, cloze-able): NDPS `section:1`; BNS `section:1` (or first section with enough long words).

---

## 14. Playground revision state

**Prototype (this overlay):** on first Cloze completion: `status=review`, `interval_days=1`, `next_revision=today+1`. Subsequent completions advance `1→3→7→15→30→60` then `mastered`. Independent of `learning_unit_progress`. Constitution `/calendar` **unchanged** in this batch; due counts appear on My Playground cards.

**Finished product:** revision Day 1 starts when the section is **Learned** (required modes complete), not when Cloze alone is tapped through.

If `source_hash` ≠ live hash: surface “This provision has changed” on that card; do not auto-advance.

---

## 15. Exact files proposed for Batch 1

**New**

- `docs/PLAYGROUND_TWO_LAW_AUDIT.md` (this file)
- `src/constitution_memorizer/playground/` — `__init__.py`, `locators.py`, `source.py`, `revision.py`, `cloze.py`, `db.py`, `repository.py`
- `alembic/versions/20260906_0017_playground_overlay.py`
- templates: `playground.html`, `playground_select.html`, `playground_cloze.html`
- `static/playground.js`
- `tests/test_playground.py`

**Additive shared (Constitution behaviour unchanged)**

- `web/app.py` — `/playground*` routes
- `web/templates/bare_act.html` — Add to Playground button
- `web/templates/base.html` — optional footer link; script tag
- `web/static/styles.css` / `mobile.css` — Playground classes only
- `progress/db.py` — **only** if needed to run Playground DDL beside existing `SCHEMA_SQL` without changing Constitution tables (prefer calling `playground.db.ensure_schema` from `create_app` instead)

**Forbidden**

- `learn.html`, `quiz.py`, `learning/schemas.py`, `learning_unit_generator.py`, `scheduler.py` ladder/complete, Constitution JSON, `learning_unit_progress` columns

---

## 16. Confirmation Constitution code does not need modification

Playground can resolve NDPS/BNS sections through existing `get_bare_act`. Cloze and revision are new modules. Progress is new tables. Integration is additive HTTP + one button on the Bare Act head. **No Constitution domain change is required.**

---

## Batch 1 file list (implementation)

See §15. Proof: `git diff` on forbidden paths empty; existing Constitution and Bare Act tests green; new tests cover add idempotency, guest redirect, locator round-trip, Cloze integrity on both laws, hash mismatch flag, RLS enabled in Alembic scan.
