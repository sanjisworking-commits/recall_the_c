# Playground Stage 2 — S2-0 report

End-of-batch closeout for the S2-0 **measurement** baseline. Spec §59
structure. Local Cloud Agent characterization, **not a production SLA**.
Not Stage 2 complete. Not S2-1 implementation.

```text
No tuning performed in S2-0; this batch establishes the baseline.
```

Parent of this documentation commit: `b4dc3ac5923688fb653c427176b5894ebe3c6a2c`
(T24 baseline markdown). Operator measurements were taken at T22/T23 HEAD
`bbea109adfa66ac8a95ac773ed2039eb1d4a9039`. Durable numbers live in
[PLAYGROUND_STAGE2_BASELINE.md](PLAYGROUND_STAGE2_BASELINE.md). This report
does not re-run T23.

---

## 1. Purpose

Original T25 / WS13: set live Stage 2 status to `IN PROGRESS`, tick only
proven measurement boxes, record original versus actual PostgreSQL
coverage, and name **exactly one** S2-1 recommendation. Completing S2-0
does not complete Stage 2.

---

## 2. Baseline environment

| Item | Value |
|---|---|
| SHA (operator run) | `bbea109adfa66ac8a95ac773ed2039eb1d4a9039` |
| SHA (human baseline) | `b4dc3ac5923688fb653c427176b5894ebe3c6a2c` |
| SHA (this report / tracker) | this T25 commit (parent `b4dc3ac`) |
| Python | 3.12.3 |
| SQLite | 3.45.1 |
| PostgreSQL | 16.15 (Ubuntu), Unix peer, disposable DB `s2_0_explain_t23_20261009t224132` |
| Alembic | `20260927_0027` |
| `--app-env` | `test` |
| Host | Cloud Agent VM; in-process ASGI TestClient; not Railway; not production |
| Operator stamp | `20261009T224132` |
| Clock | harness `PLAYGROUND_TEST_NOW` 2026-09-16 12:00 UTC |
| Fixture size | plus-10; pro-30 home-only; due-heavy Today; BNSS `bnss_runtime_v1.json` **1 395 157 bytes**; EXPLAIN roster 30, selection 520, progress 520, mode_progress 3120 |

Machine/runtime caveat: another host, a network browser, or production
Postgres will differ. Milliseconds here are not SLAs.

---

## 3. Instrumentation

Playground request breakdown extends the existing
`web/request_context.py` framework (T1–T9, locked by T22).

| Piece | What S2-0 recorded |
|---|---|
| Route groups | `normalize_request_path_group` — `/playground`, `/playground/laws/{law_id}`, source-review, learn, `/dashboard`, `/calendar`, roster, sitemap. No raw `law_id` or UUID in `path_group`. |
| Timing stages | Middleware owns `total_ms`. Playground stages include `playground_device`, `playground_entitlement`, `playground_roster_access`, `playground_home_build`, `playground_today`, `playground_calendar`, `playground_workspace_build`, `playground_source_review`, `playground_source_scan`, `bare_act_load`, `template`. |
| Counters | `playground_repo_round_trips`, `playground_db_reads` / writes, device lookups, `playground_entitlement_resolves`, `bare_act_cache_misses`. |
| Notes | Bounded tokens: `auth_state`, `playground_access_result`, `playground_device_result`, `playground_roster_result`, `bare_act_cache`. |
| Logging / sampling | `PERF_LOG_SAMPLE_RATE` samples **logging**, never collection. |
| Privacy | No Bearer, session/device cookie values, emails, or webhook secrets in breakdown logs (T22). Fixture UUID is not reprinted here. |

T10 was document-only (no new caches). See §16.

---

## 4. Route baseline (SQLite sequential HTTP)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite. Not PostgreSQL HTTP.** T13: warmup 5, N 50, HTTP 200×50.

| Scenario | Route | p50 ms | p95 ms | max ms | round trips p50 | db_reads p50 | Act / cache |
|---|---|---|---|---|---|---|---|
| plus-10 | `/playground` | 6.627 | 11.574 | 35.693 | 12 | 10 | no Act load (home) |
| pro-30 | `/playground` (home-only) | 10.388 | 12.939 | 40.268 | 12 | 10 | no Act load |
| due-heavy | `/dashboard` | 14.697 | 15.934 | 42.845 | **129** | **129** | no Act load |
| learned-heavy | `/playground` | 8.886 | 11.432 | 38.827 | 12 | 10 | no Act load |
| source-review | `/playground/laws/{law_id}/source-review` | 120.960 | 180.284 | 199.591 | 51 | 9 | `bare_act_cache=hit` |
| law-workspace | `/playground/laws/{law_id}` | 27.908 | 36.693 | 46.067 | 12 | 11 | `bare_act_cache=hit` |

