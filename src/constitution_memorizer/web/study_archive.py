"""Local study files and fixed-date revision history, separate from clause progress."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

OFFSETS = (3, 7, 15, 30, 60)
MAX_FILE = 25 * 1024 * 1024
MAX_BATCH = 100 * 1024 * 1024


def checked_link(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "Links must be full http:// or https:// URLs without credentials."
        ) from None
    if len(value) > 4000:
        raise ValueError("Link is too long.")
    return value


def file_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"%PDF-"):
        return ".pdf", "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise ValueError("Choose a PDF, JPEG, PNG, GIF or WebP file.")


class StudyArchive:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.files = self.root / "files"
        self.files.mkdir(exist_ok=True)
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS study_entry (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, studied_on TEXT NOT NULL,
                    notes TEXT NOT NULL, activity TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS study_asset (
                    id TEXT PRIMARY KEY, entry_id TEXT NOT NULL REFERENCES study_entry(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, media_type TEXT NOT NULL, storage_key TEXT, url TEXT);
                CREATE TABLE IF NOT EXISTS study_review (
                    entry_id TEXT NOT NULL REFERENCES study_entry(id) ON DELETE CASCADE,
                    offset_days INTEGER NOT NULL, completed_on TEXT NOT NULL,
                    PRIMARY KEY (entry_id, offset_days));
            """)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.root / "archive.sqlite3", timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self, entry_id: str):
        with self.db() as conn:
            row = conn.execute(
                "SELECT * FROM study_entry WHERE id=?", (entry_id,)
            ).fetchone()
            if row is None:
                raise KeyError(entry_id)
            entry = dict(row)
            assets = conn.execute(
                "SELECT * FROM study_asset WHERE entry_id=? ORDER BY rowid", (entry_id,)
            ).fetchall()
            entry["assets"] = [
                {k: a[k] for k in ("id", "name", "media_type", "url")} for a in assets
            ]
            done = {
                r["offset_days"]: r["completed_on"]
                for r in conn.execute(
                    "SELECT * FROM study_review WHERE entry_id=?", (entry_id,)
                )
            }
        start = date.fromisoformat(entry["studied_on"])
        entry["reviews"] = [
            {
                "offset": d,
                "due_on": (start + timedelta(days=d)).isoformat(),
                "completed_on": done.get(d),
            }
            for d in OFFSETS
        ]
        return entry

    def list_all(self):
        with self.db() as conn:
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM study_entry ORDER BY studied_on DESC, rowid DESC"
                )
            ]
        return [self.get(i) for i in ids]

    def save(self, title, studied_on, notes, activity, uploads, links, entry_id=None):
        title = title.strip()
        if not title or len(title) > 200:
            raise ValueError("Enter a heading of 1–200 characters.")
        if len(notes) > 20000:
            raise ValueError("Notes must be under 20,000 characters.")
        start = date.fromisoformat(studied_on)
        if start > date.today():
            raise ValueError(
                "Choose the date you actually studied or revised (today or earlier)."
            )
        if activity not in {"Studied", "Revised"}:
            raise ValueError("Choose Studied or Revised.")
        # Validate the full schedule before any writes.
        start + timedelta(days=OFFSETS[-1])
        links = [checked_link(v) for v in links if v.strip()]
        if len(uploads) + len(links) > 20:
            raise ValueError("Add at most 20 attachments at a time.")
        if (
            any(len(data) > MAX_FILE for _, data in uploads)
            or sum(len(data) for _, data in uploads) > MAX_BATCH
        ):
            raise ValueError("Files are limited to 25 MB each and 100 MB per upload.")
        prepared = [(name, data, *file_type(data)) for name, data in uploads]
        if entry_id:
            self.get(entry_id)
        else:
            entry_id = uuid4().hex
        written = []
        try:
            with self.db() as conn:
                conn.execute(
                    "INSERT INTO study_entry VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, notes=excluded.notes",
                    (entry_id, title, start.isoformat(), notes, activity),
                )
                for name, data, suffix, mime in prepared:
                    asset_id = uuid4().hex
                    key = asset_id + suffix
                    path = self.files / key
                    with path.open("xb") as f:
                        written.append(path)
                        f.write(data)
                    conn.execute(
                        "INSERT INTO study_asset VALUES (?,?,?,?,?,NULL)",
                        (
                            asset_id,
                            entry_id,
                            Path(name.replace("\\", "/")).name[:255],
                            mime,
                            key,
                        ),
                    )
                for url in links:
                    conn.execute(
                        "INSERT INTO study_asset VALUES (?,?,?,?,NULL,?)",
                        (uuid4().hex, entry_id, url, "text/uri-list", url),
                    )
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return self.get(entry_id)

    def complete(self, entry_id: str, offset: int, done: bool):
        entry = self.get(entry_id)
        if offset not in OFFSETS:
            raise ValueError("Unknown revision day.")
        due = date.fromisoformat(entry["studied_on"]) + timedelta(days=offset)
        if done and due > date.today():
            raise ValueError("This revision is not due yet.")
        with self.db() as conn:
            if done:
                conn.execute(
                    "INSERT OR IGNORE INTO study_review VALUES (?,?,?)",
                    (entry_id, offset, date.today().isoformat()),
                )
            else:
                conn.execute(
                    "DELETE FROM study_review WHERE entry_id=? AND offset_days=?",
                    (entry_id, offset),
                )
        return self.get(entry_id)

    def asset_file(self, asset_id):
        with self.db() as conn:
            row = conn.execute(
                "SELECT * FROM study_asset WHERE id=?", (asset_id,)
            ).fetchone()
        if row is None or not row["storage_key"]:
            raise KeyError(asset_id)
        path = (self.files / row["storage_key"]).resolve()
        if path.parent != self.files.resolve() or not path.is_file():
            raise KeyError(asset_id)
        return path, row["media_type"], row["name"]

    def calendar_context(self):
        by_day, overdue = {}, []
        today = date.today().isoformat()
        for entry in self.list_all():
            base = {"id": entry["id"], "title": entry["title"]}
            by_day.setdefault(entry["studied_on"], []).append(
                dict(base, label=entry["activity"], done=True)
            )
            for review in entry["reviews"]:
                item = dict(
                    base,
                    label=f'Day {review["offset"]}',
                    done=bool(review["completed_on"]),
                    **review,
                )
                by_day.setdefault(review["due_on"], []).append(item)
                if review["due_on"] < today and not review["completed_on"]:
                    overdue.append(item)
        return {
            "study_by_day": by_day,
            "study_overdue": sorted(overdue, key=lambda r: r["due_on"]),
        }


