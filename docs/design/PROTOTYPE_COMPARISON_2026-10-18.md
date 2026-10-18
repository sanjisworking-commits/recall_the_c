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
prototype screens per width). Signed-in screens could not be compared:
staging signs in only through Google, and that sign-in has to be done by
the account owner. §3 lists those rows ready to run.

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
| D8 | Sign in | `/login` | DEVIATION DV-10 | Split dark/light sign-in page vs the prototype's centred form. |
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

## 3. Signed-in rows — pending

These need the account owner signed in on staging (Google). Prototype
captures exist for every row in both widths and can be regenerated with
§5. Routes are from `5d89fbd`.

| Prototype screen | Staging route | Prototype state |
|---|---|---|
| Bare Act head (Plus) — "+ Add to Playground" | `/laws/uapa` | `viewer=plus&screen=act&law=uapa` |
| Add sheet — act vs sections | `/playground/laws/uapa/add` | `…&sheet=1` |
| Section picker — clause depth | `/playground/laws/uapa/sections` | `screen=picker` |
| Playground — activated laws | `/playground` | `screen=playground&seed=1` |
| Playground — empty | `/playground` (no laws) | `screen=playground&empty=1` |
| Learn — six modes | start from the Act page `/playground/laws/{law}` (modes are entered through POST `…/learn/{mode}/start`) | `screen=learn&seed=1` |
| Today (signed in) | `/dashboard` | `screen=today&seed=1` |
| Calendar (saved recall) | `/calendar` | `screen=calendar&seed=1` (desktop: add `calDesign=classic`) |
| Roster — manage this month | `/playground/roster` | `screen=roster&seed=1` |
| Rollover — next month | `/playground/roster/next` | `screen=rollover` |
| Act progress | `/playground/laws/{law}` | `screen=progress&seed=1` |
| Section learned | `/playground/laws/{law}/sections/{n}/learned` | `screen=complete` |
| Act mastered | `/playground/laws/{law}/mastered` | `screen=milestone` |
| Profile / Settings (signed in) | `/profile`, `/settings` | `viewer=plus` |
| Devices | `/profile/security/devices` | `screen=devices` |
| Subscription states | `/profile`, Act head | desktop `viewer=` expired / halted / paused / deviceLimit / deviceRevoked / replacementLimit; `notice=` pending / cancelAtEnd / upgrade / downgradeScheduled / resubscribed |

Checkout cannot be exercised on staging (no Razorpay keys); speech modes
fall back to typed input (no Deepgram key).

## 4. Deviations

| ID | Where | What differs | Classification |
|---|---|---|---|
| DV-1 | Phone guest shell | `/browse`, `/laws`, `/dashboard`, `/laws/uapa`, `/laws/bns` show the legacy four-tab bar (`mobile-tabbar is-guest`: Browse/Search/Learn/Sign in); `/laws/ndps`, `/playground`, `/profile` show the five-tab bar; `/settings` shows none. Prototype: five-tab bar on every guest screen. | Scope gap — tracker D20 limited the five-tab HTML to signed-in multiuser pages; the 18 Oct prototypes extend it to guests. |
| DV-2 | `/laws/ndps` (guest, both widths) | `guest_screen4` is `ndps_guest_head()` from `web/guest_bareact_head.py`: constant title, meta "6 Chapters · Sections 1–83 · Schedule" and three constant rows. The Act JSON (`web/ndps_act_final.json`) has eight chapters; the full accordion is in the HTML but hidden for guests; the fixture rows have no `href`. Prototype: eight linked rows, "8 Chapters". | **Defect** — guest head must be built from the loaded Act, with navigable rows. |
| DV-3 | `/laws/uapa`, `/laws/bns` (guest) | Only NDPS gets the new guest head (`if bare.slug == "ndps"`). Other Acts render the legacy Bare Act page (ABOUT THIS ACT, Chapters/Schedules tabs, accordion open on Chapter I). Prototype uses one head for NDPS, BNS and UAPA. | Scope gap — generalise the head to every eligible Act (folds into DV-2's fix). |
| DV-4 | Desktop shell | `/laws/uapa`, `/laws/bns`, `/dashboard`, `/settings`, `/login` use the legacy desktop shell (Home/Browse/Search/Learn + "Learning as guest" + footer). Prototype: new top nav on every screen. | Scope gap. |
| DV-5 | `/dashboard` (guest) | Legacy dashboard content and copy on both widths. Prototype: greeting + date + "Reading as a guest", "Nothing due yet." card with Sign in / Browse the Bare Acts. | Scope gap. |
| DV-6 | `/calendar` (guest) | Redirects to login. Prototype shows the empty month with a sign-in card. | Behavioural gap — decide whether guests should see the calendar. |
| DV-7 | `/settings` (guest) | Phone: STUDY card missing, no bottom tab bar. Desktop: legacy shell and layout (no guest card, no STUDY card, no back link). | Scope gap. |
| DV-8 | `/laws` | Phone: legacy template with per-card CTAs, no subtitle, no search field. Desktop: NDPS "6 Chapters" vs prototype "8 Chapters"; UAPA card lacks "· Schedule". | Phone: scope gap. Counts: content decision — NDPS has six numbered chapters plus IIA and VA; the prototype counts eight. Pick one and apply it to catalogue, head and card. |
| DV-9 | `/playground` gate, desktop | "Create an account" secondary button missing. | Minor. |
| DV-10 | `/login` | Different page entirely (dark hero + Google + phone vs light Google + email/password). Email/password auth does not exist in the app. | Intentional divergence to confirm — the login page is a previously accepted screen. |
| DV-11 | `/` | Phone: CTAs pinned to the bottom instead of under the tagline. Desktop: footer line missing. | Minor. |
| DV-12 | `/browse` phone | Legacy page (see P2). Desktop already matches. | Scope gap. |
| DV-13 | `/profile` phone | Copy: "Sign in to save progress and unlock the Constitution learning experience." vs "Sign in to save progress." | Minor copy. |

Prototype-side issues noticed while driving it (not code defects): the
gate screen spells "offical"; the phone Playground month still reads
"12 Aug – 11 Sep"; the roster says NDPS has "129 sections" while the Act
head says 83.

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
