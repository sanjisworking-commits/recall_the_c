"""FastAPI application factory for the learning UI."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, ValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from constitution_memorizer.admin.dependencies import admin_hint
from constitution_memorizer.admin.routes import create_admin_router
from constitution_memorizer.admin.repository import (
    PostgresAdminRepository,
    SqliteAdminRepository,
)
from constitution_memorizer.admin.store import (
    AdminHintCache,
    PostgresAccessStore,
    SqliteAccessStore,
)
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.guest import ROOT_ASSET_PATHS as _ROOT_ASSET_PATHS
from constitution_memorizer.auth.rate_limit import OtpRateLimiter
from constitution_memorizer.auth.routes import create_auth_router, install_auth_middleware
from constitution_memorizer.auth.sessions import InMemorySessionStore, PostgresSessionStore
from constitution_memorizer.auth.exceptions import AuthConfigError
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.learning.schemas import LearningUnitsDocument
from constitution_memorizer.progress.memory import MemoryEngine
from constitution_memorizer.progress.pg_pool import (
    POOL_OPEN_TIMEOUT_SECONDS,
    make_connection_pool,
)
from constitution_memorizer.progress.postgres_repository import PostgresProgressRepository
from constitution_memorizer.reports.contact_notifier import ResendContactMessageNotifier
from constitution_memorizer.reports.contact_repository import (
    PostgresContactMessageRepository,
)
from constitution_memorizer.reports.contact_schemas import (
    ContactMessageRequest,
    ContactMessageResponse,
)
from constitution_memorizer.reports.notifier import ResendIssueReportNotifier
from constitution_memorizer.reports.repository import PostgresIssueReportRepository
from constitution_memorizer.reports.schemas import ReportIssueRequest, ReportIssueResponse
from constitution_memorizer.reports.turnstile import (
    TURNSTILE_CONTACT_ACTION,
    TURNSTILE_REPORT_ACTION,
    TurnstileRejectedError,
    TurnstileUnavailableError,
    TurnstileVerifier,
)
from constitution_memorizer.utils.json_io import read_json

logger = logging.getLogger(__name__)
timing_logger = logging.getLogger("uvicorn.error")
from constitution_memorizer.progress.repository import (
    AUTO_SEEN_MODES_SET,
    LEARN_MODES,
    LEARN_MODES_SET,
    ONBOARDING_KEY,
    VALID_NOTIFICATION_FREQUENCIES,
    VALID_ONBOARDING_STATUSES,
    VALID_THEMES,
    SplitMode,
    StudySession,
)
from constitution_memorizer.progress.scheduler import (
    INTERVAL_LADDER,
    ModesIncompleteError,
    ReminderEngine,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web.request_context import (
    TIMING_STAGES,
    begin_request_timings,
    bound_engine,
    bound_memory,
    record_request_note,
    record_request_timing,
    reset_request_timings,
    snapshot_request_counters,
    snapshot_request_notes,
    snapshot_request_timings,
    wants_request_breakdown,
)
from constitution_memorizer.web.amendments import get_article_amendments, load_amendments
from constitution_memorizer.web.browse import (
    adjacent_article_numbers,
    article_phone_meta,
    BROWSE_MARKS_BY_KEY,
    marks_for_article,
    parse_news_articles,
    browse_due_total,
    browse_parts_sections,
    find_part_section,
    part_href,
    part_progress_summary,
    part_title_from_seed,
    present_browse_marks,
    build_article_view,
    list_article_numbers,
    load_reviewed_document,
)
from constitution_memorizer.web.explainers import explainer_asset_path, visual_explainer
from constitution_memorizer.planner.eligibility import is_unlearned
from constitution_memorizer.planner.models import pace_label as plan_pace_label
from constitution_memorizer.progress.repository import LEARN_MODES
from constitution_memorizer.web.progress_stats import (
    _is_completed,
    path_units_for_article,
)
from constitution_memorizer.web.calendar_view import (
    build_calendar_month,
    build_revisions_view,
)
from constitution_memorizer.web.completion import (
    build_completion,
    caught_up_quote,
    LearnNavigation,
    done_json_payload,
    next_learn_url,
    resolve_learn_navigation,
    session_entry_mode,
    with_params,
    wants_json,
)
from constitution_memorizer.web.billing import (
    BillingError,
    billing_enabled,
    create_order as billing_create,
    verify_signature as billing_verify,
)
from constitution_memorizer.web.entitlements import (
    PREVIEW_STATES,
    access_summary,
    article_key,
    can_use_auto_plan,
    entitlements_active,
    learning_entitlement_args,
    preview_state,
    resolve_learn_access,
)
from constitution_memorizer.web.gloss import gloss_placeholder_for, load_gloss_placeholders
from constitution_memorizer.web.legal import (
    PAGES,
    legal_page_context,
    missing_legal_configuration,
)
from constitution_memorizer.web.pricing import (
    DEFAULT_DAYS,
    MORE_DAYS,
    PLANS,
    billing_line,
    get_plan,
    per_day,
    plans_json,
)
from constitution_memorizer.web.quiz import build_quiz, grade_quiz, has_quiz
from constitution_memorizer.web.quotes import load_quotes
from constitution_memorizer.web.judicial_evolution import (
    get_judicial_evolution,
    load_judicial_evolution,
)
from constitution_memorizer.web.bare_acts import get_bare_act
from constitution_memorizer.web.law_catalog import load_catalog
from constitution_memorizer.web.laws_data import get_law
from constitution_memorizer.web.memory_calendar import build_memory_month, schedule_chip_states
from constitution_memorizer.web.progress_stats import progress_dashboard
from constitution_memorizer.web.search import resolve_search
from constitution_memorizer.web.service import (
    LEARN_MODE_LABELS,
    active_revision_session,
    continue_unit_id,
    done_button_state,
    due_checklist,
    earliest_upcoming_revision,
    has_cloze_blanks,
    home_lede,
    kind_badge_label,
    learn_meta_line,
    methods_tracker_line,
    maybe_activate_auto_plan,
    needs_split_choice,
    _is_missing_optional_schema,
    REVISION_INTENT_CONSUME,
    REVISION_INTENT_PRACTICE,
    early_revision_due,
    ensure_auto_roadmap,
    may_persist_revision_modes,
    parse_revision_intent,
    persist_session_anchor_theme,
    resolve_learn_target,
    revision_position_label,
    select_today_mix,
    session_progress,
    start_or_resume_learning,
    start_or_resume_revision,
    user_today,
    sibling_chips,
    subclause_stem_text,
    unit_crumb,
    unit_type_label,
)
from constitution_memorizer.web.tables_data import list_table_tabs, load_table_tab, row_is_muted
from constitution_memorizer.web.text_annotations import (
    annotate_plain_text,
    annotations_for_article,
    annotations_for_unit,
    load_text_annotations,
)

def _effective_required_modes(unit, units, required_modes) -> set[str]:
    """Entitlement-required modes minus the ones impossible for this unit.

    Gated modes are never fake-completed: a unit that cannot produce a quiz
    (or a cloze blank) simply doesn't require that mode this cycle.
    """
    required = set(required_modes)
    if "test" in required and not has_quiz(unit, units):
        required.discard("test")
    if "cloze" in required and not has_cloze_blanks(unit.text):
        required.discard("cloze")
    return required


class QuizSubmission(BaseModel):
    cycle: int
    answers: list[object]
    revision_intent: str | None = None


WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    """Open the shared Postgres pool before traffic; close it on shutdown."""
    pool = getattr(app.state, "db_pool", None)
    try:
        if pool is not None:
            pool.open(wait=True, timeout=POOL_OPEN_TIMEOUT_SECONDS)
        yield
    finally:
        if pool is not None:
            pool.close()
_ALLOWED_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
_PHOTO_MAGIC: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"GIF87a", ".gif", "image/gif"),
    (b"GIF89a", ".gif", "image/gif"),
    (b"RIFF", ".webp", "image/webp"),  # WebP also starts with RIFF….WEBP
]


def _sniff_photo(content: bytes, filename: str) -> tuple[str, str]:
    """Return (suffix, media_type) from magic bytes, else filename suffix."""
    for magic, suffix, media_type in _PHOTO_MAGIC:
        if content.startswith(magic):
            if suffix == ".webp" and b"WEBP" not in content[:16]:
                continue
            return suffix, media_type
    # HEIC/HEIF brands in ISO BMFF
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in {b"heic", b"heif", b"mif1", b"msf1", b"hevc"}:
            return ".heic", "image/heic"
    suffix = Path(filename).suffix.lower() or ".jpg"
    if suffix not in _ALLOWED_PHOTO_SUFFIXES:
        suffix = ".jpg"
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    return suffix, media_types.get(suffix, "application/octet-stream")


def create_app(
    *,
    units_path: Path | str | None = None,
    db_path: Path | str | None = None,
    reviewed_path: Path | str | None = None,
    amendments_path: Path | str | None = None,
    gloss_placeholders_path: Path | str | None = None,
    text_annotations_path: Path | str | None = None,
    judicial_evolution_path: Path | str | None = None,
    multiuser: bool = False,
    multiuser_settings: MultiUserSettings | None = None,
    auth_provider=None,
    session_store=None,
    issue_report_repo=None,
    issue_report_notifier=None,
    issue_report_turnstile_verifier=None,
    contact_message_repo=None,
    contact_message_notifier=None,
    progress_repo=None,
    access_store=None,
    admin_repo=None,
    calendar_store=None,
    gcal_transport=None,
    speech_provider=None,
) -> FastAPI:
    """Create the learning UI app bound to concrete unit/progress paths."""
    root = Path.cwd()
    resolved_units = Path(units_path or root / "data" / "output" / "learning_units.json")
    resolved_db = Path(db_path or root / "data" / "progress" / "progress.db")
    resolved_reviewed = Path(
        reviewed_path
        if reviewed_path is not None
        else root / "data" / "output" / "constitution.reviewed.json"
    )
    resolved_amendments = Path(
        amendments_path
        if amendments_path is not None
        else root / "data" / "reference" / "amendments.seed.json"
    )
    resolved_gloss_placeholders = Path(
        gloss_placeholders_path
        if gloss_placeholders_path is not None
        else root / "data" / "reference" / "gloss_placeholders.seed.json"
    )
    resolved_text_annotations = Path(
        text_annotations_path
        if text_annotations_path is not None
        else root / "data" / "reference" / "text_annotations.json"
    )
    resolved_judicial_evolution = Path(
        judicial_evolution_path
        if judicial_evolution_path is not None
        else root / "data" / "reference" / "judicial_evolution.seed.json"
    )

    if not resolved_units.exists():
        raise FileNotFoundError(
            f"learning_units.json not found at {resolved_units}. "
            "Run: python -m constitution_memorizer.cli generate-units --force"
        )

    settings = multiuser_settings or MultiUserSettings()
    # Turnstile config is independent of multi-user auth startup validation.
    settings.validate_issue_report_turnstile()
    # Opt-in only via the multiuser= argument (CLI sets this from MULTIUSER_ENABLED).
    # Do not infer from process env here — that leaks across pytest cases.
    multiuser_on = bool(multiuser)
    # Real Supabase credentials are required only when multi-user is on and
    # the caller did not inject a test/fake auth provider.
    if multiuser_on and auth_provider is None:
        settings.validate_for_startup(require_secrets=True)
        missing = settings.missing_supabase()
        if missing:
            raise AuthConfigError(
                "Missing "
                + ", ".join(missing)
                + ". Add them to .env in the repo root, then restart. "
                "SUPABASE_URL must be https://<project-ref>.supabase.co "
                "(not https://supabase.com/dashboard/...)."
            )

    resolved_db = Path(resolved_db).expanduser().resolve()
    resolved_units = Path(resolved_units).expanduser().resolve()
    database_url = (settings.database_url or "").strip()
    use_postgres = multiuser_on and database_url.startswith("postgresql")
    # Hosted multi-user must not silently fall back to SQLite.
    if multiuser_on and settings.app_env in {"staging", "production"}:
        if not database_url.startswith("postgresql"):
            raise AuthConfigError(
                "MULTIUSER_ENABLED=true in staging/production requires "
                "DATABASE_URL to be a PostgreSQL URL "
                "(postgresql://… or postgresql+…://…). "
                f"Got: {database_url!r}"
            )
    memory_log_enabled = bool(settings.memory_log_enabled)
    relevant_laws_enabled = bool(settings.relevant_laws_enabled)

    if memory_log_enabled and use_postgres:
        raise AuthConfigError(
            "MEMORY_LOG_ENABLED=true is not supported with PostgreSQL yet."
        )

    units_doc = LearningUnitsDocument.model_validate(read_json(resolved_units))
    catalog = {unit.id: unit for unit in units_doc.units}
    db_pool = None

    def _ensure_pool():
        nonlocal db_pool
        if db_pool is None:
            db_pool = make_connection_pool(database_url)
        return db_pool

    if progress_repo is not None:
        engine = ReminderEngine.from_repository(
            progress_repo, catalog, user_id=LOCAL_USER_ID
        )
    elif use_postgres:
        engine = ReminderEngine.from_repository(
            PostgresProgressRepository(_ensure_pool()),
            catalog,
            user_id=LOCAL_USER_ID,
        )
    else:
        engine = ReminderEngine.from_paths(
            resolved_db, resolved_units, user_id=LOCAL_USER_ID
        )

    if memory_log_enabled:
        memory = MemoryEngine(
            engine.repo.conn,  # type: ignore[attr-defined]
            resolved_db.parent / "memory_media",
            user_id=LOCAL_USER_ID,
        )
    else:
        memory = None
    reviewed = load_reviewed_document(
        resolved_reviewed if resolved_reviewed.exists() else None
    )
    # Stale non-editable installs often miss Browse Part segregation — surface paths.
    import constitution_memorizer.web.browse as _browse_mod  # noqa: PLC0415

    print(
        f"Browse module: {_browse_mod.__file__} "
        f"(reviewed={'yes' if reviewed is not None else 'missing → Part seed/tags'})"
    )
    amendments = load_amendments(
        resolved_amendments if resolved_amendments.exists() else None
    )
    gloss_placeholders = load_gloss_placeholders(
        resolved_gloss_placeholders if resolved_gloss_placeholders.exists() else None
    )
    text_annotations = load_text_annotations(
        resolved_text_annotations if resolved_text_annotations.exists() else None
    )
    judicial_evolution = load_judicial_evolution(
        resolved_judicial_evolution if resolved_judicial_evolution.exists() else None
    )
    resolved_quotes = root / "data" / "reference" / "quotes.json"
    quotes = load_quotes(resolved_quotes if resolved_quotes.exists() else None)

    def _theme_for_request(request: Request) -> str:
        if getattr(request.state, "is_guest", False) and app.state.multiuser_enabled:
            return "auto"
        bound = getattr(request.state, "bound_engine", None) or app.state.engine
        # No timing here on purpose: get_theme() records `theme` only when it
        # actually reaches the repo, so a theme_ms in the log is proof of a
        # read rather than proof of a call.
        return bound.get_theme()

    def _onboarding_for_request(request: Request) -> str:
        # Tour is a signed-in, multiuser surface only. Absent setting = "".
        if not app.state.multiuser_enabled:
            return ""
        if getattr(request.state, "current_user", None) is None:
            return ""
        bound = getattr(request.state, "bound_engine", None)
        if bound is None:
            return ""
        # `stage` makes this read visible the way get_theme() already is:
        # recorded only when it reaches the repo. Onboarding was the one of the
        # three nav reads with no stage at all, so it was invisible in the logs.
        value = bound.get_setting(ONBOARDING_KEY, stage="onboarding_setting") or ""
        return value if value in VALID_ONBOARDING_STATUSES else ""

    def _due_for_request(request: Request) -> int:
        if getattr(request.state, "is_guest", False) or getattr(
            request.state, "current_user", None
        ) is None:
            if app.state.multiuser_enabled:
                return 0
        bound = getattr(request.state, "bound_engine", None) or app.state.engine
        started = time.perf_counter()
        total = browse_due_total(bound)
        record_request_timing("nav_due", started)
        return total

    templates = Jinja2Templates(
        directory=str(TEMPLATES_DIR),
        context_processors=[
            lambda request: {
                "app_name": "Recall the C",
                "theme_preference": _theme_for_request(request),
                "onboarding_status": _onboarding_for_request(request),
                "browse_due_total": _due_for_request(request),
                "current_user": getattr(request.state, "current_user", None),
                "is_guest": bool(
                    app.state.multiuser_enabled
                    and getattr(request.state, "current_user", None) is None
                ),
                "multiuser_enabled": app.state.multiuser_enabled,
                "memory_log_enabled": memory_log_enabled,
                "relevant_laws_enabled": relevant_laws_enabled,
                "pricing_enabled": bool(settings.pricing_enabled),
                # Cosmetic nav hint only (~60s TTL cache); /admin itself
                # re-checks the authoritative role store on every request.
                "is_admin_hint": admin_hint(request),
                # Fixed banner label while the admin Entitlement Preview is
                # active (verified admins only; empty string otherwise).
                "admin_preview_label": PREVIEW_STATES.get(
                    preview_state(request) or "", ""
                ),
                # Guests cannot submit Contact Us / Report Issue — do not expose
                # Turnstile site key or load the client script for them.
                "report_turnstile_enabled": bool(
                    settings.report_turnstile_enabled
                    and getattr(request.state, "current_user", None) is not None
                ),
                "report_turnstile_site_key": (
                    (settings.report_turnstile_site_key or "").strip()
                    if (
                        settings.report_turnstile_enabled
                        and getattr(request.state, "current_user", None) is not None
                    )
                    else ""
                ),
                "csrf_token": (
                    getattr(getattr(request.state, "auth_session", None), "csrf_token", None)
                    or request.cookies.get("rtc_csrf")
                ),
            }
        ],
    )
    templates.env.globals["visual_explainer"] = visual_explainer
    templates.env.globals["browse_mark"] = BROWSE_MARKS_BY_KEY.get

    app = FastAPI(title="Recall the C", version="0.8.0", lifespan=_app_lifespan)
    app.state.engine = engine
    app.state.memory = memory
    app.state.reviewed = reviewed
    app.state.amendments = amendments
    app.state.gloss_placeholders = gloss_placeholders
    app.state.text_annotations = text_annotations
    app.state.judicial_evolution = judicial_evolution
    app.state.quotes = quotes
    app.state.units_path = resolved_units
    app.state.db_path = resolved_db
    app.state.reviewed_path = resolved_reviewed
    app.state.multiuser_enabled = multiuser_on
    app.state.multiuser_settings = settings
    app.state.memory_log_enabled = memory_log_enabled
    app.state.relevant_laws_enabled = relevant_laws_enabled
    app.state.article_entitlements_enabled = bool(settings.article_entitlements_enabled)
    app.state.pricing_enabled = bool(settings.pricing_enabled)
    # Razorpay Standard Checkout. The secret stays on app.state for
    # server-side order creation + HMAC verification only — no template or
    # JSON payload ever reads it.
    app.state.razorpay_key_id = str(settings.razorpay_key_id or "")
    app.state.razorpay_key_secret = str(settings.razorpay_key_secret or "")
    app.state.use_postgres_progress = use_postgres
    app.state.oauth_states = {}
    app.state.otp_limiter = OtpRateLimiter()
    if auth_provider is not None:
        app.state.auth_provider = auth_provider
    elif multiuser_on:
        from constitution_memorizer.auth.supabase_provider import SupabaseAuthProvider

        app.state.auth_provider = SupabaseAuthProvider(
            supabase_url=settings.supabase_url.strip(),
            anon_key=settings.supabase_anon_key.strip(),
        )
    else:
        app.state.auth_provider = FakeAuthProvider()
    if session_store is not None:
        app.state.session_store = session_store
    elif multiuser_on and settings.database_url.startswith("postgresql"):
        app.state.session_store = PostgresSessionStore(_ensure_pool())
    else:
        app.state.session_store = InMemorySessionStore()

    if issue_report_repo is not None:
        app.state.issue_report_repo = issue_report_repo
    elif settings.database_url.startswith("postgresql"):
        app.state.issue_report_repo = PostgresIssueReportRepository(_ensure_pool())
    else:
        app.state.issue_report_repo = None

    if issue_report_notifier is not None:
        app.state.issue_report_notifier = issue_report_notifier
    elif settings.issue_report_notify_configured():
        app.state.issue_report_notifier = ResendIssueReportNotifier(
            settings.resend_api_key,
            settings.report_email_from,
            settings.report_email_to,
        )
    else:
        app.state.issue_report_notifier = None

    # Injection alone does not enable Turnstile; REPORT_TURNSTILE_ENABLED is source of truth.
    if issue_report_turnstile_verifier is not None:
        app.state.issue_report_turnstile_verifier = issue_report_turnstile_verifier
    elif settings.issue_report_turnstile_configured():
        app.state.issue_report_turnstile_verifier = TurnstileVerifier(
            settings.report_turnstile_secret_key,
        )
    else:
        app.state.issue_report_turnstile_verifier = None

    if contact_message_repo is not None:
        app.state.contact_message_repo = contact_message_repo
    elif settings.database_url.startswith("postgresql"):
        app.state.contact_message_repo = PostgresContactMessageRepository(
            _ensure_pool()
        )
    else:
        app.state.contact_message_repo = None

    if contact_message_notifier is not None:
        app.state.contact_message_notifier = contact_message_notifier
    elif settings.issue_report_notify_configured():
        app.state.contact_message_notifier = ResendContactMessageNotifier(
            settings.resend_api_key,
            settings.report_email_from,
            settings.report_email_to,
        )
    else:
        app.state.contact_message_notifier = None

    # Admin foundation: hot-path access store (role + effective grant) and the
    # cold-path console repository. ADMIN_ENABLED gates the console only; the
    # role's entitlement bypass follows user_roles regardless of the flag.
    if access_store is not None:
        app.state.access_store = access_store
    elif use_postgres:
        app.state.access_store = PostgresAccessStore(_ensure_pool())
    else:
        _sqlite_conn = getattr(engine.repo, "conn", None)
        app.state.access_store = (
            SqliteAccessStore(_sqlite_conn) if _sqlite_conn is not None else None
        )

    # Google Calendar projection store (domain-owned, dual-backend). The
    # feature also needs GCAL_CLIENT_ID/SECRET/TOKEN_KEY — routes check both.
    from constitution_memorizer.calendar_sync.store import (
        PostgresCalendarStore,
        SqliteCalendarStore,
    )

    if calendar_store is not None:
        app.state.calendar_store = calendar_store
    elif use_postgres:
        app.state.calendar_store = PostgresCalendarStore(_ensure_pool())
    else:
        _sqlite_conn = getattr(engine.repo, "conn", None)
        app.state.calendar_store = (
            SqliteCalendarStore(_sqlite_conn) if _sqlite_conn is not None else None
        )
    app.state.gcal_transport = gcal_transport

    from constitution_memorizer.speech.deepgram import DeepgramSpeechProvider
    from constitution_memorizer.speech.limits import SpeechRateLimiter
    from constitution_memorizer.speech.provider import UnavailableSpeechProvider

    if speech_provider is not None:
        app.state.speech_provider = speech_provider
    elif (settings.deepgram_api_key or "").strip():
        app.state.speech_provider = DeepgramSpeechProvider(settings.deepgram_api_key)
    else:
        app.state.speech_provider = UnavailableSpeechProvider()
    app.state.speech_rate_limiter = SpeechRateLimiter()

    if admin_repo is not None:
        app.state.admin_repo = admin_repo
    elif use_postgres:
        app.state.admin_repo = PostgresAdminRepository(_ensure_pool())
    else:
        _sqlite_conn = getattr(engine.repo, "conn", None)
        app.state.admin_repo = (
            SqliteAdminRepository(_sqlite_conn) if _sqlite_conn is not None else None
        )

    app.state.admin_enabled = bool(settings.admin_enabled)
    app.state.admin_hint_cache = AdminHintCache()

    app.state.db_pool = db_pool

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    install_auth_middleware(app)

    @app.middleware("http")
    async def feature_flag_gate(request: Request, call_next):
        """404 disabled Memory/Laws prefixes before auth can redirect guests."""
        path = request.url.path
        if not app.state.memory_log_enabled and (
            path == "/memory" or path.startswith("/memory/")
        ):
            return HTMLResponse("Not Found", status_code=404)
        if not app.state.relevant_laws_enabled and (
            path == "/laws" or path.startswith("/laws/")
        ):
            return HTMLResponse("Not Found", status_code=404)
        return await call_next(request)

    @app.middleware("http")
    async def request_timing(request: Request, call_next):
        """Log method/path/status/duration_ms; skip health and static assets."""
        path = request.url.path
        skip = (
            path in _ROOT_ASSET_PATHS
            or path.startswith("/static/")
        )
        breakdown = wants_request_breakdown(path)
        token = begin_request_timings() if breakdown else None
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            if breakdown:
                # Recorded here, after call_next, because the auth middleware
                # runs inside this one and is what sets current_user. Without
                # it a duration_ms line cannot be read: guest and signed-in are
                # different code paths, and only one of them touches the DB.
                if not app.state.multiuser_enabled:
                    auth_state = "single_user"
                elif getattr(request.state, "current_user", None) is not None:
                    auth_state = "authed"
                else:
                    auth_state = "guest"
                record_request_note("auth_state", auth_state)
            if not skip:
                duration_ms = (time.perf_counter() - started) * 1000.0
                timing_logger.info(
                    "request method=%s path=%s status=%s duration_ms=%.1f",
                    request.method,
                    path,
                    status,
                    duration_ms,
                )
                snapshot = snapshot_request_timings()
                counters = snapshot_request_counters()
                notes = snapshot_request_notes()
                if snapshot or counters or notes:
                    parts = [
                        f"request_breakdown method={request.method} path={path}"
                    ]
                    for stage in TIMING_STAGES:
                        if stage not in snapshot:
                            continue
                        total_ms, count = snapshot[stage]
                        parts.append(f"{stage}_ms={total_ms:.1f}")
                        parts.append(f"{stage}_n={count}")
                    for name, count in counters.items():
                        parts.append(f"{name}={count}")
                    for name, value in notes.items():
                        parts.append(f"{name}={value}")
                    timing_logger.info(" ".join(parts))
            if token is not None:
                reset_request_timings(token)

    app.include_router(create_auth_router(templates))
    app.include_router(create_admin_router(templates))

    from constitution_memorizer.calendar_sync.routes import router as gcal_router
    from constitution_memorizer.speech.routes import router as speech_router

    app.include_router(gcal_router)
    app.include_router(speech_router)

    def _engine() -> ReminderEngine:
        bound = bound_engine.get()
        if bound is not None:
            return bound
        return app.state.engine

    def _memory() -> MemoryEngine:
        bound = bound_memory.get()
        if bound is not None:
            return bound
        memory = app.state.memory
        if memory is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return memory

    def _modes_payload(
        unit_id: str,
        seen: set[str] | None = None,
        required_count: int = 6,
    ) -> dict[str, object]:
        current = seen if seen is not None else _engine().modes_seen(unit_id)
        return {
            "seen": sorted(current),
            "count": len(current),
            "remaining": max(0, required_count - len(current)),
            "complete": len(current) >= required_count,
            "tracker": methods_tracker_line(len(current), required_count),
        }

    def _revision_intent_from_query(request: Request) -> str | None:
        return parse_revision_intent(request.query_params.get("revision_intent"))

    def _sync_auto_roadmap(
        request: Request, eng: ReminderEngine, *, force: bool = True
    ) -> None:
        args = learning_entitlement_args(request, eng)
        ensure_auto_roadmap(
            eng,
            as_of=user_today(eng),
            auto_entitled=can_use_auto_plan(request),
            force=force,
            **args,
        )

    # Root paths browsers ask for without being told to. Serving them stops a
    # steady drip of 404s that each paid for a session lookup — and, on a stale
    # cookie, could spend the user's one-shot /session-expired redirect on an
    # icon request.
    @app.get("/sw.js")
    async def service_worker() -> FileResponse:
        """A worker that unregisters itself. See static/sw.js for why."""
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="text/javascript",
            # Must not be cached: a stale copy is an orphaned worker that never
            # sees the kill switch.
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/favicon.ico")
    async def favicon_ico() -> FileResponse:
        """PNG bytes at the .ico path — every current browser accepts it."""
        return FileResponse(STATIC_DIR / "brand-c.png", media_type="image/png")

    @app.get("/apple-touch-icon.png")
    @app.get("/apple-touch-icon-precomposed.png")
    async def apple_touch_icon() -> FileResponse:
        """iOS probes both spellings at the root when adding to home screen."""
        return FileResponse(STATIC_DIR / "brand-c.png", media_type="image/png")

    @app.get("/sitemap.xml")
    async def sitemap_xml() -> FileResponse:
        """Public crawler sitemap. No auth, no login redirect."""
        return FileResponse(
            WEB_DIR / "sitemap.xml",
            media_type="application/xml",
        )

    @app.get("/robots.txt")
    async def robots_txt() -> FileResponse:
        """Public robots.txt with the production sitemap declaration."""
        return FileResponse(
            WEB_DIR / "robots.txt",
            media_type="text/plain; charset=utf-8",
        )

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        if app.state.multiuser_enabled:
            if getattr(request.state, "current_user", None) is None:
                # Marketing landing. The light variant is currently disabled —
                # always serve the dark landing (a stale rtc_landing_theme
                # cookie must not strand anyone on light). landing_light.html
                # stays in the repo, dormant, for easy re-enable.
                return templates.TemplateResponse(
                    request,
                    "landing.html",
                    {
                        "landing_review_days": list(INTERVAL_LADDER),
                    },
                )
            # Authenticated home is the dashboard.
            return RedirectResponse(url="/dashboard", status_code=303)
        eng = _engine()
        today = date.today()
        due = due_checklist(eng, as_of=today)
        cont = continue_unit_id(eng, as_of=today)
        cont_unit = eng.get_unit(cont) if cont else None
        stats = eng.stats()
        upcoming = earliest_upcoming_revision(eng, as_of=today)
        all_caught_up = not due and cont_unit is None
        caught_up_detail = "Nothing due today."
        if all_caught_up and upcoming is not None:
            caught_up_detail = (
                f"Nothing due today. Next review lands "
                f"{upcoming.day} {upcoming.strftime('%b')}."
            )
        elif all_caught_up:
            caught_up_detail = "Nothing due today. Start from Browse when you are ready."

        continue_meta = None
        if cont_unit is not None:
            bits = [
                unit_type_label(cont_unit),
                f"~{cont_unit.estimated_learning_time}s",
                f"difficulty {cont_unit.difficulty}/5",
            ]
            continue_meta = " · ".join(bits)

        is_guest_home = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        done_id = request.query_params.get("done")
        completion = build_completion(
            eng=eng,
            quotes=app.state.quotes,
            done_id=done_id,
            request=request,
            is_guest=is_guest_home,
            today=today,
            continue_href="/",
            continue_label=None,
        )
        home_quote = (
            caught_up_quote(app.state.quotes, today) if all_caught_up else None
        )

        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "due_units": due,
                "continue_unit": cont_unit,
                "continue_kind": (
                    unit_type_label(cont_unit) if cont_unit is not None else None
                ),
                "continue_meta": continue_meta,
                "stats": stats,
                "today": today,
                "today_label": (
                    f"{today.strftime('%A')}, {today.day} {today.strftime('%B %Y')}"
                ),
                "home_lede": home_lede(
                    due_count=len(due),
                    has_continue=cont_unit is not None,
                ),
                "all_caught_up": all_caught_up,
                "caught_up_detail": caught_up_detail,
                "caught_up_quote": home_quote,
                "completion": completion,
                "stat_line": (
                    f"{stats['review']} in review · "
                    f"{stats['mastered']} mastered · "
                    f"{stats['split_preferences']} split choices"
                ),
                "unit_type_label": unit_type_label,
            },
        )

    @app.get("/learn", response_class=HTMLResponse)
    async def learn_index(request: Request) -> RedirectResponse:
        eng = _engine()
        today = date.today()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if not is_guest:
            due = eng.due_today(as_of=today)
            if due:
                return RedirectResponse(
                    url=f"/learn/{due[0].learning_unit_id}", status_code=303
                )
            cont = continue_unit_id(eng, as_of=today)
            if cont:
                return RedirectResponse(url=f"/learn/{cont}", status_code=303)
        return RedirectResponse(url="/browse", status_code=303)

    @app.get("/learn/{unit_id}", response_class=HTMLResponse)
    async def learn(
        request: Request,
        unit_id: str,
        mode: str = "read",
    ) -> HTMLResponse:
        eng = _engine()
        unit = eng.get_unit(unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")

        if mode == "card":
            # Compatibility alias for old bookmarks: card became test. Keep
            # every other query parameter; only the mode key changes.
            params = dict(request.query_params)
            params["mode"] = "test"
            return RedirectResponse(
                url=f"/learn/{unit_id}?{urlencode(params)}", status_code=303
            )
        learn_mode = mode if mode in LEARN_MODES_SET else "read"
        is_guest_early = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if not is_guest_early:
            # include_modes loads every unit's seen-set in the same bundle, so
            # the clause rail can show per-clause progress without one
            # roundtrip per sibling.
            eng.bootstrap_request(
                include_modes=True,
                include_account=entitlements_active(request),
            )

        # Every hop inside a session has to keep carrying it, so redirects
        # rebuild their query instead of hand-writing one parameter.
        carried = {
            "session": request.query_params.get("session") or "",
            "mode": learn_mode if learn_mode != "read" else "",
            "revision_intent": _revision_intent_from_query(request) or "",
        }

        # Guests skip split preference (no personal data); show the clause as-is.
        if not is_guest_early and needs_split_choice(eng, unit):
            return RedirectResponse(
                # `mode` is deliberately dropped: on /choose that key means
                # whole-vs-letters, not a recall mode.
                url=with_params(
                    f"/learn/{unit_id}/choose", {"session": carried["session"]}
                ),
                status_code=303,
            )

        target_id = unit_id if is_guest_early else resolve_learn_target(eng, unit_id)
        if target_id != unit_id:
            return RedirectResponse(
                url=with_params(f"/learn/{target_id}", carried),
                status_code=303,
            )

        target = eng.get_unit(target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")

        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        # Article-aware mode locks (guest / free-cap-reached lock Type & Recite).
        learn_lock = resolve_learn_access(request, eng, target.article_number)
        locked_modes = learn_lock.locked_modes
        mode_locked = learn_mode in locked_modes
        required_modes = _effective_required_modes(
            target, eng.units, learn_lock.required_modes
        )
        # Guests may try modes without writing progress.
        if is_guest:
            # Only auto-seen modes count on open; gated modes are tracked
            # client-side once their gate fires.
            seen: set[str] = (
                {learn_mode}
                if (not mode_locked and learn_mode in AUTO_SEEN_MODES_SET)
                else set()
            )
            progress = None
            done_count, chain_len = 0, 1
            pct = 0
            # Done unlocks client-side once the effective open modes are
            # complete; clicking it then opens the sign-in prompt.
            done_state = done_button_state(target, seen, required=required_modes)
            done_unlocked = done_state["unlocked"]
            done_label = done_state["label"]
        else:
            today = user_today(eng)
            revision_intent = _revision_intent_from_query(request)
            persist_ok = may_persist_revision_modes(
                eng, target.id, as_of=today, intent=revision_intent
            )
            # Locked modes are never recorded as seen; unclaimed Articles keep
            # mode visits provisional (client-tracked) until claimed on Done.
            # Gated modes are never marked by a GET — they report via /seen
            # (or /quiz for Test). Early-review practice / missing intent
            # must not persist revision-cycle modes_seen.
            if (
                mode_locked
                or not learn_lock.can_persist_modes_seen
                or learn_mode not in AUTO_SEEN_MODES_SET
                or not persist_ok
            ):
                seen = eng.modes_seen(target.id)
            else:
                seen = eng.mark_mode_seen(target.id, learn_mode)
            progress = eng.get_progress(target.id)
            done_count, _position, chain_len = session_progress(eng, target)
            pct = int(round(100 * done_count / chain_len)) if chain_len else 0
            done_state = done_button_state(target, seen, required=required_modes)
            done_unlocked = done_state["unlocked"]
            done_label = done_state["label"]
        modes_payload = _modes_payload(
            target.id, seen, required_count=len(required_modes)
        )

        started = time.perf_counter()
        chips = sibling_chips(eng, target)
        stem = subclause_stem_text(eng, target)
        rail_kind = (
            "letters"
            if target.type.value == "SUBCLAUSE"
            else ("clauses" if chips else None)
        )
        curated = get_article_amendments(app.state.amendments, target.article_number)
        amend_note = curated.learn_note if curated is not None else None
        catalog = app.state.text_annotations
        unit_anns = annotations_for_unit(catalog, target.id, surface="learn")
        notes = catalog.notes if hasattr(catalog, "notes") else {}
        annotated_text = annotate_plain_text(
            target.text,
            unit_anns,
            notes=notes,
            unit_id=target.id,
        )
        record_request_timing("learn_build", started)

        # Server-validated Free-Article claim prompt / subscription gate panels.
        claim_prompt = None
        subscription_gate = False
        target_key = article_key(target.article_number)
        if not is_guest and target_key is not None:
            wants_claim = request.query_params.get("claim") == "1"
            wants_gate = request.query_params.get("gate") == "subscription"
            if wants_claim or wants_gate:
                learn_gate_access = resolve_learn_access(
                    request, eng, target.article_number
                )
                if wants_claim and learn_gate_access.should_prompt_claim:
                    claim_prompt = {
                        "article_number": target_key,
                        "slots_remaining": learn_gate_access.free_slots_remaining,
                    }
                if wants_gate and learn_gate_access.cap_reached:
                    subscription_gate = True

        # Test-mode quiz: seeded on the revision cycle so every Done rotates
        # the questions; answers never leave the server.
        quiz_cycle = progress.times_completed if progress is not None else 0
        quiz_available = has_quiz(target, eng.units)
        quiz_questions = (
            [q.public_dict() for q in build_quiz(target, eng.units, cycle=quiz_cycle)]
            if quiz_available
            else []
        )
        cloze_available = has_cloze_blanks(target.text)

        # A session is only navigation context, so an unusable one is stripped
        # rather than redirected away from: the page still renders, just
        # sequentially. Redirecting would loop on a stale deep link, and
        # accepting it unchecked would let `?session=` typed onto any Browse
        # URL inherit somebody's revision queue.
        session = _load_session_context(eng, request, target.id, is_guest=is_guest)
        session_id = session.id if session is not None else ""
        session_label = (
            revision_position_label(session, target.id) if session is not None else None
        )

        done_id = request.query_params.get("done")
        revision_intent = _revision_intent_from_query(request)
        early_due = (
            None
            if is_guest
            else early_revision_due(eng, target.id, as_of=user_today(eng))
        )
        mode_suffix = with_params(
            f"/learn/{target.id}",
            {
                "mode": learn_mode if learn_mode != "read" else "",
                "session": session_id,
                "revision_intent": revision_intent or "",
            },
        )
        started = time.perf_counter()
        completion = build_completion(
            eng=eng,
            quotes=app.state.quotes,
            done_id=done_id,
            request=request,
            is_guest=is_guest,
            continue_href=mode_suffix,
            continue_label=target.display_title,
        )
        record_request_timing("completion", started)
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "learn.html",
            {
                "unit": target,
                "progress": progress,
                "session_id": session_id,
                "session_kind": session.kind if session is not None else "",
                "revision_label": session_label,
                "revision_remaining": session.remaining if session is not None else 0,
                "kind_badge": kind_badge_label(target),
                "unit_crumb": unit_crumb(target),
                "session_label": f"{done_count} of {chain_len}",
                "session_pct": pct,
                "sibling_chips": chips,
                "rail_kind": rail_kind,
                "stem_text": stem,
                "learn_meta": learn_meta_line(target, progress) if progress else "Guest try",
                "done_label": done_label,
                "done_unlocked": done_unlocked,
                "modes_seen": seen,
                "modes_tracker": modes_payload["tracker"],
                "mode_labels": LEARN_MODE_LABELS,
                "learn_modes": LEARN_MODES,
                "learn_mode": learn_mode,
                "amend_note": amend_note,
                "annotated_text": annotated_text,
                "has_text_annotations": bool(unit_anns),
                "is_guest": is_guest,
                "completion": completion,
                "claim_prompt": claim_prompt,
                "subscription_gate": subscription_gate,
                "locked_modes": locked_modes,
                "lock_reason": (
                    "guest" if is_guest else ("cap" if learn_lock.cap_reached else None)
                ),
                "seen_provisional": (
                    not is_guest and not learn_lock.can_persist_modes_seen
                ),
                "required_modes": [m for m in LEARN_MODES if m in required_modes],
                "quiz_cycle": quiz_cycle,
                "quiz_available": quiz_available,
                "quiz_questions": quiz_questions,
                "cloze_available": cloze_available,
                "read_hint": (
                    "Bare Act wording, verbatim. Read it twice, then pick a recall mode."
                ),
                "revision_intent": revision_intent or "",
                "early_revision_due": early_due,
                "early_revision_prompt": bool(early_due) and revision_intent is None,
            },
        )
        record_request_timing("template", started)
        return response

    def _load_session_context(
        eng: ReminderEngine,
        request: Request,
        unit_id: str,
        *,
        is_guest: bool,
    ) -> StudySession | None:
        """The ``?session=`` queue, if it is this user's, active, and holds this unit.

        Guests get None unconditionally: a guest's engine is bound to
        LOCAL_USER_ID, so honouring a session id would read a shared row.
        """
        session_id = (request.query_params.get("session") or "").strip()
        if not session_id or is_guest:
            return None
        session = eng.get_study_session(session_id)
        if session is None or session.status != "active":
            return None
        if session.plan_date != user_today(eng):
            return None
        if not session.contains(unit_id):
            return None
        return session

    @app.post("/learn/{unit_id}/seen")
    async def learn_mode_seen(
        request: Request,
        unit_id: str,
        mode: str = Form(...),
        revision_intent: str = Form(""),
    ) -> JSONResponse:
        eng = _engine()
        unit = eng.get_unit(unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        if mode not in LEARN_MODES:
            raise HTTPException(status_code=400, detail="Invalid learn mode")
        if mode == "test":
            return JSONResponse(
                {"ok": False, "error": "quiz_required", "mode": "test"},
                status_code=400,
            )
        # Trust model: for cloze/letters/type/recite the client reports a
        # completed attempt and the server takes its word (no leaderboard).
        # Test is /quiz-only — never recorded here.
        # Locked modes must never be recorded as seen (UI lock is not trusted).
        if entitlements_active(request):
            eng.preload_account_claims()
        access = resolve_learn_access(request, eng, unit.article_number)
        if access.is_locked(mode):
            return JSONResponse(
                {"ok": False, "error": "mode_locked", "mode": mode},
                status_code=403,
            )
        intent = parse_revision_intent(revision_intent) or _revision_intent_from_query(
            request
        )
        today = user_today(eng)
        if not may_persist_revision_modes(eng, unit_id, as_of=today, intent=intent):
            return JSONResponse({"ok": True, "persisted": False, "mode": mode})
        if not access.can_persist_modes_seen:
            # Claimable/cap-reached Articles: mode visits stay provisional
            # (client-tracked) until the Article is claimed on Done — they
            # never quietly become permanent account progress.
            return JSONResponse({"ok": True, "persisted": False, "mode": mode})
        required = _effective_required_modes(unit, eng.units, access.required_modes)
        seen = eng.mark_mode_seen(unit_id, mode)
        payload = _modes_payload(unit_id, seen, required_count=len(required))
        payload["done"] = done_button_state(unit, seen, required=required)
        payload["persisted"] = True
        return JSONResponse(payload)

    @app.post("/learn/{unit_id}/quiz")
    async def learn_quiz(request: Request, unit_id: str) -> JSONResponse:
        """Grade a Test-mode submission. Test is marked only through this route."""
        eng = _engine()
        unit = eng.get_unit(unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        if not has_quiz(unit, eng.units):
            return JSONResponse(
                {"ok": False, "error": "no_quiz"}, status_code=400
            )
        try:
            submission = QuizSubmission.model_validate(await request.json())
        except (ValidationError, ValueError):
            return JSONResponse(
                {"ok": False, "error": "answers_invalid"}, status_code=400
            )

        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        # Stale-cycle protection: a Done in another tab advances the cycle and
        # clears unit_modes_seen — an old tab's submission must not complete
        # the new cycle. The server's own cycle is authoritative.
        progress = None if is_guest else eng.get_progress(unit_id)
        current_cycle = progress.times_completed if progress is not None else 0
        if submission.cycle != current_cycle:
            return JSONResponse(
                {"ok": False, "error": "stale_quiz", "current_cycle": current_cycle},
                status_code=409,
            )

        questions = build_quiz(unit, eng.units, cycle=current_cycle)
        answers = submission.answers
        if len(answers) != len(questions) or any(
            a is None or (isinstance(a, str) and not a.strip()) for a in answers
        ):
            return JSONResponse(
                {"ok": False, "error": "answers_incomplete"}, status_code=400
            )
        for question, answer in zip(questions, answers):
            if question.kind == "mcq":
                bad = (
                    not isinstance(answer, int)
                    or isinstance(answer, bool)
                    or not (0 <= answer < len(question.options))
                )
            else:
                bad = not isinstance(answer, str)
            if bad:
                return JSONResponse(
                    {"ok": False, "error": "answers_invalid"}, status_code=400
                )

        graded = grade_quiz(questions, answers)
        payload: dict[str, object] = {
            "ok": True,
            "score": {"correct": graded["correct"], "total": graded["total"]},
            "results": graded["results"],
        }
        if is_guest:
            payload["persisted"] = False
            return JSONResponse(payload)
        access = resolve_learn_access(request, eng, unit.article_number)
        if access.is_locked("test"):  # defensive: test is an open mode today
            return JSONResponse(
                {"ok": False, "error": "mode_locked", "mode": "test"},
                status_code=403,
            )
        if not access.can_persist_modes_seen:
            payload["persisted"] = False
            return JSONResponse(payload)
        intent = parse_revision_intent(
            submission.revision_intent
        ) or _revision_intent_from_query(request)
        if not may_persist_revision_modes(
            eng, unit_id, as_of=user_today(eng), intent=intent
        ):
            payload["persisted"] = False
            return JSONResponse(payload)
        required = _effective_required_modes(unit, eng.units, access.required_modes)
        # Idempotent upsert — resubmitting the same cycle is harmless.
        seen = eng.mark_mode_seen(unit_id, "test")
        payload.update(_modes_payload(unit_id, seen, required_count=len(required)))
        payload["done"] = done_button_state(unit, seen, required=required)
        payload["persisted"] = True
        return JSONResponse(payload)

    def _user_today(request: Request, eng: ReminderEngine) -> date:
        """The user's local calendar date — see ``service.user_today``.

        Kept as a thin wrapper so the many call sites here keep their shape;
        the logic moved to service.py because sessions and the dashboard need
        the same date and must not disagree with the ladder across midnight.
        """
        return user_today(eng)

    def _apply_learn_done(
        eng: ReminderEngine,
        unit_id: str,
        *,
        today: date,
        required_modes: frozenset[str] | None,
        intent: str | None,
        claim_article: str | None = None,
        require_all_modes: bool = True,
    ):
        """Branch Done onto mark_done vs complete_revision_early vs no-op."""
        due = early_revision_due(eng, unit_id, as_of=today)
        if due is not None:
            if intent == REVISION_INTENT_PRACTICE:
                return "practice"
            if intent != REVISION_INTENT_CONSUME:
                return "need_intent"
            return eng.complete_revision_early(
                unit_id,
                as_of=today,
                require_all_modes=require_all_modes,
                required_modes=required_modes,
                claim_article=claim_article,
            )
        return eng.mark_done(
            unit_id,
            as_of=today,
            require_all_modes=require_all_modes,
            required_modes=required_modes,
            claim_article=claim_article,
        )

    def _schedule_calendar_sync(request: Request, eng: ReminderEngine) -> None:
        """Fire-and-forget Google Calendar reconciliation after a state change."""
        try:
            from constitution_memorizer.calendar_sync.routes import schedule_sync

            schedule_sync(request, eng.user_id)
        except Exception:  # noqa: BLE001 — projection must never break core flow
            logger.exception("calendar sync scheduling failed")

    @app.post("/learn/{unit_id}/done")
    async def learn_done(request: Request, unit_id: str):
        eng = _engine()
        unit = eng.get_unit(unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            if wants_json(request):
                return JSONResponse({"ok": False, "error": "sign_in_required"}, status_code=401)
            return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)

        # Free-account Article claiming / cap gate (parent-Article level).
        # Units without an article_number (overviews) are never claim-gated.
        claim_key = article_key(unit.article_number)
        if claim_key is not None:
            access = resolve_learn_access(request, eng, unit.article_number)
            if access.cap_reached:
                # 3/3 Free Articles in use — Done on a new Article persists nothing.
                if wants_json(request):
                    return JSONResponse(
                        {
                            "ok": False,
                            "error": "subscription_required",
                            "article_number": claim_key,
                        },
                        status_code=402,
                    )
                return RedirectResponse(
                    url=f"/learn/{unit_id}?gate=subscription", status_code=303
                )
            if access.should_prompt_claim:
                # Unclaimed Articles keep mode visits provisional (nothing is
                # persisted server-side), so the Done POST carries the client's
                # provisional mode list. Claiming rides on Done: only prompt
                # once Done would succeed.
                form = await request.form()
                provisional_modes = {
                    m.strip()
                    for m in str(form.get("modes") or "").split(",")
                    if m.strip() in LEARN_MODES
                }
                claim_required = _effective_required_modes(
                    unit, eng.units, access.required_modes
                )
                modes_ok = (
                    claim_required <= provisional_modes
                    or eng.modes_complete(unit_id)
                )
                if not modes_ok:
                    if wants_json(request):
                        return JSONResponse(
                            {"ok": False, "error": "modes_incomplete"},
                            status_code=409,
                        )
                    return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
                if form.get("claim_article") != "1":
                    if wants_json(request):
                        return JSONResponse(
                            {
                                "ok": False,
                                "error": "claim_required",
                                "article_number": claim_key,
                                "slots_remaining": access.free_slots_remaining,
                            },
                            status_code=409,
                        )
                    return RedirectResponse(
                        url=f"/learn/{unit_id}?claim=1", status_code=303
                    )
                # Previewed access (admin Entitlement Preview) synthesizes
                # should_prompt_claim with can_persist_done=False — a
                # combination outside the real matrix. Confirming the claim
                # must write nothing.
                if not access.can_persist_done:
                    if wants_json(request):
                        return JSONResponse({"ok": True, "persisted": False})
                    return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
                # Confirmed: claim + Done + schedule land in ONE transaction —
                # the claim insert rides inside commit_completion, so either
                # everything persists or nothing does.
                try:
                    today = _user_today(request, eng)
                    intent = parse_revision_intent(
                        form.get("revision_intent")
                    ) or _revision_intent_from_query(request)
                    result = _apply_learn_done(
                        eng,
                        unit_id,
                        today=today,
                        required_modes=None,
                        intent=intent,
                        claim_article=claim_key,
                        require_all_modes=False,
                    )
                except ModesIncompleteError:
                    return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
                if result == "practice":
                    if wants_json(request):
                        return JSONResponse({"ok": True, "persisted": False})
                    return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
                if result == "need_intent":
                    if wants_json(request):
                        return JSONResponse(
                            {"ok": False, "error": "early_revision_intent_required"},
                            status_code=409,
                        )
                    return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
                if result.progress.times_completed == 1:
                    maybe_activate_auto_plan(eng, as_of=today)
                _sync_auto_roadmap(request, eng)
                _schedule_calendar_sync(request, eng)
                navigation = _advance_session(
                    eng, request, unit_id, result.next_unit_id, outcome="completed",
                    done_unit_id=unit_id,
                )
                if wants_json(request):
                    return JSONResponse(
                        done_json_payload(
                            eng=eng,
                            quotes=app.state.quotes,
                            unit=unit,
                            result=result,
                            request=request,
                            multiuser=app.state.multiuser_enabled,
                            navigation=navigation,
                        )
                    )
                return RedirectResponse(url=navigation.next_url, status_code=303)
        done_access = resolve_learn_access(request, eng, unit.article_number)
        if not done_access.can_persist_done:
            # Reachable only under the admin Entitlement Preview — every real
            # non-persisting state (guest, cap) returned above.
            if wants_json(request):
                return JSONResponse({"ok": True, "persisted": False})
            return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
        done_required = _effective_required_modes(
            unit, eng.units, done_access.required_modes
        )
        today = _user_today(request, eng)
        form = await request.form()
        intent = parse_revision_intent(
            form.get("revision_intent")
        ) or _revision_intent_from_query(request)
        try:
            result = _apply_learn_done(
                eng,
                unit_id,
                today=today,
                required_modes=frozenset(done_required),
                intent=intent,
            )
        except ModesIncompleteError:
            if wants_json(request):
                return JSONResponse(
                    {"ok": False, "error": "modes_incomplete"},
                    status_code=409,
                )
            return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
        if result == "practice":
            if wants_json(request):
                return JSONResponse({"ok": True, "persisted": False})
            return RedirectResponse(
                url=with_params(
                    f"/learn/{unit_id}",
                    {"revision_intent": REVISION_INTENT_PRACTICE},
                ),
                status_code=303,
            )
        if result == "need_intent":
            if wants_json(request):
                return JSONResponse(
                    {"ok": False, "error": "early_revision_intent_required"},
                    status_code=409,
                )
            return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
        if result.progress.times_completed == 1:
            maybe_activate_auto_plan(eng, as_of=today)
        _sync_auto_roadmap(request, eng)
        _schedule_calendar_sync(request, eng)
        navigation = _advance_session(
            eng, request, unit_id, result.next_unit_id, outcome="completed",
            done_unit_id=unit_id,
        )
        if wants_json(request):
            return JSONResponse(
                done_json_payload(
                    eng=eng,
                    quotes=app.state.quotes,
                    unit=unit,
                    result=result,
                    request=request,
                    multiuser=app.state.multiuser_enabled,
                    navigation=navigation,
                )
            )
        return RedirectResponse(url=navigation.next_url, status_code=303)

    @app.post("/learn/{unit_id}/again")
    async def learn_again(request: Request, unit_id: str) -> RedirectResponse:
        """Defer this unit until tomorrow, then advance to the next unit."""
        eng = _engine()
        if eng.get_unit(unit_id) is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        result = eng.defer_until_tomorrow(unit_id, as_of=_user_today(request, eng))
        _sync_auto_roadmap(request, eng)
        _schedule_calendar_sync(request, eng)
        # Deferred, not completed: the unit leaves today's queue without
        # counting as a revision done.
        navigation = _advance_session(
            eng, request, unit_id, result.next_unit_id, outcome="deferred"
        )
        return RedirectResponse(url=navigation.next_url, status_code=303)

    def _advance_session(
        eng: ReminderEngine,
        request: Request,
        unit_id: str,
        fallback_next_unit_id: str | None,
        *,
        outcome: str,
        done_unit_id: str | None = None,
    ) -> LearnNavigation:
        """Where this completion goes next, session-aware.

        A guest never reaches here (Done returns earlier), so the session is
        read unconditionally; membership is still checked inside the resolver
        so a forged id cannot redirect someone else's queue.
        """
        session_id = (request.query_params.get("session") or "").strip()
        session = eng.get_study_session(session_id) if session_id else None
        if session is not None and (
            session.status != "active" or session.plan_date != user_today(eng)
        ):
            session = None
        return resolve_learn_navigation(
            eng=eng,
            unit_id=unit_id,
            fallback_next_unit_id=fallback_next_unit_id,
            session=session,
            outcome=outcome,  # type: ignore[arg-type]
            multiuser=app.state.multiuser_enabled,
            done_unit_id=done_unit_id,
        )

    @app.post("/revision/start")
    async def revision_start(request: Request) -> RedirectResponse:
        """Open (or resume) today's revision queue and enter its first item.

        A POST, not a GET: it creates durable state, and being idempotent
        means a double-tap resumes the same session rather than snapshotting
        the due list twice.
        """
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            # A guest engine is bound to LOCAL_USER_ID; writing a session here
            # would land in a shared row.
            return RedirectResponse(url="/login?next=/dashboard", status_code=303)
        today = user_today(eng)
        try:
            started = time.perf_counter()
            session = start_or_resume_revision(eng, as_of=today)
            record_request_timing("revision_start", started)
        except Exception as error:  # noqa: BLE001 — re-raised unless it is the schema gap
            if not _is_missing_optional_schema(error):
                raise
            # Code is live ahead of its migration. Fall back to the behaviour
            # this CTA replaced — walk the due list sequentially — so the
            # button is never a dead end.
            logger.warning("study_session tables are missing; starting an unqueued revision")
            session = None
            due = due_checklist(eng, as_of=today)
            if not due:
                return RedirectResponse(url=_home_url(), status_code=303)
            return RedirectResponse(
                url=next_learn_url(
                    eng,
                    due[0].id,
                    multiuser=app.state.multiuser_enabled,
                    mode=session_entry_mode("revision"),
                ),
                status_code=303,
            )
        if session is None or not session.pending:
            return RedirectResponse(url=_home_url(), status_code=303)
        first = session.pending[0].learning_unit_id
        return RedirectResponse(
            url=next_learn_url(
                eng,
                first,
                multiuser=app.state.multiuser_enabled,
                session_id=session.id,
                mode=session_entry_mode("revision"),
            ),
            status_code=303,
        )

    def _home_url() -> str:
        return "/dashboard" if app.state.multiuser_enabled else "/"

    def _revision_blocks_new_learning(eng: ReminderEngine, today: date) -> bool:
        if due_checklist(eng, as_of=today):
            return True
        revision = active_revision_session(eng, as_of=today)
        return bool(revision is not None and revision.remaining > 0)

    def _plan_my_day_allowed(eng: ReminderEngine, today: date) -> bool:
        if _revision_blocks_new_learning(eng, today):
            return False
        if eng.get_learning_plan().mode != "self_paced":
            return False
        if eng.study_session_for_day(kind="auto_learning", plan_date=today) is not None:
            return False
        return True

    def _guest_login(next_url: str) -> RedirectResponse:
        return RedirectResponse(url=f"/login?next={next_url}", status_code=303)

    @app.post("/learn/{unit_id}/skip")
    async def learn_skip(request: Request, unit_id: str):
        """Skip a new-learning queue item without writing progress."""
        eng = _engine()
        if eng.get_unit(unit_id) is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            if wants_json(request):
                return JSONResponse({"ok": False, "error": "sign_in_required"}, status_code=401)
            return RedirectResponse(url=f"/learn/{unit_id}", status_code=303)
        session_id = (request.query_params.get("session") or "").strip()
        session = eng.get_study_session(session_id) if session_id else None
        if (
            session is None
            or session.status != "active"
            or session.plan_date != user_today(eng)
            or session.kind not in ("auto_learning", "day_plan")
            or not session.contains(unit_id)
        ):
            return RedirectResponse(url=_home_url(), status_code=303)
        navigation = resolve_learn_navigation(
            eng=eng,
            unit_id=unit_id,
            fallback_next_unit_id=None,
            session=session,
            outcome="deferred",
            multiuser=app.state.multiuser_enabled,
        )
        _sync_auto_roadmap(request, eng)
        if wants_json(request):
            return JSONResponse(
                {
                    "ok": True,
                    "next_url": navigation.next_url,
                    "session_id": navigation.session_id,
                    "session_remaining": navigation.remaining,
                }
            )
        return RedirectResponse(url=navigation.next_url, status_code=303)

    @app.post("/learning/start")
    async def learning_start(request: Request) -> RedirectResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/dashboard")
        eng.bootstrap_request(include_account=entitlements_active(request))
        today = user_today(eng)
        try:
            eng.ensure_planner_bundle(as_of=today)
        except Exception as error:  # noqa: BLE001 — schema-gap only
            if not _is_missing_optional_schema(error):
                raise
        started = time.perf_counter()
        blocked = _revision_blocks_new_learning(eng, today)
        record_request_timing("due_build", started)
        if blocked:
            return RedirectResponse(url=_home_url(), status_code=303)
        for kind in ("auto_learning", "day_plan"):
            existing = eng.active_study_session(kind=kind, plan_date=today)
            if existing is not None and existing.pending:
                first = existing.pending[0].learning_unit_id
                return RedirectResponse(
                    url=next_learn_url(
                        eng,
                        first,
                        multiuser=app.state.multiuser_enabled,
                        session_id=existing.id,
                        mode=session_entry_mode(existing.kind),
                    ),
                    status_code=303,
                )
        if not can_use_auto_plan(request):
            return RedirectResponse(url=_home_url(), status_code=303)
        plan = eng.get_learning_plan()
        if not plan.is_auto or plan.daily_target is None:
            return RedirectResponse(url=_home_url(), status_code=303)
        args = learning_entitlement_args(request, eng)
        ensure_auto_roadmap(
            eng,
            as_of=today,
            auto_entitled=True,
            **args,
        )
        planned = eng.list_auto_plan_day(today)
        unit_ids = (
            [item.learning_unit_id for item in planned.items] if planned is not None else []
        )
        already = eng.study_session_for_day(kind="auto_learning", plan_date=today)
        if already is not None:
            session = already
        else:
            session = start_or_resume_learning(
                eng, kind="auto_learning", unit_ids=unit_ids, as_of=today
            )
            if session is not None:
                persist_session_anchor_theme(eng, unit_ids)
        if session is None or not session.pending:
            return RedirectResponse(url=_home_url(), status_code=303)
        first = session.pending[0].learning_unit_id
        return RedirectResponse(
            url=next_learn_url(
                eng,
                first,
                multiuser=app.state.multiuser_enabled,
                session_id=session.id,
                mode=session_entry_mode(session.kind),
            ),
            status_code=303,
        )

    @app.get("/learning/plan-my-day", response_class=HTMLResponse)
    async def plan_my_day_get(request: Request) -> HTMLResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/learning/plan-my-day")
        today = user_today(eng)
        if not _plan_my_day_allowed(eng, today):
            return RedirectResponse(url=_home_url(), status_code=303)
        return templates.TemplateResponse(request, "plan_my_day.html", {})

    @app.post("/learning/plan-my-day")
    async def plan_my_day_post(
        request: Request,
        target: int = Form(...),
    ) -> RedirectResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/learning/plan-my-day")
        if target not in (3, 5, 7):
            raise HTTPException(status_code=400, detail="Invalid learning target")
        today = user_today(eng)
        if not _plan_my_day_allowed(eng, today):
            return RedirectResponse(url=_home_url(), status_code=303)
        args = learning_entitlement_args(request, eng)
        unit_ids = select_today_mix(eng, target=target, as_of=today, **args)
        session = start_or_resume_learning(
            eng, kind="day_plan", unit_ids=unit_ids, as_of=today
        )
        if session is None or not session.pending:
            return RedirectResponse(url=_home_url(), status_code=303)
        # Back to Today, where the mix is now listed as the path. Planning the
        # day and starting it are two decisions: dropping straight into the
        # first unit took the second one on the user's behalf, and hid what
        # had just been planned.
        return RedirectResponse(url=_home_url(), status_code=303)

    @app.post("/learning/plan-my-day/dismiss")
    async def plan_my_day_dismiss(request: Request) -> RedirectResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/dashboard")
        eng.dismiss_plan_prompt(user_today(eng))
        return RedirectResponse(url=_home_url(), status_code=303)

    @app.get("/onboarding/plan", response_class=HTMLResponse)
    async def onboarding_plan_get(request: Request) -> HTMLResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/onboarding/plan")
        return templates.TemplateResponse(
            request,
            "onboarding_plan.html",
            {
                "auto_available": can_use_auto_plan(request),
                "plan": eng.get_learning_plan(),
                "csrf_token": request.cookies.get("rtc_csrf") or "",
            },
        )

    @app.post("/onboarding/plan")
    async def onboarding_plan_post(
        request: Request,
        mode: str = Form("self_paced"),
        daily_target: str = Form(""),
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/onboarding/plan")
        expected = request.cookies.get("rtc_csrf") or ""
        if expected and csrf_token != expected:
            return RedirectResponse(url="/onboarding/plan?error=csrf", status_code=303)
        # Preview simulates another tier in the UI; it must not persist this
        # admin's durable learning-plan row.
        if preview_state(request) is not None:
            return RedirectResponse(url=_home_url(), status_code=303)
        chosen_mode = "self_paced"
        target: int | None = None
        if mode == "auto" and can_use_auto_plan(request):
            try:
                parsed = int(daily_target)
            except ValueError:
                parsed = 0
            if parsed in (3, 5, 7):
                chosen_mode = "auto"
                target = parsed
        eng.upsert_learning_plan(
            mode=chosen_mode, daily_target=target, as_of=user_today(eng)
        )  # type: ignore[arg-type]
        _sync_auto_roadmap(request, eng)
        return RedirectResponse(url=_home_url(), status_code=303)

    @app.post("/settings/learning-plan")
    async def settings_learning_plan(
        request: Request,
        mode: str = Form("self_paced"),
        daily_target: str = Form(""),
    ) -> RedirectResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if is_guest:
            return _guest_login("/settings")
        # Preview is a UI/testing simulation. It is not Auto Plan entitlement
        # and must not rewrite this user's durable learning-plan preference.
        if preview_state(request) is not None:
            return RedirectResponse(url="/settings", status_code=303)
        chosen_mode = "self_paced"
        target: int | None = None
        if mode == "auto" and can_use_auto_plan(request):
            try:
                parsed = int(daily_target)
            except ValueError:
                parsed = 0
            if parsed in (3, 5, 7):
                chosen_mode = "auto"
                target = parsed
        eng.upsert_learning_plan(
            mode=chosen_mode, daily_target=target, as_of=user_today(eng)
        )  # type: ignore[arg-type]
        _sync_auto_roadmap(request, eng)
        return RedirectResponse(url="/settings?saved=1", status_code=303)

    @app.get("/learn/{clause_id}/choose", response_class=HTMLResponse)
    async def choose_get(request: Request, clause_id: str) -> HTMLResponse:
        eng = _engine()
        unit = eng.get_unit(clause_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        if not unit.allows_letter_split:
            return RedirectResponse(url=f"/learn/{clause_id}", status_code=303)
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if not is_guest:
            eng.bootstrap_request()
        session_param = request.query_params.get("session") or ""
        existing = eng.get_split_preference(clause_id)
        if existing is not None:
            target = eng.next_to_learn_from_clause(clause_id) or clause_id
            return RedirectResponse(
                url=with_params(f"/learn/{target}", {"session": session_param}),
                status_code=303,
            )
        done_id = request.query_params.get("done")
        started = time.perf_counter()
        completion = build_completion(
            eng=eng,
            quotes=app.state.quotes,
            done_id=done_id,
            request=request,
            is_guest=is_guest,
            continue_href=f"/learn/{clause_id}/choose",
            continue_label=unit.display_title,
        )
        record_request_timing("completion", started)
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "choose.html",
            {"unit": unit, "completion": completion, "session_id": session_param},
        )
        record_request_timing("template", started)
        return response

    @app.post("/learn/{clause_id}/choose")
    async def choose_post(
        request: Request,
        clause_id: str,
        mode: str = Form(...),
    ) -> RedirectResponse:
        eng = _engine()
        unit = eng.get_unit(clause_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        if not unit.allows_letter_split:
            return RedirectResponse(url=f"/learn/{clause_id}", status_code=303)
        if mode not in ("whole", "letters"):
            raise HTTPException(status_code=400, detail="mode must be whole or letters")
        chosen: SplitMode = mode  # type: ignore[assignment]
        eng.set_split_preference(clause_id, chosen)
        _schedule_calendar_sync(request, eng)
        _sync_auto_roadmap(request, eng)
        session_id = (request.query_params.get("session") or "").strip()
        session = eng.get_study_session(session_id) if session_id else None
        if (
            chosen == "letters"
            and session is not None
            and session.kind in ("auto_learning", "day_plan")
            and session.status == "active"
            and session.plan_date == user_today(eng)
            and session.contains(clause_id)
            and is_unlearned(eng, clause_id)
        ):
            children = [child for child in unit.child_unit_ids if child]
            if children:
                eng.replace_study_session_unit(
                    session_id=session.id,
                    old_unit_id=clause_id,
                    new_unit_ids=children,
                )
        target = eng.next_to_learn_from_clause(clause_id, mode=chosen) or clause_id
        return RedirectResponse(
            url=with_params(
                f"/learn/{target}",
                {"session": session_id},
            ),
            status_code=303,
        )

    @app.post("/learn/{unit_id}/reset")
    async def reset_unit(
        request: Request,
        unit_id: str,
        mode: str = Query(default="read"),
    ) -> RedirectResponse:
        eng = _engine()
        if eng.get_unit(unit_id) is None:
            raise HTTPException(status_code=404, detail="Learning unit not found")
        eng.delete_progress(unit_id)
        eng.clear_modes_seen(unit_id)
        _schedule_calendar_sync(request, eng)
        if mode == "card":  # compatibility alias for the retired mode key
            mode = "test"
        learn_mode = mode if mode in LEARN_MODES else "read"
        # Re-seed the currently open mode on the next GET; redirect preserves mode.
        suffix = f"?mode={learn_mode}" if learn_mode != "read" else ""
        return RedirectResponse(url=f"/learn/{unit_id}{suffix}", status_code=303)

    @app.post("/reset")
    async def reset_all(request: Request) -> RedirectResponse:
        """Clear this user's progress and preferences (study reset)."""
        eng = _engine()
        eng.reset_all_personal_data()
        _schedule_calendar_sync(request, eng)
        return RedirectResponse(url="/", status_code=303)

    @app.get("/browse", response_class=HTMLResponse)
    async def browse_index(request: Request) -> HTMLResponse:
        eng = _engine()
        if not getattr(request.state, "is_guest", False):
            eng.bootstrap_request(
                include_news=True,
                include_account=entitlements_active(request),
            )
        started = time.perf_counter()
        sections = browse_parts_sections(eng, app.state.reviewed)
        record_request_timing("browse_build", started)
        parts_source = "reviewed" if app.state.reviewed is not None else "units-seed"
        access = access_summary(request, eng)
        claimed = set(access.claimed_articles) if access.enabled else set()
        # Phone Browse is Part-first (design 02): each Part card carries its own
        # progress and due count, and opens a Part page instead of scrolling.
        today = date.today()
        cont_id = continue_unit_id(eng, as_of=today)
        part_cards = [
            {
                "section": section,
                "href": part_href(section.part_number),
                "summary": part_progress_summary(
                    eng, section, today=today, continue_id=cont_id
                ),
            }
            for section in sections
        ]
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "browse_index.html",
            {
                "sections": sections,
                "part_cards": part_cards,
                "has_reviewed": app.state.reviewed is not None,
                "parts_source": parts_source,
                "present_marks": present_browse_marks(sections),
                "access": access,
                "claimed_articles": claimed,
            },
        )
        record_request_timing("template", started)
        return response

    @app.get("/browse/part/{part_slug}", response_class=HTMLResponse)
    async def browse_part(request: Request, part_slug: str) -> HTMLResponse:
        """One Part, Articles as rows (mobile designs 03 / 16 / 18)."""
        eng = _engine()
        if not getattr(request.state, "is_guest", False):
            eng.bootstrap_request(
                include_news=True,
                include_account=entitlements_active(request),
            )
        started = time.perf_counter()
        sections = browse_parts_sections(eng, app.state.reviewed)
        record_request_timing("browse_build", started)
        section = find_part_section(sections, part_slug)
        if section is None:
            raise HTTPException(status_code=404, detail="Part not found")
        access = access_summary(request, eng)
        claimed = set(access.claimed_articles) if access.enabled else set()
        today = date.today()
        cont_id = continue_unit_id(eng, as_of=today)
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "browse_part.html",
            {
                "section": section,
                "summary": part_progress_summary(
                    eng, section, today=today, continue_id=cont_id
                ),
                "present_marks": present_browse_marks([section]),
                "access": access,
                "claimed_articles": claimed,
            },
        )
        record_request_timing("template", started)
        return response

    @app.get("/browse/article/{article_number}", response_class=HTMLResponse)
    async def browse_article(request: Request, article_number: str) -> HTMLResponse:
        eng = _engine()
        if not getattr(request.state, "is_guest", False):
            eng.bootstrap_request(
                include_news=True,
                include_account=entitlements_active(request),
            )
        started = time.perf_counter()
        view = build_article_view(
            eng,
            app.state.reviewed,
            article_number,
            amendments_catalog=app.state.amendments,
        )
        if view is None:
            raise HTTPException(status_code=404, detail="Article not found")
        prev_number, next_number = adjacent_article_numbers(
            eng, app.state.reviewed, view.article_number
        )
        gloss_text = eng.get_gloss(view.article_number) or ""
        gloss_ph = gloss_placeholder_for(
            app.state.gloss_placeholders, view.article_number
        )
        judicial = get_judicial_evolution(
            app.state.judicial_evolution, view.article_number
        )
        catalog = app.state.text_annotations
        browse_anns = annotations_for_article(
            catalog,
            view.article_number,
            [u.id for u in view.learn_units],
            surface="browse",
        )
        notes = catalog.notes if hasattr(catalog, "notes") else {}
        annotated_text = annotate_plain_text(
            view.full_text,
            browse_anns,
            notes=notes,
            unit_id=f"browse-article-{view.article_number}",
        )
        # Phone header (design 04): the Part by name, the saved / progress /
        # amendments meta line, and the Article's own marks in the top bar.
        access = access_summary(request, eng)
        claimed = set(access.claimed_articles) if access.enabled else set()
        part_title = (
            part_title_from_seed(view.part_number)
            if str(view.part_number or "").upper() != "UNKNOWN"
            else None
        )
        phone_meta = article_phone_meta(
            view.learn_units,
            saved=view.article_number in claimed,
            amendment_count=len(view.amendments or ()),
        )
        in_news = view.article_number in parse_news_articles(
            eng.get_news_articles_raw()
        )
        record_request_timing("article_build", started)
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "browse_article.html",
            {
                "article": view,
                "prev_article": prev_number,
                "next_article": next_number,
                "gloss_text": gloss_text,
                "gloss_placeholder": gloss_ph,
                "judicial_evolution": judicial,
                "annotated_text": annotated_text,
                "has_text_annotations": bool(browse_anns),
                "part_title": part_title,
                "phone_meta": phone_meta,
                "article_marks": marks_for_article(
                    view.article_number, in_news=in_news
                ),
                "access": access,
            },
        )
        record_request_timing("template", started)
        return response

    @app.put("/browse/article/{article_number}/gloss")
    async def put_article_gloss(article_number: str, request: Request) -> JSONResponse:
        eng = _engine()
        numbers = {n.lower() for n in list_article_numbers(eng, app.state.reviewed)}
        if article_number.lower() not in numbers:
            # Allow gloss for units-known articles even if not in reviewed list
            has_units = any(
                (u.article_number or "").lower() == article_number.lower()
                for u in eng.units.values()
            )
            if not has_units:
                raise HTTPException(status_code=404, detail="Article not found")
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid JSON") from exc
        text = str(payload.get("text", "")) if isinstance(payload, dict) else ""
        trimmed = text.strip()
        if not trimmed:
            eng.delete_gloss(article_number)
            return JSONResponse({"ok": True, "text": "", "words": 0})
        eng.upsert_gloss(article_number, text)
        words = len(trimmed.split())
        return JSONResponse({"ok": True, "text": text, "words": words})

    @app.delete("/browse/article/{article_number}/gloss")
    async def delete_article_gloss(article_number: str) -> JSONResponse:
        eng = _engine()
        eng.delete_gloss(article_number)
        return JSONResponse({"ok": True, "text": "", "words": 0})

    @app.get("/api/articles/{article_number}/progress")
    async def article_progress_summary(
        request: Request, article_number: str
    ) -> JSONResponse:
        """Per-Article CTA state, fetched after first paint.

        Deliberately its own endpoint: the Article page must not gain a
        synchronous progress read just to personalise one button, so the HTML
        ships the neutral label and this fills it in afterwards. Guests never
        call it and get nothing if they do.
        """
        if app.state.multiuser_enabled and (
            getattr(request.state, "current_user", None) is None
        ):
            return JSONResponse({"ok": False}, status_code=401)
        eng = _engine()
        eng.bootstrap_request(include_modes=True)
        started = time.perf_counter()
        today = date.today()
        required, _pending = path_units_for_article(eng, article_number)
        if not required:
            record_request_timing("article_progress", started)
            return JSONResponse(
                {"ok": True, "state": "not_started", "modes_done": 0,
                 "modes_total": len(LEARN_MODES)}
            )

        # One unit speaks for the Article: a unit due today wins, else the
        # first one still incomplete. Never sum modes across units — "2 of 6"
        # has to describe a single clause to mean anything.
        lead = None
        state = "not_started"
        for unit in required:
            progress = eng.get_progress(unit.id)
            if progress is not None and progress.next_revision is not None:
                if progress.next_revision <= today:
                    lead, state = unit, "due"
                    break
        if lead is None:
            for unit in required:
                if not _is_completed(eng, unit.id):
                    lead = unit
                    break
            if lead is not None:
                seen_any = any(len(eng.modes_seen(u.id)) > 0 for u in required)
                state = "started" if seen_any else "not_started"
            else:
                lead, state = required[0], "started"
        payload = {
            "ok": True,
            "state": state,
            "modes_done": len(eng.modes_seen(lead.id)),
            "modes_total": len(LEARN_MODES),
        }
        record_request_timing("article_progress", started)
        return JSONResponse(payload)

    @app.get("/search", response_class=HTMLResponse)
    async def search_page(
        request: Request,
        q: str | None = Query(default=None),
    ) -> HTMLResponse:
        eng = _engine()
        hit = None
        if q and q.strip():
            hit = resolve_search(eng, q.strip())
            if hit.redirect_url:
                return RedirectResponse(url=hit.redirect_url, status_code=303)
        return templates.TemplateResponse(
            request,
            "search.html",
            {
                "q": q or "",
                "hit": hit,
            },
        )

    @app.get("/calendar", response_class=HTMLResponse)
    async def calendar_page(
        request: Request,
        year: int | None = Query(default=None),
        month: int | None = Query(default=None),
    ) -> HTMLResponse:
        eng = _engine()
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        if not is_guest:
            eng.bootstrap_request(include_account=entitlements_active(request))
        today = user_today(eng)
        y = year if year is not None else today.year
        m = month if month is not None else today.month
        if m < 1 or m > 12 or y < 1 or y > 9999:
            raise HTTPException(status_code=400, detail="Invalid year or month")
        if not is_guest:
            from constitution_memorizer.planner.roadmap import roadmap_horizon

            month_start = date(y, m, 1)
            month_end = (
                date(y + 1, 1, 1) - timedelta(days=1)
                if m == 12
                else date(y, m + 1, 1) - timedelta(days=1)
            )
            horizon = roadmap_horizon(today)
            try:
                eng.ensure_planner_bundle(
                    as_of=today,
                    auto_start=min(today, month_start),
                    auto_until=max(horizon, month_end),
                )
            except Exception as error:  # noqa: BLE001 — schema-gap only
                if not _is_missing_optional_schema(error):
                    raise
                logger.warning(
                    "planner tables are missing; Calendar is falling back. "
                    "Run `alembic upgrade head` against this database."
                )
            _sync_auto_roadmap(request, eng, force=False)
        started = time.perf_counter()
        view = build_calendar_month(
            eng,
            year=y,
            month=m,
            today=today,
            auto_entitled=can_use_auto_plan(request),
        )
        # The phone shows this month's data as a week strip + today + ladder
        # (design 19); only meaningful for the current month.
        revisions = (
            build_revisions_view(eng, today=today)
            if (y, m) == (today.year, today.month)
            else None
        )
        # Design 4f names the pace on planned rows ("New · Steady plan"). Only an
        # auto plan has one — Plan my day never sets a pace, so those days read
        # plain "New".
        pace = None
        if not is_guest:
            try:
                plan = eng.get_learning_plan()
                if plan is not None and plan.is_auto:
                    pace = plan_pace_label(plan.daily_target)
            except Exception:  # noqa: BLE001 — the calendar must still render
                logger.exception("learning plan pace lookup failed")
        record_request_timing("calendar_build", started)
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "calendar.html",
            {"calendar": view, "revisions": revisions, "pace_label": pace},
        )
        record_request_timing("template", started)
        return response

    @app.get("/progress", response_class=HTMLResponse)
    async def progress_page(request: Request) -> HTMLResponse:
        if app.state.multiuser_enabled and getattr(request.state, "current_user", None) is None:
            return templates.TemplateResponse(
                request,
                "guest_gate.html",
                {"gate_kind": "progress", "reason": "default"},
            )
        eng = _engine()
        eng.bootstrap_request()
        started = time.perf_counter()
        dashboard = progress_dashboard(
            eng,
            reviewed=app.state.reviewed,
            today=date.today(),
        )
        record_request_timing("progress_dashboard", started)
        return templates.TemplateResponse(
            request,
            "progress.html",
            {"dashboard": dashboard},
        )

    @app.get("/progress/mastered", response_class=HTMLResponse)
    async def progress_mastered_page(request: Request) -> HTMLResponse:
        if app.state.multiuser_enabled and getattr(request.state, "current_user", None) is None:
            return templates.TemplateResponse(
                request,
                "guest_gate.html",
                {"gate_kind": "progress", "reason": "default"},
            )
        eng = _engine()
        eng.bootstrap_request()
        started = time.perf_counter()
        dashboard = progress_dashboard(
            eng,
            reviewed=app.state.reviewed,
            today=date.today(),
        )
        record_request_timing("progress_dashboard", started)
        return templates.TemplateResponse(
            request,
            "progress_mastered.html",
            {"dashboard": dashboard},
        )

    @app.get("/tables", response_class=HTMLResponse)
    async def tables_page(
        request: Request,
        tab: str | None = Query(default=None),
    ) -> HTMLResponse:
        tabs = list_table_tabs()
        if not tabs:
            raise HTTPException(
                status_code=500,
                detail="Tables data missing — run from repo root and pull sprint-29",
            )
        tab_ids = {t.id for t in tabs}
        selected = tab if tab in tab_ids else tabs[0].id
        payload = load_table_tab(selected)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Table not found: {selected}")
        return templates.TemplateResponse(
            request,
            "tables.html",
            {
                "tabs": tabs,
                "selected": selected,
                "payload": payload,
                "row_is_muted": row_is_muted,
            },
        )

    def _bootstrap_laws_request(request: Request) -> None:
        """One batched read for the shared template context on Laws pages.

        A Laws page renders no user data, but the chrome around it does:
        base.html needs the theme, the onboarding status and the due badge.
        Unbootstrapped those are three independent reads, and production
        measured each at ~217 ms cross-region — about 650 ms of a 656 ms
        request. Seeding the engine's request-local caches once turns all
        three into cache hits, which is the shape /browse already has.

        Defaults only. Laws needs no account, modes or news pack; asking for
        one would trade three reads for a larger single one.

        Guests never get here: every one of those context values
        short-circuits for them, so bootstrapping would add a read to a path
        that today performs none.
        """
        if not app.state.multiuser_enabled:
            # Single-user keeps one long-lived engine whose caches already
            # survive between requests; there is nothing per-request to seed.
            return
        if getattr(request.state, "current_user", None) is None:
            return
        bound = getattr(request.state, "bound_engine", None)
        if bound is None:
            return
        bound.bootstrap_request()

    @app.get(
        "/laws", response_class=HTMLResponse, dependencies=[Depends(_bootstrap_laws_request)]
    )
    async def laws_page(request: Request) -> HTMLResponse:
        catalog = load_catalog()
        context = {
            "catalog": catalog,
            "laws": catalog.laws,
            "subjects": catalog.visible_subjects,
            "initial_q": request.query_params.get("q") or "",
            "initial_subject": request.query_params.get("subject") or "",
        }
        started = time.perf_counter()
        response = templates.TemplateResponse(request, "laws.html", context)
        record_request_timing("template", started)
        return response

    @app.get(
        "/laws/{law_id}", response_class=HTMLResponse, dependencies=[Depends(_bootstrap_laws_request)]
    )
    async def law_detail_page(request: Request, law_id: str) -> HTMLResponse:
        # One Laws namespace, two kinds of Act. A Bare Act is read in full, so
        # it gets the chapter list; a seeded law is a clause extract mapped to
        # Articles, so it keeps the page it has always had.
        bare = get_bare_act(law_id)
        if bare is not None:
            started = time.perf_counter()
            response = templates.TemplateResponse(
                request, "bare_act.html", {"act": bare}
            )
            record_request_timing("template", started)
            return response
        act = get_law(law_id)
        if act is None:
            raise HTTPException(status_code=404, detail="Law not found")
        tracked = set(list_article_numbers(_engine(), app.state.reviewed))
        return templates.TemplateResponse(
            request,
            "law_detail.html",
            {"act": act, "tracked_articles": tracked},
        )

    @app.get(
        "/laws/{law_id}/section/{number}",
        response_class=HTMLResponse,
        dependencies=[Depends(_bootstrap_laws_request)],
    )
    async def bare_act_section_page(
        request: Request, law_id: str, number: str
    ) -> HTMLResponse:
        # Reference reading: no auth, no entitlement, no engine. Nothing here
        # records progress, schedules a revision or writes a calendar event.
        bare = get_bare_act(law_id)
        if bare is None:
            raise HTTPException(status_code=404, detail="Law not found")
        section = bare.section(number)
        if section is None:
            raise HTTPException(status_code=404, detail="Section not found")
        previous, following = bare.neighbours(number)
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "bare_act_section.html",
            {
                "act": bare,
                "section": section,
                "prev_section": previous,
                "next_section": following,
                "footnotes": bare.notes(section.note_ids),
            },
        )
        record_request_timing("template", started)
        return response

    @app.get(
        "/laws/{law_id}/schedule/{schedule_slug}",
        response_class=HTMLResponse,
        dependencies=[Depends(_bootstrap_laws_request)],
    )
    async def bare_act_schedule_page(
        request: Request, law_id: str, schedule_slug: str
    ) -> HTMLResponse:
        bare = get_bare_act(law_id)
        if bare is None:
            raise HTTPException(status_code=404, detail="Law not found")
        schedule = bare.schedule(schedule_slug)
        if schedule is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        started = time.perf_counter()
        response = templates.TemplateResponse(
            request,
            "bare_act_schedule.html",
            {
                "act": bare,
                "schedule": schedule,
                "footnotes": bare.notes(schedule.note_ids),
            },
        )
        record_request_timing("template", started)
        return response

    @app.get("/memory", response_class=HTMLResponse)
    async def memory_page(
        request: Request,
        year: int | None = Query(default=None),
        month: int | None = Query(default=None),
    ) -> HTMLResponse:
        today = date.today()
        y = year if year is not None else today.year
        m = month if month is not None else today.month
        if m < 1 or m > 12:
            raise HTTPException(status_code=400, detail="Invalid month")
        try:
            calendar = build_memory_month(_memory(), year=y, month=m, today=today)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        entries = _memory().list_all()
        photo_ids = {
            entry.id for entry in entries if _memory().photo_file(entry.id) is not None
        }
        return templates.TemplateResponse(
            request,
            "memory.html",
            {
                "calendar": calendar,
                "entries": entries,
                "photo_ids": photo_ids,
            },
        )

    @app.post("/memory")
    async def memory_create(
        title: str = Form(...),
        acronym: str = Form(""),
    ) -> RedirectResponse:
        cleaned = title.strip()
        if not cleaned:
            raise HTTPException(status_code=400, detail="Title required")
        entry = _memory().create(title=cleaned, acronym=acronym.strip())
        return RedirectResponse(url=f"/memory/{entry.id}", status_code=303)

    @app.get("/memory/media/{entry_id}")
    async def memory_media(entry_id: str) -> FileResponse:
        path = _memory().photo_file(entry_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        _, media_type = _sniff_photo(path.read_bytes()[:64], path.name)
        return FileResponse(path, media_type=media_type)

    @app.get("/memory/{entry_id}", response_class=HTMLResponse)
    async def memory_detail_page(request: Request, entry_id: str) -> HTMLResponse:
        entry = _memory().get(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        photo_path = _memory().photo_file(entry_id)
        return templates.TemplateResponse(
            request,
            "memory_detail.html",
            {
                "entry": entry,
                "schedule": schedule_chip_states(entry, today=date.today()),
                "has_photo": photo_path is not None,
            },
        )

    @app.post("/memory/{entry_id}/notes")
    async def memory_save_notes(
        entry_id: str,
        notes: str = Form(""),
    ) -> RedirectResponse:
        if _memory().get(entry_id) is None:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        _memory().update_notes(entry_id, notes)
        return RedirectResponse(url=f"/memory/{entry_id}", status_code=303)

    @app.post("/memory/{entry_id}/done")
    async def memory_done(entry_id: str) -> RedirectResponse:
        if _memory().get(entry_id) is None:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        _memory().mark_done(entry_id)
        return RedirectResponse(url=f"/memory/{entry_id}", status_code=303)

    @app.post("/memory/{entry_id}/photo")
    async def memory_upload_photo(
        entry_id: str,
        photo: UploadFile = File(...),
    ) -> RedirectResponse:
        mem = _memory()
        if mem.get(entry_id) is None:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        content = await photo.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty upload")
        filename = photo.filename or "note.jpg"
        suffix, _media_type = _sniff_photo(content, filename)
        if suffix not in _ALLOWED_PHOTO_SUFFIXES:
            raise HTTPException(status_code=400, detail="Unsupported image type")
        user_dir = mem.user_media_dir()
        # Remove any prior file for this entry (extension may change after sniff).
        for old in user_dir.glob(f"{entry_id}.*"):
            try:
                old.unlink()
            except OSError:
                pass
        dest_name = f"{entry_id}{suffix}"
        dest = user_dir / dest_name
        dest.write_bytes(content)
        from constitution_memorizer.progress.user_ids import as_user_id

        storage_key = f"{as_user_id(mem.user_id)}/{dest_name}"
        mem.set_photo(entry_id, storage_key)
        return RedirectResponse(url=f"/memory/{entry_id}", status_code=303)

    @app.get("/terms", response_class=HTMLResponse)
    @app.get("/privacy", response_class=HTMLResponse)
    @app.get("/grievance", response_class=HTMLResponse)
    async def legal_page(request: Request) -> HTMLResponse:
        """Public Terms, Privacy and Grievance pages for Google OAuth branding."""
        slug = request.url.path.strip("/")
        page = PAGES.get(slug)
        if page is None:
            raise HTTPException(status_code=404, detail="Not found")
        if getattr(settings, "app_env", "") == "production":
            missing = missing_legal_configuration(settings)
            if missing:
                logger.warning(
                    "Legal pages missing configuration; do not submit Google "
                    "verification while these are empty: %s",
                    ", ".join(missing),
                )
        return templates.TemplateResponse(
            request,
            page.template,
            legal_page_context(slug, settings),
        )

    @app.get("/pricing", response_class=HTMLResponse)
    async def pricing_page(
        request: Request,
        d: str | None = Query(default=None),
    ) -> HTMLResponse:
        """Duration-selector pricing page. 404 while PRICING_ENABLED is off."""
        if not app.state.pricing_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        selected = get_plan(d if d is not None else DEFAULT_DAYS)
        is_guest = bool(
            app.state.multiuser_enabled
            and getattr(request.state, "current_user", None) is None
        )
        return templates.TemplateResponse(
            request,
            "pricing.html",
            {
                "all_plans": PLANS,
                "more_days": list(MORE_DAYS),
                "selected": selected,
                "selected_per_day": f"{per_day(selected):.2f}",
                "selected_billing": billing_line(selected),
                "pricing_data": plans_json(),
                "free_href": "/login" if is_guest else "/browse",
                "cta_href": (
                    "/login" if is_guest else "/subscribe/confirm"
                ),
                # Standalone marketing pricing page follows the same persisted
                # landing theme (default dark) as the / landing.
                "landing_theme": (
                    "light"
                    if request.cookies.get("rtc_landing_theme") == "light"
                    else "dark"
                ),
            },
        )

    @app.get("/subscribe/confirm", response_class=HTMLResponse)
    async def subscribe_confirm(
        request: Request,
        d: str | None = Query(default=None),
    ) -> Response:
        """Purchase step 1 — confirm the plan before the payment handoff."""
        if not app.state.pricing_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        plan = get_plan(d if d is not None else DEFAULT_DAYS)
        user = getattr(request.state, "current_user", None)
        if app.state.multiuser_enabled and user is None:
            return RedirectResponse(
                url=f"/login?next=/pricing%3Fd%3D{plan.days}", status_code=303
            )
        start = date.today()
        end = start + timedelta(days=plan.days)
        account = None
        if user is not None:
            account = user.email or user.phone or user.display_name
        return templates.TemplateResponse(
            request,
            "purchase_confirm.html",
            {
                "plan": plan,
                "plan_billing": billing_line(plan),
                "period_line": (
                    f"{start.day} {start.strftime('%b %Y')} → "
                    f"{end.day} {end.strftime('%b %Y')}"
                ),
                "account_label": account,
            },
        )

    @app.get("/subscribe/pay", response_class=HTMLResponse)
    async def subscribe_pay(
        request: Request,
        d: str | None = Query(default=None),
    ) -> Response:
        """Purchase step 2 — Razorpay Checkout (placeholder while keys absent)."""
        if not app.state.pricing_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        plan = get_plan(d if d is not None else DEFAULT_DAYS)
        user = getattr(request.state, "current_user", None)
        if app.state.multiuser_enabled and user is None:
            return RedirectResponse(
                url=f"/login?next=/pricing%3Fd%3D{plan.days}", status_code=303
            )
        checkout_live = billing_enabled(app.state)
        checkout_data = None
        if checkout_live:
            checkout_data = {
                "days": plan.days,
                "key_id": app.state.razorpay_key_id,
                "name": "Recall the C",
                "description": f"{plan.days}-Day Recall",
                "prefill_email": getattr(user, "email", None) or "",
                "prefill_contact": getattr(user, "phone", None) or "",
                "order_url": "/api/billing/order",
                "verify_url": "/api/billing/verify",
            }
        start = date.today()
        end = start + timedelta(days=plan.days)
        return templates.TemplateResponse(
            request,
            "purchase_result.html",
            {
                "plan": plan,
                "stage": "pay",
                "checkout_live": checkout_live,
                "checkout_data": checkout_data,
                "period_line": (
                    f"{start.day} {start.strftime('%b %Y')} → "
                    f"{end.day} {end.strftime('%b %Y')}"
                ),
            },
        )

    def _billing_user(request: Request) -> object | None:
        """The account a purchase belongs to (multiuser only — the local
        single-user owner already has full access and never buys)."""
        if not app.state.multiuser_enabled:
            return None
        return getattr(request.state, "current_user", None)

    @app.post("/api/billing/order")
    async def billing_create_order(request: Request) -> JSONResponse:
        """Create a Razorpay order for a plan. Amount comes from the pricing
        catalog server-side; the client only ever names a duration."""
        if not billing_enabled(app.state):
            raise HTTPException(status_code=404, detail="Not found")
        user = _billing_user(request)
        if user is None:
            return JSONResponse(
                {"ok": False, "error": "sign_in_required"}, status_code=401
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        plan = get_plan(body.get("days") if isinstance(body, dict) else None)
        amount_paise = plan.price_inr * 100
        eng = _engine()
        try:
            order = billing_create(
                key_id=app.state.razorpay_key_id,
                key_secret=app.state.razorpay_key_secret,
                amount_paise=amount_paise,
                receipt=f"rtc-{plan.days}d-{uuid4().hex[:12]}",
            )
        except BillingError as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc)}, status_code=exc.status_code
            )
        eng.repo.create_billing_order(
            eng.user_id,
            order_id=order.order_id,
            plan_days=plan.days,
            amount_paise=order.amount_paise,
            currency=order.currency,
        )
        return JSONResponse(
            {
                "ok": True,
                "order_id": order.order_id,
                "amount": order.amount_paise,
                "currency": order.currency,
                "key_id": app.state.razorpay_key_id,
                "plan_days": plan.days,
            }
        )

    @app.post("/api/billing/verify")
    async def billing_verify_payment(request: Request) -> JSONResponse:
        """Verify Razorpay's payment signature; only then grant paid access.

        Signature mismatch or an unknown/foreign order returns 400 and marks
        nothing paid. Success marks the order paid and inserts the
        'payment'-source access grant in one repository transaction.
        """
        if not billing_enabled(app.state):
            raise HTTPException(status_code=404, detail="Not found")
        user = _billing_user(request)
        if user is None:
            return JSONResponse(
                {"ok": False, "error": "sign_in_required"}, status_code=401
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        order_id = str(body.get("razorpay_order_id") or "")
        payment_id = str(body.get("razorpay_payment_id") or "")
        signature = str(body.get("razorpay_signature") or "")
        if not (order_id and payment_id and signature):
            return JSONResponse(
                {"ok": False, "error": "missing_fields"}, status_code=400
            )
        eng = _engine()
        order = eng.repo.get_billing_order(eng.user_id, order_id)
        if order is None:
            return JSONResponse(
                {"ok": False, "error": "unknown_order"}, status_code=400
            )
        if not billing_verify(
            order_id=order_id,
            payment_id=payment_id,
            signature=signature,
            key_secret=app.state.razorpay_key_secret,
        ):
            return JSONResponse(
                {"ok": False, "error": "signature_mismatch"}, status_code=400
            )
        ends = datetime.now(timezone.utc) + timedelta(days=order.plan_days)
        newly_paid = eng.repo.mark_billing_order_paid(
            eng.user_id,
            order_id=order_id,
            payment_id=payment_id,
            grant_id=str(uuid4()),
            access_ends_at=ends.replace(microsecond=0).isoformat(),
        )
        next_url = (
            "/onboarding/plan?from=subscribe"
            if newly_paid
            else f"/subscribe/result?order={order_id}"
        )
        return JSONResponse({"ok": True, "next": next_url})

    @app.get("/subscribe/result", response_class=HTMLResponse)
    async def subscribe_result(
        request: Request,
        order: str | None = Query(default=None),
    ) -> Response:
        """Purchase step 3 — receipt for a verified, persisted payment."""
        if not app.state.pricing_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        user = _billing_user(request)
        if user is None:
            return RedirectResponse(url="/login?next=/pricing", status_code=303)
        eng = _engine()
        row = eng.repo.get_billing_order(eng.user_id, order or "")
        if row is None or row.status != "paid" or row.paid_at is None:
            return RedirectResponse(url="/pricing", status_code=303)
        plan = get_plan(row.plan_days)
        paid_on = date.fromisoformat(row.paid_at[:10])
        until = paid_on + timedelta(days=row.plan_days)
        return templates.TemplateResponse(
            request,
            "purchase_result.html",
            {
                "plan": plan,
                "stage": "receipt",
                "access_until": f"{until.day} {until.strftime('%b %Y')}",
                # What was actually charged for this order, not today's catalog.
                "paid_inr": row.amount_paise // 100,
                "receipt_email": getattr(user, "email", None),
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request,
        saved: int | None = Query(default=None),
        gcal: str | None = Query(default=None),
    ) -> HTMLResponse:
        eng = _engine()
        # Revision-calendar section context: shown only when the feature is
        # configured AND the viewer is a signed-in multiuser account.
        gcal_ctx: dict[str, object] | None = None
        settings_obj = getattr(app.state, "multiuser_settings", None)
        user = getattr(request.state, "current_user", None)
        if user is not None:
            eng.bootstrap_request(
                include_news=True,
                include_account=entitlements_active(request),
            )
        if (
            app.state.multiuser_enabled
            and user is not None
            and settings_obj is not None
            and settings_obj.gcal_configured
            and getattr(app.state, "calendar_store", None) is not None
        ):
            from constitution_memorizer.calendar_sync.routes import (
                retry_stale_pending,
            )
            from constitution_memorizer.calendar_sync.sync import calendar_prefs

            started = time.perf_counter()
            connection = app.state.calendar_store.get_connection(user.id)
            record_request_timing("calendar_connection", started)
            # A restart can strand sync_pending=1 with no task alive; viewing
            # Settings restarts a stale one so "Syncing…" is never a lie.
            try:
                retry_stale_pending(request, user.id, connection=connection)
            except Exception:  # noqa: BLE001 — settings must always render
                logger.exception("stale-pending calendar retry failed")
            started = time.perf_counter()
            prefs = calendar_prefs(eng)
            record_request_timing("calendar_prefs", started)
            gcal_ctx = {
                "connection": connection,
                "connected": bool(connection is not None and connection.is_active),
                "prefs": prefs,
                "status_param": gcal or "",
                "csrf_token": request.cookies.get("rtc_csrf") or "",
            }
        plan = None
        next_learning_day = None
        auto_entitled = can_use_auto_plan(request)
        if user is not None:
            try:
                plan = eng.get_learning_plan()
                from constitution_memorizer.planner.eligibility import remaining_unseen_count
                from constitution_memorizer.planner.planner import LearningPlanner

                today = user_today(eng)
                next_learning_day = LearningPlanner().next_learning_day(
                    eng,
                    plan,
                    as_of=today,
                    remaining_unseen=remaining_unseen_count(eng, as_of=today),
                    auto_entitled=auto_entitled,
                )
            except Exception:  # noqa: BLE001 — settings must still render
                logger.exception("learning plan context failed")
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "frequency": eng.get_notification_frequency(),
                "saved": bool(saved),
                "access": access_summary(request, eng),
                "gcal": gcal_ctx,
                "learning_plan": plan,
                "can_auto_plan": auto_entitled,
                "next_learning_day": next_learning_day,
            },
        )

    @app.post("/settings")
    async def settings_save(
        notification_frequency: str | None = Form(None),
    ) -> RedirectResponse:
        # Optional: the multiuser Settings form no longer includes the study
        # reminder radios (calendar reminders replaced them); the single-user
        # form still posts a value, and an invalid one is still rejected.
        eng = _engine()
        if notification_frequency is not None:
            if notification_frequency not in VALID_NOTIFICATION_FREQUENCIES:
                raise HTTPException(
                    status_code=400, detail="Invalid notification frequency"
                )
            eng.set_notification_frequency(notification_frequency)  # type: ignore[arg-type]
        # news_articles is site-wide, not a personal preference — it moved to
        # /admin/content. It used to be written here unconditionally from a
        # Form("") default, so any save that omitted it wiped the value.
        return RedirectResponse(url="/settings?saved=1", status_code=303)

    @app.get("/onboarding/state")
    async def onboarding_state_get(request: Request) -> JSONResponse:
        """Current tour status — lets a stale cached page (back button) check
        whether the tour is really still active before booting the layer."""
        if not app.state.multiuser_enabled:
            raise HTTPException(status_code=404, detail="Not Found")
        user = getattr(request.state, "current_user", None)
        if user is None:
            return JSONResponse(
                {"ok": False, "error": "sign_in_required"}, status_code=401
            )
        value = _engine().get_setting(ONBOARDING_KEY) or ""
        if value not in VALID_ONBOARDING_STATUSES:
            value = ""
        return JSONResponse({"ok": True, "status": value})

    @app.post("/onboarding/state")
    async def onboarding_state(
        request: Request,
        status: str = Form(...),
        csrf_token: str = Form(""),
    ):
        """Advance or replay the first-login tour (signed-in, multiuser only).

        The tour layer (onboarding.js) posts skipped/completed as same-origin
        XHR; the Settings "Replay the tour" form posts active with CSRF.
        """
        if not app.state.multiuser_enabled:
            raise HTTPException(status_code=404, detail="Not Found")
        user = getattr(request.state, "current_user", None)
        if user is None:
            if wants_json(request):
                return JSONResponse(
                    {"ok": False, "error": "sign_in_required"}, status_code=401
                )
            return RedirectResponse(url="/login?next=/settings", status_code=303)
        if status not in VALID_ONBOARDING_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid onboarding status")
        if not wants_json(request) and (
            request.cookies.get("rtc_csrf") != csrf_token
        ):
            return RedirectResponse(url="/settings", status_code=303)
        _engine().set_setting(ONBOARDING_KEY, status)
        if wants_json(request):
            return JSONResponse({"ok": True, "status": status})
        # Replaying from Settings lands where the tour starts.
        dest = "/dashboard" if status == "active" else "/settings"
        return RedirectResponse(url=dest, status_code=303)

    @app.get("/api/explainers/{article_id}")
    async def explainer_svg(request: Request, article_id: str) -> FileResponse:
        """Serve a registered Visual Explainer SVG (signed-in when multi-user)."""
        if app.state.multiuser_enabled and getattr(
            request.state, "current_user", None
        ) is None:
            raise HTTPException(status_code=403, detail="Sign in required")
        asset = explainer_asset_path(article_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Explainer not found")
        return FileResponse(path=asset, media_type="image/svg+xml")

    @app.post("/api/theme")
    async def theme_save(theme: str = Form(...)) -> JSONResponse:
        if theme not in VALID_THEMES:
            raise HTTPException(status_code=400, detail="Invalid theme")
        _engine().set_theme(theme)  # type: ignore[arg-type]
        return JSONResponse({"theme": theme})

    @app.post("/api/text-size")
    async def text_size_save(request: Request, size: str = Form(...)) -> JSONResponse:
        try:
            parsed = int(size)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid text size") from None
        if parsed < 16 or parsed > 24:
            raise HTTPException(status_code=400, detail="Invalid text size")
        user = getattr(request.state, "current_user", None)
        if app.state.multiuser_enabled and user is None:
            return JSONResponse({"size": parsed})
        _engine().set_setting("text_size", str(parsed))
        return JSONResponse({"size": parsed})

    @app.post(
        "/api/report-issue",
        response_model=ReportIssueResponse,
        status_code=201,
    )
    async def report_issue(
        request: Request, payload: ReportIssueRequest
    ) -> ReportIssueResponse:
        """Accept a signed-in issue report and insert into PostgreSQL."""
        user = getattr(request.state, "current_user", None)
        if app.state.multiuser_enabled and user is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in to report an issue.",
            )
        # Never trust browser-supplied reporter_email; derive from session.
        session_email = None
        if user is not None:
            session_email = (user.email or "").strip() or None
        payload = payload.model_copy(update={"reporter_email": session_email})

        # REPORT_TURNSTILE_ENABLED is the source of truth (not verifier presence).
        if settings.report_turnstile_enabled:
            verifier = getattr(app.state, "issue_report_turnstile_verifier", None)
            if verifier is None:
                raise HTTPException(
                    status_code=503,
                    detail="Verification temporarily unavailable. Please try again.",
                )
            if not payload.turnstile_token:
                raise HTTPException(
                    status_code=400,
                    detail="Verification required. Please try again.",
                )
            try:
                # Staging/production: also enforce action + hostname.
                # Development/test: require success:true only (dummy keys return action=test).
                if settings.app_env in {"staging", "production"}:
                    await verifier.verify(
                        payload.turnstile_token,
                        expected_action=TURNSTILE_REPORT_ACTION,
                        allowed_hostnames=(
                            settings.issue_report_turnstile_allowed_hostnames()
                        ),
                    )
                else:
                    await verifier.verify(
                        payload.turnstile_token,
                        expected_action=None,
                        allowed_hostnames=None,
                    )
            except TurnstileRejectedError:
                raise HTTPException(
                    status_code=400,
                    detail="Verification failed. Please try again.",
                ) from None
            except TurnstileUnavailableError:
                logger.exception("Turnstile Siteverify unavailable")
                raise HTTPException(
                    status_code=503,
                    detail="Verification temporarily unavailable. Please try again.",
                ) from None
            except Exception:
                logger.exception("Unexpected Turnstile verification error")
                raise HTTPException(
                    status_code=503,
                    detail="Verification temporarily unavailable. Please try again.",
                ) from None

        repo = getattr(app.state, "issue_report_repo", None)
        if repo is None:
            raise HTTPException(
                status_code=503,
                detail="Unable to submit report right now.",
            )
        try:
            report = repo.create_report(
                article_number=payload.article_number,
                section=payload.section,
                selected_text=payload.selected_text,
                issue_type=payload.issue_type,
                description=payload.description,
                suggested_correction=payload.suggested_correction,
                source_url=payload.source_url,
                reporter_email=payload.reporter_email,
                page_url=payload.page_url,
            )
        except Exception:
            logger.exception("Failed to insert issue_reports row")
            raise HTTPException(
                status_code=503,
                detail="Unable to submit report right now.",
            ) from None

        notifier = getattr(app.state, "issue_report_notifier", None)
        if notifier is not None:
            try:
                await notifier.send(report=report, payload=payload)
            except Exception:
                logger.exception(
                    "Failed to send issue report email for report_id=%s",
                    report.id,
                )

        return ReportIssueResponse(
            success=True,
            report_id=report.id,
            status=report.status,
        )

    @app.post(
        "/api/contact",
        response_model=ContactMessageResponse,
        status_code=201,
    )
    async def contact_message(
        request: Request, payload: ContactMessageRequest
    ) -> ContactMessageResponse:
        """Accept a signed-in Contact Us message and insert into PostgreSQL."""
        user = getattr(request.state, "current_user", None)
        if app.state.multiuser_enabled and user is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in to contact us.",
            )
        session_email = None
        if user is not None:
            session_email = (user.email or "").strip() or None
        payload = payload.model_copy(update={"reporter_email": session_email})

        if settings.report_turnstile_enabled:
            verifier = getattr(app.state, "issue_report_turnstile_verifier", None)
            if verifier is None:
                raise HTTPException(
                    status_code=503,
                    detail="Verification temporarily unavailable. Please try again.",
                )
            if not payload.turnstile_token:
                raise HTTPException(
                    status_code=400,
                    detail="Verification required. Please try again.",
                )
            try:
                if settings.app_env in {"staging", "production"}:
                    await verifier.verify(
                        payload.turnstile_token,
                        expected_action=TURNSTILE_CONTACT_ACTION,
                        allowed_hostnames=(
                            settings.issue_report_turnstile_allowed_hostnames()
                        ),
                    )
                else:
                    await verifier.verify(
                        payload.turnstile_token,
                        expected_action=None,
                        allowed_hostnames=None,
                    )
            except TurnstileRejectedError:
                raise HTTPException(
                    status_code=400,
                    detail="Verification failed. Please try again.",
                ) from None
            except TurnstileUnavailableError:
                logger.exception("Turnstile Siteverify unavailable")
                raise HTTPException(
                    status_code=503,
                    detail="Verification temporarily unavailable. Please try again.",
                ) from None
            except Exception:
                logger.exception("Unexpected Turnstile verification error")
                raise HTTPException(
                    status_code=503,
                    detail="Verification temporarily unavailable. Please try again.",
                ) from None

        repo = getattr(app.state, "contact_message_repo", None)
        if repo is None:
            raise HTTPException(
                status_code=503,
                detail="Unable to send message right now.",
            )
        try:
            message = repo.create_message(
                topic=payload.topic,
                message=payload.message,
                page_url=payload.page_url,
                reporter_email=payload.reporter_email,
            )
        except Exception:
            logger.exception("Failed to insert contact_messages row")
            raise HTTPException(
                status_code=503,
                detail="Unable to send message right now.",
            ) from None

        notifier = getattr(app.state, "contact_message_notifier", None)
        if notifier is not None:
            try:
                await notifier.send(message=message, payload=payload)
            except Exception:
                logger.exception(
                    "Failed to send contact message email for message_id=%s",
                    message.id,
                )

        return ContactMessageResponse(
            success=True,
            message_id=message.id,
            status=message.status,
        )

    return app