PostgreSQL sequential HTTP percentiles: **unavailable**.

Recorded `template` stage (T13; supports the template-rendering profile
tick; not a tune):

| Scenario | template p50 ms | template p95 ms | total p95 ms |
|---|---|---|---|
| plus-10 | 0.517 | 0.854 | 11.574 |
| pro-30 | 0.488 | 0.549 | 12.939 |
| due-heavy | 1.013 | 1.312 | 15.934 |
| learned-heavy | 0.573 | 0.833 | 11.432 |
| source-review | 0.837 | 1.175 | 180.284 |
| law-workspace | 1.055 | 1.252 | 36.693 |

On source-review, `playground_source_scan` p50/p95 = 110.769 / 168.384 ms.
The recorded `template` p95 (1.175 ms) is not the source-review total p95
driver. That comparison uses the stage measurements above; it is not an
optimization.

---

## 5. Query plans (PostgreSQL EXPLAIN)

Baseline measurement on this Cloud Agent VM, not a production SLA.
Label: `disposable PostgreSQL baseline, not an SLA`. T23 rerun, nine
`EXPLAIN (ANALYZE, BUFFERS)` plans. Actual TEXT:
`/opt/cursor/artifacts/t23/explain/explain-pro-30-{label}.txt`. Frozen JSON
`plan_file` metadata still says `docs/performance/explain-pro-30-{label}.txt`
(does not match the T23 TEXT directory). Historical T15 committed dumps at
SHA `b3baa6c` are older and were not overwritten.

| Label | Plan shape | Exec ms | Index names | N+1 hint |
|---|---|---|---|---|
| current_roster_lookup | Sort; Seq Scan | 0.045 | [] | false |
| roster_capacity_count | Aggregate; Sort; Seq Scan | 0.051 | [] | false |
| home_summary_aggregate | Sort; Hash Right Join; GroupAggregate; Hash Left Join; Seq Scan; HashAggregate | 4.309 | [] | false |
| due_revisions | Sort; Hash Join; Seq Scan | 0.656 | [] | false |
| calendar_schedule | Sort; Hash Join; Seq Scan | 0.611 | [] | false |
| device_count | Aggregate; Seq Scan | 0.019 | [] | false |
| device_lookup | Seq Scan | 0.012 | [] | false |
| current_subscription | Seq Scan | 0.013 | [] | false |
| source_review_aggregate | Sort; Seq Scan | 0.044 | [] | false |

All nine: sequential scan present, empty `index_names`. Plan-shape
observation. Not an index change. EXPLAIN is not PostgreSQL HTTP.

---

## 6. Original versus actual PostgreSQL coverage

| Item | Original spec | Actual S2-0 |
|---|---|---|
| Authorized T23 operator matrix | Full local baseline | **Complete** |
| PG EXPLAIN (ANALYZE, BUFFERS) | Disposable DB, plan summaries | **Complete** (nine plans, §5) |
| Sequential HTTP labeled Postgres (p50/p95) | Spec §56 / WS6 | **Unavailable** (frozen T13 `assert_fresh_sqlite`) |
| Concurrent GET on PostgreSQL | WS10 | **Unavailable** (frozen T18 abort) |
| T19/T20/T21 on PostgreSQL | implied PG proof | **Unavailable** (SQLite cells complete) |
| Original full PostgreSQL performance coverage | required for numbers labeled “Postgres” | **Incomplete** |

PostgreSQL EXPLAIN cannot substitute for PostgreSQL HTTP latency or
PostgreSQL concurrent GET. SQLite timings in this report are SQLite
timings.

---

## 7. Scaling (T16)

N+1 **locks** at roster N = 1 / 10 / 30 (round trips, not milliseconds):

| Surface | Finding |
|---|---|
| Home `/playground` | `playground_repo_round_trips` and `playground_db_reads` **constant** across N. Summaries and source-review reads batched. |
| Today `/dashboard` | `list_due_revisions` = 1 at each N. `list_revision_mode_progress` follow-up = **`[4, 40, 120]`**. |
| Calendar `/calendar` | `list_revision_schedule` = 1. Same follow-up **`[4, 40, 120]`**. |

Home is not growing per law. Today follow-up is linear in due facts. That
remaining shape is **not eliminated** in S2-0. Tracker box “Measure and
eliminate remaining N+1” stays unchecked. It is the S2-1 target (§17).

