# Playground — design handoff

`Playground.dc.html` is a **design-only state demonstrator** for the finished Playground UX. Open it in a browser next to `support.js`. All styles are inline on the elements (read values straight off the markup); tokens are CSS variables (`--pg-*`) set on the page root so the theme toggle can swap them.

## Scoring and scope rule

- This file earns **0 Stage 1 points**. It is not a milestone, not a template, and not evidence for any tracker row.
- It **must not reopen roster math**. Capacity, same-month remove/re-add, Keep/Remove on rollover, pending, and device rules are locked in `docs/PLAYGROUND.md` and `docs/PAYMENT_ENTITLEMENT_AUDIT.md` (M1–M5). The prototype only visualises them. If a screen here seems to disagree with those docs, the docs win.
- The law list is illustrative. Production eligibility stays `list_playground_eligible_laws()` (NDPS, BNS, BNSS today).

## Preview controls (outside the device frame)

Labelled **"Design preview — not part of the product."** Never ship them.

- **Scenario:** Active Plus 8/10, Active Plus 10/10, Empty Plus, Pro, Max, Historical law, Guest, Free account, Pending, Halted, Paused, Expired, Device limit, Device revoked, Replacement limit, Cancel at period end, Upgrade, Downgrade scheduled, Resubscribed, Rollover. Picking *Historical law* jumps to Law states; picking *Rollover* jumps to the Rollover screen.
- **Screen:** Home, Roster, Rollover, Law workspace, Law states, Add confirm, Remove confirm.
- **Viewport:** Mobile 390×844 (bottom tab bar) / Desktop ~1040px (top tabs, two-column law grid, persistent capacity rail on the right).
- **Theme:** Light / Dark. Dark swaps the tokens only; it is not a new brand.

Remove, Add back, Add to Playground, and Keep/Remove are live in the prototype, so the capacity rules can be tried by clicking.

## M6 production implementation

M6 production implementation uses the design artifact.
The preview controls remain design-only.
M1–M5 contracts remain unchanged.

Runtime: FastAPI + Jinja + vanilla JS + [`/static/playground.css`](../../src/constitution_memorizer/web/static/playground.css). Tokens follow `--pg-*` on `html[data-theme]`. There is no separate Playground theme preference.

**Locked prototype questions (do not reopen):**

- Pending + same-month Add back is allowed because it consumes 0 new slots. Pending still blocks a new law, a historical law not consumed this month, and rollover Keep into a new period.
- Undecided rollover is not carried forward, consumes 0 target-period spaces, and remains an unresolved candidate until explicit Keep.

**Status badges (production facts):**

| Badge | Backend fact |
|---|---|
| Not started | no selected sections, or progress without Cloze complete and not due |
| Learning | overlay `learned_count` / `cloze_done` (Cloze-complete is **not** product Learned) |
| Due | `due_count > 0` or `next_revision <= today` |
| Mastered | existing overlay `status = mastered` only |
| Learned | reserved; M8 owns the product transition |

**Scenario parity (production, not the design preview switcher):**

