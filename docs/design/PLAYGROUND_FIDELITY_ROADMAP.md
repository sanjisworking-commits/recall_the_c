# Playground fidelity roadmap — milestone tracker

Status: M0 accepted as the **planning baseline** on 2026-10-18, with the
evidence limitations in §0.4. Design direction approved (not
implementation): five-tab navigation for guests with gates preserved;
NDPS listed as eight chapter entries (I, II, IIA, III, IV, V, VA, VI) from
the canonical Act data; a common data-driven Bare Act head preserving
About, Schedules and full chapter/section navigation; Today may be
visually restyled but keeps the accepted dashboard functions; Google-only
sign-in, gated guest Calendar, Plus/Pro/Max pricing, accepted account
controls and the parked Study archive stay unchanged.

Goal: bring the Playground UI on `cursor/playground-220d` to high fidelity
with the 18 October 2026 phone and desktop prototypes, delivered as
independently acceptable milestones. Source audit: M0 in
`docs/design/PROTOTYPE_COMPARISON_2026-10-18.md` (DV-1 … DV-19, §4.1
decisions). Nothing below is authorised for implementation until the owner
approves the milestone and its acceptance checklist.

## 0. Rules for every milestone

1. **Checklist first.** The milestone's acceptance checklist (this file,
   plus a per-milestone `docs/design/milestones/M<N>.md`) is written and
   approved before any code changes.
2. **Scope only.** Implement the listed routes and templates; nothing else.
   Locked decisions (§0.2) are never changed inside a milestone.
3. **Tests in the milestone.** Each milestone carries its own route/template
   tests, an accessibility check and the regression gate; none of it is
   deferred to a final sweep.
4. **Evidence.** Staging screenshots at 390 and 1280, light and dark (where
   the prototype has a dark state, otherwise palette consistency), paired
   with the prototype state named in the milestone, committed under
   `docs/design/proto-comparison-<date>/m<N>/`.
5. **Acceptance before the next.** Deviations are listed in the milestone
   file; the owner accepts, defers or rejects each before the next milestone
   starts. A milestone PR stays draft until accepted.
6. **Isolation.** One branch per milestone, `pg-m<N>-<slug>`, cut from the
   current head of `cursor/playground-220d`; one draft PR into
   `cursor/playground-220d`. While Gate E3 pins the branch at `5d89fbd`,
   PRs stay draft and unmerged; merging is a separate authorisation that
   also needs the pin lifted. No milestone touches PR #188, production
   Railway, production Supabase or any deployment.

### 0.1 Shared definition of done

- Full non-integration pytest suite green (CI `Unit tests`), section-hash
  drift 0, sitemap and packaging tests green.
- No new template renders a hard-coded fixture where loaded data exists.
- Keyboard: every interactive element reachable and visibly focused; tab
  bar and top nav expose `aria-current`; dialogs/sheets trap focus and
  close on Escape; colour contrast ≥ 4.5:1 for text in light and dark.
- Phone (390) and desktop (1280) captured; no horizontal scroll at 390.
- Milestone file lists every remaining difference against the prototype
  with a class (F/G/I/U) and the owner's decision.

### 0.2 Locked decisions carried into every milestone

Google-only login (no email/password, no OTP) · guest `/calendar` stays
gated · plans are Plus/Pro/Max ₹199/399/1,199 · Study archive (Stage 2)
stays parked; calendar compares against `calDesign=classic` · accepted
account surfaces on Profile stay · the NDPS fixture head is replaced only
after the owner's design decision (M2 asks for it) · no production or
deployment change.

### 0.3 Deployment and comparison gates

Staging serves the frozen commit `5d89fbd`. A milestone's implementation
can be compared on staging only after the owner separately approves a
staging deployment of that milestone's branch. Until then, local captures
(from the `playground-dev` launcher) support preliminary review and are
labelled "local"; **hosted acceptance requires the approved deployment**.
Production Railway and Supabase are never used.

