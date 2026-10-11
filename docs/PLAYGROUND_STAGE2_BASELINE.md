# Playground Stage 2 baseline

Local Stage 2 baseline measurement at HEAD
`bbea109adfa66ac8a95ac773ed2039eb1d4a9039`, captured by the T23 operator run
(stamp `20261009T224132`) on this Cloud Agent VM. **Not a production SLA.**
Not a capacity certificate. Not Railway. Not a p95 budget.

This document is the durable human record of that run. Committed tables here
are normative for readers if the external T23 JSON later vanishes. Machine
JSON and EXPLAIN TEXT under `/opt/cursor/artifacts/t23/` are provenance only
and are not in Git.

---

## 1. Purpose and baseline disclaimer

Stage 2 T24 records what the frozen T13–T21 harnesses actually measured at
T22’s closed HEAD. T23 was run-only: it produced artifacts, not a commit.
T24 transcribes those artifacts. It does not rerun the operator, tune SQL,
add cache headers, rewrite Today, or close Stage 2.

Every timing table in this file is a **baseline measurement on this Cloud
Agent VM, not a production SLA.** Another machine, another dataset, or a
networked browser will differ. In-process ASGI `TestClient` is not a browser
and is not Lighthouse.

Identifier: execution T24 = original T24 = baseline documentation. Not
UI-redesign T24. Tracker ticks, `PLAYGROUND.md` status, and the S2-0 report
belong to T25 and are not decided here.

---

## 2. How to read this document

| Kind | Meaning |
|---|---|
| **Measurement** | A number copied from schema-valid T23 JSON or from T23 PostgreSQL EXPLAIN TEXT. Displayed to three decimal places (JSON remains the source). |
| **Observation** | A qualitative fact already present in those measurements. Not a fix. Not a ranking. |
| **Correctness lock** | A pytest assertion from T16, T17, or T22. It is not a latency percentile. |
| **Unavailable** | The frozen CLI cannot produce the cell. Not skipped, not filled from SQLite, not replaced by EXPLAIN. |
| **Future work** | T25 and later. This document does not recommend an S2-1 change. |

Source hierarchy used while writing:

1. Schema-valid T23 JSON and the nine T23 PostgreSQL EXPLAIN TEXT files.
2. Accepted `/opt/cursor/artifacts/stage2_T23_report.md`.
3. Historical committed T15 EXPLAIN files, labelled older (SHA `b3baa6c`).

If JSON and a plan-transcribed figure had disagreed, JSON would win. They
did not: three-decimal display is rounding only. T23 was not rerun.

SQLite timings are never labelled PostgreSQL.

---

## 3. SQLite / PostgreSQL coverage boundaries

PostgreSQL EXPLAIN (ANALYZE, BUFFERS) on a disposable database is complete
for query-plan characterization. It cannot substitute for PostgreSQL HTTP
latency or PostgreSQL concurrent GET measurements, which the frozen harness
cannot produce. Original full PostgreSQL performance coverage is incomplete.

| Coverage item | Status |
|---|---|
| Authorized T23 operator matrix | Complete |
| PG EXPLAIN | Complete |
| PG HTTP percentiles | Unavailable |
| PG concurrent GET | Unavailable |
| Original full PG perf coverage | Incomplete |

| Measurement class | What exists | Label in this document |
|---|---|---|
| Sequential HTTP percentiles | T13 six SQLite scenarios, warmup 5 / N 50 | SQLite in-process ASGI baseline |
| BNSS cold / warm HTTP | T14 SQLite, 50 per class per route | SQLite cold and warm, kept separate |
| PostgreSQL EXPLAIN | T23 nine ANALYZE/BUFFERS plans on a disposable DB; historical T15 TEXT in Git | Plan shape on disposable PostgreSQL |
| Concurrent GET | T18 SQLite C=1/5/10/25 × 5 batches | ASGI in-flight overlap on SQLite |
| Mutations / webhooks | T19 SQLite, 5 waves, N=10 / M=10 | Correctness plus wall times on this VM |
| PostgreSQL sequential HTTP | Frozen T13 refuses `postgresql://` | **Unavailable** |
| PostgreSQL concurrency | Frozen T18–T21 abort (messages name T23) | **Unavailable** |

