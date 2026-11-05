# Recall the C

Local study app for memorising the **Constitution of India** (Bare Act wording, verbatim).

Two layers:

1. **Corpus pipeline** — PDF → structured JSON → correction overlay → learning units  
2. **Learning UI** — spaced repetition over those units (Read / Cloze / Letters / Type / Recite / Card)

**Hard rules**

- Learning code must **not** mutate Docling output, the parser, or `constitution.reviewed.json` by hand.  
- Bare Act text fixes go only in [`data/corrections/corrections.json`](data/corrections/corrections.json), then regenerate.  
- Memorised card text stays Bare Act wording (no paraphrase).  
- If a diglot footer says an amendment **has been struck down by the Supreme Court**, omit that amendment’s wording from `body_text`.

Future ideas: [`docs/FUTURE.md`](docs/FUTURE.md).

---

## Sprint changelog

| Sprint / pass | Branch | Major changes |
|---------------|--------|---------------|
| Phase 1 | `cursor/constitution-pdf-pipeline-1a75` | Docling PDF extract → normalise → parse → validate; Bare Act JSON schema |
| Phase 2 | `cursor/phase-2-parser-hardening-1a75` | Structure hardening, corrections overlay, review report, fixtures |
| Sprint 1 | `cursor/sprint-1-learning-unit-generator-1a75` | Learning units generator (`ARTICLE` / `CLAUSE` / Part / Schedule) |
| Sprint 2 | `cursor/sprint-2-alphabetic-fallback-1a75` | Letter dual units + flat-body text fallback splitter |
| Sprint 3 | `cursor/sprint-3-sqlite-scheduler-1a75` | SQLite progress + spaced-repetition `ReminderEngine` |
| Sprint 4 | `cursor/sprint-4-learn-home-ui-1a75` | FastAPI Learn/Home UI + Choose whole vs letters |
| Sprint 5 | `cursor/sprint-5-browse-search-progress-1a75` | Browse article, Search deep-links, Progress totals |
| Sprint 6 | `cursor/sprint-6-design-tokens-1a75` | Design tokens / monochrome paper UI |
| Sprint 7 | `cursor/sprint-7-sheet-nav-1a75` | Sheet chrome + nav (Home / Browse / Calendar / Progress / Search) |
| Sprint 8 | `cursor/sprint-8-home-screen-1a75` | Home: due list, Continue, caught-up state |
| Hotfix | `cursor/fix-articles-1-2-1a75` | Restored Articles 1–2 Bare Act text |
| Hotfix | `cursor/fix-browse-artefacts-1a75` | Art 201/124 artefacts; exclude mis-parsed schedule “articles” |
| Hotfix | `cursor/fix-articles-44-45-1a75` | Restored Articles 44–45 |
| Hotfix | `cursor/corpus-artefact-sweep-1a75` | Global artefact scrub + more schedule exclusions |
| Sprint 9 | `cursor/sprint-9-choose-incomplete-1a75` | Choose + incomplete panels |
| Sprint 10 | `cursor/sprint-10-learn-read-1a75` | Learn Read layout |
| Sprint 11 | `cursor/sprint-11-sibling-rails-1a75` | Clause/letter sibling rails + stem |
| Sprint 12 | `cursor/sprint-12-again-tomorrow-1a75` | Again tomorrow + sticky mobile footer |
| Sprint 13 | `cursor/sprint-13-learn-card-1a75` | Card flip mode |
| Sprint 14 | `cursor/sprint-14-learn-cloze-1a75` | Cloze tap-to-reveal |
| Sprint 15 | `cursor/sprint-15-learn-letters-1a75` | Letters (first-letter) mode |
| Sprint 16 | `cursor/sprint-16-learn-type-1a75` | Type with live per-word diff |
| Sprint 17 | `cursor/sprint-17-learn-recite-1a75` | Recite blur + hold-to-peek |
| Sprint 18 | `cursor/sprint-18-recite-voice-1a75` | Recite voice accuracy (Web Speech) |
| Hotfix | `cursor/fix-articles-365-plus-1a75` | Restored / created Arts 365–395 |
| Sprint 19 | `cursor/sprint-19-calendar-1a75` | Calendar month grid |
| Sprint 20 | `cursor/sprint-20-progress-mastery-1a75` | Progress mastery map |
| Sprint 21 | `cursor/sprint-21-amendment-history-1a75` | Browse/Learn amendment notes (seed) |
| Sprint 22 | `cursor/sprint-22-explain-it-back-1a75` | Browse “Explain it back” gloss |
| Sprint 23 | `cursor/sprint-23-mac-packaging-1a75` | Mac start/stop scripts + serve LaunchAgent |
| Sprint 24 | `cursor/sprint-24-study-reminders-1a75` | `send-reminders` + ntfy |
| Sprint 25 | `cursor/sprint-25-mac-install-backup-1a75` | Bootstrap, install-all agents, progress backup |
| Sprint 26 | `cursor/sprint-26-notification-settings-1a75` | Settings: reminder cadence |
| Sprint 27 | `cursor/sprint-27-amendment-corpus-1a75` | Full amendment catalog → in-corpus seed |
| Sprint 28 | `cursor/sprint-28-mac-app-dmg-1a75` | Planned — Recall the C `.dmg` |
| Sprint 29 | `cursor/sprint-29-tables-browse-1a75` | Tables page; Browse by Parts; Home skips Part overviews |
| Sprint 30 | `cursor/sprint-30-methods-theme-1a75` | Six-method Done gate; How to use; Recall the C; Auto/Dark/Light |
| Corpus text pass | `cursor/corpus-text-pass-1a75` | Card-by-card Bare Act fixes via corrections; `prefer_article_unit`; footnote hover |
| Footer / laws / memory | `cursor/footer-laws-memory-1a75` | Footer tools; Relevant laws Browse; Memory log calendar + photos |
| Native macOS reminders | `cursor/native-macos-reminders-1a75` | `--channel macos`; digest includes Memory dues; Browse due badges |
| Browse card 1c | `cursor/browse-card-1c-1a75` | Corner ribbon, count line, In news pills, red Browse nav badge |
| Schedules reference | `cursor/schedules-reference-1a75` | Twelve read-only Schedule cards after Part XXII; designed `/browse/schedules/{slug}` pages |

