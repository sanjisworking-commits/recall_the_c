# M1 — review of the hosted paid-tier evidence pack (Cursor, 2026-10-19)

Reviewer: Claude, 2026-10-20. Requested by `CLAUDE-REVIEW.md` (SHA-256 `369366b3…9529c85`): four reviews assessed separately, then one pass / changes-required decision against `M1.md` (M1-F01–F11, M1-V01–V05, M1-A01–A04). The pack is evidence for M1's hosted validation on staging deployment `3b37f8947c05577b57af93a2a53f1ac5539c4e3a` (`recallc-playground-staging`, GitHub deployment `7168307529`). It is not payment validation and does not expand M1 into paid features.

## 0. What was actually reviewable

| File | Received | Reviewable |
|---|---|---|
| `manifest.json` (SHA-256 `e2aa3beb…91ed94`) | 288 rows: deployed SHA, capture time, account label and UUID, tier, route, viewport, theme, filename, SHA-256, `top_nav` / `phone_bar` booleans, result, known defects; `device_readback`, `accounts` with subscription ids | yes — the row log is the basis of this review |
| `free-pre-grant.zip` (SHA-256 `ff090fbf…0358c4`) | 132 PNGs, every file's hash matches its manifest row | yes |
| `plus.zip`, `pro.zip`, `max.zip` | **0 bytes each** (SHA-256 of the empty string). The 156 paid rows in the manifest have filenames and hashes, but no image reached this machine | **no** — the paid screenshots could not be looked at |

Consequence: the paid-tier reviews below rest on the manifest's recorded results and the code on the deployed branch, not on inspected images. M1-V01 makes the original PNGs authoritative, so **no pass can be given on the paid rows until the three archives are re-supplied**. The review of each row's *classification* is complete; the review of each row's *image* is not.

Two statements in the pack are stale and should be corrected before it is filed: `m1_accepted: false` / "M1 is still unaccepted" — the owner accepted M1 on 2026-10-19 with documented exceptions (M1.md §8); and "the hosted paid states remain unverified" is exactly what this pack addresses.

## 1. Review A — M1 shell and navigation (the checklist's subject)

Against M1-F01–F03, F07 (as far as captures show it), F10, F11 and V04:

| Evidence | Finding |
|---|---|
| Free pre-grant, 132 PNGs, 24 §4 routes × 390/1280 × light/dark + responsive set | Shell as accepted locally and in the hosted guest matrix: five-tab phone bar on the phone routes that carry it (Settings/Search/Landing/Add without, as approved), top nav with the current tab marked at 1280, account slot "Sanjali · Free account" on every shared-shell page (M1-F10 holds; checked on Browse, Dashboard, Add). Spot-checked images: `browse_1280_light`, `dashboard_390_light`, `playground-add-uapa_1280_light`, `browse_561_light`. |
| Paid rows at 1280 (33 per tier) and 390 (22 per tier), light and dark | Manifest: `top_nav=True, phone_bar=False` on every 1280 row; `phone_bar=True` on the 390 shell routes, `pass_phone_shell` ×72. DV-21 holds for subscribers on `/playground` where captured (device-gated rows still show `top_nav=True`). Consistent with M1's local non-guest cohort pass (M1-evidence §10.4). **Images not inspected (empty archives).** |
| Pins | Free pack `main87 / mob106 / pg49` = the M1 deployment. |