Two conclusions stay visible:

- Authorized operator matrix: complete.
- Original full PostgreSQL performance coverage: incomplete.

---

## 4. Environment and measurement config

Baseline measurement on this Cloud Agent VM, not a production SLA.

| Item | Value |
|---|---|
| Host | Cloud Agent VM; in-process ASGI; not Railway; not production |
| OS | Linux `cursor` 6.12.94+ x86_64 |
| Python | 3.12.3 |
| SQLite | 3.45.1 |
| PostgreSQL | 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), Unix peer |
| `--app-env` | `test` on every CLI invocation |
| `DATABASE_URL` | unset in the process environment; never consumed |
| Git HEAD | `bbea109adfa66ac8a95ac773ed2039eb1d4a9039` (T22 closed; T23 made no commit) |
| Alembic | `20260927_0027` |
| Clock | harness `PLAYGROUND_TEST_NOW` 2026-09-16 12:00 UTC |
| Operator stamp | `20261009T224132` |
| `--quick` | not used |

| Cell | Fixture / size | Warmup | Measured | Backend |
|---|---|---|---|---|
| T13 plus-10 | Plus, 10 roster laws, `GET /playground` | 5 discarded | 50 | sqlite |
| T13 pro-30 | Pro, 30 roster laws, **home-only** `GET /playground` | 5 discarded | 50 | sqlite |
| T13 due-heavy | due-heavy `GET /dashboard` | 5 discarded | 50 | sqlite |
| T13 learned-heavy | learned-heavy `GET /playground` | 5 discarded | 50 | sqlite |
| T13 source-review | NDPS source-review GET | 5 discarded | 50 | sqlite |
| T13 law-workspace | BNSS workspace GET | 5 discarded | 50 | sqlite |
| T14 | BNSS `bnss_runtime_v1.json`, **1 395 157 bytes**, largest eligible | cold 0; warm 5 discarded hits | 50 cold + 50 warm × 3 routes | sqlite |
| T15 / T23 EXPLAIN | pro-30+source-review on new PG; roster 30, selection 520, progress 520 | n/a | 9 ANALYZE | postgresql |
| T18 | warm home; warm BNSS workspace | 5 discarded | C=1,5,10,25 × **5 batches** | sqlite |
| T19 mutations | six cells | n/a | 5 waves × C=1 and C=2 | sqlite |
| T19 webhooks | FakeProvider | n/a | N=10, M=10, 5 script waves | sqlite |
| T20 | four pages | 0 | 1 GET each; gzip-9 not served | sqlite |
| T21 | one fresh interpreter child | 0 | import + `create_app` only | sqlite |

Schemas (read-only; not edited by T24):

- `docs/performance/playground-performance-baseline.schema.json`
- `docs/performance/playground-bnss-cold-warm.schema.json`
- `docs/performance/explain-pro-30.schema.json`
- `docs/performance/playground-concurrency.schema.json`
- `docs/performance/playground-mutations.schema.json`
- `docs/performance/playground-webhooks.schema.json`
- `docs/performance/playground-page-weight.schema.json`
- `docs/performance/playground-cold-start.schema.json`

There is no `docs/performance/README.md`. Human narrative lives in this file.

---

## 5. Sequential HTTP — SQLite (T13)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite sequential HTTP. Not PostgreSQL.**

Six schema-valid JSON files, warmup 5 discarded, 50 measured GETs, HTTP
`200` × 50, `database_backend=sqlite`, `--app-env test`. Pro-30 is home-only
(`path_group=/playground`). Source:
`/opt/cursor/artifacts/t23/sqlite/playground-performance-baseline-{scenario}.json`.