### 0.4 Evidence limitations carried from M0

- Signed-in **desktop** comparison in M0 was structural (DOM) only. Full-
  resolution 1280×900 staging captures for 14 states (S01–S11 plus UAPA
  head, Devices and plans with Plus selected) are in
  `desktop-signedin/README.md`; no visual acceptance has been recorded
  against them yet, and the S-row verdicts were not re-scored.
- Subscribed Playground flows (DV-17) and subscription/device edge states
  (DV-18) are unverified. `ADMIN_ENABLED=false` and `PRICING_ENABLED=false`
  on staging, so neither an admin grant nor a checkout is available there
  today; reaching those states is an owner decision.
- DV-14 is **resolved, not a defect** (S14, 2026-10-19): the plans page is
  a two-step selector and "Continue with Plus" appears once a tier is
  selected; checkout behind it stays U (`PRICING_ENABLED=false`).
- Dark fidelity cannot be judged against a design (no dark prototype).

### 0.5 How to produce a prototype reference

Serve the export folder and open the wrapper (`make_wrappers.py` in the
M0 captures folder): `phone.html?pin=1&viewer=<v>&screen=<s>[&law=…]` or
`desktop.html?pin=1&calDesign=classic&viewer=<v>&screen=<s>`. Capture with
headless Chrome at 400×860 (phone) or 1640×960 (desktop). References below
are written as `phone:<query>` / `desktop:<query>`.

## 1. Milestone board

