# M1 — review of the hosted paid-tier evidence pack (Cursor, 2026-10-19)

Reviewer: Claude, 2026-10-20 (revised the same day after the three paid archives were re-supplied). Requested by `CLAUDE-REVIEW.md` (SHA-256 `369366b3…9529c85`): four reviews assessed separately, then one pass / changes-required decision against `M1.md` (M1-F01–F11, M1-V01–V05, M1-A01–A04). The pack is evidence for M1's hosted validation on staging deployment `3b37f8947c05577b57af93a2a53f1ac5539c4e3a` (`recallc-playground-staging`, GitHub deployment `7168307529`). It is not payment validation and does not expand M1 into paid features.

## 0. What was actually reviewable

| File | Received | Reviewable |
|---|---|---|
| `manifest.json` (SHA-256 `e2aa3beb…91ed94`) | 288 rows: deployed SHA, capture time, account label and UUID, tier, route, viewport, theme, filename, SHA-256, `top_nav` / `phone_bar` booleans, result, known defects; `device_readback`, `accounts` with subscription ids | yes — the row log is the basis of this review |
| `free-pre-grant.zip` (SHA-256 `ff090fbf…0358c4`) | 132 PNGs, every file's hash matches its manifest row | yes |
| `plus.zip` (SHA-256 `ec751fb1…279c6574`), `pro.zip` (`92395f11…42fc3ffc`), `max.zip` (`4a9dbed5…c24258a`) | first delivery was 0 bytes each; re-supplied 2026-10-20: 52 PNGs per tier, every file's SHA-256 matches its manifest row, no file outside the manifest | yes |

The pack is 288 PNGs, and the manifest has 288 rows: 132 Free + 52 Plus + 52 Pro + 52 Max. Every PNG hashes to its own row. An earlier total of 420 counted the 132 Free PNGs a second time on top of those 288 rows (132 + 288 = 420). There is no further set of 132 files.

Each paid zip is 52 PNGs: 25 at 1280×900 (23 shell captures, including the device-limit Playground, plus the two `before-device-cap` shots), 22 at 390×844, and 5 other Browse widths (320, 560, 561, 768, 844×390). Across Plus, Pro and Max that is 75 + 66 + 15 = 156.

**Inspection method, one statement:** 21 filenames were opened. The other 267 rows were checked only through manifest fields (`top_nav`, `phone_bar`, `result`, `known_defects`). That is a record check. It is not an image inspection, and it is not a claim that all 156 paid images were inspected. Where a manifest field and an opened image cover the same route, they agree. Filenames opened: Free `browse_1280`, `dashboard_1280`, `dashboard_390`, `playground-add-uapa_1280`, `browse_561` (5); Plus `browse_1280`, `dashboard_1280`, `settings_1280`, `calendar_1280`, `profile_390`, `browse_561`, `before-device-cap/playground_1280` (7); Pro `dashboard_1280`, `browse_390`, `playground_1280` (device gate), `before-device-cap/playground_1280`, `before-device-cap/profile_1280` (5); Max `dashboard_1280`, `dashboard_390_dark`, `laws-ndps_390`, `before-device-cap/playground_1280` (4).

Two statements in the pack are stale and should be corrected before it is filed: `m1_accepted: false` / "M1 is still unaccepted" — the owner accepted M1 on 2026-10-19 with documented exceptions (M1.md §8); and "the hosted paid states remain unverified" is exactly what this pack addresses.

## 1. Review A — M1 shell and navigation (the checklist's subject)

Against M1-F01–F03, F07 (as far as captures show it), F10, F11 and V04:

| Evidence | Finding |
|---|---|
| Free pre-grant, 132 PNGs, 24 §4 routes × 390/1280 × light/dark + responsive set | Shell as accepted locally and in the hosted guest matrix: five-tab phone bar on the phone routes that carry it (Settings/Search/Landing/Add without, as approved), top nav with the current tab marked at 1280, account slot "Sanjali · Free account" on every shared-shell page (M1-F10 holds; checked on Browse, Dashboard, Add). Spot-checked images: `browse_1280_light`, `dashboard_390_light`, `playground-add-uapa_1280_light`, `browse_561_light`. |
| Paid rows: 25 at 1280×900, 22 at 390×844, and 5 other Browse widths, per tier | Opened images show the desktop shell (brand, five-tab top nav with the current tab filled, account slot with avatar, name and subtitle) on Plus Browse/Today/Settings/Calendar, Pro Today, and Max Today, and the device-limit Playground for Pro; the five-tab phone bar on Pro Browse 390, Max NDPS 390 and Max Today 390 dark; no phone bar on the opened 1280 images. **DV-21 for subscribers** is verified only where a nav is actually visible on an opened image: the device-limit page of `/playground`, and the three `before-device-cap` Playground homes. A nav on the device-limit page does not verify the blocked subscriber Playground, the plans screen, or Add. Those destinations were not captured and remain **unverified**. The other 1280 shell-capture rows (69) record `top_nav` true and `phone_bar` false; the six `before-device-cap` rows have no nav fields. `pass_phone_shell` is 66 rows at 390×844 plus 6 Browse rows at 320 and 560. Those fields are the record check in §0. |
| Pins | Free pack `main87 / mob106 / pg49` = the M1 deployment. |