| Scenario | Route | Warmup | N | HTTP | p50 ms | p95 ms | max ms | round trips p50 | db_reads p50 |
|---|---|---|---|---|---|---|---|---|---|
| plus-10 | `/playground` | 5 | 50 | 200×50 | 6.627 | 11.574 | 35.693 | 12 | 10 |
| pro-30 | `/playground` | 5 | 50 | 200×50 | 10.388 | 12.939 | 40.268 | 12 | 10 |
| due-heavy | `/dashboard` | 5 | 50 | 200×50 | 14.697 | 15.934 | 42.845 | 129 | 129 |
| learned-heavy | `/playground` | 5 | 50 | 200×50 | 8.886 | 11.432 | 38.827 | 12 | 10 |
| source-review | `/playground/laws/{law_id}/source-review` | 5 | 50 | 200×50 | 120.960 | 180.284 | 199.591 | 51 | 9 |
| law-workspace | `/playground/laws/{law_id}` | 5 | 50 | 200×50 | 27.908 | 36.693 | 46.067 | 12 | 11 |

`playground_repo_round_trips` and `playground_db_reads` are p50 of the
iteration counters (constant across the 50 samples in each of these files).
Due-heavy’s 129 vs Plus home’s 12 is recorded in §14 as an observation, not
a T13 defect.

PostgreSQL sequential HTTP percentiles for these routes: **unavailable**
(§8). Do not read this table as a Postgres baseline.

---

## 6. BNSS cold vs warm — SQLite (T14)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite. Cold and warm are separate distributions. Not PostgreSQL.**

Largest eligible Act: slug `bnss`, file `bnss_runtime_v1.json`,
**1 395 157 bytes**, `confirmed_largest_eligible=true`. Protocol
`bnss-cold-warm`. Source:
`/opt/cursor/artifacts/t23/sqlite/playground-bnss-cold-warm.json`.

Do not average cold and warm. Do not present a single “BNSS p95”.

### Cold (warmup 0, cache miss)

Fifty measured GETs per route. `cache_class=miss`. `bare_act_load` is
present in `stages_present`. HTTP `200` × 50.

| Route | Path | N | HTTP | p50 ms | p95 ms |
|---|---|---|---|---|---|
| playground_learn | `/playground/laws/bnss/sections/1/learn/read` | 50 | 200×50 | 15.434 | 23.551 |
| playground_workspace | `/playground/laws/bnss` | 50 | 200×50 | 37.389 | 53.297 |
| public_bare_act | `/laws/bnss` | 50 | 200×50 | 12.800 | 44.384 |

### Warm (5 discarded cache-hit warmups, then 50 hits)

`cache_class=hit`. Warm `stages_present` **omits** `bare_act_load`. HTTP
`200` × 50.

| Route | Path | N | HTTP | p50 ms | p95 ms |
|---|---|---|---|---|---|
| playground_learn | `/playground/laws/bnss/sections/1/learn/read` | 50 | 200×50 | 4.514 | 7.405 |
| playground_workspace | `/playground/laws/bnss` | 50 | 200×50 | 29.803 | 33.158 |
| public_bare_act | `/laws/bnss` | 50 | 200×50 | 4.176 | 4.921 |

---

## 7. PostgreSQL EXPLAIN — T23 nine-row table

Baseline measurement on this Cloud Agent VM, not a production SLA.
Label from JSON: `disposable PostgreSQL baseline, not an SLA`.

This nine-row table is the **T23 rerun** at HEAD `bbea109`. Historical T15
committed dumps are cited after the table and are older.

