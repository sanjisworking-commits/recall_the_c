# Playground Milestone 8 — End-of-batch report

**Branch:** `cursor/playground-220d`
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)
**Closed as:** Milestone 8 = `DONE` — weight **8**
**Stage 1:** **84.0 / 100**
**Stage 2:** `NOT STARTED`

The architectural change in this batch is the separation of **durable six-mode evidence** from **revision-cycle state**. M7 `user_playground_mode_progress` rows stay lifetime learning history. M8 adds Learned scheduling and a per-rung revision-mode table. Initial Read ✓ is never the same row as Day 7 Read ✓.

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

Stage 1 = 84.0 / 100
Stage 2 = NOT STARTED
```

M9 (amendment invalidation / affected clauses) and M10 (SEO scoring) are **not** scored.

---

## Completion rule

A provision becomes Learned **only** when all six `PLAYGROUND_LEARN_MODES` are complete:

```text
read → cloze → letters → type → recite → test
```

No subset. No Cloze-alone. No tier-specific or NDPS/BNS special case. The list is the M7 registry; M8 does not create a second required-mode list.

Atomic service path: `complete_learning_mode_and_transition_if_ready`.

```text
upsert M7 mode completion
→ count completed initial modes
→ if six and no learned/review/mastered row:
      INSERT Learned + Day 1 due (ON CONFLICT DO NOTHING)
→ commit
```

Two near-simultaneous sixth-mode completions write `learned_at` once. If the provision is already `learned` / `review` / `mastered`, initial-mode completion cannot restart the ladder.

For newly Learned:

```text
status          = learned
learned_at      = today (Asia/Kolkata)
times_completed = 0
last_completed  = NULL
interval_days   = 1
next_revision   = today + 1
```

Learned today ≠ Day 1 completed today. Opening practice on the Learned day does not consume Day 1.

Legacy proof rows with `status=review` (or `mastered`), a ladder interval, and `next_revision` remain grandfathered even when `learned_at` is NULL. They do **not** need retroactive six-mode completion. New lifecycle rows follow the all-six rule. `cloze_done` remains a compatibility column and is not production due/Learned truth.

---

## Schema

Migration: [`alembic/versions/20260925_0026_playground_revision_lifecycle.py`](../alembic/versions/20260925_0026_playground_revision_lifecycle.py)

```text
parent  20260924_0025
head    20260925_0026
```

| Object | Role |
|--------|------|
| `user_playground_progress.learned_at` | First all-six completion date (DATE / TEXT ISO date). |
| `user_playground_revision_mode_progress` | Per-rung six-mode cycle. PK `(user_id, law_id, source_locator, rung_days, mode)`. |
| `user_playground_progress_due` | `(user_id, next_revision, status)` for Today/Calendar. |

Revision-mode fields: `status` `in_progress` \| `completed`, `attempt_count`, `first_started_at`, `last_attempt_at`, `completed_at`, `source_version`, `source_hash`, timestamps. Allowed rungs: **1, 3, 7, 15, 30, 60**. Allowed modes: the six M7 IDs. No statute text, typed answers, transcripts, or audio.

Postgres: `ENABLE ROW LEVEL SECURITY` with no policies (app-role bypass; isolation is `user_id` scoping). SQLite `SCHEMA_SQL` plus `_ensure_progress_columns` for `learned_at` on existing DBs. `0025` is not edited.

Three tables stay separate:

```text
user_playground_mode_progress
  → initial learning methods

user_playground_revision_mode_progress
  → methods completed during a particular scheduled rung

user_playground_progress
  → lifecycle / revision schedule
