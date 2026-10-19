# Prototype ↔ staging comparison — 18 October 2026

Page-to-page check of the two Claude Design prototypes exported on
18 Oct 2026 against the hosted Playground staging site. The question
answered here is: **does the code on `cursor/playground-220d` render what
the prototypes show?**

| | |
|---|---|
| Staging | `https://recallthec-production.up.railway.app` — Railway project `recallc-playground-staging`, service `recall_the_c`, env `production`; `APP_ENV=staging`, `DATABASE_URL` host contains only the staging Supabase ref `tvygwasuqvtnzjyjtqrq`. Verified before any page was loaded. No database write was made during this pass. |
| Code served | `cursor/playground-220d` @ `5d89fbd` (asset pins `styles.css?v=main86`, `playground.css?v=pg48`, `mobile.css?v=mob105` match that commit). |
| Prototypes | `Recall the C - Playground.dc.html` (phone, 22 screens) and `Recall the C - Playground Desktop.dc.html` (desktop, 20 screens), both exported 18 Oct 12:47, plus `support.js`. Not committed; they live in the user's Downloads (`Playground-1.zip`, `Playground - Desktop.zip`). |
| Widths | Phone 390×844 (staging) vs the prototype's 390-wide phone frame; desktop 1280×900 (staging) vs the prototype's 1280-wide desktop frame. Light theme unless stated. |
| Captures | `docs/design/proto-comparison-2026-10-18/{phone,desktop}/` — `stg_*` is staging, `proto_*` is the prototype. Produced with headless Chrome; see §5 to regenerate. |

Verdict legend: **MATCH** = same structure, copy and shell, cosmetic
differences only · **DEVIATION** = the page exists but differs from the
prototype in shell, structure, copy or behaviour (see the DV number) ·
**NOT REACHABLE** = the state cannot be shown on staging in this pass ·
**PENDING** = needs a signed-in session (§3).

## 1. Summary

Guest-reachable screens were compared on both widths (11 staging pages, 13
prototype screens per width) in the first pass. The second pass (M0)
compared every signed-in screen reachable to a free account (§3) and
consolidated all findings into one classified matrix (§4). Subscribed
Playground flows and subscription edge states remain unverified because
reaching them would require a payment or an entitlement change.

The guest comparison splits cleanly into two groups:

- **Rendered in the new design and matching the prototype** — Landing,
  Browse (desktop), Laws index (desktop), the NDPS Bare Act head shell,
  the Playground gate, Profile. These need only small fixes (DV-8, DV-9,
  DV-11, DV-12, DV-13).
- **Still rendered by the legacy shell/templates** — Browse (phone), Laws
  index (phone), UAPA and BNS Bare Act heads (both widths), Today/dashboard
  (both widths), Settings (desktop; phone partially), Sign-in, and the
  guest Calendar (redirects). These are DV-1, DV-3, DV-4, DV-5, DV-6,
  DV-7, DV-10. The tracker's D20 row records that the five-tab shell was
  scoped to signed-in multiuser pages; the 18 Oct prototypes now show it
  on every guest screen, so this is a scope gap between the programme and
  the newer prototypes rather than a regression.

One finding is a defect independent of design scope: **the guest NDPS head
is a hard-coded fixture** (DV-2). It prints "6 Chapters" and three chapter
rows (I, II, III) plus the Schedule, while the Act JSON on the same commit
has eight chapters (I, II, IIA, III, IV, V, VA, VI), and its rows are
plain `div`s with no link, so a guest cannot open any chapter from it. The
prototype shows all eight chapters as navigable rows.

## 2. Guest rows

### 2.1 Phone (390)