| Item | Value |
|---|---|
| Disposable DB | `s2_0_explain_t23_20261009t224132` (Unix peer; left intact; not in Git) |
| Host class | `unix-peer` |
| Fixture | `pro-30+source-review` |
| Alembic on that DB | `20260927_0027` |
| Postgres | 16.15 |
| Dataset | roster 30, overlay 30, selection 520, progress 520, mode_progress 3120, revision_mode 960, source_change 24, devices 1, current_subscription 1 |
| Queries | 9 (`EXPLAIN (ANALYZE, BUFFERS)`) |
| Summary JSON | `/opt/cursor/artifacts/t23/explain/explain-pro-30-t23-summary.json` |
| Actual TEXT | `/opt/cursor/artifacts/t23/explain/explain-pro-30-{label}.txt` |
| Frozen JSON `plan_file` | `docs/performance/explain-pro-30-{label}.txt` (**does not match** the T23 TEXT directory) |

The frozen harness always records `plan_file` under `docs/performance/` even
when `--json` wrote TEXT next to the summary under `/opt/cursor/artifacts/t23/explain/`.
T24 documents both paths. It does not edit the JSON and does not overwrite
historical T15 files.

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

All nine T23 plans include a sequential scan and empty `index_names`. That is
a plan-shape observation (§14), not an index task.

EXPLAIN cannot substitute for PostgreSQL HTTP latency or PostgreSQL
concurrent GET (§3, §8).

### Historical T15 (older; not the nine-row table above)

Committed at T15 SHA `b3baa6c`, still in Git, byte-stable versus the T23
pre-run hash ledger (`/opt/cursor/artifacts/t23/hashes/before.txt`, drift
NONE):

- `docs/performance/explain-pro-30-summary.json`
- `docs/performance/explain-pro-30-{label}.txt` (nine files)

Those historical plans also showed Seq Scan and empty `index_names` at
Pro-30 volume. They are **older dumps**, not the T23 execution times in the
table. Fixture-user UUID filters appear in historical TEXT the same way they
appear in T23 TEXT; they are not reprinted here.

---

## 8. Unavailable PostgreSQL HTTP and concurrency

These rows are **unavailable**, not skipped, not completed, and not filled
from SQLite or from EXPLAIN.

| Measurement | Original spec | Frozen CLI | Baseline status |
|---|---|---|---|
| Sequential HTTP percentiles labeled Postgres | WS6 required PostgreSQL for numbers labeled “Postgres” | T13 `assert_fresh_sqlite` | **Unavailable** |
| Concurrent GET on PostgreSQL | WS10 pool note | T18 abort (message names T23) | **Unavailable** |
| T19 / T20 / T21 on PostgreSQL | T21 SQLite-only; T18–T21 abort names T23 | abort | **Unavailable** (SQLite cells themselves are complete) |

The tables in §5, §6, §9, §10, §11, and §12 are SQLite. The table in §7 is
PostgreSQL EXPLAIN only.

---

## 9. Concurrency — SQLite ASGI in-flight (T18)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite. Not PostgreSQL concurrent GET.**

`asgi_in_flight_is_not_parallel_sql` is true. Overlapping in-process ASGI
GETs are not evidence of parallel SQLite execution.

Frozen field `asgi_in_flight_is_not_parallel_sql=true` on both files.
`aborted=false`. `batches_requested=5`. Levels `[1, 5, 10, 25]`. C=25 is
present. `incomplete_batches=0` at every level. `samples_error=0`. Warmup
discarded 5. Sources:

- `/opt/cursor/artifacts/t23/sqlite/playground-concurrency-plus-10.json`
- `/opt/cursor/artifacts/t23/sqlite/playground-concurrency-law-workspace.json`

PostgreSQL concurrent GET: **unavailable** (§8).

### plus-10 — warm `GET /playground`

Home warmup (`kind=home`; bare-act cache absent on this route). HTTP 200
for every sample.

| C | Batches | samples_ok | p95 total_ms | throughput_rps p50 |
|---|---|---|---|---|
| 1 | 5 | 5 | 35.504 | 111.686 |
| 5 | 5 | 25 | 39.824 | 145.614 |
| 10 | 5 | 50 | 72.729 | 133.895 |
| 25 | 5 | 125 | 184.764 | 133.200 |

### law-workspace — warm `GET /playground/laws/bnss`