```

Today and Calendar are **projections**. There is no `user_playground_revision_calendar` or `user_playground_today_queue`.

---

## Revision engine

Official ladder, after the most recently completed lifecycle event:

```python
INTERVAL_LADDER = (1, 3, 7, 15, 30, 60)
```

Day 15 is intentional. Labels are rungs, not cumulative days since original learning.

| Transition | After all six methods of the current rung | Result |
|------------|-------------------------------------------|--------|
| Learned → Day 1 | (schedule only) | `interval_days=1`, `next_revision=learned_at+1`, `times_completed=0` |
| Day 1 → Day 3 | Day 1 complete | `status=review`, `times_completed=1`, `interval_days=3`, `next=today+3` |
| Day 3 → Day 7 | Day 3 complete | `times_completed=2`, `interval_days=7`, `next=today+7` |
| Day 7 → Day 15 | Day 7 complete | `times_completed=3`, `interval_days=15`, `next=today+15` |
| Day 15 → Day 30 | Day 15 complete | `times_completed=4`, `interval_days=30`, `next=today+30` |
| Day 30 → Day 60 | Day 30 complete | `times_completed=5`, `interval_days=60`, `next=today+60` |
| Day 60 → Mastered | Day 60 complete | `status=mastered`, `times_completed=6`, `interval_days=60`, `next_revision=NULL` |

Mastered is terminal for M8: not due, not scheduled, not in Today, no future Calendar event. No annual refresh, maintenance review, or decay.

GET of Today, Calendar, workspace, or a revision mode **never** advances the ladder. Only successful completion of all six methods of the **current** due rung advances it, once, inside a transaction:

```text
lock lifecycle row (Postgres FOR UPDATE / SQLite BEGIN IMMEDIATE)
upsert revision-mode completion
re-count current-rung completed modes
advance if six and interval_days still equals that rung
commit
```

---

## Revision modes

Same six M7 methods and the same learn route family:

```text
/playground/laws/{law_id}/sections/{number}/learn/{mode}?revision=1
```

Server resolves the due rung from persisted `interval_days`. Client `rung_days=60` is not trusted. Stale claimed rung for a mode that was **not** already completed on that rung → `409 stale_revision`. Duplicate completion of an already-completed mode on that claimed rung increments `attempt_count`, leaves status completed, and does not advance twice.

`today < next_revision` → `409 not_due`. Practice of initial M7 modes may still be available; it does not consume the scheduled revision.

Authorization order is unchanged:

```text
authentication → subscription → device → current roster → active law
→ selected section → lifecycle state → due rung → hydrate requested Act → mode
```

Pending + law active on the current roster remains learnable. Pending does not change ladder quality or rung timing.

Test quizzes add `rung_days` to the seed only when a revision rung is set, so M7 quizzes stay deterministic.

---

## Overdue

```text
overdue  ⇔ status != mastered AND next_revision IS NOT NULL AND next_revision < today
due today ⇔ next_revision == today
future    ⇔ next_revision > today
```

`days_overdue` is `today - next_revision` and is 0 on due-today. Labels: `Due today`, `1 day overdue`, `N days overdue`.

If Day 7 was due 20 days ago, the user completes that **Day 7** revision once. Next rung is Day 15, `next_revision = completion_date + 15`. No auto-skip, no catch-up, no reset to Day 1.

Today ordering: overdue oldest first, then due today, then stable law/section order. Tier/payment value is not a sort key.

---

## Persistence

| Event | Lifecycle | M7 mode rows | Revision-mode rows |
|-------|-----------|--------------|--------------------|
| Roster remove / later re-add | Unchanged | Unchanged | Unchanged; immediately actionable if due |
| Monthly Keep | Unchanged | Unchanged | Unchanged |
| Monthly Decline / inactive | Unchanged, not actionable | Unchanged | Unchanged; re-enters Today/Calendar on later Add |
| Subscription expiry → resubscribe | Unchanged | Unchanged | Unchanged; overdue if the date passed |
| Device revoke / other allowed device | Unchanged | Unchanged | Unchanged; account-wide |
| Mastered + any of the above | Stays Mastered | Unchanged | Unchanged |

M9 may later define amendment consequences. M8 does not demote Learned or Mastered when statute text changes.

---

## Today

`list_due_revisions(user_id, as_of, active_law_ids)` is one batched read. Active law IDs come from the current roster. No Bare Act hydration.

Each card: law title, Section {number}, revision rung, Due today / N days overdue, CTA **Revise** to the first incomplete mode of the current rung.

Inactive historical laws are omitted from the actionable queue and keep their stored `next_revision`. Re-adding the law makes the same due date immediately overdue if it has passed.

The Today shell adds a **Law revisions** block beside Constitution work. Combined `due_count` is a read-model sum; persistence is not merged.

---

## Calendar

`list_revision_schedule(user_id, start_date, end_date, active_law_ids)` projects the **single** persisted `next_revision`. The full ladder is not pre-rendered.

Event identity: `{short} · Section {n} — Day {rung} revision`, category **Law revision**, href on the law/revision route — never a Constitution `learning_unit_id`. Due/current date opens the revision entry point; future dates open the law workspace. Future click does not advance.

Mastered provisions have `next_revision=NULL`, so no future event. Completing a revision replaces the current projected event with the next persisted date through the lifecycle row.

---

## Progress summaries

`list_playground_summaries` is grouped SQL, not N+1 per selected section.

| Count | Definition |
|-------|------------|
| `selected_count` | Selected locators |
| `learning_count` | Some initial mode progress, no `learned`/`review`/`mastered` |
| `learned_count` | Lifecycle `learned` or `review` (not mastered) |
| `due_count` | `next_revision <= today` and not mastered |
| `mastered_count` | `status = mastered` |

One completed M7 mode is **not** Learned. Law-card precedence: **Mastered > Due > Learned > Learning > Not started**. Section rows use M6 language (Learning · 4 of 6 methods / Learned + First revision · Day 1 / Due · Day 7 · Revise / Mastered · Completed).

---

## Scope protection

| Surface | M8 action |
|---------|-----------|
| `PLAYGROUND_LEARN_MODES` | Unchanged. No new/removed/paid mode. |
| M3/M4/M5 payment, device, roster | Unchanged. Revision still requires current-roster authorization. |
| M9 amendment invalidation | Not implemented. Hash/version is stored; ladder is not reset. |
| M10 SEO | Not scored. Existing `noindex` on private surfaces is preserved. |
| Constitution `learning_unit_progress` / ReminderEngine / calendar tables | Unchanged. Law chips are an additive projection. |

---

## Tests

Focused module: [`tests/test_playground_m8.py`](../tests/test_playground_m8.py)

Coverage includes 0/6 and 5/6 not Learned, 6/6 Learned + Day 1 tomorrow, every rung including Day 15 = 15, overdue one-rung re-anchor, early `409 not_due`, stale `409 stale_revision`, duplicate sixth-mode, Learned and revision sixth-mode races, roster remove/re-add, subscription expiry, device revoke, Today current-roster filter (NDPS + overdue BNS, not inactive BNSS) with zero Act hydration, Calendar chips, lifecycle-aware summaries, Kolkata 18:30 UTC boundary, legacy review/mastered, `cloze_done` not due truth, and M7 registry protection.

M7’s 44 focused tests remain green. M3–M6, Today, Calendar, and Constitution calendar projection tests remain green.

Full suite command:

```bash
python3 -m pytest -m "not integration" -q --tb=line
```

Alembic head after this batch: `20260925_0026`.

---

## Git

| SHA | What |
|-----|------|
| [`a9e6c18`](https://github.com/sanjisworking-commits/recall_the_c/commit/a9e6c18a660702261f581f2e8160d92395490b0f) | Ship Playground Learned-to-Mastered revision lifecycle (`0026`, engine, Today/Calendar, tracker 84.0) |

HEAD at report time: `a9e6c18a660702261f581f2e8160d92395490b0f`. Parent is M7 close-out `0859f9d247758473c2bafc47ab9155b1c767cd15`.

---

## What this batch is not

- Not M9: source hash/version is stored on revision-mode rows; statute change does not invalidate Learned or demote Mastered.
- Not M10: private Playground/Today/Calendar stay off the public SEO scoreboard.
- Not a second learning engine: revision reuses `PLAYGROUND_LEARN_MODES` and the existing learn route family.
- Not a Constitution calendar rewrite: law chips are an additive projection with category `Law revision`.
