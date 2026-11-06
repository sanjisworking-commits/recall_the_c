# M2-R captures (Free under `choices`, guest, Plus, Free under `monthly`)

Representative subset; the full scenario runs (every state × 390/1280 × light/dark, keyboard traces, injected failure verdicts) are summarised in `manifest-{free,guest,plus,monthly}.json`. Reproduce with `../tools/capture_m2r.py` against `dev_playground_m2r.sh` (choices) / `dev_playground_m2r_monthly.sh`.

| file | sha256 |
|---|---|
| `m2r-free_free_free0-ndps_390x844_light_head.png` | `e2ba6856c18a5a2a…` |
| `m2r-free_free_free0-ndps_390x844_light_sheet.png` | `e33e7f5ec61f9003…` |
| `m2r-free_free_free0-ndps_390x844_light_scope.png` | `a62df685a253dd37…` |
| `m2r-free_free_free0-ndps_390x844_light_fail-rolled_back.png` | `ec87354dc412cde4…` |
| `m2r-free_free_free0-ndps_1280x900_dark_head.png` | `093df43e1df1726c…` |
| `m2r-free_free_free0-ndps_1280x900_dark_sheet.png` | `3923cf90d80c27cd…` |
| `m2r-free_free_free0-ndps_1280x900_dark_fail-rolled_back.png` | `61c0b2f5b215ca65…` |
| `m2r-free_free_free0-ndps_1280x900_dark_retry-rolled_back.png` | `46e28bd96f2dac3a…` |
| `m2r-free_free_free0-ndps-unknown_1280x900_light_fail-unknown.png` | `8bf22c442d1ff13e…` |
| `m2r-free_free_free0-ndps-unknown_390x844_light_fail-unknown.png` | `3c3a7c30a1e04fe8…` |
| `m2r-free_free_free1-uapa_1280x900_light_head.png` | `3f4f0cab3df31e8e…` |
| `m2r-free_free_free1-uapa_1280x900_light_sheet.png` | `3c3a262e150a0a02…` |
| `m2r-free_free_free2-pss_390x844_dark_head.png` | `50821428a4188cbb…` |
| `m2r-free_free_free3-limit-bns_390x844_light_head.png` | `0cda4a862beb45a7…` |
| `m2r-free_free_free3-limit-bns_390x844_light_sheet.png` | `9424ab2853de53d7…` |
| `m2r-free_free_free3-limit-bns_1280x900_dark_sheet.png` | `f5bdbbc3562daded…` |
| `m2r-free_free_free3-active-ndps_1280x900_light_head.png` | `7fd3c58a6808470e…` |
| `m2r-free_free_free3-mtp_390x844_light_head.png` | `1cafc6487d512713…` |
| `m2r-free_free_free3-readd-ndps_390x844_dark_head.png` | `6595ae14d026957a…` |
| `m2r-free_free_free3-readd-ndps_390x844_dark_sheet.png` | `13709c711ff2e5da…` |
| `m2r-free_free_free3-readd-ndps_1280x900_light_sheet.png` | `7e539d9e46350e18…` |
| `m2r-free_free_free3-readd-ndps_1280x900_light_scope.png` | `2b85acca8bc86d5f…` |
| `m2r-plus_plus_bnss_1280x900_light_sheet.png` | `fa647b828abe0dac…` |
| `m2r-plus_plus_bnss_390x844_dark_sheet.png` | `2259077ae0b5ba9f…` |
| `m2r2-guest_guest_ndps_390x844_light_sheet.png` | `6b4e7880510041bf…` |
| `m2r2-guest_guest_ndps_1280x900_dark_sheet.png` | `360021e3a83bdd93…` |
| `m2r2-monthly_free_bnss_1280x900_light_head.png` | `89cd43992d0f2bb6…` |
| `m2r2-monthly_free_bnss_1280x900_light_sheet.png` | `7a4858b5030f5145…` |

`m2r2-*` files and `manifest-guest.json` / `manifest-monthly.json` were re-captured after the owner decisions of 2026-11-06 (5-11: one "Continue with Google" action on the guest sheet; 5-1: no price on the subscribe sheet or the Act-head Free note); the superseded guest sheet and monthly head/sheet captures remain in git history at `8c6b542`.
