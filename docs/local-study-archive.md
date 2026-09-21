# Local calendar study archive

Run the existing local launcher on port 8001 and open `/calendar`. Use **Add study material** or the **+** beside a calendar date. Supply a heading, the date you studied/revised, notes, multiple PDFs/photos, and/or one web URL per line.

Each entry appears on its original date and at **+3, +7, +15, +30 and +60 calendar days**. These are offsets from the original study date, not cumulative gaps. For example, a 21 September entry returns on 24 September, 28 September, 6 October, 21 October and 20 November. The Constitution clause ladder stays unchanged.

Click a heading to open its attachments in a dialog. Choose among attachments without leaving the calendar. PDFs use the browser PDF viewer; photos appear at full available width. Links offer an original-site button and an optional sandboxed embedded preview (some websites block embedding). Open-in-new-tab remains available when a browser cannot preview a PDF.

**Mark done** records the actual date of completion. It is available once a revision is due. Repeated clicks are idempotent; **Undo** reopens that revision. Late completion does not move future dates. Overdue revisions remain in the expandable list above the calendar, including overdue items from earlier months. Opening a file does not mark it done.

**Edit / add attachments** updates the heading and notes and appends files/links to the same entry. Existing attachments and completed revisions remain intact; its original date and activity cannot be changed by editing. To start a new cycle after studying/revising the topic again, add a new entry on that day.

## Local files and backup

With the default launcher, files live in:

```
data/progress/study-materials/
  archive.sqlite3
  files/
    <generated-id>.pdf
    <generated-id>.png
```

The SQLite file contains headings, notes, dates, original filenames, URLs and completion history. Files are copied once, using generated filenames; all revision dates point to those same copies. A URL is stored as a bookmark, not a downloaded copy of the website. Original uploaded files are not modified.

This folder is already excluded from Git by `data/progress/*`. Back up the **entire folder** with the app stopped, then restore the database and files together. Browser storage is not used. If a custom progress database is selected, the default archive is its sibling `study-materials` directory. Python integrations may override `create_app(study_materials_dir=...)`; keep any custom location outside tracked source files.

The feature is installed only for single-user mode and available through `localhost`, `127.0.0.1` or `::1`. It is not installed in multiuser mode. Uploads accept PDF, PNG, JPEG, GIF and WebP signatures, with 25 MiB per file, 100 MiB total, and at most 20 attachments per request. HEIC photos must first be exported as JPEG/PNG. Writes require the per-process token from the calendar page; reload an old tab after restarting the app.

This release schedules entries in the app calendar. It does not add desktop notifications or sync these personal files to Google Calendar.

## Verification

```
python -m pytest tests/test_study_archive.py tests/test_calendar_projection.py tests/test_calendar_bootstrap_diagnostics.py tests/test_web_app.py
```
