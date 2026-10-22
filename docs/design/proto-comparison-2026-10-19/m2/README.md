# M2 evidence — Bare Act head family (LOCAL / PRELIMINARY)

Companion to `docs/design/milestones/M2-evidence.md`. Candidate `pg-m2-act-head` @ `a146dff`; baseline `pg-m1-guest-shell` @ `9281f27`.

- `frozen/` — baseline captures (light viewport; guest and Free for every route, Plus / Plus-active / expired / halted for the head and Add rows). Prefix `frozen_<tier>_…`, `frozen-active_plus_…`.
- `candidate/` — the same matrix at `a146dff` (`cand_<tier>_…`), plus `_sheet.png` after the first `[data-pg-sheet]` trigger is clicked.
- `responsive/` — 320/560/561/720/768/844×390 light candidate captures (NDPS, UAPA, BNSS, signed-in Free) and the frozen 561/768 signed-in captures used to show the floating-avatar artefact predates M2.
- `states/` — chapter expanded, About open, focused row, focused schedule link (both widths; the OS theme of the capture host, dark).
- `keyboard/` — Enter-opens-chapter and sheet-open captures from the keyboard trace (`manifests/candidate_keyboard_trace.json`).
- `proto/` — the 18 Oct prototype wrapper states for the Act screen and the Add sheet, every viewer, both surfaces.
- `manifests/` — one manifest per capture run (route, viewer, width, theme, status chain, head probe, SHA-256 per PNG) and `all_captures_sha256.json`, the hashes of every PNG captured (1,502: light, dark, full-page, regression routes) including those not committed here.
- `tools/` — the capture, state, keyboard, prototype and table scripts, the route lists and the test-rewrite contract.

Captured with headless Google Chrome 155.0.8059.82 over CDP (DPR 1) against the local dev launcher; sign-in through the dev fake provider; no cookie or token was written to any file.
