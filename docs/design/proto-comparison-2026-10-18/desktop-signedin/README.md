# Signed-in desktop baseline — staging @ 5d89fbd (Free account)

Captured by Cursor on 2026-10-18 (README in the source archive) against
`https://recallthec-production.up.railway.app`, deployment
`32971cbf-1519-46b3-9637-8b4405d219e4` (verified 2026-10-18 to serve
`5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8`). Account: the owner's Google
account, free plan ("Sanjali · Free account"). Viewport 1280×900 CSS px;
every PNG header reads 1280×900; theme Light.

S01–S11 source archive: `69ynqs.zip`, 634,929 bytes, SHA-256
`e76b824763eeecf29ad0c69e14fd6248ca02df3f154a4057b1ae44c117c044fb`,
extracted into an isolated folder; contents verified as 11 PNGs plus one
UTF-8 README, nothing else. Claude viewed every image and confirmed each
shows the signed-in state and the stated route.

S12–S14 were captured live on 2026-10-19 from the same signed-in Chrome
session against the same deployment (not in `69ynqs.zip`). Viewport
1280×900 CSS px; every PNG header reads 1280×900; theme Light; identity
`guest=false`, name Sanjali. S14 href is
`/playground?stage=plans&tier=plus` with the Plus card selected
(`selected=true`). Cursor viewed all three images.

| Row | Route | File | Size | SHA-256 |
|---|---|---|---|---|
| S01 | `/` | `signed_in_s01_landing_1280x900.png` | 1280×900 | `1c443461db59cb31d9c759f38c39ef3197f5cf27446336fd200db12517c650c3` |
| S02 | `/browse` | `signed_in_s02_browse_1280x900.png` | 1280×900 | `c56cf4e6433add099224ccbc02af2dcddd91383530289a5efaaf5bf54aa80563` |
| S03 | `/laws` | `signed_in_s03_laws_1280x900.png` | 1280×900 | `0e9599732ffc54655b9be66efac866008b7215d4b22f12c7f0940422ce567f5c` |
| S04 | `/laws/ndps` | `signed_in_s04_bareact_1280x900.png` | 1280×900 | `561da8e1462171f96bf14b0570944e66d33c5c8a91344db76ae11adfdfe0a2a1` |
| S05 | `/playground/laws/ndps/add` | `signed_in_s05_add_1280x900.png` | 1280×900 | `579ba6cd137e3267613ab243b58c29ad2e2fedfd292b72e33ec301c603d35644` |
| S06 | `/playground` | `signed_in_s06_playground_1280x900.png` | 1280×900 | `caaf75a610c225be707e0e1ef59ea5f262f8f6993e878c83b79caf1f232f2954` |
| S07 | `/playground?stage=plans` | `signed_in_s07_playground_gate_1280x900.png` | 1280×900 | `cd7d4f218f8b0ee7f78fe54e2f34bc0d435980d5340dd307bca9d61491c3448b` |
| S08 | `/dashboard` | `signed_in_s08_today_1280x900.png` | 1280×900 | `17c2e9f96dd7f5188f974eac0cc80c0bbc5ac15de520a14dd20750cdf2d94164` |
| S09 | `/calendar` | `signed_in_s09_calendar_1280x900.png` | 1280×900 | `2bc66409fa2f5e8100858cfe367099b6e8df962057b4b4e80ce3862db3bc6ec5` |
| S10 | `/profile` | `signed_in_s10_profile_1280x900.png` | 1280×900 | `84071d339d0d399b7fffc5273457ac5572dbb73df20867ee238a6ba2ae213271` |
| S11 | `/settings` | `signed_in_s11_settings_1280x900.png` | 1280×900 | `598abb2ac1a027bfe02a1a69bffc91a70900a3d88002b34b86363881ba62881f` |
| S12 | `/laws/uapa` | `signed_in_s12_uapa_1280x900.png` | 1280×900 | `f702beb9f49953a49b6b7acf8a133a9d2d9344254f9d82cdf0cdf949d80e2651` |
| S13 | `/profile/security/devices` | `signed_in_s13_devices_1280x900.png` | 1280×900 | `1dc6978735abb102d02df1007cf12d21bc925ba3f4615b06180b94842d1a80d4` |
| S14 | `/playground?stage=plans&tier=plus` | `signed_in_s14_plans_plus_1280x900.png` | 1280×900 | `033b5bd19792a8bbc1a03c914eac1d50a66776cae1759445b4ff7fbe5e4ecb13` |

Observations recorded while verifying (for M1/M5/M6, not acted on):

- S04: the signed-in NDPS head is the fixture (6 Chapters, three rows +
  Schedule) with "Subscribe to use Playground" — DV-2 applies to signed-in.
- S05: opened by direct URL, the Add sheet renders as a standalone page
  with the legacy footer (Tables / Relevant laws / Playground / Settings /
  Contact us / theme chip) and only the brand + account slot in the
  header; in-page opening from the Act head remains unverified (DV-15).
- S06/S07/S14: gate and plans pages show only the brand and account slot in
  the header (no main nav) — differs from the desktop prototype gate,
  which keeps the full top nav. S14 confirms the two-step selector
  (DV-14): with `tier=plus` the Plus card is outlined and the CTA reads
  "Continue with Plus".
- S08: the signed-in dashboard body is unstyled-list content under the
  new top nav (accepted dashboard functions; restyle is M4).
- S09: the signed-in calendar already shows Study-archive controls
  ("My material", "Add task", "+ Add study material for this day") on
  staging; the classic prototype has none. Record for M6 scope review
  against the parked Stage 2 decision.
- S12: signed-in UAPA is the legacy Bare Act page (ABOUT THIS ACT,
  Chapters/Schedules accordion, Chapter I expanded) under the new
  five-tab desktop nav with Browse active, plus "Unlock Playground ·
  from ₹199 / month." / "Subscribe to use Playground". DV-3 applies to
  signed-in. Not re-scored against the M0 S-row.
- S13: empty Devices state ("0 of 2 devices", "No active devices…")
  under the new top nav with Profile active. The account slot shows
  "Sanjali" without the "Free account" subtitle that other signed-in
  pages carry.
- `/laws` phone-only CTA check is N/A on desktop. No remaining
  outstanding signed-in desktop states from the M1 prerequisite list.
  Subscribed/paid flows remain unverified (DV-17 / DV-18).

Companion in-session captures from Claude's browser pane (phone 375×812
crops) live in `../phone-signedin/`; the `proto_desk_*_signedin.png` files
in this folder are the prototype references (`viewer=signedIn`).
