# Playground Milestone 9 — End-of-batch report

**Branch:** `cursor/playground-220d`
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)
**Closed as:** Milestone 9 = `DONE` — weight **5**
**Stage 1:** **89.0 / 100**
**Stage 2:** `NOT STARTED`

The architectural change in this batch is the separation of **source-review facts** from **learning history**. An amendment creates a new review record. It does not rewrite initial-mode rows, revision-mode rows, Learned, Mastered, `next_revision`, interval, or selection. A provision may legitimately be **Mastered + Law updated**.

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
Milestone 8 = DONE — 20/20
Milestone 9 = DONE — 15/15

Stage 1 = 89.0 / 100
Stage 2 = NOT STARTED
```

M10 (SEO scoring) and M11 are **not** scored.

```text
Source identity
[x] canonical locator
[x] law source version
[x] registry law source hash
[x] section source hash

Amendment detection
[x] cheap law-level version/hash comparison
[x] no whole-corpus hash work on Playground home
[x] changed law triggers targeted section comparison
[x] unchanged sections preserve learning state
[x] affected sections flagged

UX
[x] “Law updated” state
[x] number of affected learned provisions
[x] review affected provisions
[x] source provenance visible where appropriate

Commercial behaviour
[x] amended version does not create a second law slot
[x] same law_id remains same roster law
```

---

## Source identity

Existing layers are unchanged.

| Layer | Source | Notes |
|-------|--------|--------|
| Canonical locator | `{law_id}:section:{number}` via `SectionLocator` / `section_locator()` / `parse_locator()` | No second section-key format. |
| Law version | `BareActSpec.source_version` | Not Act year, filename suffix, mtime, Git SHA, or billing version. |
| Registry identity | `playground_law_source_identity(law_id)` → `identity_token = source_hash or filename` | Registry metadata only. Does not open JSON, hash the runtime file, hydrate the Act, or scan the corpus. Filename fallback is a **token**, not a cryptographic SHA. UI shows `Source version {n}`. |
| Section hash | `source_hash(section)` after that one Act is hydrated | `number` + `title` + `canonical_body_text(section)`. Title-only change is a change. |

No request-time `Path.read_bytes()` / `sha256(runtime_json)`.

---

## Detection

Two-stage detector in [`playground/source_review.py`](../src/constitution_memorizer/playground/source_review.py):

```text
CHEAP GATE
stored user_playground_item.source_version / law_source_hash
vs
current BareActSpec source_version / identity_token

if unchanged:
    stop (hydrated = false)

if changed:
    hydrate ONLY that law
    compare user-relevant section hashes
