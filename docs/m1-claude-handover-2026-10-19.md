# M1 evidence handover — request a checklist decision

This package does **not** accept M1. Four ZIPs are evidence for review. They are not a pass.

Deployed SHA: `3b37f8947c05577b57af93a2a53f1ac5539c4e3a` (`recallc-playground-staging / production`, GitHub deployment `7168307529`). Payment integration was not exercised and is **not** verified.

Please assess the four reviews separately, then give one **pass / changes required** decision against the existing M1 checklist (`docs/design/milestones/M1.md`: M1-F01–F11, M1-V01–V05, M1-A01–A04). Do not expand M1 into every paid feature. Do not treat these ZIPs as acceptance.

| Review | What to decide |
|---|---|
| M1 shell/navigation | Whether the captured shell meets the agreed checklist |
| Known M1 defects | Resolve, or record an explicit approved deferral. Open items include 561–720 px duplicate top and phone navigation, the avatar overlapping Browse content, real browser zoom, screen-reader smoke, and the automated accessibility scan |
| Paid-page content/layout | Record under the milestone that owns it, unless it is already DV-20/DV-21. Pro capacity overflow and the duplicated “30 30 laws / month” are layout defects, not payment proof |
| Entitlements | Confirm the intended tier was signed in. This is not payment validation |

## Packs

| ZIP | What it is |
|---|---|
| `free-pre-grant.zip` | The existing signed-in Free matrix, captured `2026-10-19T18:42:44Z` **before** the Plus grant. 132 PNGs. Not recreated. That login is now Plus |
| `plus.zip` | Plus shell routes at 390 and 1280, light and dark, plus Browse responsive widths, plus the earlier Playground/Profile shots from when a device slot was still open |
| `pro.zip` | Same shell set for Pro |
| `max.zip` | Same shell set for Max. The earlier Playground shot shows the Unlimited home; the header on that shot says Free account |

Shared row log: `manifest.json` (SHA, capture time, UUID, tier, route, viewport, theme, filename, result, known defects).

Guest hosted matrix and responsive set remain the earlier §10 captures. They were not repeated.

## Coverage

**Completed**

- Free, pre-grant: 24 section 4 routes at 390 and 1280, light and dark, plus the responsive width set. Account was Free. Pins `main87` / `mob106` / `pg49`.
- Plus, Pro, Max desktop shell at 1280, light and dark, on Browse, Laws, NDPS, Article 14, Today, Calendar, Profile, Settings, Devices, Search, and Terms.
- Same routes at 390, light and dark (phone shell).
- Browse at 320, 560, 561, 768, and 844×390, light, for each paid tier.
- Tier check: Today, Calendar, Profile, and Settings show RecallC Plus / Pro / Max. Profile cards show Active Plus (10), Pro (30), and Max (unlimited).
- Plus Playground, captured with a free device slot: subscriber home, 0 of 10, header RecallC Plus.
- Max Playground, same pass: Unlimited subscriber home.

**Failed**

- Desktop account slot says **Free account** on Browse, Laws, NDPS, Article 14, Devices, Search, and Terms for Plus, Pro, and Max. DV-20 asks for the plan name once subscribed.
- Pro Playground header says Free account, and the capacity indicator extends past the sidebar card.
- Pro Profile renders **30 30 laws / month**.
- Max Playground header says Free account while the body shows Unlimited.
- 561 px Browse still shows the top nav and the phone bar together for Plus, Pro, and Max. The Free capture already showed the avatar overlapping the title. These stay open.
- A fresh browser now hits the Playground device gate for all three paid accounts (`data-hard-gate`, 2 of 2). That is enforcement, not an M1 shell pass.

**Untested**

- Repeating Playground, plans, and Add at every theme and width after the device cap filled. Those routes were not recaptured, because devices were not cleared.
- Guest matrix (already recorded earlier; not in these ZIPs).
- Mouse, touch, and keyboard traversal (M1-F07), flag-off (M1-F06), prototype pixel diff (M1-V02/V03), 200% zoom, screen reader, and automated scan (M1-A01–A04).
- Expired, halted, paused, renewal, and Razorpay payment.

## Device counts

Immediately after the grants, `user_device` was 0 for all three accounts. The first paid browser pass then registered two active web devices on each account (Chrome on Linux and Web browser) between `2026-10-19T20:32:08Z` and `20:33:53Z`. Counts were read again after the later shell capture and were still 2, 2, and 2. Nothing was revoked. “2 of 2” on Profile is that inventory, not a stale label from before the browser checks.

## Period

Stored expiry `2026-11-16T20:30Z` is 17 November at about 02:00 IST. The Profile sentence “17 November” matches that.