| # | Prototype screen | Staging route | Verdict | Notes / evidence |
|---|---|---|---|---|
| P1 | Landing | `/` | MATCH (DV-11) | Same logo, title, tagline, two CTAs, footer line. Staging pins the CTAs to the bottom; prototype places them under the tagline. `stg_phone_landing` / `proto_phone_landing_guest` |
| P2 | Browse — Constitution | `/browse` | DEVIATION DV-1, DV-12 | Legacy page: "Browse" header with search icon and Sign-in pill, Part cards with progress bars, four-tab bar (Browse/Search/Learn/Sign in). Prototype: "Browse the Constitution" + subtitle, guest banner with Sign-in button, Laws/Tables, MARKS legend, article-card grid under each Part, five-tab bar. |
| P3 | Laws index | `/laws` | DEVIATION DV-1, DV-8 | Legacy template: inline "← Browse Laws" header, no subtitle, search icon instead of field, every card carries "Sign in to add this law to Playground." plus a CTA button; four-tab bar. Prototype cards have no CTA. |
| P4 | Bare Act head — NDPS | `/laws/ndps` | DEVIATION DV-2 | New head shell and five-tab bar match the prototype, but the content is a fixture: "6 Chapters", three chapter rows + Schedule, rows not linked. Prototype: "8 Chapters · Sections 1–83 · Schedule" and eight linked rows. |
| P5 | Bare Act head — UAPA | `/laws/uapa` | DEVIATION DV-3 | Legacy Bare Act page: "BARE ACT" kicker without "INDIA CODE", no meta line, "Sign in to add this law…" lede, ABOUT THIS ACT link, Chapters/Schedules tabs, accordion with Chapter I expanded, four-tab bar. |
| P6 | Bare Act head — BNS | `/laws/bns` | DEVIATION DV-3 | Same legacy page as UAPA. |
| P7 | Playground gate | `/playground` | MATCH | Kicker, title, lede, three benefits, Sign in + Create an account, footnote, five-tab bar. (Prototype typo "offical"; staging spells it correctly.) |
| P8 | Sign in | `/login` | DEVIATION DV-10 | Staging: dark "Nothing you learn is lost." hero, Continue with Google, mobile number (marked not available), Continue as guest. Prototype: light "Sign in to RecallC", Google + email/password form, "Create an account". |
| P9 | Today (guest) | `/dashboard` | DEVIATION DV-1, DV-5 | Legacy dashboard: "Welcome. / Reading as a guest", washed-out Today's Recall card, "Good places to begin", sign-in card, four-tab bar. Prototype: "Good morning. / Sunday 6 September · Reading as a guest", "Nothing due yet." card with Sign in and "Browse the Bare Acts →", five-tab bar. |
| P10 | Calendar (guest) | `/calendar` | NOT REACHABLE — DV-6 | Redirects to `/login?next=%2Fcalendar`. Prototype shows the month grid with "Your calendar is empty until you sign in". |
| P11 | Profile (guest) | `/profile` | MATCH (DV-13) | Same cards and five-tab bar; copy differs slightly ("…and unlock the Constitution learning experience" vs "Sign in to save progress."). |
| P12 | Settings (guest) | `/settings` | DEVIATION DV-7 | Guest card, APP (Appearance, Motion), ACCOUNT and legal footer match. Missing: the STUDY card ("Learning plan and revision calendar appear once you sign in"). No bottom tab bar at all on this page (only the legacy top nav, hidden on phone). |
| P13 | Devices | `/profile/security/devices` | PENDING | Guest redirect to login, as expected; compare signed in. |

### 2.2 Desktop (1280)