```

`is_law_registry_outdated(item, current_identity)` is metadata-only.

Targeted scan triggers: stale law workspace open, section management for that law, explicit `GET /playground/laws/{law_id}/source-review`. Home does not scan.

User-relevant locators are the union of:

```text
user_playground_selection
user_playground_mode_progress
user_playground_revision_mode_progress
user_playground_progress
```

`historical_section_identity(...)` picks the most recent practiced baseline (revision-mode, then initial mode, then lifecycle, then selection). Practiced rows outrank a later re-select. Baseline selection is for detection only; historical hashes stay put.

Classification:

| Current Act | `change_kind` |
|-------------|---------------|
| Locator does not resolve | `missing` |
| `is_omitted` | `omitted` |
| Live `source_hash` ≠ stored baseline | `changed` |
| Live hash equals stored | unchanged — no change row |

New unread sections are not affected learned provisions. A law-level identity change with zero user-relevant diffs persists a scan with `affected_total = 0` and does not warn “N provisions changed.”

---

## Schema

Migration: [`alembic/versions/20260927_0027_playground_source_changes.py`](../alembic/versions/20260927_0027_playground_source_changes.py)

```text
parent  20260925_0026
head    20260927_0027
```

`0026` is not edited.

| Object | Role |
|--------|------|
| `user_playground_source_change` | Per-provision amendment event. PK `(user_id, law_id, source_locator, current_source_version, current_law_source_hash)`. |
| `user_playground_source_scan` | Compact law-level scan so home can show persisted affected counts with zero hydration. |

Change kinds: `changed` \| `missing` \| `omitted`. Status: `pending` \| `reviewed`. No canonical statute text. No recall attempts, speech, or typed answers.

Repeated scans of the same registry version are idempotent (`ON CONFLICT`). A later v3 scan is a distinct event; v2 pending history remains. Review POST is scoped to `detected_source_version` + `detected_law_source_hash`; a stale v2 review against live v3 is `409 stale_source_review`.

Postgres: `ENABLE ROW LEVEL SECURITY` with no policies (app-role bypass; isolation is `user_id` scoping). SQLite `SCHEMA_SQL` parity.

Overlay activation identity (`user_playground_item.source_version` / `law_source_hash`) is historical and is **not** rewritten when a new registry version is observed. Warning suppression uses the scan/review rows.

---

## Preservation

Detection and review do **not** automatically:

* delete or rewrite initial-mode history
* delete or rewrite revision-mode history
* reset to Read / Day 1
* demote Learned or Mastered
* change `next_revision` or `interval_days`
* delete selection rows
* bulk-update stored hashes / source versions

Marking reviewed sets `status = reviewed` and `reviewed_at`. It does not complete a mode, mark the new source learned, or rewrite old identity. Future practice against the current source records current identity on **new** rows only.

---

## UX

Copy family: **Law updated**, then **N learned provision(s) changed since your recorded learning source**, CTA **Review affected provisions**. No “progress is invalid / start over / learning deleted.”

| State | Home | Workspace |
|-------|------|-----------|
| Registry stale, no scan yet | Law updated + Review affected provisions | Law updated panel |
| Scan finds pending learned changes | Law updated · N affected provisions | count + Review CTA |
| Scan finds zero user-relevant diffs | no affected-provision alert | Source updated. Your learned provisions are unchanged. |
| All current pending rows reviewed | no pending alert | All updates reviewed |

Changed existing section: current title + `VERBATIM TEXT` + `canonical_body_text`. No fabricated before/after wording (hashes are stored, not old statute text). Missing/omitted: “No longer present in the current source” / omitted copy; no broken Revise CTA; Read current Act. Direct learn to a missing historical section 303s to source-review (JSON `source_missing` 404). Inactive this-month law cannot open the private review workflow. Public Bare Act remains readable.

Provenance: `Source version {n}` on workspace, learn, and review. No invented Gazette date, ministry, department, or official URL. No raw hashes as primary UX.

---

## Commercial

Roster identity is `law_id`. NDPS v1 → v2 is the same roster row and the same used count. Carry-forward of NDPS after a registry change is still one candidate and one target-period slot. Re-add in a later month is one slot for that `law_id`, not v1 + v2.

---

## Performance

| Surface | Acts hydrated |
|---------|----------------|
| `GET /playground` | 0 (registry comparison + batched scan/change reads) |
| `GET /playground/roster` | 0 |
| `GET /playground/roster/next` | 0 |
| Today / Calendar | 0 |
| Source-review for one law | ≤ 1 (that law only) |

Home uses `batch_source_presentations`: one `list_items`, one `list_source_scans`, one `list_source_changes`. No per-card source-change query. No whole-corpus hash. No IndiaCode / Gazette / AI.

---

## Tests

Focused module: [`tests/test_playground_m9.py`](../tests/test_playground_m9.py) — **21** tests.

Coverage includes 0027 parent/head/RLS/SQLite, locator + version + filename-token + section hash, cheap same-identity zero hydration, stale home/roster/roster-next zero hydration, targeted A-changed / B-unchanged / C-missing with one Act, unchanged and changed learning-field equality, reviewed_at without learning mutation, v2→v3 stale review 409, workspace Mastered + Law updated, missing learn redirect, zero-affected copy, generic BNS omitted, same-month slot, carry-forward one slot, Today/Calendar/home/roster 0 Acts then NDPS-only review, inactive-law block, practiced baseline over later selection, batched home reads, no “progress lost” copy.

M8, M7, M6, M5-A, M5-B, playground, Calendar, law-loading, devices M4-A, and migrations regressions: **292 passed** in that focused group.

Full suite command:

```bash
python3 -m pytest -m "not integration" -q --tb=line
```

Result: **2295 passed**, 9 skipped, 1 deselected, **0 failed** (incoming baseline 2274 passed).

Alembic head after this batch: `20260927_0027`.

GitHub CI on `cursor/playground-220d`: **success** for implementation `6d2b74c` and HEAD `3fea1de`.

---

## Git

| SHA | What |
|-----|------|
| [`6d2b74c`](https://github.com/sanjisworking-commits/recall_the_c/commit/6d2b74c06042444f28972fe95884d882db46af68) | Ship Playground source-integrity review (`0027`, detector, review UX, M9 tests) |
| [`6a60099`](https://github.com/sanjisworking-commits/recall_the_c/commit/6a600990946464f411dbdb88a3c65ac80473066d) | Score Milestone 9 as DONE at Stage 1 89.0 |
| [`3fea1de`](https://github.com/sanjisworking-commits/recall_the_c/commit/3fea1dee3efb58193c0f0b32e20a48737e8711f3) | Record the Milestone 9 tracker SHA in the close-out report |

Implementation SHA: `6d2b74c06042444f28972fe95884d882db46af68`. Tracker SHA: `6a600990946464f411dbdb88a3c65ac80473066d`. CI-green HEAD at this write: `3fea1dee3efb58193c0f0b32e20a48737e8711f3`.

PR [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188) is open on this branch.

---

## Out of scope

- Not M10: Playground `noindex` / sitemap scoring.
- Not a second roster identity keyed by `source_version`.
- Not automatic relearning, ladder reset, or semantic amendment summaries.
- Not request-time statute acquisition.
