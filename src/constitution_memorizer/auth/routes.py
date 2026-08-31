"""Authentication HTTP routes + guest-first middleware."""

from __future__ import annotations

import logging
import secrets
import time
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from constitution_memorizer.auth.exceptions import (
    InvalidCredentialsError,
    OtpExpiredError,
    RateLimitError,
)
from constitution_memorizer.auth.guest import requires_auth, signin_redirect
from constitution_memorizer.auth.phone import (
    display_national,
    mask_phone,
    normalize_e164,
)
from constitution_memorizer.auth.pkce import code_challenge_s256, new_code_verifier
from constitution_memorizer.auth.rate_limit import OtpRateLimiter
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    new_csrf_token,
)
from constitution_memorizer.progress.repository import ONBOARDING_KEY
from constitution_memorizer.web.completion import build_completion, caught_up_quote
from constitution_memorizer.web.entitlements import (
    access_summary,
    can_use_auto_plan,
    entitlements_active,
    learning_entitlement_args,
    subscription_status,
)
from constitution_memorizer.web.request_context import record_request_timing
from constitution_memorizer.web.service import user_today

logger = logging.getLogger(__name__)

PKCE_COOKIE_NAME = "rtc_pkce_verifier"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _safe_next(raw: str | None) -> str:
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/dashboard"
    return raw