| Prototype scenario | Production surface | Backend trigger | Expected UI | Test |
|---|---|---|---|---|
| Active Plus 8/10 | `GET /playground` | plus, 8 consumed | `8 of 10 laws` / `2 spaces available` | `test_plus_home_8_of_10_capacity_and_shell` |
| Active Plus 10/10 | `GET /playground` | plus, 10 consumed | `10 of 10 laws` / `Playground full for {month}` | `test_plus_home_full_10_of_10` |
| Empty Plus | `GET /playground` | plus, 0 used | `0 of 10 laws` / empty copy | `test_empty_plus_home` |
| Pro | `GET /playground` | pro | `N of 30 laws` | `test_pro_and_max_capacity_copy` |
| Max | `GET /playground` | max | `N laws this month` / `Unlimited` | `test_pro_and_max_capacity_copy` |
| Historical law | `GET /laws/{id}` | overlay, inactive this month | Progress saved / Add to this month | `test_historical_saved_progress_copy` |
| Guest | `GET /playground` 303; `GET /laws/{id}` | unauthenticated | Sign in, never checkout | `test_guest_law_cta_is_sign_in_not_checkout` |
| Free account | `GET /playground`, `GET /laws/{id}` | signed-in, not subscribed | View Playground plans | `test_free_account_law_cta_is_plans_not_constitution_lock` |
| Pending | `GET /playground` | `status=pending` | PaymentStateBanner; roster usable; new add blocked; Add back allowed | `test_pending_banner_blocks_new_and_keeps_roster` |
| Halted | `GET /playground` | `status=halted` | EntitlementGate, Manage subscription | `test_hard_gates_copy_and_ctas` |
| Paused | `GET /playground` | `status=paused` | EntitlementGate | `test_hard_gates_copy_and_ctas` |
| Expired | `GET /playground` | paid_period_ended | Your Playground is paused | `test_hard_gates_copy_and_ctas` |
| Device limit | `GET /playground` | 3rd installation | Manage devices, no Subscribe | `test_device_gates_do_not_offer_subscribe` |
| Device revoked | `GET /playground` | revoked this device | This device no longer has Playground access | `tests/test_devices_m4b.py` |
| Replacement limit | `GET /playground` | 4th replacement / 30d | Too many recent device changes | `tests/test_devices_m4c.py` |
| Cancel at period end | `GET /playground` | `cancel_at_period_end` | Plan ends {date} | `test_cancel_upgrade_welcome_banners` |
| Upgrade | `GET /playground?notice=upgrade` | confirmed upgrade | Your Playground now supports {limit} laws | `test_cancel_upgrade_welcome_banners` |
| Downgrade scheduled | `GET /playground` | `scheduled_tier` lower | Pro until {date} / Changes to Plus | `test_cancel_upgrade_welcome_banners` |
| Resubscribed | `GET /playground?notice=welcome` | welcome/empty+saved | Welcome back | `test_cancel_upgrade_welcome_banners` |
| Rollover | `GET /playground/roster/next` | previous-month candidates | Keep / Remove / Undecided radiogroup | `test_rollover_keep_remove_undecided_and_browse` |

Seven prototype screens map as: Home `/playground`; Roster `/playground/roster`; Rollover `/playground/roster/next`; Law workspace `/playground/laws/{id}`; Law states distributed across `/laws` and Bare Act; Add confirm `GET /playground/laws/{id}/add`; Remove confirm `GET /playground/roster/{id}/remove`.

## Semantic class names

| Class | Region |
|---|---|
| `PlaygroundShell` | Device frame (header, banner, main, tabs, sheet overlay) |
| `PrimaryTabs` | Today · Browse · Playground · Calendar · Profile (`--bottom` mobile, `--top` desktop). Active tab has `aria-current="page"` |
| `RosterCapacity` | Planning bar + counts (`--hero`, `--rail`, `--compact`, `--next`, `--preview`) |
| `LawCard` | Law card on Home and Browse (`--compact` for removed/saved rows) |
| `LawStatusBadge` | Text + small mark. Status: Not started, Learning, Learned, Due, Mastered. Membership: In Playground, In September Playground, Progress saved, Removed this month, Playground full this month, Law updated |
| `DueBadge` | "3 due today", "Due today", "2 overdue" — ink outline, never red |
| `ProgressSummary` | Due today / Overdue / Sections learned grid (also on gates as saved progress) |
| `RosterManager` | `/playground/roster` |
| `RolloverCandidate` | One `/playground/roster/next` row with its Keep/Remove segmented control |
| `EntitlementGate` | Replaces the Playground body for Guest, Free, device, and payment blocks |
| `PaymentStateBanner` | Shell banner (pending, upgrade, resubscribed); `--quiet` on the Home hero (cancel at period end, scheduled downgrade); `--inline` on the Rollover screen (downgrade) |
| `CanonicalText` | Learning prompt + VERBATIM TEXT reveal (`LearningPrompt`, `VerbatimText` children) |
| `TrustMark` | "Verbatim, always." with the § mark |

## Screens and exact copy