Verdict A: **shell PASS for Free, Plus, Pro and Max on the captured routes**; the subscriber Playground, plans and Add screens are not part of this verdict (unverified).

## 2. Review B — known M1 defects

| Item | Status in this pack | Decision already on record |
|---|---|---|
| 561–720 px duplicate top nav + phone bar (signed-in) | reproduced: Free `/browse`, `/laws/ndps`, `/settings`, `/search`, `/terms` at 561 and 720 (`fail_duplicate_nav` ×10); Plus/Pro/Max `/browse` at 561 | **approved deferral** — M1 accepted 2026-10-19 with this as a documented exception → M1b (M1.md §8, roadmap). Not a new finding. |
| Avatar overlapping Browse content at 561 (Free `browse_561`) | reproduced (visible in the Free image: the account avatar floats over the page title) | part of the same signed-in-shell exception → M1b. Also seen at 768 in the M2 baseline (`M2-evidence.md` §5.3). |
| Real browser zoom, screen-reader smoke, automated scan | not in this pack ("Untested") | **approved deferral** → M1b. Unchanged. |
| M1-F07 traversal, M1-F06 flag-off, M1-V02/V03 pixel diff | not in this pack | covered locally in M1-evidence (F06/F07 by tests and local traces; V02/V03 by the local comparison). Hosted repetition was never required by the checklist. |

Verdict B: **no new M1 defect; every open item is an approved, recorded deferral.** Nothing to resolve inside M1.

## 3. Review C — paid-page content and layout (record under the owning milestone)

| Finding (manifest result) | Owner milestone | Note |
|---|---|---|
| Account slot says "Free account" for Plus, Pro and Max on Browse, Laws, NDPS, Article 14, Devices, Search, Terms, and on one Playground row (`fail_tier_label` ×52: 42 at 1280×900 on those seven routes, 1 Playground row at 1280×900, and 9 Browse rows at 561/768/844) | **DV-20 acceptance exception.** An M5 fix is a proposed deferral, pending the owner. It is not a pass. | DV-20 requires the plan name once subscribed. That requirement fails on these routes. M1-F10, the Free-account subtitle, is a separate sentence and still holds on the Free pack. On `/browse`, `/laws*` and `/playground` the frozen subtitle chain prints "RecallC Plus" only for the active-Plus predicate and "Free account" otherwise, so Pro and Max never match it. One suggestion is that the Plus grant did not present as `subscription_status == "active"` on those routes. That remains an unconfirmed hypothesis. The grant method and the subscription row would settle it. Today, Calendar, Profile and Settings show the plan name and do not use that chain. |
| Pro `/playground` capacity indicator extends beyond the sidebar card (`fail_layout`) | **M7 (Playground home)** | layout defect, not payment proof |
| Pro `/profile` reads "30 30 laws / month" (`fail_duplicate_count`) | **M5 (Profile)** | cause: the subscription card sets `stat_big` to the limit and `stat_label` to `catalogue_limit_label(limit)`, which already begins with the limit (`playground/view.py`); the card prints both. Plus shows the same shape ("10 · 10 laws / month", `profile_390`); Max prints "Unlimited laws / month" with no big figure. Every numeric tier is affected, not only Pro. |
| Browse body for subscribers still prints the Free plan banner "Free plan — pick any 3 Articles to learn. All 3 slots free. · Unlock all" (Plus `browse_1280`; the manifest did not flag it) | **M3 (Browse)** | page copy keyed to the Free disposition; not shell, not M1 |
| Desktop Today body renders as unstyled text for Free, Plus and Max (`dashboard_1280`): no cards, bare links | **M4 (Today)** | the frozen signed-in desktop Today, identical in the Free pre-grant capture; Pro shows the plan-prompt variant styled as a card. Not a paid-tier regression and not M1 |
| Max `/playground` header "Free account" while the body shows the Unlimited home (`fail_tier_label`) | same DV-20 exception as the first row | same unconfirmed hypothesis as the first row |
| Plus `/playground` captured with a free device slot: subscriber home, 0 of 10, header "RecallC Plus" | M7 reference | recorded as pass |

