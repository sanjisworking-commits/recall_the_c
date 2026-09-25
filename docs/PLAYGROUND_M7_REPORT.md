# Playground Milestone 7 — End-of-batch report

**Branch:** `cursor/playground-220d`
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)
**Closed as:** Milestone 7 = `DONE` — weight **15**
**Stage 1:** **76.0 / 100**
**Stage 2:** `NOT STARTED`

The architectural change in this batch is the separation of **mode completion** from **revision scheduling**. M7 ships six durable learning methods. M8 will define the single transition from those completed methods to **Learned → Day 1**.

Scoreboard: [PLAYGROUND_DELIVERY_TRACKER.md](PLAYGROUND_DELIVERY_TRACKER.md). Product rules: [PLAYGROUND.md](PLAYGROUND.md).

---

## Tracker

```text
Milestone 0 = DONE
Milestone 1 = DONE
Milestone 2 = DONE
Milestone 3 = DONE
Milestone 4 = DONE
Milestone 5 = DONE
Milestone 6 = DONE — 37/37
Milestone 7 = DONE — 15

Stage 1 = 76.0 / 100
Stage 2 = NOT STARTED
```

M8 (Learned → Day 1 → 3 → 7 → 15 → 30 → 60 → Mastered) and M9 amendment handling are **not** scored.

---

## Mode contract

Exact IDs, in product order:

```text
read → cloze → letters → type → recite → test
```

Display names:

```text
Read
Cloze
Letters
Type
Recite
Test
```

The tracker’s M7 mode boxes are:

```text
[x] Read
[x] Cloze productionized
[x] Letters
[x] Type
[x] Recite
[x] Test
```

Authoritative registry (`playground/learning/modes.py`):

```python
PLAYGROUND_LEARN_MODES = (
    "read",
    "cloze",
    "letters",
    "type",
    "recite",
    "test",
)

PLAYGROUND_MODE_LABELS = {
    "read": "Read",
    "cloze": "Cloze",
    "letters": "Letters",
    "type": "Type",
    "recite": "Recite",
    "test": "Test",
}
```

**Type** is the write-it-out method: “Write it out, word for word.”

There is **no** seventh `Write` mode. `type` was not renamed to `write`. `letters` was not removed. Templates consume server-provided `mode_definitions()`; there is no second mode list in JS or routes.

The documentation correction of the ambiguous tracker shorthand (Cloze / Type / Recite / Write / remaining mode 5 / remaining mode 6) earned **0 points** by itself. Credit is for the production six-mode engine.

---

## Schema

| Item | Value |
|------|--------|
| Migration | [`alembic/versions/20260924_0025_playground_mode_progress.py`](../alembic/versions/20260924_0025_playground_mode_progress.py) |
| Parent | `20260917_0024` |
| Head | single `20260924_0025` |
| Table | `user_playground_mode_progress` |
| Identity | `PRIMARY KEY (user_id, law_id, source_locator, mode)` |
| Mode CHECK | `read`, `cloze`, `letters`, `type`, `recite`, `test` |
| Status CHECK | `in_progress`, `completed` |
| Columns | `status`, `attempt_count`, `first_started_at`, `last_attempt_at`, `completed_at`, `source_version`, `source_hash`, `created_at`, `updated_at` |
| RLS | `ENABLE ROW LEVEL SECURITY` (no policies; app-role bypass, same overlay convention) |
| SQLite | `ensure_sqlite_schema` + same CHECK/unique + backfill |
| Backfill | `user_playground_progress.cloze_done != 0` → `mode=cloze`, `status=completed`, `ON CONFLICT DO NOTHING` |
| Untouched | historical `0024`; `user_playground_progress` revision rows |

The mode-progress table stores **state**, not answers. Typed statutory attempts, speech transcripts, audio, cloze revealed words, and quiz answer text are **not** persisted.

`user_playground_progress` remains for M8 revision lifecycle and historical proof data. M7 does not replace it.

---

## Engine

Package: [`src/constitution_memorizer/playground/learning/`](../src/constitution_memorizer/playground/learning/).

Canonical learning unit: `{law_id}:section:{number}` (example `ndps:section:8`).

Canonical source for every mode:

```text
BareAct → Section → canonical_body_text(section)
```

Statute is not copied into templates, JS constants, new JSON learning files, new DB text columns, or mode-specific copies.

URL family (all six values; unknown mode → 404):

```text
GET  /playground/laws/{law_id}/sections/{number}/learn/{mode}
POST /playground/laws/{law_id}/sections/{number}/learn/{mode}/start
POST /playground/laws/{law_id}/sections/{number}/learn/{mode}/complete
POST /playground/laws/{law_id}/sections/{number}/learn/test/quiz
```

No parallel `/playground/type/...` or `/playground/recite/...` routes. Existing `/learn/cloze` remains valid and opens Cloze inside the production engine. Generic `/complete` for `test` is **404**; Test completes only through `/learn/test/quiz`.