Warm cache proof: `cache_class=hit`, `bare_act_load_absent=true`. HTTP 200
for every sample.

| C | Batches | samples_ok | p95 total_ms | throughput_rps p50 |
|---|---|---|---|---|
| 1 | 5 | 5 | 31.765 | 34.479 |
| 5 | 5 | 25 | 143.039 | 35.251 |
| 10 | 5 | 50 | 323.759 | 34.846 |
| 25 | 5 | 125 | 744.495 | 33.976 |

---

## 10. Mutations and webhooks — SQLite (T19)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite. Not production load capacity.** No sentence of the form “supports
N concurrent subscribers” applies.

`live_razorpay=false`. FakeProvider. No Razorpay sockets. No production or
Railway traffic.

### Mutations

Source: `/opt/cursor/artifacts/t23/sqlite/playground-mutations.json`.

`aborted=false`, `waves_requested=5`, `concurrency_levels_requested=[1, 2]`,
`http_smokes=false`, `m5b_excluded=true`, `busy_timeout_ms=8000`,
`wave_timeout_s=10`, `database_backend=sqlite`. Frozen cell caveat: do not
compare absolute latency across materially different initial states. This
table is correctness counts, not a latency ranking.

| Cell | C=1 waves / correct / incomplete | C=2 waves / correct / incomplete |
|---|---|---|
| roster-cap | 5 / 5 / 0 | 5 / 5 / 0 |
| roster-same-law | 5 / 5 / 0 | 5 / 5 / 0 |
| device-cap | 5 / 5 / 0 | 5 / 5 / 0 |
| device-idem | 5 / 5 / 0 | 5 / 5 / 0 |
| progress-learned | 5 / 5 / 0 | 5 / 5 / 0 |
| revision-sixth | 5 / 5 / 0 | 5 / 5 / 0 |

Six cells × two concurrency levels × five waves: all `correct_waves=5`,
`incomplete_waves=0`.

### Webhooks

Source: `/opt/cursor/artifacts/t23/sqlite/playground-webhooks.json`.

`aborted=false`, `n=10`, `m=10`, `waves_requested=5`,
`live_razorpay=false`, `database_backend=sqlite`.

| Proof | Result |
|---|---|
| Sequential first | owned=true, HTTP 200, `processed` |
| Sequential replay | owned=false, HTTP 200, `processed`; deliveries=2, duplicate=1, errors=0 |
| Concurrent duplicate, 5 waves | each wave deliveries=2, duplicate=1, owned=1, errors=0, incomplete=false |
| Unique N=10 | deliveries=10, owned=10, duplicate=0 |
| Replay M=10 | deliveries=10, duplicate=10, owned=0, extra_provider_fetches=0 |
| Out-of-order pair | `subscription.pending` then `subscription.charged`; deliveries=2, owned=2, duplicate=0, errors=0 |
| Event rows after script wave | 12 (= N unique + the pending/charged pair) |
| Script waves | 5 |

---

## 11. Page weight — four-page inventory (T20)

Baseline measurement on this Cloud Agent VM, not a production SLA.
**SQLite in-process TestClient. Not a served gzip encoding. Not Lighthouse.**

Source: `/opt/cursor/artifacts/t23/sqlite/playground-page-weight.json`.

`complete=true`, `aborted=false`, `git_head=bbea109adfa66ac8a95ac773ed2039eb1d4a9039`,
`alembic_head=20260927_0027`, `measurement_mode=in_process_testclient_disk_gzip`,
`gzip_compresslevel=9`, **`gzip_served=false`**, `compression_served=identity`,
`lighthouse=false`, `browser_network=false`, `external_network=false`.
Four pages, each `complete=true`, HTTP 200, `http_failures=[]`.

Gzip-equivalent bytes are `gzip.compress` at compresslevel 9 of the
measured bytes. That encoding was **not served**.