Latency growth at N=30: T13 pro-30 home p95 12.939 ms versus plus-10
11.574 ms (SQLite, home-only). That is not a PostgreSQL scale test.
“Users with 30 active laws” and “High progress-row counts” stay unchecked.

---

## 8. BareAct (T14, T17, T21)

Largest eligible Act: `bnss` / `bnss_runtime_v1.json` / **1 395 157 bytes**
/ `confirmed_largest_eligible=true`. **SQLite.** Cold and warm are
separate. Do not average them.

Cold (warmup 0, cache miss, `bare_act_load` present):

| Route | Path | N | p50 ms | p95 ms | `bare_act_load` p50/p95 |
|---|---|---|---|---|---|
| playground_learn | `/playground/laws/bnss/sections/1/learn/read` | 50 | 15.434 | 23.551 | 7.994 / 13.718 |
| playground_workspace | `/playground/laws/bnss` | 50 | 37.389 | 53.297 | 8.263 / 9.431 |
| public_bare_act | `/laws/bnss` | 50 | 12.800 | 44.384 | 8.048 / 8.943 |

Warm (5 discarded hits, then 50; `bare_act_load` omitted):

| Route | Path | N | p50 ms | p95 ms |
|---|---|---|---|---|
| playground_learn | `/playground/laws/bnss/sections/1/learn/read` | 50 | 4.514 | 7.405 |
| playground_workspace | `/playground/laws/bnss` | 50 | 29.803 | 33.158 |
| public_bare_act | `/laws/bnss` | 50 | 4.176 | 4.921 |

Cache effectiveness: cold `cache_class=miss`; warm `cache_class=hit`.
T17: repeated 0 Act hydration on active Plus routes, unauthenticated
`/sitemap.xml`, and halted home. T21: import 428.694 ms and `create_app`
359.239 ms, `get_bare_act=0`, `_load_cached=0`, `hydrated_slugs=[]`,
`first_request=null`, `contract_passed=true`. No startup SLA.

Zero-hydration catalogue / dashboard under load remains the pre-existing
Stage 2 `[x]` (Stage 1 contract). S2-0 reconfirmed it; it was not unticked.

---

## 9. Page weight (T20)

**SQLite in-process TestClient.** `gzip.compress` compresslevel 9, **not
served**. Lighthouse false. No external fetch.

| Page | Path | HTML source | HTML gzip-9 | HTML+CSS+JS source | HTML+CSS+JS gzip-9 |
|---|---|---|---|---|---|
| plus_home | `/playground` | 34 019 | 6 634 | 858 928 | 163 716 |
| bnss_workspace | `/playground/laws/bnss` | 60 280 | 8 474 | 885 189 | 165 556 |
| bnss_learn | `/playground/laws/bnss/sections/1/learn/read` | 31 717 | 7 017 | 856 626 | 164 099 |
| bnss_public | `/laws/bnss` | 319 144 | 22 999 | 1 144 053 | 180 081 |

Static `cache_policy`: **16 / 16** `cache_control=null`. All 16 have ETag
and Last-Modified. Example: `/static/styles.css?v=main85`. Observation
only. Caching-headers tracker box stays unchecked. Tune JS/CSS stays
unchecked.

---

## 10. Concurrency, mutations, webhooks (T18, T19)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite.** PostgreSQL concurrent GET: **unavailable**.

`asgi_in_flight_is_not_parallel_sql` is true. Overlapping ASGI GETs are not
parallel SQLite. T18: `aborted=false`, five batches, C=1/5/10/25,
`incomplete_batches=0`.

plus-10 warm `GET /playground`:

| C | Batches | samples_ok | p95 total_ms | throughput_rps p50 |
|---|---|---|---|---|
| 1 | 5 | 5 | 35.504 | 111.686 |
| 5 | 5 | 25 | 39.824 | 145.614 |
| 10 | 5 | 50 | 72.729 | 133.895 |
| 25 | 5 | 125 | 184.764 | 133.200 |

law-workspace warm `GET /playground/laws/bnss` (cache hit):

| C | Batches | samples_ok | p95 total_ms | throughput_rps p50 |
|---|---|---|---|---|
| 1 | 5 | 5 | 31.765 | 34.479 |
| 5 | 5 | 25 | 143.039 | 35.251 |
| 10 | 5 | 50 | 323.759 | 34.846 |
| 25 | 5 | 125 | 744.495 | 33.976 |

“Concurrent subscriber traffic” stays unchecked (not production traffic;
not PostgreSQL).

### T19 mutations

`live_razorpay=false`. `waves_requested=5`. `concurrency_levels_requested=[1, 2]`.
All six cells `correct_waves=5`, `incomplete_waves=0` at C=1 and C=2.
No production-capacity claim.