---

## Technical overview

### Stack

- Python **3.10+** (3.12 preferred)  
- Corpus: Pydantic, RapidFuzz (Docling only for PDF extract: `pip install -e ".[pdf]"`)  
- App: FastAPI, Uvicorn, Jinja2, SQLite  
- Tests: Pytest (+ httpx)

### Data flow

```text
PDF → extract/normalize/parse → constitution.json
     → correct (corrections.json) → constitution.reviewed.json
     → generate-units → learning_units.json
     → serve (UI) + progress.db
```

### Important paths

| Path | Role |
|------|------|
| `data/input/constitution_bare_act.pdf` | Source PDF |
| `data/output/constitution.json` | Parsed corpus (local / gitignored) |
| `data/output/constitution.reviewed.json` | After corrections; Browse source (local / gitignored) |
| `data/output/learning_units.json` | Schedulable units (**tracked**) |
| `data/corrections/corrections.json` | Manual Bare Act overlays |
| `data/reference/text_annotations.json` | Learn Read/Card hover footnotes |
| `data/reference/judicial_evolution.seed.json` | Browse-only Judicial Evolution notes |
| `data/reference/amendments.seed.json` | Amendment timeline + learn notes |
| `data/reference/laws.seed.json` | Relevant laws Browse seed |
| `data/reference/tables/` | Tables page JSON |
| `data/progress/progress.db` | Progress, prefs, glosses, theme, Memory log (local) |
| `data/progress/memory_media/` | Memory log photos (local) |

### Package layout

```text
src/constitution_memorizer/
  extraction/ normalization/ parsing/ validation/   # PDF pipeline
  corrections/   # overlay + artefact scrub
  learning/      # unit generator
  progress/      # SQLite + ReminderEngine
  web/           # FastAPI UI
  cli.py
```

### CLI (corpus)

`correct` and `generate-units` do **not** need Docling. They need `data/output/constitution.json` from a prior extract (or skip regen and use tracked `learning_units.json`).

PDF extract / full pipeline (optional Docling extra):