def install_study_archive(app, root: Path):
    """Only installed for the local single-user launcher; never on hosted multiuser."""
    archive = StudyArchive(root)
    app.state.study_archive = archive
    token = secrets.token_urlsafe(32)
    app.state.study_token = token

    def local_only(request: Request):
        if request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise HTTPException(
                403, "Study files are available only through localhost."
            )
        if request.method != "GET" and not secrets.compare_digest(
            request.headers.get("X-Study-Token", ""), token
        ):
            raise HTTPException(403, "Reload the calendar before saving.")

    router = APIRouter(
        prefix="/api/study-materials", dependencies=[Depends(local_only)]
    )

    def get(entry_id):
        try:
            return archive.get(entry_id)
        except KeyError:
            raise HTTPException(404, "Study material not found.") from None

    @router.get("/{entry_id}")
    def detail(entry_id: str):
        return get(entry_id)

    async def save(title, studied_on, notes, activity, files, links, entry_id=None):
        try:
            if entry_id:
                old = get(entry_id)
                studied_on, activity = old["studied_on"], old["activity"]
            if len(files) > 20:
                raise ValueError("Add at most 20 files at a time.")
            uploads, total = [], 0
            for upload in files:
                content = await upload.read(MAX_FILE + 1)
                total += len(content)
                if len(content) > MAX_FILE or total > MAX_BATCH:
                    raise HTTPException(
                        413, "Files are limited to 25 MB each and 100 MB per upload."
                    )
                uploads.append((upload.filename or "Attachment", content))
            return archive.save(
                title,
                studied_on,
                notes,
                activity,
                uploads,
                links.splitlines(),
                entry_id,
            )
        except (ValueError, OverflowError) as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            for upload in files:
                await upload.close()

    @router.post("")
    async def create(
        title: str = Form(...),
        studied_on: str = Form(...),
        notes: str = Form(""),
        activity: str = Form("Studied"),
        files: list[UploadFile] = File(default=[]),
        links: str = Form(""),
    ):
        return await save(title, studied_on, notes, activity, files, links)

    @router.post("/{entry_id}")
    async def update(
        entry_id: str,
        title: str = Form(...),
        notes: str = Form(""),
        files: list[UploadFile] = File(default=[]),
        links: str = Form(""),
    ):
        return await save(title, "", notes, "", files, links, entry_id)

    @router.post("/{entry_id}/reviews/{offset}")
    def complete(entry_id: str, offset: int, done: bool = Form(True)):
        get(entry_id)
        try:
            return archive.complete(entry_id, offset, done)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/files/{asset_id}")
    def media(asset_id: str):
        try:
            path, mime, name = archive.asset_file(asset_id)
        except KeyError:
            raise HTTPException(
                404, "The file is missing from the local study folder."
            ) from None
        return FileResponse(
            path,
            media_type=mime,
            filename=name,
            content_disposition_type="inline",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    app.include_router(router)