def create_auth_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str | None = None) -> HTMLResponse:
        settings = request.app.state.multiuser_settings
        csrf = request.cookies.get(CSRF_COOKIE_NAME) or new_csrf_token()
        phone_raw = request.query_params.get("phone") or ""
        phone_national = display_national(phone_raw) if phone_raw else ""
        reason = request.query_params.get("reason") or "default"
        response = templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": error or request.query_params.get("error"),
                "google_enabled": settings.auth_google_enabled,
                "phone_enabled": settings.phone_sign_in_available,
                "csrf_token": csrf,
                "otp_sent": request.query_params.get("otp") == "1",
                "resent": request.query_params.get("resent") == "1",
                "phone_value": phone_national,
                "phone_e164": phone_raw if phone_raw.startswith("+") else "",
                "next_url": _safe_next(request.query_params.get("next")),
                "reason": reason,
                "auth_state": request.query_params.get("state") or (
                    "otp" if request.query_params.get("otp") == "1" else "default"
                ),
            },
        )
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf,
            httponly=False,
            samesite="lax",
            secure=bool(settings.cookie_secure),
            path="/",
        )
        return response

    @router.get("/auth/google/start")
    async def google_start(request: Request) -> RedirectResponse:
        settings = request.app.state.multiuser_settings
        if not settings.auth_google_enabled:
            return RedirectResponse(url="/login?error=google_disabled", status_code=303)
        state = secrets.token_urlsafe(24)
        verifier = new_code_verifier()
        challenge = code_challenge_s256(verifier)
        request.app.state.oauth_states[state] = True
        redirect_url = f"{settings.app_base_url.rstrip('/')}/auth/callback"
        url = request.app.state.auth_provider.get_google_authorization_url(
            redirect_url,
            state=state,
            code_challenge=challenge,
            code_challenge_method="S256",
        )
        response = RedirectResponse(url=url, status_code=303)
        next_url = _safe_next(request.query_params.get("next"))
        cookie_kw = {
            "httponly": True,
            "samesite": "lax",
            "secure": bool(settings.cookie_secure),
            "max_age": 600,
            "path": "/",
        }
        response.set_cookie("rtc_oauth_state", state, **cookie_kw)
        response.set_cookie(PKCE_COOKIE_NAME, verifier, **cookie_kw)
        response.set_cookie("rtc_auth_next", next_url, **cookie_kw)
        return response

    @router.get("/auth/callback", response_model=None)
    async def auth_callback(request: Request):
        settings = request.app.state.multiuser_settings
        params = request.query_params
        # Implicit-flow fallback: tokens arrive in the URL hash (not sent to server).
        if (
            not params.get("code")
            and not params.get("access_token")
            and not params.get("error")
        ):
            return templates.TemplateResponse(request, "auth_callback.html", {})

        if params.get("error"):
            logger.info(
                "OAuth provider error=%s desc=%s",
                params.get("error"),
                params.get("error_description"),
            )
            return RedirectResponse(url="/login?error=oauth_failed", status_code=303)

        cookie_state = request.cookies.get("rtc_oauth_state")
        state = params.get("state") or ""
        # CSRF: require the start cookie. Query state must match when present.
        if not cookie_state:
            return RedirectResponse(url="/login?error=oauth_state", status_code=303)
        if state and state != cookie_state:
            return RedirectResponse(url="/login?error=oauth_state", status_code=303)
        request.app.state.oauth_states.pop(cookie_state, None)

        redirect_url = f"{settings.app_base_url.rstrip('/')}/auth/callback"
        verifier = request.cookies.get(PKCE_COOKIE_NAME)
        try:
            auth_session = request.app.state.auth_provider.exchange_oauth_callback(
                code=params.get("code"),
                access_token=params.get("access_token"),
                refresh_token=params.get("refresh_token"),
                redirect_url=redirect_url,
                code_verifier=verifier,
            )
        except InvalidCredentialsError:
            logger.info("OAuth callback exchange failed")
            return RedirectResponse(url="/login?error=oauth_failed", status_code=303)
        response = _establish_session(request, auth_session)
        response.delete_cookie(PKCE_COOKIE_NAME, path="/")
        response.delete_cookie("rtc_oauth_state", path="/")
        return response

    @router.get("/auth/transition", response_class=HTMLResponse)
    async def auth_transition(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "auth_transition.html",
            {
                "next_url": _safe_next(request.query_params.get("next")),
                "error": request.query_params.get("error"),
            },
        )

    @router.post("/auth/phone/send")
    async def phone_send(
        request: Request,
        csrf_token: str = Form(...),
        next: str = Form("/dashboard"),
        phone: str = Form(""),
        country_code: str = Form("+91"),
        national_number: str = Form(""),
        resend: str = Form(""),
    ) -> RedirectResponse:
        settings = request.app.state.multiuser_settings
        if not settings.phone_sign_in_available:
            return RedirectResponse(url="/login?error=phone_disabled", status_code=303)
        if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
            return RedirectResponse(url="/login?error=csrf", status_code=303)
        if settings.captcha_enabled:
            captcha = (await request.form()).get("captcha_token")
            if not captcha:
                return RedirectResponse(url="/login?error=captcha", status_code=303)
        raw_phone = (phone or "").strip()
        if not raw_phone:
            digits = "".join(ch for ch in national_number if ch.isdigit())
            raw_phone = f"{country_code.strip() or '+91'}{digits}"
        try:
            normalized = normalize_e164(raw_phone)
        except InvalidCredentialsError:
            qs = urlencode(
                {
                    "error": "phone_format",
                    "phone": national_number or phone,
                    "state": "invalid-phone",
                    "next": _safe_next(next),
                }
            )
            return RedirectResponse(url=f"/login?{qs}", status_code=303)
        limiter: OtpRateLimiter = request.app.state.otp_limiter
        ip = _client_ip(request)
        try:
            limiter.check_send(phone=normalized, ip=ip)
            request.app.state.auth_provider.send_phone_otp(normalized)
            limiter.record_send(phone=normalized, ip=ip)
        except RateLimitError:
            logger.info("OTP rate limited for %s", mask_phone(normalized))
            qs = urlencode(
                {
                    "otp": "1",
                    "phone": normalized,
                    "error": "too_many_attempts",
                    "next": _safe_next(next),
                }
            )
            return RedirectResponse(url=f"/login?{qs}", status_code=303)
        except InvalidCredentialsError:
            logger.info("OTP send failed for %s", mask_phone(normalized))
        params = {
            "otp": "1",
            "phone": normalized,
            "next": _safe_next(next),
        }
        if (resend or "").strip() in {"1", "true", "yes"}:
            params["resent"] = "1"
        return RedirectResponse(url=f"/login?{urlencode(params)}", status_code=303)

    @router.post("/auth/phone/verify")
    async def phone_verify(
        request: Request,
        phone: str = Form(...),
        otp: str = Form(...),
        csrf_token: str = Form(...),
        next: str = Form("/dashboard"),
    ) -> RedirectResponse:
        settings = request.app.state.multiuser_settings
        if not settings.phone_sign_in_available:
            return RedirectResponse(url="/login?error=phone_disabled", status_code=303)
        if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
            return RedirectResponse(url="/login?error=csrf", status_code=303)
        try:
            normalized = normalize_e164(phone)
        except InvalidCredentialsError:
            return RedirectResponse(url="/login?error=phone_format", status_code=303)
        # Combine 6 separate OTP cells if posted as otp0..otp5
        form = await request.form()
        if not otp or len(otp.strip()) < 6:
            cells = "".join(str(form.get(f"otp{i}", "") or "") for i in range(6))
            if cells:
                otp = cells
        limiter: OtpRateLimiter = request.app.state.otp_limiter
        try:
            limiter.check_verify(phone=normalized)
            auth_session = request.app.state.auth_provider.verify_phone_otp(
                normalized, otp.strip()
            )
            limiter.record_verify_success(phone=normalized)
        except RateLimitError:
            qs = urlencode(
                {
                    "otp": "1",
                    "phone": normalized,
                    "error": "too_many_attempts",
                    "next": _safe_next(next),
                }
            )
            return RedirectResponse(url=f"/login?{qs}", status_code=303)
        except OtpExpiredError:
            limiter.record_verify_failure(phone=normalized)
            qs = urlencode(
                {
                    "otp": "1",
                    "phone": normalized,
                    "error": "otp_expired",
                    "next": _safe_next(next),
                }
            )
            return RedirectResponse(url=f"/login?{qs}", status_code=303)
        except InvalidCredentialsError:
            limiter.record_verify_failure(phone=normalized)
            qs = urlencode(
                {
                    "otp": "1",
                    "phone": normalized,
                    "error": "bad_otp",
                    "next": _safe_next(next),
                }
            )
            return RedirectResponse(url=f"/login?{qs}", status_code=303)
        return _establish_session(request, auth_session, next_url=_safe_next(next))

    @router.post("/logout")
    async def logout(request: Request) -> RedirectResponse:
        settings = request.app.state.multiuser_settings
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if session_id:
            request.app.state.session_store.delete(session_id)
        response = RedirectResponse(url="/signed-out", status_code=303)
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        response.delete_cookie("rtc_oauth_state", path="/")
        if settings.cookie_secure:
            response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=True)
        return response

    @router.get("/signed-out", response_class=HTMLResponse)
    async def signed_out(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "signed_out.html", {})

    @router.get("/session-expired", response_class=HTMLResponse)
    async def session_expired(request: Request) -> HTMLResponse:
        response = templates.TemplateResponse(request, "session_expired.html", {})
        # Drop the stale cookie so guests are not looped back here.
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return response

    @router.get("/welcome", response_class=HTMLResponse)
    async def welcome_get(request: Request) -> HTMLResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return signin_redirect(next_url="/welcome")
        return templates.TemplateResponse(
            request,
            "welcome.html",
            {
                "user": user,
                "csrf_token": request.cookies.get(CSRF_COOKIE_NAME) or "",
                "display_name": user.display_name or "",
            },
        )

    @router.post("/welcome")
    async def welcome_post(
        request: Request,
        display_name: str = Form(...),
        csrf_token: str = Form(...),
    ) -> RedirectResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return signin_redirect(next_url="/welcome")
        if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
            return RedirectResponse(url="/welcome?error=csrf", status_code=303)
        name = display_name.strip()
        if not name:
            return RedirectResponse(url="/welcome?error=name", status_code=303)
        repo = request.app.state.engine.repo
        first_welcome = repo.needs_welcome(user.id)
        repo.upsert_profile(
            user.id,
            display_name=name,
            avatar_url=user.avatar_url,
        )
        # First name save on a fresh account starts the onboarding tour.
        # Later /welcome visits (name edits) never restart or downgrade it.
        if first_welcome and repo.get_setting(user.id, ONBOARDING_KEY) is None:
            repo.set_setting(user.id, ONBOARDING_KEY, "active")
        dest = "/onboarding/plan" if first_welcome else "/dashboard"
        return RedirectResponse(url=dest, status_code=303)

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return templates.TemplateResponse(
                request,
                "guest_gate.html",
                {"gate_kind": "dashboard", "reason": "default"},
            )
        eng = getattr(request.state, "bound_engine", None) or request.app.state.engine.for_user(
            user.id
        )
        bundle = eng.bootstrap_request(
            include_profile=True,
            include_modes=True,
            include_account=entitlements_active(request),
        )
        profile = bundle.profile
        if profile is None or not (profile.get("display_name") or "").strip():
            return RedirectResponse(url="/welcome", status_code=303)
        label = (
            profile.get("display_name")
            or user.display_name
            or (mask_phone(user.phone) if user.phone else user.email or "Learner")
        )
        try:
            from constitution_memorizer.web.dashboard import build_dashboard_context

            started = time.perf_counter()
            today = user_today(eng)
            ctx = build_dashboard_context(
                eng,
                display_label=label,
                as_of=today,
                auto_entitled=can_use_auto_plan(request),
                mix_eligibility=learning_entitlement_args(request, eng),
            )
            record_request_timing("dashboard_build", started)
            ctx["user"] = user
            ctx["dashboard_state"] = "ok"
            ctx["access"] = access_summary(request, eng)
            # Lifecycle surfaces (design 04/07): only expiring-soon and lapsed
            # may appear outside Profile. Dormant while billing returns None.
            ctx["subscription"] = subscription_status(request, eng)
            done_id = request.query_params.get("done")
            started = time.perf_counter()
            ctx["completion"] = build_completion(
                eng=eng,
                quotes=getattr(request.app.state, "quotes", []) or [],
                done_id=done_id,
                request=request,
                is_guest=False,
                continue_href="/dashboard",
                continue_label=None,
            )
            ctx["caught_up_quote"] = (
                caught_up_quote(getattr(request.app.state, "quotes", []) or [], today)
                if ctx.get("due_count") == 0
                else None
            )
            record_request_timing("completion", started)
            started = time.perf_counter()
            response = templates.TemplateResponse(request, "dashboard.html", ctx)
            record_request_timing("template", started)
            return response
        except Exception:
            logger.exception("Dashboard data load failed for user %s", user.id)
            started = time.perf_counter()
            response = templates.TemplateResponse(
                request,
                "dashboard.html",
                {
                    "user": user,
                    "display_label": label,
                    "first_name": (label or "Learner").split()[0],
                    "greeting": f"Hello, {(label or 'Learner').split()[0]}.",
                    "subtext": "Your saved progress is safe.",
                    "dashboard_state": "data-error",
                    "due_count": 0,
                    "due_minutes": 0,
                    "due_chips": [],
                    "due_chips_more": 0,
                    "first_due_id": None,
                    "continue_unit": None,
                    "continue_meta": "",
                    "continue_mode_line": "",
                    "continue_pct": 0,
                    "strip": {
                        "articles_started": 0,
                        "units_completed": 0,
                        "units_mastered": 0,
                        "day_streak": 0,
                        "revisions_done": 0,
                    },
                    "recent": [],
                    "is_new": False,
                    "nothing_due": True,
                    "today_units": [],
                    "goal_done": 0,
                    "goal_total": 0,
                    "goal_pct": 0,
                    "daily_goal_streak": 0,
                },
            )
            record_request_timing("template", started)
            return response

    @router.get("/profile", response_class=HTMLResponse)
    async def profile_get(request: Request) -> HTMLResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return signin_redirect(next_url="/profile", reason="default")
        from constitution_memorizer.web.service import free_article_slots

        eng = request.app.state.engine.for_user(user.id)
        profile = eng.repo.get_profile(user.id) or {}
        access = access_summary(request, eng)
        slots = (
            free_article_slots(eng) if access.enabled and access.is_free else []
        )
        return templates.TemplateResponse(
            request,
            "profile.html",
            {
                "user": user,
                "profile": profile,
                "access": access,
                "free_slots": slots,
                "subscription": subscription_status(request, eng),
                "display_label": profile.get("display_name")
                or user.display_name
                or (mask_phone(user.phone) if user.phone else user.email or "Learner"),
                "csrf_token": request.cookies.get(CSRF_COOKIE_NAME) or "",
                "saved": request.query_params.get("saved") == "1",
                "edit_name": request.query_params.get("edit") == "name",
            },
        )

    @router.post("/profile")
    async def profile_post(
        request: Request,
        csrf_token: str = Form(...),
        action: str = Form("save"),
        display_name: str = Form(""),
    ) -> RedirectResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return signin_redirect(next_url="/profile")
        if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
            return RedirectResponse(url="/profile?error=csrf", status_code=303)
        eng = request.app.state.engine.for_user(user.id)
        if action == "delete_account":
            # Soft delete for this phase: clear personal data + session.
            # Orchestration lives HERE, not in the progress domain — the
            # revision engine stays ignorant of Google Calendar.
            eng.reset_all_personal_data()
            calendar_store = getattr(request.app.state, "calendar_store", None)
            if calendar_store is not None:
                try:
                    # Revoke the Google grant BEFORE deleting the sealed token —
                    # afterwards Recall no longer holds the credential, and the
                    # user's Google account shouldn't keep listing us.
                    mu_settings = getattr(
                        request.app.state, "multiuser_settings", None
                    )
                    connection = calendar_store.get_connection(user.id)
                    if (
                        connection is not None
                        and connection.refresh_token_sealed
                        and mu_settings is not None
                        and mu_settings.gcal_configured
                    ):
                        from constitution_memorizer.calendar_sync.crypto import (
                            TokenSealError,
                            TokenSealer,
                        )
                        from constitution_memorizer.calendar_sync.google_client import (
                            revoke_token,
                        )

                        try:
                            token = TokenSealer(mu_settings.gcal_token_key).unseal(
                                connection.refresh_token_sealed
                            )
                            await revoke_token(
                                token,
                                transport=getattr(
                                    request.app.state, "gcal_transport", None
                                ),
                            )
                        except TokenSealError:
                            pass  # rotated key — nothing to revoke remotely
                    calendar_store.delete_user_data(user.id)
                except Exception:  # noqa: BLE001 — deletion must not 500
                    logger.exception("calendar cleanup failed during account delete")
            session_id = request.cookies.get(SESSION_COOKIE_NAME)
            if session_id:
                request.app.state.session_store.delete(session_id)
            response = RedirectResponse(url="/signed-out", status_code=303)
            response.delete_cookie(SESSION_COOKIE_NAME, path="/")
            return response
        name = display_name.strip() or (user.display_name or "")
        eng.repo.upsert_profile(user.id, display_name=name, avatar_url=user.avatar_url)
        return RedirectResponse(url="/profile?saved=1", status_code=303)

    return router