| Page | Path | HTML source | HTML gzip-9 | HTML+CSS+JS source | HTML+CSS+JS gzip-9 |
|---|---|---|---|---|---|
| plus_home | `/playground` | 34 019 | 6 634 | 858 928 | 163 716 |
| bnss_workspace | `/playground/laws/bnss` | 60 280 | 8 474 | 885 189 | 165 556 |
| bnss_learn | `/playground/laws/bnss/sections/1/learn/read` | 31 717 | 7 017 | 856 626 | 164 099 |
| bnss_public | `/laws/bnss` | 319 144 | 22 999 | 1 144 053 | 180 081 |

Static `cache_policy`: **16 / 16** rows have `cache_control=null`. All 16
have an `ETag` and a `Last-Modified`. Example (first-party CSS):
`/static/styles.css?v=main85`, ETag `"27918d3d507a0da2659f24b391aae4c5"`,
Last-Modified `Thu, 08 Oct 2026 03:41:34 GMT`. This is recorded in §14 as
an observation. T24 does not add Cache-Control.

Third-party font URLs were recorded and not fetched.

---

## 12. Cold start and zero-hydration (T21)

Baseline measurement on this Cloud Agent VM, not a production SLA.
Durations are report-only. No startup SLA.

Source: `/opt/cursor/artifacts/t23/sqlite/playground-cold-start.json`.

`complete=true`, `contract_passed=true`, `aborted=false`,
`database_backend=sqlite`, `measurement_mode=fresh_interpreter_subprocess`,
`first_request=null`, `child_returncode=0`,
`git_head=bbea109adfa66ac8a95ac773ed2039eb1d4a9039`. Spy on `get_bare_act`
and `_load_cached` installed before `web.app` import.

| Phase | duration_ms | get_bare_act | load_cached | hydrated_slugs |
|---|---|---|---|---|
| import | 428.694 | 0 | 0 | [] |
| create_app | 359.239 | 0 | 0 | [] |

Zero Act hydration on import and on `create_app`. No PostgreSQL child (frozen
T21 is SQLite-only).

---

## 13. Correctness locks (T16, T17, T22) and T23 pytest evidence

These are **regression locks**, not operator percentiles. T13–T21 numbers
above do not replace them. T24 did not rerun the 1/10/30 loops or add
duration asserts.

| Lock | What it guards | Relation to measurements |
|---|---|---|
| T16 | Home summaries and source-review reads stay batched as roster N grows (1/10/30). Today and Calendar keep one due/schedule list call; `list_revision_mode_progress` follow-up is linear in due facts (`[4, 40, 120]` in that fixture). Device lookups are route-specific (home 2, Today 1, Calendar 1), not a global “one lookup” lock. Seq Scan in EXPLAIN is not treated as N+1 without Nested Loop inner correlation. | Operator round-trip **counts** in §5 are measurements of one fixture at one N; T16 locks **shape vs N**, not p95. |
| T17 | Repeated zero Act hydration on active Plus routes, unauthenticated `/sitemap.xml`, and halted-home (plus roster denial). | T21 §12 measures import/`create_app` hydration in a fresh child. T17 locks request-path hydration across repeats. |
| T22 | Playground breakdown vocabulary; Stage 1 freeze text and Alembic head `20260927_0027`; Plus route matrix; guest/free/halted/device-limit/roster-full identity; request-local isolation; privacy of query strings in breakdown logs. | Observability contract. Not a timing SLA. |

T23 focused pytest (`tests/test_playground_stage2_observability.py`,
benchmarking, M11, migrations, request-breakdown): **507 passed**
(253.94 s, complete log).

T23 full suite: full non-integration pytest exited 0; final summary log truncated

Additional context that does not replace that sentence: process exit 0 in
2903.851 s; surviving log prefix had 0 failures and 0 errors. Do not treat
any other suite total as a T23 result.

---

## 14. Characterization-only findings

Three observations from the T23 artifacts. **Not T24 changes. Not S2-1
recommendations. Not optimization ranking.** T25 owns any single next-batch
recommendation.