| M | Name | Screen family | Depends on | Owner decisions needed first | Status |
|---|---|---|---|---|---|
| M0 | Audit baseline | all | — | — | **ACCEPTED as planning baseline** (PR #218, draft; limitations §0.4) |
| M1 | Guest shell parity (+ DV-20 account slot, DV-21 nav on gate/plans/Add) | shell only: tab bar, top nav, account slot | — | checklist accepted 2026-10-19; implementation authorized 2026-10-19 (local only) | **in progress** |
| M2 | Bare Act head family (content + in-page navigation) | `/laws/{id}` for every eligible Act, Add sheet | M1 (shell) | direction approved (data-driven head, 8 NDPS entries, About/Schedules preserved) | proposed |
| M3 | Browse and Laws index (phone) | `/browse`, `/laws`, `/browse/part/*` phone | M1 | — | proposed |
| M4 | Today / dashboard | `/dashboard` guest + signed-in, both widths | M1 | §4.1 item 8 | proposed |
| M5 | Account family | `/profile`, `/settings`, `/profile/security/devices`, `/playground` gate + plans | M1 | DV-9 (one or two gate buttons), DV-14 (plan select control) | proposed |
| M6 | Calendar (classic) | `/calendar` signed-in, month/week, day panel | M1 | — | proposed |
| M7 | Subscribed Playground flows | `/playground`, `…/laws/{id}`, `…/sections`, Learn, roster, rollover, learned, mastered | M2 | a staging-only entitlement for the test account (admin grant, no payment) | proposed |
| M8 | Subscription and device edge states | expired/halted/paused, device limit/revoked/replacement, notices | M7 | how each state is reached on staging without payment | proposed |
| M9 | Landing and polish | `/`, dark palette sweep, copy nits (DV-11, DV-13), residual A11y | M1–M6 | — | proposed |

M3, M4, M5 and M6 are independent of each other once M1 lands; they can
run in parallel on separate branches. M2 is independent of M3–M6.

## 2. Milestones

### M1 — Guest shell parity

- **Routes / screens:** every guest-reachable page: `/`, `/browse`, `/laws`,
  `/laws/{id}`, `/playground`, `/dashboard`, `/settings`, `/profile`,
  `/login`, `/terms`, `/privacy`, `/grievance`, `/tables`, `/search`.
- **Expected behaviour:** guests get the same shell as signed-in users:
  five-tab bottom bar on phone (Today / Browse / Playground / Calendar /
  Profile, Playground tab inactive-styled for guests), new top nav with a
  "Sign in" button on desktop, no legacy `PrimaryTabs` Home/Browse/Search/
  Learn bar, no "Learning as guest" chip, footer reduced to the new
  design's legal links. Calendar tab for guests still lands on the login
  redirect (locked).
- **Visual references:** `phone:viewer=guest&screen=browse|laws|today|
  settings|profile|gate`, `desktop:viewer=guest&screen=…` (same list).
- **Tests:** template tests asserting the guest shell markup
  (`mobile-tabbar PrimaryTabs--bottom` present and `mobile-tabbar is-guest`
  absent on each listed route; top nav text; `aria-current` on the active
  tab); existing guest-gate tests unchanged; snapshot of nav HTML for
  guest vs signed-in differing only in the account slot.
- **A11y:** tab bar is a `nav` with labelled links; focus ring visible;
  contrast of inactive tabs.
- **Acceptance:** DV-1 and DV-4 closed on all listed routes at 390 and
  1280; no change to page content (that is M3–M6); regression suite green.
- **Scope control:** shared navigation and shell components only (see
  `milestones/M1.md` §2). No page content, authentication, legal pages or
  accepted functionality change; Act-head content and navigation belong to
  M2.
- **Branch / PR:** `pg-m1-guest-shell` → draft PR into
  `cursor/playground-220d`. First task: a full-resolution desktop capture
  set of the signed-in pages (the M0 desktop pass was structural only).
- **Checklist:** `docs/design/milestones/M1.md`.

### M2 — Bare Act head family

- **Routes / screens:** `/laws/{id}` for every eligible Act (NDPS, BNS,
  UAPA, and the others in the catalogue), both viewers; the Add sheet
  `/playground/laws/{id}/add` and its in-page opener; schedules reached
  from the head.
- **Expected behaviour:** one head template generated from the loaded
  Act: kicker "BARE ACT · INDIA CODE", title, meta line
  "<n> Chapters · Sections a–b[ · Schedule]", CTA by viewer (guest "Sign in
  to use Playground", free account "Subscribe to use Playground", Plus
  "+ Add to Playground", in Playground "Already in Playground"), chapter
  rows that **link** to the chapter, schedule row(s) after the chapters,
  About-this-Act content and the schedule list preserved (location to be
  decided in the milestone file). The NDPS fixture is deleted. Add sheet
  title "Add to Playground", lede naming the Act, footnote listing the
  plans; desktop renders it as a centred modal, phone as a bottom sheet;
  Escape/scrim closes it.
- **Owner decisions required before start:** §4.1 items 4 and 9; chapter
  count wording for NDPS (6 numbered + IIA/VA vs 8) applied consistently to
  catalogue, head and card.
- **Visual references:** `phone:viewer=guest|signedIn|plus&screen=act&law=
  ndps|bns|uapa`, `…&sheet=1`; desktop same.
- **Tests:** for each eligible Act, the head renders every chapter in the
  JSON with a link and the meta line matches the JSON; a test that fails
  if `guest_bareact_head.py` constants are still referenced; Add-sheet
  copy per viewer; existing reader, schedule and sitemap tests green;
  section hash drift 0.
- **A11y:** chapter rows are links or buttons, not divs; sheet/modal has
  `role="dialog"`, labelled title, focus trap.
- **Acceptance:** DV-2, DV-3, DV-15 closed; S3/S4 rows MATCH at 390 and
  1280 for guest and free account; Plus state compared when M7's
  entitlement exists, otherwise marked U.
- **Branch / PR:** `pg-m2-act-head`.

### M3 — Browse and Laws index (phone)

- **Routes / screens:** `/browse` phone (guest and signed-in),
  `/browse/part/{slug}` phone, `/laws` phone.
- **Expected behaviour:** Browse phone = prototype: title "Browse the
  Constitution", subtitle, guest banner with Sign-in button or free-plan
  banner ("Free plan — pick any 3 Articles… Unlock all") for free
  accounts, Laws/Tables cards, MARKS legend, Part headers with article
  card grid (collapsible). Laws phone: "← Browse" back link, kicker
  BROWSE, title, subtitle, search field, category chips, cards with
  chevron and meta only (no per-card CTA); the CTA lives on the Act head.
  Desktop Browse adds the free-plan banner for signed-in free accounts.
- **Visual references:** `phone:viewer=guest|signedIn&screen=browse|laws`;
  `desktop:viewer=signedIn&screen=browse`.
- **Tests:** template tests for banner variants by viewer; no CTA inside
  law cards on phone; search input present; article grid count equals the
  Part's article count; existing browse/search tests green.
- **A11y:** collapsible Part headers are buttons with `aria-expanded`;
  chips are a labelled group.
- **Acceptance:** DV-8 (phone part), DV-12, S10, S11 closed.
- **Branch / PR:** `pg-m3-browse-laws`.

### M4 — Today / dashboard

- **Routes / screens:** `/dashboard` guest and signed-in, phone and
  desktop; empty and populated states.
- **Expected behaviour:** greeting block per prototype ("Good morning." +
  weekday/date, avatar or guest ring, streak chip, theme toggle), Today's
  Recall card (ring, due count, Continue revision / Learn your first
  Article), TODAY'S PATH list when there is a plan; guest variant "Nothing
  due yet." with Sign in and "Browse the Bare Acts →". Accepted content
  (Good places to begin, Set a learning plan, Take the two-minute tour) is
  kept and restyled, not removed, unless the owner decides otherwise in
  §4.1 item 8. Desktop uses the two-column layout.
- **Visual references:** `phone:viewer=guest&screen=today`,
  `phone:viewer=signedIn|plus&screen=today&seed=1`; desktop same.
- **Tests:** template tests per state; existing dashboard/plan-my-day
  tests green.
- **Acceptance:** DV-5 and S1 closed for the states reachable on staging;
  populated path compared after learning one Article on the test account
  (a staging write, allowed) or marked U.
- **Branch / PR:** `pg-m4-today`.

### M5 — Account family

- **Routes / screens:** `/profile`, `/settings`,
  `/profile/security/devices`, `/playground` gate and
  `/playground?stage=plans`, guest and signed-in, both widths.
- **Expected behaviour:** Profile card copy ("Free account · Constitution
  learning included"), SUBSCRIPTION card "No plan yet … See plans ›",
  section order per prototype, accepted account surfaces retained below;
  Settings guest STUDY card, Pace note with "Unlock every Article →",
  CALENDAR section when Google Calendar is configured, desktop layout per
  prototype; Devices page titled "Devices" with the REGISTERED card and a
  designed empty state; gate buttons per the DV-9 decision; plans page
  with a select control per card leading to the existing checkout route
  (checkout itself untested on staging).
- **Visual references:** `phone:viewer=guest|signedIn&screen=profile|
  settings|devices|gate`; desktop same.
- **Tests:** per-viewer template tests; devices tests for empty and
  populated lists; no change to auth, grants or billing code.
- **A11y:** segmented controls are radio groups; toggles have labels.
- **Acceptance:** DV-7, DV-9, DV-13, DV-14 (control present), DV-16
  closed where reachable; Google Calendar section marked U on staging.
- **Branch / PR:** `pg-m5-account`.

### M6 — Calendar (classic)

- **Routes / screens:** `/calendar` signed-in, phone and desktop; month
  and week; day panel.
- **Expected behaviour:** desktop header "Month YYYY" with Month/Week,
  ←/Today/→, legend (Memorized / Review done / Review due / Scheduled /
  New / Overdue), grid chips per unit type, day panel; phone grid with
  dots/bars, legend, day agenda card. No Study-archive controls (parked).
- **Visual references:** `phone:viewer=plus&screen=calendar&seed=1` (ignore
  the Study-material tab, "My material", "Add task" and "Mark revised"
  rows), `desktop:viewer=plus&calDesign=classic&screen=calendar&seed=1`.
- **Tests:** calendar view-model tests for chip classes; GCal preference
  tests unchanged.
- **Acceptance:** S6 populated state compared after at least one scheduled
  revision exists on the test account; empty state already MATCH.
- **Branch / PR:** `pg-m6-calendar`.

### M7 — Subscribed Playground flows

- **Precondition (owner):** a staging-only Playground entitlement for the
  test account, issued through the admin grant route on staging, never
  through payment and never on production. Without it the milestone
  cannot be verified and stays U.
- **Routes / screens:** `/playground` (laws present, empty),
  `/playground/laws/{id}` (Act progress), `…/sections` (picker, clause
  depth), Learn modes (six), `…/sections/{n}/learned`, `…/mastered`,
  `/playground/roster`, `/playground/roster/next`, Today with Playground
  items, Act head Plus state and "act vs sections" Add sheet.
- **Expected behaviour:** per the Plus-viewer prototype screens (phone
  and desktop references `viewer=plus&screen=playground|empty|picker|learn|
  progress|complete|milestone|roster|rollover|today&seed=1`), including the
  known picker defect from the earlier local run (promoting to whole
  section clears clause boxes; unticking one clause then selects only that
  clause).
- **Tests:** the existing Playground route tests, locator/unit tests,
  picker tests extended for the clause-promotion case; speech modes with
  typed fallback (no Deepgram on staging).
- **Acceptance:** DV-17 rows compared at both widths; every remaining
  difference classified.
- **Branch / PR:** `pg-m7-playground-flows`.

### M8 — Subscription and device edge states

- **Precondition (owner):** a safe way to put the staging test account
  into each state (expired, halted, paused; device limit, revoked,
  replacement limit; each notice) without payment, for example admin
  grant edits on staging. States that cannot be reached stay U.
- **Routes / screens:** Act head, Profile SUBSCRIPTION card, Playground
  home notices, Devices page, session-expired page.
- **References:** desktop `viewer=expired|halted|paused|deviceLimit|
  deviceRevoked|replacementLimit`, `notice=pending|cancelAtEnd|upgrade|
  downgradeScheduled|resubscribed`, `sessionExpired=1`; phone
  `viewer=expired`.
- **Acceptance:** DV-18 rows compared or explicitly left U with the reason.
- **Branch / PR:** `pg-m8-edge-states`.

### M9 — Landing and polish

- **Routes / screens:** `/` both widths; dark-palette sweep of all
  milestone pages; copy nits (DV-11, DV-13); residual accessibility
  findings from M1–M8.
- **Acceptance:** landing CTAs under the tagline on phone, desktop footer
  line present; dark palette consistent on every page; no open A11y
  finding above minor.
- **Branch / PR:** `pg-m9-polish`.

## 3. Acceptance record

| M | Checklist approved | Implemented (SHA) | Tests | Evidence folder | Deviations open | Accepted on |
|---|---|---|---|---|---|---|
| M0 | n/a (audit) | 2866ede, b4a0517 | n/a | `proto-comparison-2026-10-18/` | DV-1…DV-19 classified; desktop signed-in visual pass incomplete | accepted as planning baseline 2026-10-18 |
| M1 | revised after independent review (`milestones/M1.md`, Appendix A verifies findings); awaiting owner approval. Prerequisites: hosted deployment verified (deployment `32971cbf…` = `5d89fbd`, 2026-10-18); full-resolution signed-in desktop baseline captured for 14 states (Cursor, 2026-10-18/19) including UAPA head, Devices and selected-plan | — | — | — | — | — |
| M2 | — | — | — | — | — | — |
| M3 | — | — | — | — | — | — |
| M4 | — | — | — | — | — | — |
| M5 | — | — | — | — | — | — |
| M6 | — | — | — | — | — | — |
| M7 | — | — | — | — | — | — |
| M8 | — | — | — | — | — | — |
| M9 | — | — | — | — | — | — |