```bash
pip install -e ".[pdf]"
python -m constitution_memorizer.cli pipeline --pdf data/input/constitution_bare_act.pdf --output-dir data --force
python -m constitution_memorizer.cli correct --force
python -m constitution_memorizer.cli generate-units --force
python -m constitution_memorizer.cli review-report --force
```

After editing `corrections.json` only:

```bash
python -m constitution_memorizer.cli correct --force
python -m constitution_memorizer.cli generate-units --force
```

### Learning behaviour (short)

- Split-capable clauses → Choose **whole** vs **letters** (stored in SQLite).  
- Done advances spaced repetition (`1 → 3 → 7 → 14 → 30 → 60` days → mastered).  
- Sprint 30: Done unlocks after visiting all six recall methods on that unit.  
- `prefer_article_unit` on a correction → one Learn card titled `Article N` (lettered body kept intact).  
- Word footnotes (e.g. Art 124(1) “seven”) use Read/Card hover via [`data/reference/text_annotations.json`](data/reference/text_annotations.json).

### Tests

```bash
pip install -r requirements-ci.txt && pip install -e .
pytest -m "not integration" -q
```

Full PDF/Docling integration (needs `pip install -e ".[pdf]"`): `pytest -m integration`.

---

## How to run the app

### 1. Install (once)

```bash
cd /path/to/memorize_the_c
python3.12 -m venv .venv          # or python3 (must be 3.10+)
source .venv/bin/activate
pip install -U pip
pip install -r requirements-ci.txt   # UI + tests (no Docling)
pip install -e .
```

Mac shortcut from repo root:

```bash
bash scripts/mac/bootstrap.sh
```

### 2. Units file

`data/output/learning_units.json` is committed. If missing:

```bash
# only works if constitution.json already exists locally
python -m constitution_memorizer.cli correct --force
python -m constitution_memorizer.cli generate-units --force
```

If `correct` errors with `constitution.json` not found, skip regen and use the tracked `learning_units.json` (Browse needs a local `constitution.reviewed.json`).

### 3. Serve

```bash
source .venv/bin/activate
python -m constitution_memorizer.cli serve --host 127.0.0.1 --port 8001
```

Open **http://127.0.0.1:8001/** (hard-refresh after branch switches).  
Stop: `Ctrl+C`.

Mac: `open scripts/mac/start-ui.command` · `bash scripts/mac/stop-ui.sh`.

Do **not** set `MULTIUSER_ENABLED` on 8001 — that launcher stays local SQLite.

Hosted multi-user (Supabase + Postgres) is **http://127.0.0.1:8010/** via `open scripts/mac/start-multiuser.command`. See [`docs/multiuser-auth.md`](docs/multiuser-auth.md).

### 4. Optional Mac agents / reminders

```bash
# Default: macOS Notification Center (no ntfy required)
bash scripts/mac/install-all-agents.sh

# Optional phone push:
# export REMINDER_CHANNEL=ntfy
# export NTFY_TOPIC=cm-yourname-study
# bash scripts/mac/install-all-agents.sh
```

Cadence + In news articles: **http://127.0.0.1:8001/settings**.  
Digest covers Constitution due/overdue units **and** Memory log reviews.  
Dry-run: `python -m constitution_memorizer.cli send-reminders --channel console --dry-run`.  
macOS test: `python -m constitution_memorizer.cli send-reminders --channel macos --at "$(date +%Y-%m-%dT%H:%M)"`.  
Backup: `bash scripts/mac/backup-progress.sh` → `~/Documents/ConstitutionMemorizerBackups/`.

### UI map

| Route | Purpose |
|-------|---------|
| `/` | Home — due + continue |
| `/learn/{unit_id}` | Six recall modes |
| `/browse` | Parts → articles, then the twelve Schedules |
| `/browse/schedules/{slug}` | One Schedule (read-only Bare Act reference) |
| `/tables` | Quick-reference tables |
| `/laws` | Relevant laws (Browse) |
| `/memory` | Memory log calendar + revision sheets |
| `/search` | Article / clause / letter jump |
| `/progress` | Mastery map |
| `/calendar` | Constitution month schedule |
| `/settings` | Reminder cadence, In news, theme |

---

## Disclaimer

Study aid only — **not** legal advice. Verify against an official Bare Act publication.