| # | Prototype screen | Staging route | Verdict | Notes / evidence |
|---|---|---|---|---|
| D1 | Landing | `/` | MATCH (DV-11) | Identical layout; staging omits the footer line "BARE ACT · VERBATIM · DAY 1 · 3 · 7 · 15 · 30 · 60". |
| D2 | Browse — Constitution | `/browse` | MATCH | New top nav, guest banner, Laws/Tables, MARKS, article grid. Differences: header shows a "Guest · Not signed in" avatar instead of the prototype's black Sign-in button; MARKS use icons rather than colour squares; staging adds a subtitle the desktop prototype lacks. |
| D3 | Laws index | `/laws` | MATCH (DV-8) | Same header, search field, chips and two-column cards. NDPS card says "6 Chapters" (prototype "8 Chapters"); UAPA card lacks "· Schedule". |
| D4 | Bare Act head — NDPS | `/laws/ndps` | DEVIATION DV-2 | Shell matches; content is the same fixture as P4. |
| D5 | Bare Act head — UAPA | `/laws/uapa` | DEVIATION DV-3, DV-4 | Legacy desktop shell (Home/Browse/Search/Learn, "Learning as guest", footer with theme chip) and legacy Bare Act page. |
| D6 | Bare Act head — BNS | `/laws/bns` | DEVIATION DV-3, DV-4 | As D5. |
| D7 | Playground gate | `/playground` | MATCH (DV-9) | Two-column gate matches; staging's card has only "Sign in" — the prototype also shows "Create an account". |
| D8 | Sign in | `/login` | DEVIATION DV-10 (intentional) | Standalone split dark/light sign-in page (no shared nav by design) vs the prototype's centred form. |
| D9 | Today (guest) | `/dashboard` | DEVIATION DV-4, DV-5 | Legacy shell and legacy dashboard copy. |
| D10 | Calendar (guest) | `/calendar` | NOT REACHABLE — DV-6 | Redirects to login. |
| D11 | Profile (guest) | `/profile` | MATCH | Identical. |
| D12 | Settings (guest) | `/settings` | DEVIATION DV-4, DV-7 | Legacy shell, centred single column, no guest card, no STUDY card, no "← Today". |
| D13 | Devices | `/profile/security/devices` | PENDING | Guest redirect. |

### 2.3 Dark theme (phone, guest)

Staging was captured with `prefers-color-scheme: dark` on `/browse`,
`/laws`, `/laws/ndps`, `/playground`, `/profile`: every page renders a
consistent dark palette, including the legacy pages. The exported
prototype has no dark variant that can be switched on outside the design
app (`support.js` only uses `?theme=` for the canvas background), so dark
mode was checked for palette consistency only, not against a dark
prototype.

## 3. Signed-in rows (M0, second pass)

Session: the account owner signed in with Google in the browser pane;
`/dashboard` greeted the account by name and `/profile` showed "Signed in
with Google", Devices 0 of 2 and no Playground subscription. The account
is therefore the prototype's `signedIn` viewer (free account, Constitution
included, Playground locked). No cookie, token or credential was copied
anywhere. No write was made other than page views.

Evidence: `phone-signedin/stg_phone_*_signedin.png` (375×812 crops) against
`phone-signedin/proto_phone_*_signedin.png`; desktop prototype states in
`desktop-signedin/`. Desktop staging rows were verified structurally from
the DOM (shell, headings, sections, CTAs) at an emulated 1280×900 because
the browser pane was too narrow for a legible desktop capture during this
pass. Full-resolution 1280×900 captures for 14 signed-in states were added
on 2026-10-19 (`desktop-signedin/README.md`), including `/laws/uapa`,
Devices and `/playground?stage=plans&tier=plus`; the S-row verdicts below
were not re-scored against them.

