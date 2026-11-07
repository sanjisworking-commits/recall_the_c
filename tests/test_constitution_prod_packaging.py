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
    source = (ROOT / "src/constitution_memorizer/web/asgi.py").read_text(encoding="utf-8")
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
    assert "constitution_memorizer.web.asgi:app" in railpack
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

    from constitution_memorizer.web import asgi as asgi_mod
    from constitution_memorizer.web import app as web_app

    def boom(**_kwargs):
        raise RuntimeError("simulated boot failure")

    monkeypatch.setattr(web_app, "create_app", boom)
    app = asgi_mod.load_hosted_app()
    client = TestClient(app)
    healthz = client.get("/healthz")
    assert healthz.status_code == 200
    assert healthz.json() == {"status": "ok"}
    assert client.get("/health").status_code == 200


def test_railway_probe_config_matches_healthz():
    railway = (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert 'healthcheckPath = "/healthz"' in railway
    assert "healthcheckTimeout" in railway
    assert "restartPolicyType" in railway
    nixpacks = (ROOT / "nixpacks.toml").read_text(encoding="utf-8")
    assert 'providers = ["python"]' in nixpacks
    assert "${PORT:-8080}" in nixpacks
