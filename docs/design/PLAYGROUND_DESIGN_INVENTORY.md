# Playground design inventory

Programme inventory for `docs/PLAYGROUND_UI_REDESIGN_PLAN.md` §16.1–§16.2 and §21.

**Not a Stage 1 document.** Stage 1 remains frozen at **DONE — 100.0 / 100**.

```text
Inventory SHA: 5035ce2e9d6e2ac14a01367d25e41dc12565257f  (after main merge)
Pre-merge:     a5edca57d06f2a516fb2111be6e2e6f5db507f67
Branch:        cursor/playground-220d
main:          0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942
Alembic head:  20260927_0027
```

---

## 1. Authoritative prototype files

The programme names two Claude Design exports (updated 2026-09-28):

| Expected path | Viewport | Expected size | Status on this SHA |
|---|---|---|---|
| `docs/design/Recall the C - Playground Desktop.dc.html` | 1280px | 2,902 lines | **ABSENT** |
| `docs/design/Recall the C - Playground.dc.html` | 390×844 | 1,829 lines | **ABSENT** |

They are not in this repository, not in this VM, and not under `/opt/cursor` or `/tmp`. The plan’s source note (`~/Downloads/Playground-Mobile.zip` / `Playground-Desktop.zip`) is an author-machine path.

**§16.1 prototype-screen count from the named files: 0.**

Until those files are committed (T36 / R7, also required before U1), Layer 1 cannot be inventoried screen-by-screen against the prototypes. Production surfaces below are still classified A–E so no active page remains unclassified.

### 1.1 File present in `docs/design/` that is **not** the programme source

| File | Lines | Role |
|---|---|---|
| `Playground.dc.html` | 1,314 | Stage 1 M6 state demonstrator. Seven screens. **Do not treat as the 2026-09-28 redesign prototype.** |
| `PLAYGROUND-HANDOFF.md` | — | M6 handoff. Eligibility still NDPS/BNS/BNSS. Guest `/playground` 303. |
| `Constitution Memorizer App.dc.html` | 639 | Constitution product prototype, not Playground redesign. |
| `Constitution Memorizer.dc.html` | 180 | Constitution mobile/card anatomy. |
| `playground-current-ui/` | 20 PNGs | As-is production screenshots from the local walk. Useful as current-UI reference, not as the target design. |

Non-authoritative screens in `Playground.dc.html` (for contrast only):

| Screen | `data-screen-label` | Production equivalent |
|---|---|---|
| Home | Home | `GET /playground` → `playground.html` |
| Roster | Roster | `GET /playground/roster` |
| Rollover | Rollover | `GET /playground/roster/next` |
| Law workspace | Law workspace | `GET /playground/laws/{id}` |
| Law states | Law states | `/laws` + Bare Act CTAs |
| Add confirm | (sheet) | `GET /playground/laws/{id}/add` |
| Remove confirm | (sheet) | `GET /playground/roster/{id}/remove` |

Those seven screens do **not** include Learn modes, clause picker, Today Playground nodes, Calendar week, speech, completion, Profile subscription card, or Settings reminders. The 2026-09-28 prototypes are required for those.

---

## 2. Production template inventory (80 active files)

Count matched the plan’s first-pass “81 templates” at `c76ba92`. T7 deleted obsolete `playground_cloze.html`, leaving **80**.

### 2.1 Classification totals

| Class | Meaning | Count |
|---|---|---|
| A | Direct prototype match (or A, verify-only) | 20 |
| B | Another design family; restyle non-conforming elements | 45 |
| C | Missing from prototype; designed extension | 4 templates + listed states |
| D | Explicitly out of scope (§21.4) | 11 |
| E | Obsolete; removed after T7 proof | **0** (`playground_cloze.html` deleted) |
| **Unclassified templates** | | **0** |
| **Active templates** | | **80** (was 81 before T7) |

### 2.2 Class A — Playground / shell / matched product surfaces (18)