1. **Due-heavy Today projection.** `GET /dashboard` recorded **129**
   `playground_repo_round_trips` versus **12** for Plus home (`GET /playground`)
   in the T13 SQLite sequential run. The same 129 vs 12 shape was already
   visible at T22. This is existing Stage 1 Today behavior. T24 does not
   rewrite the dashboard.

2. **Static cache headers.** First-party static responses in the T20
   inventory have **no `Cache-Control`**. All 16 `cache_policy` rows are
   `cache_control=null`. **ETag and Last-Modified are present.** T24 does
   not add headers and does not tick a caching-headers tracker box.

3. **Pro-30 EXPLAIN sequential scans.** All nine T23 plans (and the older
   committed T15 plans) show sequential scans with empty `index_names`.
   Plan-shape observation on a disposable Pro-30 dataset. T24 does not add
   an index migration and does not tick “Tune indexes”.

---

## 15. Artifact provenance and reproducibility limits

| Kind | Location | In Git? |
|---|---|---|
| This human baseline | `docs/PLAYGROUND_STAGE2_BASELINE.md` | yes (this file) |
| T13–T21 / T23 JSON | `/opt/cursor/artifacts/t23/sqlite/` | no |
| T23 EXPLAIN TEXT + summary | `/opt/cursor/artifacts/t23/explain/` | no |
| T23 EXPLAIN JSON `plan_file` metadata | `docs/performance/explain-pro-30-{label}.txt` | metadata only; T23 bytes are not there |
| Historical T15 EXPLAIN | `docs/performance/explain-pro-30-*` | yes (older; SHA `b3baa6c`) |
| JSON schemas | `docs/performance/*.schema.json` | yes (read-only here) |
| T23 env | `/opt/cursor/artifacts/t23/env.txt` | no |
| T23 report | `/opt/cursor/artifacts/stage2_T23_report.md` | no |
| SQLite files | `/tmp/t23-20261009T224132-*.db` | no (left on the VM) |
| Disposable PG DB | `s2_0_explain_t23_20261009t224132` | no (left intact) |
| Prior gitignored operator JSON | `artifacts/playground-*.json` | gitignored; **not** the T23 timing source |

Further limits:

- HEAD `bbea109`; T23 made no commit. This documentation commit is T24 only.
- Hardware and runtime are this Cloud Agent image. Re-running elsewhere will
  not reproduce milliseconds.
- Client is in-process ASGI, not a network browser, not Lighthouse.
- `asgi_in_flight_is_not_parallel_sql`.
- No Railway, production, or live Razorpay.
- Displayed milliseconds are three-decimal rounding of JSON floats. JSON
  wins if a later reader needs more precision.
- External `/opt/cursor/artifacts/t23/` may not survive the VM. The tables
  in this file are the durable human record of this run.

Privacy: this document does not print `BENCH_EMAIL`, Bearer tokens, session
or device cookie values, webhook secrets, or the fixture user UUID. T23
EXPLAIN TEXT filters include that frozen fixture UUID in the same way
historical T15 TEXT does; it is not reproduced here.

---

## 16. Scope exclusions and T25 boundary

T24 created this file and nothing else. It did not:

- edit `docs/performance/*`, `docs/PLAYGROUND.md`, or
  `docs/PLAYGROUND_DELIVERY_TRACKER.md`
- create `docs/PLAYGROUND_STAGE2_S2_0_REPORT.md`
- change source, tests, schemas, or migrations
- commit T23 JSON or EXPLAIN TEXT
- rerun T23
- assert an SLA
- recommend Cache-Control, indexes, or a Today rewrite

Left to **T25** (unauthorized at the time this baseline was written):

- tracker Stage 2 header and proven-only ticks
- explicit non-ticks
- `docs/PLAYGROUND_STAGE2_S2_0_REPORT.md`
- exactly one S2-1 recommendation chosen from evidence
- any `PLAYGROUND.md` live-index status flip
- any claim that Stage 2 measurement closes optimization work

This baseline does not decide those items.