Verdict C: the subscriber "Free account" subtitle is an unmet DV-20 requirement, recorded in §5 as an acceptance exception. Moving the fix to M5 is a proposed deferral. The Browse Free-plan banner (M3), the unstyled desktop Today body (M4), the Profile limit duplication (M5), and the Pro Playground capacity overflow (M7) sit with those milestones.

## 4. Review D — entitlements (which tier was signed in)

| Evidence | Finding |
|---|---|
| `accounts`: Plus = the former Free account (UUID `2093aa58…`, subscription `2f967e11…`), Pro `50cc6c08…` / `4b0aaa22…`, Max `1134a7d0…` / `a04780d7…` | three distinct subscription records, one per tier |
| Tier chrome: Today, Calendar, Profile, Settings show "RecallC Plus / Pro / Max"; Profile cards "Active Plus (10) / Pro (30) / Max (unlimited)"; period "17 November" matches stored expiry `2026-11-16T20:30Z` (02:00 IST) | consistent with the intended tier on each login |
| `device_readback`: 0 devices after the grants; two active web devices per account registered 20:32:08–20:33:53Z (Chrome on Linux + "Web browser"); still 2/2/2 after the shell pass; nothing revoked | the Playground device gate on a third browser (`blocked_device_limit` ×3) is the device entitlement enforcing its cap; it is neither an M1 defect nor a pass |
| `payment_integration_verified: false` | correct: grants are not payments. Nothing here validates Razorpay, renewal, expiry, pause or halt |

Verdict D: **the intended tier was signed in on each account.** Opened images show "RecallC Plus" on Plus Today, Settings and Calendar, "RecallC Pro" on Pro Today and the pre-cap Profile, and "RecallC Max" on Max Today. Profile period text and Devices "2 of 2" are the manifest and `device_readback`. A Devices PNG is not in the 21-filename list.

## 5. Decision against the M1 checklist

**PASS for the captured shell routes, with two exceptions recorded against M1 (DV-20 for subscribers; DV-21 subscriber destinations unverified)** — nothing else changed:

- The shell criteria hold for Free, Plus, Pro and Max on the captured routes under the method in §0 (21 filenames opened; the other 267 rows by manifest record). The signed-in exceptions reproduced (561–720 px duplicate navigation, avatar overlap; zoom, screen reader and scan not run) are the deferrals the owner approved on 2026-10-19 for M1b.
- **Exception to record against M1 (DV-20, M1-F10's companion requirement that the plan name shows once subscribed):** on staging the account slot reads "Free account" for Plus, Pro and Max on Browse, Laws, NDPS, Article 14, Devices, Search, Terms and the device-limit page. This requirement is **not met** for subscribers. Routing the fix to M5 is a proposed deferral for the owner to approve, not a pass. The grant-status explanation for the Plus login is a hypothesis, unconfirmed.
- **Exception to record against M1 (DV-21 for subscribers):** a visible nav on the device-limit page, and the three pre-cap Playground homes, are the only subscriber Playground checks. The blocked subscriber Playground, plans, and Add remain unverified, as do the other themes and widths of the subscriber Playground.
- Recorded under their owning milestones (§3), as proposed deferrals: the subscriber "Free account" subtitle fix (M5, see the DV-20 exception above), the Browse Free-plan banner for subscribers (M3), the unstyled desktop Today body (M4, frozen state), the Profile limit duplication for every numeric tier (M5), the Pro Playground capacity overflow (M7).
- Corrections to the pack before filing: `m1_accepted: false` and "M1 is still unaccepted" are stale (accepted 2026-10-19 with exceptions); the first delivery's three empty archives are superseded by the verified re-delivery (hashes in §0).
- Not covered and still open: Playground, plans and Add for paid tiers at every theme and width (blocked by the device cap; a recapture needs one device revoked per account — a staging write, not done); expired, halted, paused, renewal and Razorpay — none of which this pack claims.

This is the reviewer's decision against the checklist. It changes nothing about M1's acceptance of 2026-10-19 and authorises no merge, deployment, grant, device revocation or recapture.