| Template | Route / surface | Batch | Tracker IDs |
|---|---|---|---|
| `base.html` | App shell, nav, assets | R0, R1 | D18–D21, D24–D25, T1, T33 |
| `bare_act.html` | `GET /laws/{slug}` Bare Act head + CTA | R0, R3 | D26–D30, T1, T4 |
| `playground_base.html` | Playground shell | R1 | D18–D25, T39 |
| `playground.html` | `GET /playground` | R3 | D51–D63, D125–D127 |
| `playground_add.html` | `GET /playground/laws/{id}/add` | R3 | D31–D40 |
| `playground_select.html` | `GET /playground/laws/{id}/sections` | R2 | D41–D50, D128–D129 |
| `playground_law.html` | `GET /playground/laws/{id}` | R4 | D64–D74, D132 |
| `playground_learn.html` | `GET /playground/laws/{id}/sections/{n}/learn/{mode}` | R4 | D75–D87, D139, D141 |
| `playground_remove.html` | `GET /playground/roster/{id}/remove` | R5 | D95 |
| `playground_roster.html` | `GET /playground/roster` | R5 | D93–D94, D96 |
| `playground_roster_next.html` | `GET /playground/roster/next` | R5 | D97–D100, D130 |
| `playground_gate.html` | Playground entitlement / device gates | R3 | D101–D106, D131 |
| `subscription_manage.html` | `GET /billing/subscriptions` | R3, R5 | D104–D105, T21 |
| `dashboard.html` | `GET /dashboard` (Today) | R6 | D115–D119 |
| `calendar.html` | `GET /calendar` | R6 | D120–D124 |
| `profile.html` | `GET /profile` | R5 | D107–D110 |
| `settings.html` | `GET /settings` | R5 | D111–D114 |
| `partials/playground.html` | Public-law / catalogue CTA partial | R3 | D26–D28, T18 |

### 2.3 Class A, verify only (2)

| Template | Route | Notes |
|---|---|---|
| `browse_index.html` | `GET /browse` | Desktop prototype draws Laws/Browse to mirror production. Close via V23. |
| `laws.html` | `GET /laws` | Same. **Defect (T4):** `playground_states.get(law.id)` while states are keyed by Bare Act slug. |

### 2.4 Class B — other design family (45)

Restyle every non-conforming element against U1 tokens/components (V23). Closest-to-Playground first: `bare_act_section.html`, `bare_act_schedule.html`, `guest_gate.html`, `pricing.html`, `purchase_*`, `learn.html`.

| Template | Typical route |
|---|---|
| `browse_part.html` | `GET /browse/part/{slug}` |
| `browse_article.html` | `GET /browse/article/{n}` |
| `learn.html` | `GET /learn/{unit_id}` |
| `choose.html` | `GET /learn/{clause_id}/choose` |
| `incomplete.html` | Learn incomplete |
| `search.html` | `GET /search` |
| `tables.html` | `GET /tables` |
| `memory.html` | `GET /memory` |
| `memory_detail.html` | `GET /memory/{id}` |
| `law_detail.html` | `GET /laws/{id}` mapped/key-provision laws |
| `bare_act_section.html` | `GET /laws/{id}/section/{number}` |
| `bare_act_schedule.html` | `GET /laws/{id}/schedule/{slug}` |
| `progress.html` | `GET /progress` |
| `progress_mastered.html` | `GET /progress/mastered` |
| `guest_gate.html` | Guest Constitution gate |
| `welcome.html` | `GET /welcome` |
| `onboarding_plan.html` | `GET /onboarding/plan` |
| `plan_my_day.html` | `GET /learning/plan-my-day` |
| `home.html` | Signed-in `/` |
| `pricing.html` | `GET /pricing` (404 unless `PRICING_ENABLED`) |
| `purchase_confirm.html` | `GET /subscribe/confirm` (frozen) |
| `purchase_result.html` | `GET /subscribe/result` (frozen) |
| `login.html` | `GET /login` |
| `signed_out.html` | `GET /signed-out` |
| `session_expired.html` | `GET /session-expired` |
| `auth_transition.html` | `GET /auth/transition` |
| `auth_callback.html` | OAuth callback HTML |
| `landing.html` | Guest `/` |
| `landing_light.html` | Light landing variant |
| `legal/base.html` | Legal shell |
| `legal/terms.html` | `GET /terms` |
| `legal/privacy.html` | `GET /privacy` |
| `legal/grievance.html` | `GET /grievance` |
| `legal/_macros.html` | Legal macros |
| `visual_explainer.html` | Explainer |
| `visual_explainer_trigger.html` | Explainer trigger |
| `_completion_banner.html` | Constitution Learn partial |
| `_locked_mode.html` | Constitution Learn partial |
| `partials/auth_shell.html` | Auth chrome |
| `partials/bare_act_footnotes.html` | Act footnotes |
| `partials/bare_act_macros.html` | Act macros |
| `partials/guest_modal.html` | Guest modal |
| `partials/mode_help_modal.html` | Mode help |
| `partials/report_dialog.html` | Report issue |
| `partials/revision_exit_modal.html` | Revision exit |

### 2.5 Class C — designed extension required (4 templates + states)

Each already has a Layer 1 `D` row. No new denominator items added in this audit.