def _establish_session(
    request: Request,
    auth_session,
    *,
    next_url: str | None = None,
) -> RedirectResponse:
    settings = request.app.state.multiuser_settings
    stored = request.app.state.session_store.create(
        auth_session.user,
        access_token=auth_session.access_token,
        refresh_token=auth_session.refresh_token,
    )
    profile = request.app.state.engine.repo.get_profile(auth_session.user.id)
    if profile is None:
        request.app.state.engine.repo.upsert_profile(
            auth_session.user.id,
            display_name=auth_session.user.display_name,
            avatar_url=auth_session.user.avatar_url,
        )
    elif auth_session.user.avatar_url and not profile.get("avatar_url"):
        request.app.state.engine.repo.upsert_profile(
            auth_session.user.id,
            display_name=profile.get("display_name") or auth_session.user.display_name,
            avatar_url=auth_session.user.avatar_url,
        )
    # Durable identity directory: email/phone/last_sign_in_at refresh on every
    # successful sign-in so admin search outlives the 14-day session window.
    request.app.state.engine.repo.record_identity(
        auth_session.user.id,
        email=auth_session.user.email,
        phone=auth_session.user.phone,
    )

    dest = next_url or request.cookies.get("rtc_auth_next") or "/dashboard"
    dest = _safe_next(dest)
    if request.app.state.engine.repo.needs_welcome(auth_session.user.id):
        dest = "/welcome"
    else:
        dest = f"/auth/transition?next={dest}"

    response = RedirectResponse(url=dest, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        stored.session_id,
        httponly=True,
        samesite="lax",
        secure=bool(settings.cookie_secure),
        max_age=14 * 24 * 3600,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        stored.csrf_token,
        httponly=False,
        samesite="lax",
        secure=bool(settings.cookie_secure),
        path="/",
    )
    response.delete_cookie("rtc_auth_next", path="/")
    return response


