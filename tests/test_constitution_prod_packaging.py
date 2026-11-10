"""ASGI entrypoint, web requirements, and recursive package-data."""

from __future__ import annotations

import ast
from pathlib import Path

from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.postgres_repository import PostgresProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def test_asgi_module_does_not_import_cli():
    source = (ROOT / "src/constitution_memorizer/asgi.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
    assert "constitution_memorizer.cli" not in imported
    assert not any(name.endswith(".cli") for name in imported)
    assert "import docling" not in source.lower()
    assert "from docling" not in source.lower()


def test_requirements_web_excludes_docling_and_pytest():
    lines = [
        line.strip().lower()
        for line in (ROOT / "requirements-web.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    joined = "\n".join(lines)
    assert "docling" not in joined
    assert "pytest" not in joined
    assert any(line.startswith("fastapi") for line in lines)
    assert any(line.startswith("psycopg") for line in lines)


def test_python_version_is_pinned_for_railpack():
    """Floating 3.11 resolved to 3.11.16, which mise has no prebuild for."""
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert pinned == "3.12.11"
    railpack = (ROOT / "railpack.json").read_text(encoding="utf-8")
    assert '"python": "3.12.11"' in railpack
    assert "constitution_memorizer.asgi:app" in railpack
    assert "sh -c" in railpack
    assert "${PORT:-8080}" in railpack


def test_package_data_includes_nested_templates():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"web/templates/**/*"' in pyproject or "'web/templates/**/*'" in pyproject
    partial = (
        ROOT
        / "src/constitution_memorizer/web/templates/partials/report_dialog.html"
    )
    assert partial.is_file()


def test_create_app_uses_postgres_repo_when_multiuser_postgresql(tmp_path: Path):
    clear_settings_cache()
    from constitution_memorizer.auth.fake_provider import FakeAuthProvider
    from constitution_memorizer.auth.sessions import InMemorySessionStore

    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=MultiUserSettings(
            _env_file=None,
            APP_ENV="test",
            MULTIUSER_ENABLED="true",
            AUTH_GOOGLE_ENABLED="true",
            AUTH_PHONE_ENABLED="true",
            SESSION_SECRET="test-secret",
            SUPABASE_URL="http://example.invalid",
            SUPABASE_ANON_KEY="anon",
            DATABASE_URL="postgresql://user:pass@localhost:5432/db",
            MEMORY_LOG_ENABLED="false",
        ),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )
    assert isinstance(app.state.engine.repo, PostgresProgressRepository)
    assert app.state.memory is None
    assert app.state.use_postgres_progress is True
    clear_settings_cache()


def test_from_repository_progress_survives_engine_recreation(tmp_path: Path):
    """Shared fake repo proves Constitution progress is not path-tied."""
    from datetime import date
    from uuid import UUID

    from constitution_memorizer.learning.schemas import LearningUnitsDocument
    from constitution_memorizer.progress.db import open_progress_db
    from constitution_memorizer.progress.repository import ProgressRepository
    from constitution_memorizer.utils.json_io import read_json

    conn = open_progress_db(tmp_path / "shared.db")
    repo = ProgressRepository(conn)
    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    catalog = {u.id: u for u in doc.units}
    user = UUID("11111111-1111-4111-8111-111111111111")

    engine_a = ReminderEngine.from_repository(repo, catalog, user_id=user)
    unit_id = next(iter(catalog))
    engine_a.mark_all_modes_seen(unit_id)
    engine_a.mark_done(unit_id, as_of=date(2026, 8, 1))

    engine_b = ReminderEngine.from_repository(repo, catalog, user_id=user)
    progress = engine_b.get_progress(unit_id)
    assert progress is not None
    assert progress.status in {"review", "mastered"}
    assert progress.times_completed >= 1


def test_earliest_upcoming_revision_without_sqlite_conn(tmp_path: Path):
    from datetime import date

    from constitution_memorizer.learning.schemas import LearningUnitsDocument
    from constitution_memorizer.progress.db import open_progress_db
    from constitution_memorizer.progress.repository import ProgressRepository
    from constitution_memorizer.utils.json_io import read_json
    from constitution_memorizer.web.service import earliest_upcoming_revision

    conn = open_progress_db(tmp_path / "prog.db")
    repo = ProgressRepository(conn)
    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    catalog = {u.id: u for u in doc.units}
    engine = ReminderEngine.from_repository(repo, catalog)
    unit_id = next(iter(catalog))
    engine.mark_all_modes_seen(unit_id)
    engine.mark_done(unit_id, as_of=date(2026, 8, 1))
    upcoming = earliest_upcoming_revision(engine, as_of=date(2026, 8, 1))
    assert upcoming is None or isinstance(upcoming, date)


def test_hosted_app_serves_healthz_when_boot_fails(monkeypatch):
    from fastapi.testclient import TestClient

    from constitution_memorizer import asgi as asgi_mod

    def boom() -> None:
        raise RuntimeError("simulated boot failure")

    monkeypatch.setattr(asgi_mod, "create_hosted_app", boom)
    with TestClient(asgi_mod.BootSafeASGI()) as client:
        healthz = client.get("/healthz")
        assert healthz.status_code == 200
        assert healthz.json() == {"status": "ok"}
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/").json() == {"status": "ok"}


def test_healthz_responds_before_create_app_finishes(monkeypatch):
    import threading

    from fastapi.testclient import TestClient

    from constitution_memorizer import asgi as asgi_mod

    release = threading.Event()

    def blocked() -> None:
        release.wait(timeout=5)
        raise RuntimeError("still booting")

    monkeypatch.setattr(asgi_mod, "create_hosted_app", blocked)
    with TestClient(asgi_mod.BootSafeASGI()) as client:
        healthz = client.get("/healthz")
        assert healthz.status_code == 200
        assert healthz.json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        release.set()


def test_railway_probe_config_matches_healthz():
    railway = (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert 'healthcheckPath = "/healthz"' in railway
    assert "healthcheckTimeout" in railway
    assert "restartPolicyType" in railway
    assert "constitution_memorizer.asgi:app" in railway
    assert "PYTHONPATH=src" in railway
    assert "sh -c" in railway
    nixpacks = (ROOT / "nixpacks.toml").read_text(encoding="utf-8")
    assert 'providers = ["python"]' in nixpacks
    assert "constitution_memorizer.asgi:app" in nixpacks
    assert "${PORT:-8080}" in nixpacks
    assert "requirements-web.txt" in nixpacks
    assert "pip install . --no-deps" in nixpacks
    # Nixpacks would otherwise install this Docling-only file and skip uvicorn.
    requirements = [
        line.strip().lower()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert any(line.startswith("docling") for line in requirements)
    assert not any(line.startswith("uvicorn") for line in requirements)
    procfile = (ROOT / "Procfile").read_text(encoding="utf-8")
    assert "constitution_memorizer.asgi:app" in procfile


def test_cli_serve_uses_boot_safe_app_on_railway():
    source = (ROOT / "src/constitution_memorizer/cli.py").read_text(encoding="utf-8")
    assert "RAILWAY_ENVIRONMENT" in source
    assert "constitution_memorizer.asgi" in source


def test_hosted_asgi_import_does_not_load_web_app():
    """Uvicorn must bind before web.app import; a subprocess keeps sys.modules clean."""
    import os
    import subprocess
    import sys

    script = (
        "import sys\n"
        "import constitution_memorizer.asgi  # noqa: F401\n"
        "loaded = [n for n in sys.modules if n == 'constitution_memorizer.web.app' "
        "or n.startswith('constitution_memorizer.web.app.')]\n"
        "raise SystemExit(0 if not loaded else 'loaded ' + ','.join(loaded))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = "src" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