**Home.** Eyebrow "My Playground", h1 "September", "8 of 10 laws" / "2 spaces available", planning bar with a legend ("7 in Playground", "1 removed this month · space still used", "2 available"). CTAs "Browse laws" and "Manage September". TrustMark "Verbatim, always. Every provision you learn is the Bare Act text, word for word." Then ProgressSummary, "In Playground this month" cards (the first card with work due is "Up next" and is the only solid primary button), "Removed this month", "Saved progress" (not in Playground this month), and a "Plan next month" row.
- Full: "10 of 10 laws" / "Playground full for September" + "Every law in it stays fully usable. Laws removed this month can be added back without using a space." Nothing is greyed out.
- Empty: "Your September Playground is empty" / "Add laws you want to learn this month. Your saved progress stays with you even when a law leaves Playground."
- Max: "8 laws this month" / "Unlimited"; the bar shows filled blocks plus an open dashed tail. Never "8 / ∞".
- Card: "NDPS Act" / "Narcotic Drugs and Psychotropic Substances Act, 1985" / "12 sections selected" / "8 learned" / DueBadge "3 due today" / "Continue" · "Read Bare Act" · "Manage". The Arbitration Act card shows "Law updated" + "Review affected provisions".

**Law states (Browse).** h1 "Laws", lede "Choose what to learn in September. Saved progress stays with each law, in or out of Playground." Groups: In your September Playground, Removed this month, Saved progress, More laws. The same badges are used everywhere:
- Never added → "Add to Playground".
- Active, not started → "In Playground" + "Start learning". Active in progress → "Continue".
- Previously studied → "Progress saved" + "You studied this law previously. Add it to September to continue where you left off." + "Add to this month".
- Learned / Mastered → the status badge (Mastered is the same quiet badge with a ringed mark).
- Month full → "Playground full this month" badge; the action becomes "Plan next month".

Wording never used: Unlock again, Repurchase, Restart, Reset progress.

