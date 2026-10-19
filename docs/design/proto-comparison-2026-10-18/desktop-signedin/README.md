# Signed-in desktop baseline — staging @ 5d89fbd (Free account)

Captured by Cursor on 2026-10-18 (README in the source archive) against
`https://recallthec-production.up.railway.app`, deployment
`32971cbf-1519-46b3-9637-8b4405d219e4` (verified 2026-10-18 to serve
`5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8`). Account: the owner's Google
account, free plan ("Sanjali · Free account"). Viewport 1280×900 CSS px;
every PNG header reads 1280×900; theme Light.

Source archive: `69ynqs.zip`, 634,929 bytes, SHA-256
`e76b824763eeecf29ad0c69e14fd6248ca02df3f154a4057b1ae44c117c044fb`,
extracted into an isolated folder; contents verified as 11 PNGs plus one
UTF-8 README, nothing else. Claude (this session) viewed every image and
confirmed each shows the signed-in state and the stated route.

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

Observations recorded while verifying (for M1/M5/M6, not acted on):

- S04: the signed-in NDPS head is the fixture (6 Chapters, three rows +
  Schedule) with "Subscribe to use Playground" — DV-2 applies to signed-in.
- S05: opened by direct URL, the Add sheet renders as a standalone page
  with the legacy footer (Tables / Relevant laws / Playground / Settings /
  Contact us / theme chip) and only the brand + account slot in the
  header; in-page opening from the Act head remains unverified (DV-15).
- S06/S07: gate and plans pages show only the brand and account slot in
  the header (no main nav) — differs from the desktop prototype gate,
  which keeps the full top nav.
- S08: the signed-in dashboard body is unstyled-list content under the
  new top nav (accepted dashboard functions; restyle is M4).
- S09: the signed-in calendar already shows Study-archive controls
  ("My material", "Add task", "+ Add study material for this day") on
  staging; the classic prototype has none. Record for M6 scope review
  against the parked Stage 2 decision.
- Not in this set (still outstanding for the desktop baseline): `/laws/uapa`
  (legacy Act page, signed-in), `/profile/security/devices`,
  `/playground?stage=plans&tier=plus` (selected state), `/laws` phone-only
  CTA check is N/A on desktop.

Companion in-session captures from Claude's browser pane (phone 375×812
crops) live in `../phone-signedin/`; the `proto_desk_*_signedin.png` files
in this folder are the prototype references (`viewer=signedIn`).