def install_auth_middleware(app) -> None:
    """Guest-first gate: corpus is public; personal data requires sign-in."""

    @app.middleware("http")
    async def multiuser_auth_gate(request: Request, call_next):
        path = request.url.path
        if path in {"/health", "/sitemap.xml", "/robots.txt"} or path.startswith("/static/"):
            return await call_next(request)

        from constitution_memorizer.web.request_context import bound_engine, bound_memory

        if not getattr(request.app.state, "multiuser_enabled", False):
            request.state.current_user = None
            request.state.is_guest = False
            request.state.bound_engine = request.app.state.engine
            request.state.bound_memory = request.app.state.memory
            request.app.state.engine.clear_planner_request_caches()
            token_e = bound_engine.set(request.app.state.engine)
            token_m = bound_memory.set(request.app.state.memory)
            try:
                return await call_next(request)
            finally:
                bound_engine.reset(token_e)
                bound_memory.reset(token_m)

        method = request.method
        from constitution_memorizer.auth.dependencies import get_optional_current_user
        from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME

        # Stale cookie → session expired page (once), for HTML GETs.
        raw_cookie = request.cookies.get(SESSION_COOKIE_NAME)
        started = time.perf_counter()
        user = get_optional_current_user(request)
        record_request_timing("auth_session", started)
        if (
            raw_cookie
            and user is None
            and method == "GET"
            and path not in {
                "/session-expired",
                "/login",
                "/signed-out",
                "/health",
                "/sitemap.xml",
                "/robots.txt",
                "/terms",
                "/privacy",
                "/grievance",
            }
            and not path.startswith("/static/")
            and not path.startswith("/auth/")
        ):
            return RedirectResponse(url="/session-expired", status_code=303)

        request.state.current_user = user
        request.state.is_guest = user is None
        if user is not None:
            request.state.bound_engine = request.app.state.engine.for_user(user.id)
            memory = getattr(request.app.state, "memory", None)
            request.state.bound_memory = (
                memory.for_user(user.id) if memory is not None else None
            )
        else:
            request.state.bound_engine = request.app.state.engine
            request.state.bound_memory = getattr(request.app.state, "memory", None)

        bound = getattr(request.state, "bound_engine", None)
        if bound is not None:
            bound.clear_planner_request_caches()

        if user is None and requires_auth(path, method):
            # Inline gates for dashboard/progress GET; otherwise sign-in.
            if method == "GET" and (
                path.startswith("/dashboard")
                or path.startswith("/progress")
                or path == "/settings"
            ):
                pass  # dashboard/progress: guest_gate.html; settings: the page itself
            elif method == "GET" and (
                path.startswith("/calendar")
                or path.startswith("/memory")
                or path.startswith("/settings")
                or path.startswith("/profile")
                or path.startswith("/api/theme")
                or path.startswith("/admin")
            ):
                return signin_redirect(next_url=path, reason="default")
            elif method != "GET":
                reason = (
                    "mastered"
                    if path.endswith("/done")
                    else (
                        "again"
                        if path.endswith("/again")
                        else (
                            "note"
                            if "/memory" in path or path.endswith("/gloss")
                            else "default"
                        )
                    )
                )
                return signin_redirect(next_url=path, reason=reason)

        if path == "/" and user is not None:
            return RedirectResponse(url="/dashboard", status_code=303)

        token_e = bound_engine.set(request.state.bound_engine)
        token_m = bound_memory.set(request.state.bound_memory)
        try:
            return await call_next(request)
        finally:
            bound_engine.reset(token_e)
            bound_memory.reset(token_m)
