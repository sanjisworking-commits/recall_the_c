# Playground (this branch)

**Guest = explore. Account = complete Constitution. Subscription = Playground. Tier = monthly roster capacity only** (plus 10 / pro 30 / max unlimited distinct laws **active this Playground month**). Overlay item/selection/progress is **persistent learning**, not that quota. **Playground also requires a registered device** (`PLAYGROUND_DEVICE_LIMIT = 2`, same for every tier). Constitution Learn and law reading never use this gate.

RecallC Playground is the paid learning overlay on verbatim Bare Act JSON. Tiers do not change modes, ladders, quality, or device cap. Same-month remove + re-add does not consume an extra roster slot; next month’s laws are carry-forward candidates (Keep uses a new-period slot). **Neither payment, the roster, nor device revocation may delete progress.**

| Document | Status |
|----------|--------|
| [PLAYGROUND_TWO_LAW_AUDIT.md](PLAYGROUND_TWO_LAW_AUDIT.md) | Overlay design. Cloze = architectural proof, not the finished mode set. Item/selection/progress = persistent learning, not monthly quota and not the device registry. |
| [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md) | User-type + **device registry** + **monthly roster**. **Not implemented.** See §21 for prices / Razorpay states / refunds / replacement-churn integers. Do not implement lifetime unlocks or per-tier device SKUs. |

**On this branch (proof):** Add to Playground, section selection, Cloze, revision rows, guest → sign-in. No subscription gate. No monthly roster. No device cookie. Cloze currently starts Day 1 (prototype).

**Finished train (not done):** user-type resolver (stop reading article claims for access), **device registry** (`rtc_device` + Profile → Security → Your devices), **monthly roster + rollover UI** (Keep/Remove, Add to this month, Playground full), remaining RecallC-style modes, official Learned → then revision, Razorpay lifecycle (billing clock ≠ playground month), admin override. Open §21 cells block charging live; they do not restore article entitlements or lifetime unlocks.