Authorization order (unchanged from M3–M5):

```text
authentication → subscription → device → current roster → active law
→ selected section → hydrate requested Act → mode
```

A section not selected for learning redirects to section selection. No progress write.

GET does not complete a mode and does not gratuitously insert rows. Meaningful start may write `status=in_progress`. Completion is an atomic `ON CONFLICT` upsert: one logical row, `status=completed`, `attempt_count` increments on a submitted attempt, `completed_at` stays the first completion.

### Per mode

| Mode | Canonical source | Interaction | Completes when | Persistence | Resume | Web / mobile |
|------|------------------|-------------|----------------|-------------|--------|--------------|
| **Read** | `canonical_body_text` | “First, read it once.” / “Read it closely. Bare Act wording, verbatim.” | Explicit **Mark as read**. GET alone does not complete. | `complete_mode(read)` | Completed Read stays Done after reload | Phone: stepper + Mark as read on-screen (deck hidden &lt;1040px). Desktop: deck + Mark as read (Playground does not use Constitution’s hidden `.learn-read-controls`). |
| **Cloze** | same; blanks derived at request time | Light / Medium / Heavy; tap-to-reveal; no LLM | All blanks tapped, or **Mark Cloze complete** if even Heavy cannot yield a blank | `complete_mode(cloze)` — **not** `complete_cloze` | Independent of other modes | Density + blanks on every viewport. Does not reuse Constitution `.learn-panel-cloze` (`display:none` without `.learn[data-mode]`). |
| **Letters** | same; initials at runtime, never stored | Speak / Read / Full text; typed fallback if speech fails | **Mark Letters complete** | `complete_mode(letters)` | Independent | Speech failure does not block the mode |
| **Type** | same; compared with `recall_align` | “Write it out, word for word.” Typed attempt is **not** stored | Check / full match → **Mark Type complete** | `complete_mode(type)` | In-progress remains identifiable; unsaved typed text is not restored | Same completion on phone and desktop |
| **Recite** | same | Blur + hold-to-peek + speech; typed fallback | Accuracy map then **Mark Recite complete**. No audio or transcript stored | `complete_mode(recite)` | Same | Usable without microphone |
| **Test** | same; same-section distractors only | Seeded keyword fill; MCQ only when safe distractors exist | Valid complete quiz POST | `complete_mode(test)` after server grade | Cycle = `attempt_count`; stale cycle → 409 | Answers never in GET HTML/JSON |

---

## Test mode

- Law-generic generator: `build_section_quiz(law_id, source_locator, canonical_body, cycle, source_hash)`.
- Independent of `LearningUnit` / `build_quiz(unit, units)`.
- Seed: SHA-256 of `law_id:locator:cycle:source_hash` → same attempt, same quiz, no stored answer key.
- Keyword fill is always available for a non-empty body (lower letter-length fallback if the normal threshold is too thin).
- MCQ is added only when the **same section** yields enough safe distractors. No other Act is hydrated. No corpus scan.
- GET `public_dict()` is `{kind, prompt, options}` — no expected answers.
- Grade is server-side. Malformed/incomplete payload → **400**. Stale cycle → **409**.
- Completion is recorded after a structurally complete attempt. No extra perfection requirement.

---

## Progress

- One row per `(user_id, law_id, source_locator, mode)`. Completing Type does not touch Cloze.
- Read model `ProvisionModeProgress`: `source_locator`, `completed_modes`, `in_progress_modes`, `completed_count`, `total_modes = 6`, `next_mode`, `source_outdated`. No revision scheduling in this model.
- Next mode is the first incomplete ID in the six-mode order. If all six are complete, there is no next mode (M8 will own Learned).
- Workspace CTAs: **Start learning** / **Continue**. Labels: `N of 6 methods` / `6 of 6 methods`. Proof copy “Learn (Cloze)” is no longer the only learning CTA.
- Any completed mode → product **Learning**. All six complete may show **6 of 6 methods complete**. That is **not** product **Learned**.
- Progress is user-scoped, not device-scoped. Logout, device change, roster removal, later-month re-add, subscription expiry, and device revocation do not delete mode rows. Authorization may block learning temporarily.

Repository API (SQLite and Postgres identical): `get_mode_progress`, `list_mode_progress`, `start_mode`, `complete_mode`. No mode SQL in HTTP routes.

---

## M8 boundary

The production six-mode path does **not** call `complete_cloze`, `next_revision_date`, `advance_interval`, or `INTERVAL_LADDER`.

Those helpers remain on the overlay repositories for legacy/prototype compatibility only.

Confirmed:

- no new Day 1 scheduling
- no new interval advancement
- no product Learned transition
- no new Mastered rows
- legacy proof revision rows (`status=review`, `next_revision`, `interval_days`) are not deleted or rewritten

M7 may expose “6 of 6 methods complete” as a learning-engine fact. Required-mode completion → Learned → Day 1 belongs to M8.

---

## Source integrity