| Surface | Route | Closest design | Tracker |
|---|---|---|---|
| Source review list | `GET /playground/laws/{id}/source-review` | Law workspace / “Law updated” | D133 |
| Source review section | `GET /playground/laws/{id}/source-review/sections/{n}` | Learn / verbatim panel | D134 |
| Devices | `GET /profile/security/devices` | Profile account list | D137 |
| Subscription checkout | `GET /billing/subscriptions/checkout` | Plans stage | D138 |
| Gate reasons with no drawn state | `playground_gate.html` variants | Gate family | D102 |
| Learn failure states | `playground_learn.html` | Learn chrome | D139 |
| Service / HTML errors, kill-switch 404 | FastAPI defaults + feature gate | Gate / empty | D140, D142 |
| Speech unavailable / offline | Learn Letters/Recite | Learn | D141 |
| Missing / omitted provision | source review | D135 |
| Mastered + Law updated | workspace / review | D136 |

### 2.6 Class D — excluded (§21.4) (11)

| Template | Route |
|---|---|
| `admin/base.html` | Admin shell |
| `admin/index.html` | `GET /admin` |
| `admin/users.html` | `GET /admin/users` |
| `admin/user_detail.html` | `GET /admin/users/{id}` (Playground diagnostics stay behaviour-only) |
| `admin/admins.html` | `GET /admin/admins` |
| `admin/access.html` | `GET /admin/access` |
| `admin/inbox.html` | Contact/inbox |
| `admin/content.html` | `GET /admin/content` |
| `admin/preview.html` | `GET /admin/preview` |
| `admin/audit.html` | `GET /admin/audit` |
| `admin/_audit_table.html` | Audit partial |

Also excluded by §21.4 (not templates): Calendar → Study archive (lives on another branch); Settings control restyle (intentional deviation D113); clause picking inside the reader.

### 2.7 Class E — obsolete (0 remaining)

| Template | Proof | Tracker |
|---|---|---|
| `playground_cloze.html` | **Deleted.** `playground.js` no longer binds `[data-playground-cloze]`. HTTP Learn never called `complete_cloze`. | T7 DONE |

Repository `complete_cloze()` remains as a grandfathered test/helper API (`tests/test_playground.py`, M3/M5 fixtures).

---

## 3. Production HTML routes (active UI)

Class follows the template that renders the page.

### 3.1 Playground

| Method | Path | Template | Class |
|---|---|---|---|
| GET | `/playground` | `playground.html` or `playground_gate.html` | A |
| GET | `/playground/roster` | `playground_roster.html` | A |
| GET | `/playground/roster/next` | `playground_roster_next.html` | A |
| GET/POST | `/playground/laws/{law_id}/add` | `playground_add.html` | A |
| GET/POST | `/playground/roster/{law_id}/remove` | `playground_remove.html` | A |
| GET | `/playground/laws/{law_id}` | `playground_law.html` | A |
| GET/POST | `/playground/laws/{law_id}/sections` | `playground_select.html` | A |
| GET | `/playground/laws/{law_id}/source-review` | `playground_source_review.html` | C |
| GET | `/playground/laws/{law_id}/source-review/sections/{number}` | `playground_source_review_section.html` | C |
| POST | `/playground/laws/{law_id}/source-review/sections/{number}/reviewed` | redirect | C (same family) |
| GET | `/playground/laws/{law_id}/sections/{number}/learn/{mode}` | `playground_learn.html` | A |
| POST | `.../learn/{mode}/start` | JSON/redirect | A (no extra page) |
| POST | `.../learn/{mode}/complete` | JSON/redirect | A |
| POST | `.../learn/test/quiz` | JSON | A |

Guest `GET /playground*` today **303s to login** (`access.py:_deny_open`). Delta H (T20) will render `playground_gate.html` instead.

Paused/expired `GET /playground` today renders **EntitlementGate**, not a read-only home. Delta G (T19).

### 3.2 Public laws / Constitution / account (selected)

| Method | Path | Template | Class |
|---|---|---|---|
| GET | `/` | `landing.html` or `home.html` | B |
| GET | `/laws` | `laws.html` | A verify |
| GET | `/laws/{id}` | `bare_act.html` or `law_detail.html` | A / B |
| GET | `/laws/{id}/section/{number}` | `bare_act_section.html` | B |
| GET | `/laws/{id}/schedule/{slug}` | `bare_act_schedule.html` | B |
| GET | `/browse` | `browse_index.html` | A verify |
| GET | `/browse/part/{slug}` | `browse_part.html` | B |
| GET | `/browse/article/{n}` | `browse_article.html` | B |
| GET | `/learn` `/learn/{unit_id}` | `learn.html` | B |
| GET | `/dashboard` | `dashboard.html` | A |
| GET | `/calendar` | `calendar.html` | A |
| GET | `/calendar?view=week` | **does not exist** | A (T29 / D122) |
| GET | `/profile` | `profile.html` | A |
| GET | `/settings` | `settings.html` | A |
| GET | `/profile/security/devices` | `devices.html` | C |
| GET | `/billing/subscriptions` | `subscription_manage.html` | A |
| GET | `/billing/subscriptions/checkout` | `subscription_checkout.html` | C |
| GET | `/login` | `login.html` | B |
| GET | `/pricing` and `/subscribe*` | frozen 404 unless `PRICING_ENABLED` | B / D142 |