Verdict A: **shell PASS on the Free pack; paid rows consistent with PASS on the manifest, image check outstanding.**

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
| Desktop account slot says "Free account" on Browse, Laws, NDPS, Article 14, Devices, Search, Terms for Plus, Pro and Max (`fail_tier_label` ×48, + 3 at 561/768/844) | **M5 (account copy)**, flagged for M1b's shell pass | Already recorded in M1-evidence §10.4 for Pro/Max/paused/pending as "the fallback subtitle 'Free account' — account copy is M5". Cause on the deployed branch: on `/browse`, `/laws*` and `/playground` the subtitle uses the frozen path-gated chain, which prints "RecallC Plus" only when the active-Plus predicate holds and "Free account" otherwise; Pro and Max never match it. That the **Plus** login also reads "Free account" there means the predicate (`is_subscribed and tier == "plus" and can_open_playground and subscription_status == "active"`) did not hold for the granted account on those routes — most likely the grant does not present as `subscription_status == "active"`, which the Today/Calendar/Profile/Settings chrome does not require. The grant method and the account's subscription row would settle it. This is **not** an M1-F10 failure: F10 is written for the Free account. It is a DV-20 follow-up: the plan name once subscribed. |
| Pro `/playground` capacity indicator extends beyond the sidebar card (`fail_layout`) | **M7 (Playground home)** | layout defect, not payment proof |
| Pro `/profile` reads "30 30 laws / month" (`fail_duplicate_count`) | **M5 (Profile)** | cause: the subscription card sets `stat_big` to the limit and `stat_label` to `catalogue_limit_label(limit)`, which already begins with the limit (`playground/view.py`); the card prints both. Max shows "Unlimited laws / month" without a big figure, so only tiers with a numeric limit duplicate it. |
| Max `/playground` header "Free account" while the body shows the Unlimited home (`fail_tier_label`) | M5 / M1b (same subtitle rule) | same cause as the first row |
| Plus `/playground` captured with a free device slot: subscriber home, 0 of 10, header "RecallC Plus" | M7 reference | recorded as pass |

Verdict C: **four defects recorded under M5/M7; none is an M1 criterion.**

## 4. Review D — entitlements (which tier was signed in)

| Evidence | Finding |
|---|---|
| `accounts`: Plus = the former Free account (UUID `2093aa58…`, subscription `2f967e11…`), Pro `50cc6c08…` / `4b0aaa22…`, Max `1134a7d0…` / `a04780d7…` | three distinct subscription records, one per tier |
| Tier chrome: Today, Calendar, Profile, Settings show "RecallC Plus / Pro / Max"; Profile cards "Active Plus (10) / Pro (30) / Max (unlimited)"; period "17 November" matches stored expiry `2026-11-16T20:30Z` (02:00 IST) | consistent with the intended tier on each login |
| `device_readback`: 0 devices after the grants; two active web devices per account registered 20:32:08–20:33:53Z (Chrome on Linux + "Web browser"); still 2/2/2 after the shell pass; nothing revoked | the Playground device gate on a third browser (`blocked_device_limit` ×3) is the device entitlement enforcing its cap; it is neither an M1 defect nor a pass |
| `payment_integration_verified: false` | correct: grants are not payments. Nothing here validates Razorpay, renewal, expiry, pause or halt |

Verdict D: **the intended tier was signed in on each account, on the manifest's evidence; the paid images are still needed to confirm the labels as displayed.**

## 5. Decision against the M1 checklist

**Changes required — on the pack, not on M1.**

- M1 criteria: nothing in this pack fails a criterion that M1 was accepted on. The shell holds for Free (images) and for Plus/Pro/Max (manifest), the signed-in exceptions reproduced are the ones already approved for M1b, and the paid-page findings belong to M5 and M7.
- What blocks a **pass** on the paid rows: `plus.zip`, `pro.zip` and `max.zip` arrived empty. Re-supply the three archives (the manifest already carries each file's SHA-256, so they can be verified on arrival), and this review's §1 and §4 image checks can be completed. Correct `m1_accepted` and the two stale sentences in `CLAUDE-REVIEW.md`.
- Recommended records: the "Free account" subtitle for subscribers on the path-gated pages as the DV-20 follow-up under M5 (with the grant-vs-subscription question answered); the Pro capacity overflow under M7; the Profile "30 30" duplication under M5; the device-cap recapture only if the owner wants the Playground/plans/Add paid rows re-shot — that needs one device revoked per account, which is a staging write and was not done.

Nothing in this review changes M1's acceptance of 2026-10-19 or authorises any merge, deployment, grant or recapture.