| Cell | C=1 waves / correct / incomplete | C=2 waves / correct / incomplete |
|---|---|---|
| roster-cap | 5 / 5 / 0 | 5 / 5 / 0 |
| roster-same-law | 5 / 5 / 0 | 5 / 5 / 0 |
| device-cap | 5 / 5 / 0 | 5 / 5 / 0 |
| device-idem | 5 / 5 / 0 | 5 / 5 / 0 |
| progress-learned | 5 / 5 / 0 | 5 / 5 / 0 |
| revision-sixth | 5 / 5 / 0 | 5 / 5 / 0 |

**Concurrent progress/revision writes** are the `progress-learned` and
`revision-sixth` cells: **SQLite, C=2, five waves**. That is the meaning of
the matching tracker tick. It is not C=25 GET traffic and not PostgreSQL.

### T19 webhooks

N=10 unique, M=10 replays, five script waves, FakeProvider.

| Proof | Result |
|---|---|
| Sequential first | owned=true, HTTP 200 |
| Sequential replay | owned=false, HTTP 200, duplicate=1 |
| Concurrent duplicate, 5 waves | each wave duplicate=1, owned=1, incomplete=false |
| Unique N=10 | owned=10, duplicate=0 |
| Replay M=10 | duplicate=10, owned=0 |
| Out-of-order | pending + charged, owned=2, duplicate=0 |
| Event rows | 12 |

Stage 1 already owns HMAC + event-id. This cell **measures** duplicate /
out-of-order handling. “Webhook failures” (failure telemetry) and “Tune
retry/idempotency” stay unchecked.

---

## 11. Findings (ranked; not fixes)

| Rank | Finding | Status in S2-0 |
|---|---|---|
| P0 | Due-heavy Today `GET /dashboard` **129** `playground_repo_round_trips` versus Plus home **12**. T16 follow-up `[4, 40, 120]`. | **Not fixed.** S2-1. |
| P1 | Source-review sequential p95 **180.284 ms**, `playground_source_scan` p95 **168.384 ms**, `template` p95 **1.175 ms**, SQL `source_review_aggregate` exec **0.044 ms**. | **Not fixed.** Not S2-1. |
| P1 | First-party static assets: **no Cache-Control**; ETag and Last-Modified present (16/16). | **Not fixed.** Caching-headers box unchecked. |
| P2 | All nine Pro-30 EXPLAIN plans: Seq Scan, empty `index_names`. | **Not fixed.** Tune-indexes box unchecked. Not a proved HTTP issue. |
| No action | T10 duplicate-work register (C-home-1, C-dev-1, C-today-1, C-ws-1, …). | **Not implemented. No caches.** |

These remain observations. S2-0 did not convert them into completed
optimizations.

---

## 12. Changes made

```text
No tuning performed in S2-0; this batch establishes the baseline.
```

S2-0 shipped measurement infrastructure (T1–T22), operator artifacts
(T23), human baseline markdown (T24), and this tracker/report slice (T25).
No index migration, no Cache-Control, no Today rewrite, no entitlement
cache, no JS/CSS bundle, no Alembic revision.

---

## 13. Tracker

- Stage 1 remains **DONE — 100.0 / 100**.
- Live Stage 2 = **`IN PROGRESS`** (S2-0 measurement baseline). Stage 2
  overall is **not** `DONE`.
- `Stage 2 may begin only after` is preserved on live snapshot lines.
- Milestone 11 historical ```text``` block still contains
  `Stage 2 = NOT STARTED` (Stage 1 close-out snapshot, not live status).

Boxes **closed** in this batch (measurement / profile / audit / verify
only):

- Database: Profile query plans
- Routing: Measure Playground route latency
- Law-loading: Verify zero-hydration (pre-existing, kept); Profile BareAct
  hydration; Measure cache effectiveness
- Performance: Page-weight audit; Profile template rendering; Cold-start
  behaviour
- Concurrency: Profile roster races; Profile device-registration races;
  Concurrent progress/revision writes under load (**SQLite C=2, five
  waves**); Measure duplicate/out-of-order Razorpay handling
- Observability: Entitlement denial reasons; Device-limit events;
  Roster-full events; Law-load latency; Playground route latency / error
  rate
- Scale: Large Acts

Deliberate **non-ticks** (uncompleted optimizations, unavailable
measurements, or overclaim):

- Measure DB latency (EXPLAIN exec ms exist; PG HTTP percentiles
  unavailable; EXPLAIN is not HTTP DB wait)