### 3.3 Admin (class D)

`GET/POST /admin*` — excluded. Regression still required (V18).

---

## 4. Non-page surfaces (no UI to redesign)

Recorded so they are not “unclassified”. Class: **no UI**.

| Surface | Notes |
|---|---|
| `POST /learn/{unit_id}/speech/transcribe` | Constitution-unit speech. Playground must not reuse this (T25). |
| `POST /api/billing/subscriptions/webhook/razorpay` | Webhook |
| `POST /api/billing/order` `/verify` | Legacy, `PRICING_ENABLED` |
| `GET /auth/google/start` `/auth/callback` | Redirect |
| `GET /calendar/google/connect` `/callback` | Redirect |
| `POST /calendar/google/disconnect` `/retry` `/preferences` | JSON/redirect |
| `GET /sitemap*.xml` `/robots.txt` | T6 noindex `/playground*` |
| `GET /sw.js` | Service worker |
| `GET /favicon.ico` `/apple-touch-icon*.png` | Icons (T36 dome-licence still open) |
| `GET /health` | Ops |
| `GET/POST /api/theme` `/api/text-size` `/api/report-issue` `/api/explainers/*` `/onboarding/state` | JSON |
| `POST /learn/{unit_id}/seen` `/quiz` `/done` `/again` `/skip` `/reset` | Constitution Learn mutations |
| Kill-switch 404 on `/playground*` | D142 |

---

## 5. Production states ↔ design coverage (§16.2)

Unchanged from the plan. Every listed production state already has D rows. No state left “undefined” in the tracker; visual proof still requires the missing prototypes.

| Production state | Covered by |
|---|---|
| Guest | D27, D35, D101, D110 |
| Free (signed in, no plan) | D27, D36, D102, D104, D108 |
| Active Plus / Pro / Max | D32, D33, D58, D104, D108 |
| Pending payment | D38, D62 |
| Paused / expired | D61, D103, D108 |
| Halted | D102, D103 |
| Cancel at period end | D62 |
| Upgrade / downgrade / resubscribed | D62, D100 |
| Device limited / revoked | D102, D137 |
| Replacement limited | D102 |
| Device config error | D102 |
| Roster full | D27, D37, D58 |
| Removed law | D57, D94 |
| Saved historical law | D57, D96 |
| Source updated | D55, D73, D133 |
| Missing / omitted provision | D135 |
| Mastered + Law updated | D136 |
| Not started / Learning / Learned / Due / Mastered | D44, D54, D72 |
| Overdue | D56, D123 |
| Empty (no laws, no sections) | D60, D74 |
| Learn failure | D139 |
| Service error | D140 |
| Speech unavailable / offline | D141 |

---

## 6. Current-branch eligibility vs programme (delta F)

On this SHA, eligible slugs are **`bns`, `bnss`, `ndps`, `uapa`, `pss`, `mtp`**. `uapa-1967` and `pota` are not eligible. `laws.html` looks up playground state by `law.full_act_ref or law.id`. Bare Act page keys by `bare.slug`. T4 is DONE. MTP picker is chapterless (`data-chapterless`); D42 chapter bands remain R2 (T5).

---

## 7. Nothing-missed classifications from this audit

| Finding | Class | Action |
|---|---|---|
| Named 2026-09-28 `.dc.html` files absent | **A** (T36) + **blocker** | Do not invent screens. Obtain files before U1. |
| `playground_cloze.html` unused in `src/` | **A** (T7) | **Removed.** `complete_cloze()` kept. |
| Auto-merged main files beyond the 5 conflicts | **A** (T1) | Review `admin/routes.py`, `progress/*`, sitemap, `mobile.css`, `styles.css`, `laws.html` during R0 merge. |
| D23 batch R2+R5 vs milestone U2 (R2+R3) | **A** (assignment unique) | Document; do not split denominator. U2 closeout must not forget R5 sticky footer. |
| Stage 2 label NOT STARTED vs PARKED | **A** | Redesign tracker uses PARKED. Do not edit Stage 1 tracker. |
| No new active template since `c76ba92` | — | Denominator stays **207**. |

**Unclassified active templates: none.**