- Every mode row records `source_version` and `source_hash` from the canonical section being practiced.
- On mode GET, live section hash is compared to stored identity. Mismatch surfaces existing M6 **Law updated**. The row is not rewritten by a read.
- M9 owns amendment reconciliation, affected-section recalculation, and progress invalidation. Recording hash/version in M7 does **not** tick M9.
- No AI-generated cloze, letters, type target, recite target, or test answer. Derived transforms are deterministic from canonical text.
- Canonical reveal still uses `canonical_body_text(section)`, never user input or transformed output.

---

## Law scope

| Requirement | Status |
|-------------|--------|
| Entire Act selection | Every non-omitted, non-empty section locator is selected. Each selected section independently enters all six modes. No “entire Act mode progress” row. |
| Individual section selection | Same six modes per selected locator. |
| Removing a section from selection | Does not silently delete historical mode progress. Selection is current scope; history remains learning state. |
| Omitted / empty nodes | `section.is_omitted` or empty `canonical_body_text` → not selectable, not learnable, no mode rows. |
| Generic eligible Acts | `is_playground_eligible_law()` + canonical registry. Route-level proof: NDPS, BNS, BNSS. No three-law allowlist. |

Playground does **not** route through `ReminderEngine`, `LearningUnit`, `learning_unit_progress`, `unit_modes_seen`, Constitution Article progress, or Constitution Done.

---

## Entitlement

All six modes are identical across Plus / Pro / Max / admin / local owner. Tier affects roster capacity only. There is no Constitution-style Type/Recite premium lock. Pending + current roster law keeps all six usable. Pending affects new roster consumption, not learning quality.

---

## Performance

- One mode request hydrates **exactly the requested Act**. Never another Act.
- Mode-progress queries are scoped to user + law + section (workspace batches by user + law).
- No N+1 per mode. No loading every overlay progress row in the account to open one section.
- Read / Cloze / Letters / Type / Test require no external service. Recite degrades if speech is unavailable. No Razorpay/provider call in learning.

---

## Accessibility

- Mode tabs: `role="tablist"` / `role="tab"`, `aria-selected`, `aria-current="page"` on the active method.
- Playground shell `:focus-visible` outline.
- Primary controls `min-height: 44px`.
- Letters / Recite remain keyboard-usable without speech.
- No mode requires hover.
- Phone (390×844): stepper, Step N of 6, section identity, mode task, large actions. Six-card deck is hidden below 1040px so the exercise is on-screen.
- Desktop (≥1040px): same modes and completion; six-card deck + wider exercise panel.

Manual review covered 390×844 light/dark and ≥1040 light/dark for all six modes. At 390 the Test tab wraps to a second row; primary actions stay tappable.

---

## Tests

| Gate | Result |
|------|--------|
| Focused `tests/test_playground_m7.py` | **44 passed** |
| Full `python3 -m pytest -m "not integration" -q --tb=line` | **2242 passed, 9 skipped, 1 deselected, 0 failed** |
| Incoming baseline | 2198 passed (2242 = 2198 + 44 M7) |
| Constitution Learn | Unchanged; included in the full suite |
| Alembic | Single head `20260924_0025` |
| CI on `cursor/playground-220d` | success on `73cd2dd`, `318079e`, `031207c` |

Coverage includes: registry without Write; migration parent/head/RLS/SQLite parity/Cloze backfill; start/complete/reload/idempotent/attempt/source identity/cross-user; GET 200 for all six; unknown mode 404; unselected section blocked before write; HTTP Cloze does not schedule Day 1; generic NDPS/BNS/BNSS six-mode path; Entire Act / omitted nodes; resume; roster/history; subscription lifecycle; source mismatch detection without mutating on read.

M7 replaces proof Cloze completion semantics. M8 will add the real Learned → Day 1 trigger.

---

## Git

| SHA | What |
|-----|------|
| [`73cd2dd`](https://github.com/sanjisworking-commits/recall_the_c/commit/73cd2dd1618401e61150ccd028c95011c973bf97) | Ship Playground six-mode learning independently of revision (engine, `0025`, tracker 76.0) |
| [`318079e`](https://github.com/sanjisworking-commits/recall_the_c/commit/318079e7808f217b68b0b56c65229d04106c4639) | Keep Playground Mark as read visible on desktop and phone |
| [`031207c`](https://github.com/sanjisworking-commits/recall_the_c/commit/031207ca2e332038a315713ea37b8923926a5f41) | Show Playground Cloze instead of reusing Constitution panel hiding |

HEAD at report time: `031207ca2e332038a315713ea37b8923926a5f41`.

---

## What this batch is not

- Not M8: no Learned transition, no Day 1, no interval ladder, no Today/Calendar integration from mode completion.
- Not M9: hash/version recording is M7 acceptance, not amendment workflow.
- Not a Constitution learning-engine rewrite. Stateless helpers may be shared; Constitution persistence, quiz wrappers, and mode tracking are unchanged.
- Not a seventh Write mode.
