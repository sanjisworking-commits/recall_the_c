"""Local archive integration: durable files, fixed dates and isolated write endpoints."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.study_archive import StudyArchive

MINI_UNITS = Path(__file__).parent / "fixtures/learning/mini_units.json"
PNG = b"\x89PNG\r\n\x1a\nexample"
PDF = b"%PDF-1.7\nexample"


@pytest.fixture
def client(tmp_path):
    app = create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.headers["X-Study-Token"] = app.state.study_token
        yield client


def add(client, **overrides):
    data = dict(
        title="Monsoon notes",
        studied_on="2026-01-30",
        activity="Studied",
        links="https://example.com/reading",
    )
    data.update(overrides)
    response = client.post(
        "/api/study-materials",
        data=data,
        files=[
            ("files", ("notes.pdf", PDF, "application/pdf")),
            ("files", ("photo.png", PNG, "image/png")),
        ],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_files_dates_calendar_and_restart(client, tmp_path):
    entry = add(client)
    assert [r["due_on"] for r in entry["reviews"]] == [
        "2026-02-02",
        "2026-02-06",
        "2026-02-14",
        "2026-03-01",
        "2026-03-31",
    ]
    assert len(entry["assets"]) == 3
    asset = entry["assets"][0]
    response = client.get("/api/study-materials/files/" + asset["id"])
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    page = client.get("/calendar?year=2026&month=2")
    assert page.status_code == 200
    assert 'data-study-id="' + entry["id"] + '"' in page.text
    assert "study-viewer" in page.text and "Day 15" in page.text
    reopened = StudyArchive(tmp_path / "study-materials")
    assert reopened.get(entry["id"]) == entry
    assert reopened.asset_file(asset["id"])[0].read_bytes() == PDF


def test_completion_is_idempotent_and_preserves_future_dates(client):
    entry = add(client)
    url = f"/api/study-materials/{entry['id']}/reviews/3"
    first = client.post(url, data={"done": "true"}).json()
    again = client.post(url, data={"done": "true"}).json()
    assert first == again
    assert first["reviews"][0]["completed_on"] == date.today().isoformat()
    assert [r["due_on"] for r in first["reviews"]] == [
        r["due_on"] for r in entry["reviews"]
    ]
    assert (
        client.post(url, data={"done": "false"}).json()["reviews"][0]["completed_on"]
        is None
    )
    assert (
        client.post(url.replace("/3", "/14"), data={"done": "true"}).status_code == 400
    )


def test_edit_keeps_assets_and_adds_more_without_reset(client):
    entry = add(client)
    client.post(f"/api/study-materials/{entry['id']}/reviews/3", data={"done": "true"})
    response = client.post(
        "/api/study-materials/" + entry["id"],
        data={
            "title": "Edited heading",
            "notes": "Summary",
            "links": "https://example.org/new",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["studied_on"] == entry["studied_on"]
    assert len(updated["assets"]) == 4
    assert updated["reviews"][0]["completed_on"] is not None


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:secret@example.com",
        "not a URL",
    ],
)
def test_invalid_links_never_write_partial_entries(client, link):
    response = client.post(
        "/api/study-materials",
        data={"title": "Bad", "studied_on": "2026-01-01", "links": link},
        files={"files": ("note.pdf", PDF)},
    )
    assert response.status_code == 400
    assert client.app.state.study_archive.list_all() == []
    assert list(client.app.state.study_archive.files.iterdir()) == []


def test_unsafe_upload_dates_and_write_protection(client):
    data = {"title": "Bad", "studied_on": "2026-01-01"}
    assert (
        client.post(
            "/api/study-materials",
            data=data,
            files={"files": ("fake.pdf", b"<script>alert(1)</script>")},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/study-materials", data={**data, "studied_on": "2026-02-30"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/study-materials",
            data={**data, "studied_on": (date.today() + timedelta(days=1)).isoformat()},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/study-materials", data=data, headers={"X-Study-Token": "wrong"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/study-materials", data=data, headers={"host": "attacker.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/study-materials/files/missing").status_code == 404


def test_future_review_not_completable_and_missing_file(client):
    entry = add(client, studied_on=date.today().isoformat())
    assert (
        client.post(
            f"/api/study-materials/{entry['id']}/reviews/3", data={"done": "true"}
        ).status_code
        == 400
    )
    asset_id = entry["assets"][0]["id"]
    client.app.state.study_archive.asset_file(asset_id)[0].unlink()
    assert client.get("/api/study-materials/files/" + asset_id).status_code == 404


def test_upload_limits(client, monkeypatch):
    import constitution_memorizer.web.study_archive as module

    monkeypatch.setattr(module, "MAX_FILE", 10)
    response = client.post(
        "/api/study-materials",
        data={"title": "Too large", "studied_on": "2026-01-01"},
        files={"files": ("large.pdf", b"%PDF-" + b"x" * 20)},
    )
    assert response.status_code == 413
    assert client.app.state.study_archive.list_all() == []


def test_failure_rolls_back_files_and_entry(tmp_path, monkeypatch):
    archive = StudyArchive(tmp_path)
    original = Path.open
    calls = 0

    def fail_second(path, *args, **kwargs):
        nonlocal calls
        if args and args[0] == "xb":
            calls += 1
            if calls == 2:
                raise OSError("disk full")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_second)
    with pytest.raises(OSError):
        archive.save(
            "Title", "2026-01-01", "", "Studied", [("a.pdf", PDF), ("b.pdf", PDF)], []
        )
    assert archive.list_all() == []
    assert list(archive.files.iterdir()) == []


def test_leap_year_and_escaped_heading(client):
    entry = add(client, studied_on="2024-02-27", title="<img src=x onerror=alert(1)>")
    assert entry["reviews"][0]["due_on"] == "2024-03-01"
    page = client.get("/calendar?year=2024&month=3")
    assert "&lt;img src=x onerror=alert(1)&gt;" in page.text
    assert "<img src=x onerror=alert(1)>" not in page.text


def test_archive_not_installed_in_multiuser_mode(tmp_path):
    from tests.test_multiuser_auth import _multi_client

    client = _multi_client(tmp_path)
    assert not hasattr(client.app.state, "study_archive")
    assert not any(
        getattr(route, "path", "").startswith("/api/study-materials")
        for route in client.app.routes
    )
    assert not (tmp_path / "study-materials").exists()