**Add confirm.** Plus/Pro: "Add BNS to September?" / "This will use 1 of your 10 law spaces for September." / "You’ll have N spaces remaining." (the *Resubscribed* scenario, 3 of 10 used, gives the spec's "6 spaces remaining"). A bar preview marks the space it will use. Actions "Add to Playground" · "Cancel". For a previously studied law it adds "Your saved progress comes with it: …". Max: "Add BNS to September Playground?" with no quota numbers. Full → "Playground full this month" sheet. Pending → "Adding new laws is temporarily unavailable" sheet.

**Remove confirm.** "Remove from September" / "Your progress will be saved." / "This does not free a law space this month." · "Remove from September" · "Cancel". After removal the row moves to "Removed this month" with "Removed this month" + "Progress saved" + "Add back", and the count stays the same. Add back uses no new space ("… is back in September. No extra space used.").

**Roster manager** (`/playground/roster`). "September Playground" / "8 of 10 used" / "2 remaining" plus a rules strip: "Removing a law saves its progress. It doesn’t free a space this month, and adding it back doesn’t use another one." Sections "Active this month" (Continue · Read · Remove) and "Removed this month" (Add back). A planning row "Plan next month" / "Manage October — choose what continues."

**Rollover** (`/playground/roster/next`, October). "Your October Playground" / "Continue with last month’s laws, or make room for something new." / "6 of 10 planned" / "4 spaces available". A key explains Keep ("Uses one October space."), Remove ("No October space. Progress stays saved."), and Undecided ("Not chosen yet."). Each candidate has a Keep | Remove segmented control (`role="radiogroup"`):
- Keep = solid ink.
- Remove = inset outline on a tinted row.
- Undecided = dashed row with an "Undecided" badge.

Keep is disabled once October is full, with "October is full. Remove another law to keep this one." Footer: "4 spaces available for new laws" + "Add new laws whenever you’re ready. Spaces don’t need to be filled now." + "Browse laws". *Downgrade scheduled* adds "Your plan now supports 10 laws. Choose which 10 to keep for October."

**Law workspace.** "NDPS Act" + badge "In September Playground"; actions "Read Bare Act" · "Manage sections". Below:
- CanonicalText: "Up next · Learning prompt" (the prompt text + "Continue"), visually separate from the "VERBATIM TEXT" block. That block shows the Section 8 citation, a blockquote with the Bare Act wording, a "Hide/Show verbatim text" toggle (`aria-expanded`), and "Verbatim, always. Bare Act wording, never rewritten."
- Section rows: § number, title, status badge, "Due today", optional "Law updated" + "Review affected provisions", and "Continue".

For a historical law (TPA) the rows say "Read" and the header offers "Add to this month". Only a launch point; no learn modes are designed here.

**Shell placeholders.** Today / Calendar / Profile: "{Tab} already exists in RecallC; this prototype does not design revision behavior."

## Gates and payment states

Hard gates replace the body and hide the primary tabs.

| Scenario | Copy | Actions |
|---|---|---|
| Guest | "Sign in to build your law-learning Playground." + "How Playground works" (4 steps) | Sign in |
| Free account | "Your RecallC account already includes the complete Constitution." / "Playground adds structured learning for laws." + How it works | View Playground plans |
| Device limit | "Device limit reached" / "Your subscription supports Playground on up to 2 registered devices." | Manage devices · Back to Constitution |
| Device revoked | "This device no longer has Playground access." | Manage devices |
| Replacement limit | "Too many recent device changes" / "For account security, new Playground devices are temporarily limited after several replacements." / "Your Constitution access and saved progress are unaffected." | Contact support · Back to Constitution |
| Halted | "Payment retries have stopped" / "Playground learning is paused. Your progress is saved." + saved-progress summary | Manage subscription · Back to Constitution |
| Paused | "Playground subscription paused" / "Your laws and learning progress are saved." + summary | Manage subscription |
| Expired | "Your Playground is paused" / "Your roster and progress are still here. Resume a Playground plan to continue learning." + summary | View Playground plans · Back to Constitution |

Non-blocking states:
- **Pending:** a banner over a fully usable Playground: "Payment retry in progress" / "You can continue your current Playground. Adding new laws is temporarily unavailable." + "Manage subscription". Add actions for new or historical laws show as disabled, with the reason in text.
- **Cancel at period end:** a quiet hero line "Plan ends 28 September" · "Manage subscription". Learning looks normal.
- **Upgrade:** banner "Your Playground now supports 30 laws." No celebration.
- **Downgrade scheduled (home):** "Pro until 28 September" · "Changes to Plus next billing cycle". The current month stays at 30.
- **Resubscribed:** banner "Welcome back" / "Your saved law progress is ready. Build your September Playground."; historical laws show "Progress saved".

## Tokens

Light: ink `#141414`, muted `#6b6b6b`, faint `#9a9a9a`, hairline `#dcdcdc`, page `#ececea`, paper `#fff`, destructive `#B42318`, subtle `#f7f7f6`.
Dark (preview): ink `#ecebe6`, muted `#a8a59e`, faint `#7d7a73`, hairline `#34322e`, page `#0f0e0d`, paper `#1a1917`, destructive `#E4776B`, subtle `#232220`.

Fraunces 700 for display, Source Sans 3 for body. Square corners, 1px hairlines, shadow only on the outer frame. No red for due or overdue; destructive red is reserved and unused on these screens (removal is not destructive).

## Accessibility

- Visible `:focus-visible` outline (2px ink, 2px offset) on every button and select.
- Status is always text plus a mark, never colour alone.
- Mobile tap targets are at least 44px (primary buttons 48px, tabs 60px).
- Iconic controls carry `aria-label` (dismiss ×, Read/Remove per law); tab icons are `aria-hidden` with visible labels.
- Sheets are `role="dialog"` with `aria-modal`; the capacity bars are `role="img"` with a full-sentence `aria-label`.
- Reduced motion: nothing is animated, and there are no transitions to disable. Keep it that way. The helmet includes a `prefers-reduced-motion` guard in case one is added.

## Prototype simplifications / open questions

- Only NDPS Act and TPA have section data **in the prototype**, so those Continue targets are illustrative. Production Continue uses real overlay selection and the existing Cloze launch path.
- The two previously open prototype questions are **locked by M5** and implemented in M6: Undecided rollover is not auto-carried; pending permits same-month Add back.