- Measure and eliminate remaining N+1 (measured, not eliminated)
- Tune indexes; Measure p95 of aggregates/dashboard reads; **tune**;
  archival strategy
- Trim queries; entitlement-cache tuning; Profile authorization **tune**;
  further batch writes/reads
- Chunking; scale search infrastructure
- Entire SEO-at-scale section
- Tune JS/CSS; Caching headers
- Tune retry/idempotency; degraded-provider
- Entire security-and-misuse section
- Webhook failures; payment reconciliation failures
- Entire operational-tooling and UX sections
- 700+ catalogue; users with 30 active laws; high progress-row counts;
  sitemap inventory scale; concurrent subscriber traffic
- Entire cleanup section

Ambiguous boxes left unchecked rather than stretched to a tick count.
Next measured optimization target: **S2-1** (§17).

---

## 14. Tests

Focused T23 WS12/benchmarking pytest: **507 passed**.

full non-integration pytest exited 0; final summary log truncated

Alembic head: `20260927_0027`. T22 freeze: tracker still contains
`DONE — 100.0 / 100` and `Stage 2 may begin only after`.
`tests/test_playground_m11.py` still accepts that freeze phrase (or the
historical `Stage 2 = NOT STARTED` in the M11 snapshot).

PostgreSQL HTTP benchmark: **unavailable** (do not read SQLite p50/p95 as
Postgres). CI: this T25 commit is local-only; PR **#188** stays draft.

---

## 15. Git

| Item | Value |
|---|---|
| Implementation SHAs | T1–T22 on `cursor/playground-220d`; T23 run-only at `bbea109`; T24 `b4dc3ac` |
| This report / tracker SHA | T25 commit (parent `b4dc3ac5923688fb653c427176b5894ebe3c6a2c`) |
| PR | **#188 DRAFT** |
| Push | none from T25 |

---

## 16. T10 duplicate-work appendix (no caches)

T10 was analysis-only at `eaa9b23` (`/opt/cursor/artifacts/stage2_T10_report.md`).
No SHA. Folded here as required. **Do not implement caches.**

Calls per request (Measured T6 reads/writes/round-trips):

| Surface | T6 | Notes |
|---|---|---|
| Plus empty `GET /playground` | 7 / 2 / 9 | Two `capacity()` / `ensure_period` (attach + home). Device lookups 2 (inspect + ensure). |
| Plus empty dashboard | 3 / 0 / 3 | Two `_active_law_ids` `get_period` with `list_due_revisions` between them. No `capacity()`. |
| Plus empty calendar | 2 / 0 / 2 | One `_active_law_ids`. Different overlay method than Today. |
| Plus NDPS workspace | 11 / 1 / 12 | One attach `capacity()`; third workspace `capacity()` skipped because snapshot period was set. Duplicate overlay `get_item`. |

Candidate register (not implemented):

| ID | Repeated work | Evidence still required |
|---|---|---|
| C-home-1 | Second `capacity()` UPDATE on GET home | Draft-hold / rollover / whether identical `updated_at` is load-bearing |
| C-home-2 / C-home-3 | Second `count_consumed` / pass `RosterCapacity` | `law_limit` not on snapshot |
| C-dev-1 | inspect then ensure `_lookup` | Overlay order; T4 lock = 2 on Plus Playground |
| C-today-1 | `_active_law_ids` ×2 on empty dashboard | Register only (T10 Q4) |
| C-ws-1 | overlay `get_item` twice | `item=` path vs outdated registry |

Rejected: sharing dashboard reads with `/playground`; inventing
`playground_total`; collapsing Halted-home hydration into T10.

---

## 17. Next batch (exactly one)

```text
Next: S2-1 Today projection round-trip reduction
because due-heavy GET /dashboard records 129 playground_repo_round_trips
versus 12 for Plus home, and T16 shows list_revision_mode_progress
follow-up linear in due facts ([4, 40, 120] at N=1/10/30)
while list_due_revisions stays one call.
EXPLAIN on disposable PostgreSQL is complete for plan shape but is not
a substitute for PostgreSQL HTTP; S2-1 is justified by the
backend-independent round-trip count, not by a Postgres p95.
```

**Future scope (not this commit):** batch or reuse Today projection reads
(`list_revision_mode_progress` or equivalent) on `GET /dashboard` while
preserving existing GET semantics (GET never advances rungs) and
zero-hydration locks on Today.

**Future exclusions:** index migrations; Cache-Control; frontend assets /
JS/CSS bundling; T10 caches / entitlement memoization; unrelated Calendar
modifications (Calendar shares a linear follow-up but is out of S2-1
unless a shared helper forces it).

S2-1 is **not implemented** in T25.
