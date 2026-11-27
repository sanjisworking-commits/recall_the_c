# M8-S — shared style: evidence

Record: `docs/design/milestones/M8-S.md`. Local evidence only.

| Path | What it holds |
|---|---|
| `../m8/tools/probe_style_m8s.py` | The page probe used here: contrast of every visible text node against the first opaque background behind it, target sizes, horizontal scroll, script exceptions. Each low-contrast reading carries its selector path and colour pair and is sorted into *failing*, *disabled* (inside a control that is `:disabled` or `aria-disabled`) or *hidden* (visually-hidden, or drawn in its own background colour). It also measures named controls (`.pg-back`, `.pg-sheet-close`, `.cal-si-dialog-head button`). Headless Chrome over CDP with the dev fake sign-in; `--guest` skips the sign-in. |
| `../m8/tools/build_decisions_doc.py` | Generator of `docs/design/milestones/ENTITLEMENT_DECISIONS.md` (not part of this batch's evidence). |
| `routes-*.json` | The routes probed: `plus` (Playground home, Manage laws, next month, Remove, Act progress, picker, six Learn modes, completion pages, Add sheet, Profile, billing, Devices, the Calendar editor dialog), `gate` (Free under `monthly`: gate, Profile, Add sheet), `guest`, `error`, `letters`, `calendar-free` / `calendar-plus`. A route's `scope` narrows the measured region; `open` clicks an entry point first; `shot` lists the frames to keep. |
| `01-baseline-079257e/` | Probe output on the accepted M7b head, before any edit: `style-probe-plus-monthly.json`, `-free-monthly`, `-guest`, `-error`, `-free-choices-calendar`; `frames/`. The `error` rows inside `style-probe-plus-monthly.json` measured a JSON response, not the error page, and are not used — the error page's baseline is `style-probe-error.json`. The gate, guest, error and Calendar baselines were taken from the `pg-m7b` worktree at `079257e` after the edit had begun here. |
| `02-candidate/` | The same probes on the candidate, plus `style-probe-plus-monthly-letters.json` (Learn `letters` re-measured after its own rule was added; it replaces the `learn-letters` rows of `style-probe-plus-monthly.json`) and `frames/`. |

Frames are named `<label>-<route>-<width>-<theme>.png`. Each baseline frame has a candidate frame of the same name.

The populated server is `m7/tools/serve_populated_m7.py` (throwaway SQLite database, fixture subscription row, no provider). A paid account registers a device per new session with a limit of two, so the server is restarted between probe runs.