| # | Prototype screen (`viewer=signedIn`) | Staging route | Verdict | Notes |
|---|---|---|---|---|
| S1 | Today | `/dashboard` | PARTIAL | Shell matches (five-tab bar, new top nav with avatar). Content is the accepted Constitution dashboard: "Welcome, Sanjali." + date + streak chip, Today's Recall ring 0/0, "Learn your first Article →", Good places to begin, Set a learning plan, Take the two-minute tour. Prototype: "Good morning." + avatar initial, Today's Recall with "3 revisions due" and Continue revision, TODAY'S PATH list. The prototype draws only a populated state; the empty state is not represented. Desktop: `main` spans the full 1280 px with no two-column layout. |
| S2 | Playground gate → plans | `/playground`, `/playground?stage=plans` | MATCH / PARTIAL | Gate matches the desktop prototype exactly ("Your RecallC account already includes the complete Constitution." + View Playground plans + HOW PLAYGROUND WORKS). Plans page: three cards Plus ₹199 · Pro ₹399 · Max ₹1199 with "Monthly. GST included." but **no select/continue control on any card**; the prototype has "Continue with <plan>". The phone prototype's plan names and prices (Core/Deep/Infinite, ₹149/299/499) are stale placeholders; the desktop prototype and staging agree on Plus/Pro/Max. |
| S3 | Bare Act head — UAPA | `/laws/uapa` | DEVIATION (DV-3) | Legacy Bare Act page (ABOUT THIS ACT, Chapters/Schedules tabs, accordion) with "Unlock Playground · from ₹199 / month." and "Subscribe to use Playground". New shell on both widths. Prototype: new head with meta line and the same CTA. |
| S4 | Bare Act head — NDPS | `/laws/ndps` | DEVIATION (DV-2) | The fixture head is also what signed-in users see (`signed_in_bareact_desktop` reuses `guest_screen4`): "6 Chapters", three unlinked rows + Schedule. |
| S5 | Add sheet | `/playground/laws/uapa/add` | PARTIAL | Staging: sheet "OCTOBER / Unlock Playground / Turning UAPA into a learning experience needs a plan. Reading it stays free. / Unlock Playground / from ₹199 / month…". Prototype: title "Add to Playground", lede names "The UAPA, 1967", footnote lists the plans. Opened by direct URL the sheet renders at the top of an empty page on both widths (desktop: a 1280×357 top sheet, not the prototype's centred modal); opening it from the Act page's CTA was not exercised and is unverified. |
| S6 | Calendar | `/calendar` | MATCH (shell, empty state) | Phone: month grid, legend Today/Overdue/Scheduled/Done/New, "TODAY · NOTHING DUE" card. Desktop: month grid, Month/Week, Today, legend, right-hand day panel. The phone prototype's filter tabs (Constitution / Laws / Study material), "My material" legend, "Only you", "Add task" and "Mark revised" rows belong to the parked Study-archive design and are not expected. Populated state unverified (no revisions on the account). |
| S7 | Profile | `/profile` | PARTIAL | Staging: name card "Signed in with Google / Edit name"; ACCOUNT (Profile, Devices 0 of 2, Learning preferences → Settings, Report an issue, Sign out); SUBSCRIPTION card "Playground / Subscribe to add Bare Acts to a monthly Playground. / Subscribe"; then Sign-in method, Security (desktop), Legal (desktop), Account (Reset progress…, Delete account…). Prototype: card "Free account · Constitution learning included"; SUBSCRIPTION "No plan yet / Playground learning is locked… / See plans ›" placed before ACCOUNT on phone; no Sign-in method / Security / Legal / Reset / Delete. Desktop staging keeps the two-column arrangement. |
| S8 | Settings | `/settings` | PARTIAL | Staging phone: account card, STUDY (Pace Self-paced/Auto Plan; Daily target disabled), APP (Appearance, Bare Act text size, Motion), ACCOUNT, Legal. Prototype: adds a note under Pace ("Part of unlocking every Article — Unlock every Article →") and a CALENDAR section with a Google Calendar toggle. Staging shows no CALENDAR section at either width: the template renders it only when a `gcal` context is present, and staging has no Google Calendar variables configured (variable names checked, no values read). The Calendar page footer nevertheless says "With Google Calendar on in Settings". Desktop staging adds "Save learning plan" and an Experience section (Completion sounds), as the desktop prototype does. |
| S9 | Devices | `/profile/security/devices` | PARTIAL | Staging: kicker SECURITY, "Your devices", "0 of 2 devices", "Active devices", "No active devices. A device is registered the first time Playground is used while subscribed." Prototype: "Devices", lede "Your plan supports Playground on up to 2 registered devices…", REGISTERED card with device rows and Remove. Empty state not drawn in the prototype; populated state unverified (needs a subscribed session). |
| S10 | Browse | `/browse` | DEVIATION (DV-12) phone / PARTIAL desktop | Phone: same page as guest (title "Browse", search, "Marks" button, Part cards with progress) under the five-tab bar; prototype shows the new Browse with "Free plan — pick any 3 Articles. All 3 slots free. Unlock all" and the article grid. Desktop: article grid present (491 article cards, 24 parts) but the free-plan banner is absent. |
| S11 | Laws index | `/laws` | DEVIATION (DV-8) phone / MATCH desktop | Phone cards carry "Unlock Playground · from ₹199 / month." + "Subscribe to use Playground"; prototype cards have no CTA. Desktop matches (search field, chips, two columns, no card CTAs). |
| S12 | Act progress, picker, Learn, Playground home/empty, roster, rollover, section learned, Act mastered | `/playground/laws/{law}`, `…/sections`, `…/learned`, `…/mastered`, `/playground/roster`, `/playground/roster/next` | UNVERIFIED | Require an active Playground subscription. Not reached: no payment was simulated and no entitlement was changed. An admin grant route exists in the code (`POST /admin/users/{id}/grants`) but `ADMIN_ENABLED=false` on staging, so even a staging-only grant would first need that flag changed — an owner decision, not something this pass did. |
| S13 | Subscription states (expired, halted, paused), device limit / revoked / replacement limit, notices (pending, cancel at end, upgrade, downgrade, resubscribed), checkout | various | UNVERIFIED | Not reachable safely; staging has no Razorpay keys. |

### 3.1 Desktop visual re-score (19 October 2026)

Scored from the 14 full-resolution 1280×900 staging captures in
`desktop-signedin/` (S01–S14, signed-in Free account, deployment
`32971cbf…` = `5d89fbd`) against the desktop prototype at
`viewer=signedIn` (`proto_desk_*_signedin.png` in the same folder). This
replaces the "structural only" qualification for the desktop rows; the
phone verdicts in §3 are unchanged.

| Capture | Route | Prototype reference | Desktop verdict | Visible differences |
|---|---|---|---|---|
| S01 | `/` | `screen=landing` | MATCH (DV-11 minor) | Signed-in landing is the same centred composition; footer line absent (as guest). |
| S02 | `/browse` | `screen=browse` | MATCH | Nav, avatar slot, free-plan banner ("Free plan — pick any 3 Articles… Unlock all"), Laws/Tables, article grid all present. MARKS legend uses icons where the prototype uses colour squares. |
| S03 | `/laws` | `screen=laws` | MATCH | Search field, chips, two-column cards, no card CTAs. Chip set differs by catalogue content (staging has Health, no Commercial). NDPS card reads "8 Chapters" when signed in but "6 Chapters" for guests (§2.2 D3) — the guest Laws page is fixture-fed; folded into DV-8. |
| S04 | `/laws/ndps` | `screen=act&law=ndps` | DEVIATION DV-2 | Fixture head (6 Chapters, three rows + Schedule). Prototype: eight rows. (The prototype's NDPS CTA always reads "Already in Playground"; use UAPA for CTA-state references.) |
| S05 | `/playground/laws/ndps/add` (accepted substitute for the M0 UAPA Add state; same template, copy differs only by Act name) | `…&sheet=1` (UAPA) | DEVIATION DV-15, DV-21 | Rendered as a standalone page: header is brand + account only, legacy footer (Tables / Relevant laws / Playground / Settings / Contact us / theme chip) directly under the card. Prototype: centred modal over the Act page with the full nav. |
| S06 | `/playground` | `screen=gate` | PARTIAL DV-21 | Body matches the prototype gate exactly; header lacks the main nav that the prototype keeps. |
| S07 | `/playground?stage=plans` | — | N/A (no prototype) | The desktop prototype has no plans stage (its gate stops at "View Playground plans"). Unselected state; see S14. |
| S08 | `/dashboard` | `screen=today` | DEVIATION DV-5 | New nav and greeting row ("Welcome, Sanjali." + date + streak chip) but the body is unstyled list content (TODAY'S RECALL block, inline links). Prototype: two-column cards with ring and TODAY'S PATH. Account slot shows the name without the "Free account" subtitle (DV-20). |
| S09 | `/calendar` | `calDesign=classic&screen=calendar` | PARTIAL (needs decision) | Title "October 2026", Month/Week, ←/Today/→ match. Legend differs (My material / Due today / Overdue / Memorized / Scheduled vs Memorized / Review done / Review due / Scheduled / New / Overdue). Staging shows Study-archive controls: "Show" filter, "Only you", "Add task", day-cell "+", side panel with "+ Add study material for this day". The classic prototype has none; Stage 2 is parked. For M6 scope review. |
| S10 | `/profile` | `screen=profile` | PARTIAL DV-13 | Two-column layout matches. Copy: "Signed in with Google" vs "Free account · Constitution learning included"; SUBSCRIPTION "Playground / Subscribe" vs "No plan yet / See plans ›". Account slot without subtitle (DV-20). |
| S11 | `/settings` | `screen=settings` | MATCH (minor) | Account card, STUDY Learning plan (Pace, Daily target, Save), APP Appearance, Experience present. Prototype adds the "Unlock every Article →" note and a CALENDAR section (env-gated on staging, U). |
| S12 | `/laws/uapa` | `screen=act&law=uapa` | DEVIATION DV-3 | Legacy Bare Act page (ABOUT THIS ACT, Chapters/Schedules tabs, accordion, legacy footer) under the new nav; CTA card "Unlock Playground · from ₹199 / month. / Subscribe to use Playground". Prototype: new head with meta line and a single CTA. |
| S13 | `/profile/security/devices` | `screen=devices` | DEVIATION DV-16 | Prose page ("SECURITY / Your devices / 0 of 2 devices / Active devices / No active devices…") with legacy footer. Prototype: "Devices" title, lede, REGISTERED card. Empty state not drawn in the prototype. Account slot without subtitle (DV-20). |
| S14 | `/playground?stage=plans&tier=plus` | — | RESOLVED (DV-14 not a defect) | Plus card outlined as selected; right card shows "Continue with Plus". Two-step selector confirmed. Checkout behind it remains U (`PRICING_ENABLED=false`). Header still brand + account only (DV-21). |

New IDs from this pass: **DV-20** account-slot inconsistency (subtitle
"Free account" shown on S02–S04, S06, S07, S12, S14 but not on S08–S11,
S13); **DV-21** signed-in gate, plans and Add pages render without the
main nav. Both are shell-level and belong to M1's scope review if the
owner agrees, otherwise M5.

## 4. Consolidated deviation matrix (M0)

Classes: **F** = functional defect (works incorrectly regardless of design
scope) · **G** = approved-design gap (the 18 Oct prototypes show it, the
branch does not; needs authorisation to build) · **I** = intentional
divergence (a locked decision or previously accepted screen; not reopened
by this audit) · **U** = unverified state.

| ID | Where | Guest | Signed-in | Class | Summary |
|---|---|---|---|---|---|
| DV-2 | `/laws/ndps` head, both widths | ✓ | ✓ | **F** | Hard-coded head from `web/guest_bareact_head.py`: "6 Chapters", three unlinked rows; Act has eight chapters. Verified functional limitation; **design decision required** before any fix (owner's instruction). |
| DV-14 | Plans page `/playground?stage=plans` | — | ✓ | **Resolved — not a defect** (S14) | Code review after the capture: the page is a two-step selector — each card is a link to `?stage=plans&tier=<tier>` with `aria-pressed`, and `gate_plan_continue_label()` renders "Continue with <plan>" only once a tier is selected. The M0 capture was the unselected state. Checkout behind it is gated by `PRICING_ENABLED` (false on staging) and billing keys, so the selected state and checkout stay **U** on staging. The selected-state render was not re-captured because the pane session had ended; verify in M5. |
| DV-1 | Phone shell on guest pages | ✓ | — | **G** | Legacy four-tab bar on `/browse`, `/laws`, `/dashboard`, `/laws/uapa`, `/laws/bns`; none on `/settings`. Signed-in pages already carry the five-tab bar everywhere. Conflicts with tracker D20 (see §4.1). |
| DV-3 | UAPA/BNS Act heads | ✓ | ✓ | **G** | New head exists only for NDPS; other Acts use the legacy Bare Act page at both widths and for both viewers. |
| DV-4 | Desktop shell on guest pages | ✓ | — | **G** | Legacy top nav on `/laws/uapa`, `/laws/bns`, `/dashboard`, `/settings`, `/login`. Signed-in desktop pages already use the new top nav. |
| DV-5 | Today / dashboard | ✓ | ✓ (S1) | **G** + **I** | Dashboard content is the accepted Constitution dashboard, not the prototype's Today ("Good morning.", TODAY'S PATH). Empty signed-in state is not in the prototype. Decision needed on whether the accepted dashboard is reopened (§4.1 item 8). |
| DV-6 | Guest `/calendar` | ✓ | — | **I** | Redirect to login stays (locked). |
| DV-7 | Settings | ✓ | ✓ (S8) | **G** / **U** | Guest phone: STUDY card missing, no tab bar; guest desktop legacy. Signed-in: Pace note missing; CALENDAR/Google section absent because it is env-gated on staging (U). |
| DV-8 | Laws index phone | ✓ | ✓ (S11) | **G** | Legacy template with per-card CTAs, no subtitle, icon instead of search field. Desktop matches. Also: NDPS chapter-count wording (6 vs 8) is a content decision. |
| DV-9 | Desktop gate | ✓ | — | **G** (minor) | "Create an account" secondary button missing on desktop; phone has it. With Google-only login both buttons start the same flow — decide whether to keep one. |
| DV-10 | `/login` | ✓ | — | **I** | Google-only login, dark hero page. Email/password and phone OTP out of scope (locked). |
| DV-11 | Landing | ✓ | — | **G** (minor) | Phone CTAs pinned to bottom; desktop footer line missing. |
| DV-12 | Browse phone | ✓ | ✓ (S10) | **G** | Legacy phone Browse for both viewers; desktop signed-in lacks the free-plan banner. |
| DV-13 | Profile copy | ✓ | ✓ (S7) | **G** (minor) + **I** | Guest copy differs; signed-in card copy, SUBSCRIPTION wording ("No plan yet / See plans") and section order differ. Extra account surfaces (Sign-in method, Security, Legal, Reset/Delete) are accepted R5 work and stay (I). |
| DV-15 | Add sheet | — | ✓ (S5) | **G** (minor) + **U** | Title/kicker/lede differ from the prototype; desktop direct-URL render is a top sheet, in-page open unverified. |
| DV-16 | Devices | — | ✓ (S9) | **G** + **U** | Page title/structure differ ("Your devices", SECURITY kicker, prose empty state vs card). Populated state unverified. |
| DV-17 | Subscribed Playground flows | — | — | **U** | Playground home/empty, picker, Learn, roster, rollover, progress, learned, mastered: not reachable without an entitlement. |
| DV-18 | Subscription edge states and checkout | — | — | **U** | Expired/halted/paused, device limit/revoked/replacement, notices, checkout. |
| DV-19 | Dark theme | ✓ | — | **U** (prototype side) | Staging dark palette is consistent; the export exposes no dark prototype, so dark fidelity cannot be judged against a design. |
| DV-20 | Header account slot (desktop, signed-in) | — | ✓ | **G** (minor, shell) | "Free account" subtitle appears on some pages (Browse, Laws, NDPS, gate, plans, UAPA) and not others (Today, Calendar, Profile, Settings, Devices). Prototype: always name + "Free account". |
| DV-21 | Gate, plans and Add pages (desktop, signed-in) | — | ✓ | **G** (shell) | Header is brand + account only; the main nav is absent. Prototype keeps the full top nav on the gate and renders Add as a modal over the Act page. |

Prototype-side issues (not code): phone gate typo "offical"; phone
Playground month "12 Aug – 11 Sep"; phone plan placeholders Core/Deep/
Infinite ₹149/299/499 (desktop and staging use Plus/Pro/Max ₹199/399/1,199);
roster says NDPS has "129 sections" while the head says 83; the phone
signed-in Calendar still draws the parked Study-archive controls.

### 4.1 Prior accepted behaviour that conflicts with the 18 Oct prototypes

| # | Accepted behaviour (where recorded) | Prototype shows | Status |
|---|---|---|---|
| 1 | Google-only login; phone OTP marked unavailable (login screen accepted earlier) | Email/password form, "Create an account" | **Locked** — not reopened. |
| 2 | Guest `/calendar` redirects to login | Guest month grid with sign-in card | **Locked** — not reopened. |
| 3 | Five-tab bar scoped to signed-in multiuser pages (tracker D20) | Five-tab bar on every guest screen | **Open decision** — M1 proposes extending it to guests. |
| 4 | New Act head built for NDPS only, from a fixture (`guest_screen4`) | One generated head for every eligible Act | **Open decision** — verified limitation; fix not authorised yet (M2 proposes). |
| 5 | Plans Plus/Pro/Max ₹199/399/1,199 (catalogue, staging, desktop prototype) | Phone prototype Core/Deep/Infinite ₹149/299/499 | **Locked** to Plus/Pro/Max; phone prototype is stale. |
| 6 | Study archive = Stage 2, PARKED (tracker) | Phone signed-in Calendar with Study-material tabs; desktop `calDesign=study` default | **Parked** — compare only against `calDesign=classic`. |
| 7 | Profile account surfaces (Sign-in method, Security, Legal, Reset/Delete) shipped in R5 | Not drawn | **Keep** — prototype omission, not a removal request. |
| 8 | Constitution dashboard content ("Welcome, Name.", Good places to begin, learning plan, tour) | Today with greeting, ring, TODAY'S PATH | **Open decision** — M4 proposes restyling without removing accepted content. |
| 9 | Legacy Bare Act page (About this Act, Chapters/Schedules tabs, accordion) for non-NDPS Acts | New head for all Acts | **Open decision** — folded into M2; schedules and About must survive in the new head. |

## 5. How the captures were made

1. Serve the export folder: `python3 -m http.server 8911 --bind 127.0.0.1`
   from the directory holding the two `.dc.html` files and `support.js`.
2. Run `make_wrappers.py <that directory>` (copy in the captures folder).
   It writes `phone.html` and `desktop.html`, which are the originals plus
   a small script that reads the query string after the design runtime
   boots: `screen=` (landing, browse, laws, act, gate, auth, today,
   calendar, profile, settings, devices, picker, playground, learn,
   roster, rollover, progress, complete, milestone), `law=ndps|bns|uapa`,
   `sheet=1`, `seed=1` (demo roster), `empty=1`, `calMonth=`, `pin=1`
   (pins the device frame to the top-left for capture) and any tweak name
   (`viewer`, `notice`, `atLimit`, `endState`, `defaultLaw`, `calDesign`,
   `showSourceStamp`, `simulateUploadFailure`, `sessionExpired`,
   `gcalSyncState`). Example:
   `http://127.0.0.1:8911/phone.html?pin=1&viewer=guest&screen=act&law=uapa`
3. Capture with headless Chrome, e.g.
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --user-data-dir=/tmp/x --window-size=400,860 --force-device-scale-factor=1 --virtual-time-budget=6000 --screenshot=out.png "<url>"`
   (desktop prototype: `--window-size=1640,960`; staging: `390,844` and
   `1280,900`). The `calDesign=classic` tweak must be set for the desktop
   calendar; its default `study` is the parked Study-archive design.
4. Signed-in staging pages cannot be captured headlessly (no session
   cookie); use a signed-in browser at the same sizes.
