"""Admin console router: /admin shell, users, grants, roster, audit.

Every route is authorized router-wide by ``require_admin`` — the
authoritative per-request role lookup. Signed-in non-admins, disabled
consoles (ADMIN_ENABLED=false) and single-user mode all 404 so the
console's existence is not disclosed; guests are redirected to login by the
auth middleware before reaching here.

All POSTs validate CSRF and follow POST-redirect-GET back to the page they
came from, with a confirmation strip driven by the ``notice`` query param.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time as dt_time, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from constitution_memorizer.admin.dependencies import require_admin
from constitution_memorizer.admin.repository import AuditRow, GrantRow
from constitution_memorizer.admin.service import (
    AdminService,
    STATUS_COLORS,
    STATUS_LABELS,
    moves_for,
)
from constitution_memorizer.admin.audit import AuditEntry
from constitution_memorizer.auth.dependencies import require_csrf
from constitution_memorizer.web.entitlements import (
    PREVIEW_COOKIE,
    PREVIEW_STATES,
)

GRANT_SOURCES = ("admin_grant", "promotion")

ACCESS_FILTERS = ("all", "active", "scheduled", "ended")

_NAV = (
    ("overview", "Overview", "/admin"),
    ("users", "Users", "/admin/users"),
    ("access", "Access", "/admin/access"),
    ("admins", "Administrators", "/admin/admins"),
    ("audit", "Audit", "/admin/audit"),
    ("reports", "Reports", "/admin/reports"),
    ("contact", "Contact", "/admin/contact"),
    ("preview", "Preview", "/admin/preview"),
    ("content", "Content", "/admin/content"),
)


def _repo(request: Request):
    repo = getattr(request.app.state, "admin_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Admin store unavailable")
    return repo


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short_date(value: str | None) -> str:
    """ISO timestamp/date → '17 Aug 2026' (empty string for None)."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return f"{parsed.day} {parsed:%b %Y}"


def _short_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return f"{parsed.day} {parsed:%b %H:%M}"


def _grant_window(grant: GrantRow, now: datetime) -> str:
    """Compact window column: '→ 30 Sep 2026', 'indefinite', 'ended …'."""
    state = grant.state(now)
    if state == "revoked":
        return f"→ revoked {_short_date(grant.revoked_at)}"
    if state == "scheduled":
        end = _short_date(grant.ends_at) if grant.ends_at else "indefinite"
        return f"{_short_date(grant.starts_at)} → {end}"
    if state == "ended":
        return f"ended {_short_date(grant.ends_at)}"
    if grant.ends_at is None:
        return "indefinite"
    return f"→ {_short_date(grant.ends_at)}"


def _flatten_diff(row: AuditRow) -> str:
    """Changed keys only, one line: 'status: new → reviewing'."""
    before = row.before_state or {}
    after = row.after_state or {}
    if not before and not after:
        return ""
    parts: list[str] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old == new:
            continue
        parts.append(f"{key}: {old if old is not None else 'none'} → "
                     f"{new if new is not None else 'none'}")
    return " · ".join(parts)


def _full_diff(row: AuditRow) -> str:
    payload = {"before": row.before_state, "after": row.after_state}
    return json.dumps(payload, sort_keys=True)


def _audit_display(rows: list[AuditRow]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        verb_color = (
            "red" if "revoke" in row.action
            else "teal" if "grant" in row.action
            else "ink"
        )
        out.append(
            {
                "at": _short_datetime(row.created_at),
                "admin": row.admin_display or row.admin_user_id[:13],
                "action": row.action,
                "action_color": verb_color,
                "target": row.target_display
                or (row.target_id or row.target_user_id or "—"),
                "diff": _flatten_diff(row),
                "full": _full_diff(row),
            }
        )
    return out


def _access_facts(user_row) -> tuple[str, str, str]:
    """(headline, colour, mono fact string) for the users table / detail."""
    if user_row.is_admin:
        return (
            "Administrator",
            "ink",
            "level=subscribed · is_subscribed=false · access_source=admin",
        )
    if user_row.grant_source:
        ends = _short_date(user_row.grant_ends_at)
        label = f"Granted · to {ends}" if ends else "Granted · indefinite"
        return (
            label,
            "teal",
            "level=subscribed · is_subscribed=false · access_source="
            + user_row.grant_source,
        )
    return (
        f"Free · {user_row.claimed_count}/3 claimed",
        "muted",
        "level=free · is_subscribed=false · access_source=free",
    )


def create_admin_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

    def _ctx(request: Request, tab: str, **extra: Any) -> dict[str, Any]:
        settings = request.app.state.multiuser_settings
        ctx: dict[str, Any] = {
            "admin_tab": tab,
            "admin_nav": _NAV,
            "admin_env_chip": (
                "ADMIN_ENABLED=true"
                if getattr(settings, "app_env", "") not in {"production"}
                else ""
            ),
            "notice": request.query_params.get("notice") or "",
        }
        ctx.update(extra)
        return ctx

    # ------------------------------------------------------------------ #
    # Home                                                               #
    # ------------------------------------------------------------------ #
    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def admin_home(request: Request) -> HTMLResponse:
        repo = _repo(request)
        counts = repo.counts()
        report_repo = getattr(request.app.state, "issue_report_repo", None)
        contact_repo = getattr(request.app.state, "contact_message_repo", None)
        report_counter = getattr(report_repo, "count_by_status", None)
        contact_counter = getattr(contact_repo, "count_by_status", None)
        new_reports = report_counter("new") if report_counter else None
        new_contacts = contact_counter("new") if contact_counter else None
        cells = [
            {
                "label": "Users",
                "value": counts.total_users,
                "sub": "accounts in the directory",
                "href": "/admin/users",
                "color": "ink",
            },
            {
                "label": "Free",
                "value": counts.free_users,
                "sub": "no role, no active grant",
                "href": "/admin/users",
                "color": "ink",
            },
            {
                "label": "Active grants",
                "value": counts.active_grants,
                "sub": "manual Recall access",
                "href": "/admin/access",
                "color": "teal" if counts.active_grants else "ink",
            },
            {
                "label": "New reports",
                "value": new_reports if new_reports is not None else "—",
                "sub": "issue reports awaiting review",
                "href": "/admin/reports",
                "color": "amber" if new_reports else "ink",
            },
            {
                "label": "New messages",
                "value": new_contacts if new_contacts is not None else "—",
                "sub": "contact inbox",
                "href": "/admin/contact",
                "color": "amber" if new_contacts else "ink",
            },
        ]
        return templates.TemplateResponse(
            request,
            "admin/index.html",
            _ctx(request, "overview", cells=cells, admins=counts.admins),
        )

    # ------------------------------------------------------------------ #
    # Users                                                              #
    # ------------------------------------------------------------------ #
    @router.get("/users", response_class=HTMLResponse)
    async def admin_users(request: Request, q: str = "") -> HTMLResponse:
        repo = _repo(request)
        rows = repo.search_users(q)
        display = []
        for row in rows:
            headline, color, _facts = _access_facts(row)
            display.append(
                {
                    "user_id": row.user_id,
                    "name": row.display_name or "—",
                    "short_id": row.user_id[:13] + "…",
                    "email": row.email or "—",
                    "phone": row.phone or "—",
                    "last_sign_in": _short_datetime(row.last_sign_in_at) or "—",
                    "role": "Admin" if row.is_admin else "—",
                    "access": headline,
                    "access_color": color,
                }
            )
        q = (q or "").strip()
        if q:
            result_line = f'{len(display)} account(s) match "{q}"'
        else:
            result_line = f"{len(display)} most recent sign-ins"
        return templates.TemplateResponse(
            request,
            "admin/users.html",
            _ctx(request, "users", q=q, users=display, result_line=result_line),
        )

    @router.get("/users/{user_id}", response_class=HTMLResponse)
    async def admin_user_detail(request: Request, user_id: str) -> HTMLResponse:
        repo = _repo(request)
        try:
            uid = UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found")
        overview = repo.get_user_overview(uid)
        if overview is None:
            raise HTTPException(status_code=404, detail="Not Found")
        now = _now()

        # Access facts from the same single-lookup shape the app itself uses.
        store = request.app.state.access_store
        override = store.resolve_access_override(uid, now)
        if override.is_admin:
            headline, color = "Administrator", "ink"
            facts = "level=subscribed · is_subscribed=false · access_source=admin"
            note = (
                "Full Recall entitlement follows the user_roles row and is "
                "independent of ADMIN_ENABLED. To remove it, revoke the role "
                "from the command line — turning the console off does not "
                "take it away."
            )
        elif override.effective_grant is not None:
            grant = override.effective_grant
            headline, color = "Recall access granted", "teal"
            facts = (
                "level=subscribed · is_subscribed=false · access_source="
                + grant.source
            )
            if grant.ends_at is not None:
                ends = f"{grant.ends_at.day} {grant.ends_at:%B %Y}"
                note = (
                    f"Manual grant, no payment record. Access ends on {ends}; "
                    "claimed Free Articles survive it."
                )
            else:
                note = (
                    "Manual grant, no payment record. Access ends only when "
                    "revoked; claimed Free Articles survive it."
                )
        else:
            headline, color = "Free", "muted"
            facts = "level=free · is_subscribed=false · access_source=free"
            note = (
                "Normal Free rules: three permanent Articles, Type and Recite "
                "locked on unclaimed Articles once the cap is reached."
            )

        # Claimed Free Articles + progress figures (read-only).
        engine = request.app.state.engine.for_user(uid)
        claimed = sorted(
            engine.claimed_articles_with_dates().items(),
            key=lambda kv: (len(kv[0]), kv[0]),
        )
        records = engine.repo.list_all_progress(uid)
        today = date.today()
        due_today = 0
        for record in records:
            due = record.next_revision
            if due is None:
                continue
            try:
                due_date = date.fromisoformat(str(due)[:10])
            except ValueError:
                continue
            if due_date <= today:
                due_today += 1
        progress = [
            {"k": "Units started", "v": len(records)},
            {
                "k": "Done cycles",
                "v": sum(r.times_completed for r in records),
            },
            {"k": "Due today", "v": due_today},
        ]

        grants = repo.list_grants(uid, limit=50)
        effective_id = (
            override.effective_grant.grant_id
            if override.effective_grant is not None
            else None
        )
        grant_rows = []
        for grant in grants:
            state = grant.state(now)
            is_effective = grant.id == effective_id
            grant_rows.append(
                {
                    "id": grant.id,
                    "state": "EFFECTIVE" if is_effective else state.upper(),
                    "state_color": (
                        "teal" if is_effective
                        else "red" if state == "revoked"
                        else "amber" if state == "scheduled"
                        else "muted"
                    ),
                    "dimmed": not is_effective,
                    "source": grant.source,
                    "window": _grant_window(grant, now),
                    "reason": grant.reason or "",
                    "can_revoke": is_effective,
                }
            )

        audit = _audit_display(repo.list_audit(uid, limit=50))
        return templates.TemplateResponse(
            request,
            "admin/user_detail.html",
            _ctx(
                request,
                "users",
                target=overview,
                joined=_short_date(overview.created_at),
                last_sign_in=_short_datetime(overview.last_sign_in_at),
                access_headline=headline,
                access_color=color,
                access_facts=facts,
                access_note=note,
                claimed=[
                    {"article": art, "on": _short_date(ts)}
                    for art, ts in claimed
                ],
                progress=progress,
                grants=grant_rows,
                audit=audit,
                grant_sources=GRANT_SOURCES,
            ),
        )

    # ------------------------------------------------------------------ #
    # Grants                                                             #
    # ------------------------------------------------------------------ #
    @router.post("/users/{user_id}/grants", dependencies=[Depends(require_csrf)])
    async def admin_create_grant(
        request: Request,
        user_id: str,
        source: str = Form(...),
        ends_on: str = Form(default=""),
        indefinite: str = Form(default=""),
        reason: str = Form(default=""),
    ) -> RedirectResponse:
        repo = _repo(request)
        try:
            uid = UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found")
        if repo.get_user_overview(uid) is None:
            raise HTTPException(status_code=404, detail="Not Found")
        if source not in GRANT_SOURCES:
            raise HTTPException(status_code=400, detail="Invalid grant source")
        reason = reason.strip()
        if not reason:
            raise HTTPException(status_code=400, detail="Reason is required")
        ends_at: datetime | None = None
        if not indefinite:
            if not ends_on.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Provide an end date or mark the grant indefinite",
                )
            try:
                ends_date = date.fromisoformat(ends_on.strip())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end date")
            # Day granularity, stored end-of-day UTC.
            ends_at = datetime.combine(
                ends_date, dt_time(23, 59, 59), tzinfo=timezone.utc
            )
            if ends_at <= _now():
                raise HTTPException(
                    status_code=400, detail="End date must be in the future"
                )
        admin_user = request.state.current_user
        grant = repo.create_grant(
            user_id=uid,
            source=source,
            ends_at=ends_at,
            reason=reason,
            granted_by=admin_user.id,
        )
        notice = (
            f"Grant {grant.id[:8]} created · audit row grant_access "
            "written in the same transaction."
        )
        return RedirectResponse(
            url=f"/admin/users/{user_id}?notice={notice}", status_code=303
        )

    @router.post("/grants/{grant_id}/revoke", dependencies=[Depends(require_csrf)])
    async def admin_revoke_grant(
        request: Request, grant_id: str
    ) -> RedirectResponse:
        repo = _repo(request)
        admin_user = request.state.current_user
        grant = repo.revoke_grant(grant_id, admin_user_id=admin_user.id)
        if grant is None:
            raise HTTPException(
                status_code=404, detail="Grant not found or already revoked"
            )
        notice = (
            f"Revoked {grant.id[:8]} · audit row revoke_grant written in the "
            "same transaction."
        )
        return RedirectResponse(
            url=f"/admin/users/{grant.user_id}?notice={notice}", status_code=303
        )

    # ------------------------------------------------------------------ #
    # Roster + all grants                                                #
    # ------------------------------------------------------------------ #
    @router.get("/admins", response_class=HTMLResponse)
    async def admin_roster(request: Request) -> HTMLResponse:
        repo = _repo(request)
        admins = [
            {
                "user_id": row.user_id,
                "name": row.display_name or row.email or "—",
                "since": _short_date(row.created_at),
                "by": row.created_by_display
                or (row.created_by[:13] + "…" if row.created_by else "bootstrap"),
            }
            for row in repo.list_admins()
        ]
        return templates.TemplateResponse(
            request,
            "admin/admins.html",
            _ctx(request, "admins", admins=admins),
        )

    @router.get("/access", response_class=HTMLResponse)
    async def admin_access(
        request: Request, state: str = "all", offset: int = 0
    ) -> HTMLResponse:
        repo = _repo(request)
        if state not in ACCESS_FILTERS:
            state = "all"
        offset = max(0, offset)
        now = _now()
        # State is derived at render; filter over a generous window, then page.
        page_size = 50
        rows = repo.list_grants(None, limit=500, offset=0)
        display = []
        for grant in rows:
            grant_state = grant.state(now)
            bucket = (
                "ended" if grant_state in {"ended", "revoked"} else grant_state
            )
            if state != "all" and bucket != state:
                continue
            display.append(
                {
                    "id": grant.id,
                    "user_id": grant.user_id,
                    "user": grant.user_display or grant.user_id[:13] + "…",
                    "state": grant_state.upper(),
                    "state_color": (
                        "teal" if grant_state == "active"
                        else "amber" if grant_state == "scheduled"
                        else "red" if grant_state == "revoked"
                        else "muted"
                    ),
                    "dimmed": grant_state in {"ended", "revoked"},
                    "source": grant.source,
                    "window": _grant_window(grant, now),
                    "reason": grant.reason or "",
                    "by": grant.granted_by_display
                    or (grant.granted_by[:13] + "…" if grant.granted_by else "—"),
                }
            )
        total = len(display)
        page = display[offset : offset + page_size]
        return templates.TemplateResponse(
            request,
            "admin/access.html",
            _ctx(
                request,
                "access",
                grants=page,
                state=state,
                filters=ACCESS_FILTERS,
                offset=offset,
                page_size=page_size,
                total=total,
            ),
        )

    # ------------------------------------------------------------------ #
    # Reports / Contact inboxes                                          #
    # ------------------------------------------------------------------ #
    def _service(request: Request) -> AdminService:
        return AdminService(
            getattr(request.app.state, "issue_report_repo", None),
            getattr(request.app.state, "contact_message_repo", None),
        )

    def _inbox_ctx(
        request: Request,
        *,
        is_reports: bool,
        status_filter: str,
    ) -> dict[str, Any]:
        repo = (
            getattr(request.app.state, "issue_report_repo", None)
            if is_reports
            else getattr(request.app.state, "contact_message_repo", None)
        )
        tab = "reports" if is_reports else "contact"
        base_path = f"/admin/{tab}"
        # Filter chips use UI labels; "resolved"/"dismissed" map back to the
        # stored values, which stay untouched by the rename.
        chips = ["all", "new", "reviewing", "resolved"]
        if is_reports:
            chips.append("dismissed")
        if status_filter not in chips:
            status_filter = "all"
        stored = {
            "all": None,
            "new": "new",
            "reviewing": "reviewing",
            "resolved": "fixed" if is_reports else "resolved",
            "dismissed": "rejected",
        }[status_filter]
        rows: list[dict[str, Any]] = []
        available = repo is not None and hasattr(
            repo, "list_reports" if is_reports else "list_messages"
        )
        if available:
            if is_reports:
                items = repo.list_reports(status=stored, limit=50)
            else:
                items = repo.list_messages(status=stored, limit=50)
            for item in items:
                if is_reports:
                    subject = (
                        f"Article {item.article_number}"
                        if item.article_number
                        else (item.section or item.issue_type)
                    )
                    body = item.description
                else:
                    subject = item.topic.replace("_", " ")
                    body = item.message
                created = item.created_at
                created_iso = (
                    created.isoformat()
                    if hasattr(created, "isoformat")
                    else str(created)
                )
                rows.append(
                    {
                        "id": str(item.id),
                        "short_id": str(item.id)[:8],
                        "subject": subject,
                        "body": body,
                        "meta": f"{item.reporter_email or 'anon'} · "
                        f"{_short_datetime(created_iso)}",
                        "status": STATUS_LABELS.get(item.status, item.status),
                        "status_color": STATUS_COLORS.get(item.status, "ink"),
                        "moves": moves_for(item.status, is_reports=is_reports),
                    }
                )
        return _ctx(
            request,
            tab,
            is_reports=is_reports,
            inbox=rows,
            available=available,
            chips=chips,
            status_filter=status_filter,
            base_path=base_path,
        )

    @router.get("/reports", response_class=HTMLResponse)
    async def admin_reports(
        request: Request, status: str = "all"
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "admin/inbox.html",
            _inbox_ctx(request, is_reports=True, status_filter=status),
        )

    @router.get("/contact", response_class=HTMLResponse)
    async def admin_contact(
        request: Request, status: str = "all"
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "admin/inbox.html",
            _inbox_ctx(request, is_reports=False, status_filter=status),
        )

    def _apply_transition(
        request: Request, *, is_reports: bool, item_id: str, status: str
    ) -> RedirectResponse:
        service = _service(request)
        admin_user = request.state.current_user
        try:
            if is_reports:
                before, after = service.update_report_status(
                    admin_user_id=str(admin_user.id),
                    report_id=item_id,
                    status=status,
                )
            else:
                before, after = service.update_contact_status(
                    admin_user_id=str(admin_user.id),
                    message_id=item_id,
                    status=status,
                )
        except LookupError as exc:
            if isinstance(exc, KeyError):
                raise HTTPException(status_code=404, detail="Not Found")
            raise HTTPException(
                status_code=503, detail="Inbox requires the hosted database"
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        tab = "reports" if is_reports else "contact"
        notice = f"{item_id[:8]} · status: {before} → {after}"
        referer_status = request.query_params.get("status", "all")
        return RedirectResponse(
            url=f"/admin/{tab}?status={referer_status}&notice={notice}",
            status_code=303,
        )

    @router.post(
        "/reports/{report_id}/status", dependencies=[Depends(require_csrf)]
    )
    async def admin_report_status(
        request: Request, report_id: str, status: str = Form(...)
    ) -> RedirectResponse:
        return _apply_transition(
            request, is_reports=True, item_id=report_id, status=status
        )

    @router.post(
        "/contact/{message_id}/status", dependencies=[Depends(require_csrf)]
    )
    async def admin_contact_status(
        request: Request, message_id: str, status: str = Form(...)
    ) -> RedirectResponse:
        return _apply_transition(
            request, is_reports=False, item_id=message_id, status=status
        )

    # ------------------------------------------------------------------ #
    # Entitlement preview                                                #
    # ------------------------------------------------------------------ #
    _PREVIEW_SUBS = {
        "free_claimable": "2 slots left, this Article unclaimed",
        "free_claimed": "Already one of their three",
        "free_cap": "Unclaimed Article at the cap",
        "subscribed": "Everything open",
    }

    # ------------------------------------------------------------------ #
    # Content — site-wide display settings                                #
    # ------------------------------------------------------------------ #
    # "Browse — In news" is a site-wide flag, not a personal preference, so it
    # lives here rather than on a user's /settings page. The router already
    # carries Depends(require_admin), so these inherit the guard.
    @router.get("/content", response_class=HTMLResponse)
    async def admin_content(request: Request) -> HTMLResponse:
        engine = request.app.state.engine
        return templates.TemplateResponse(
            request,
            "admin/content.html",
            _ctx(request, "content", news_articles=engine.get_news_articles_raw()),
        )

    @router.post("/content", dependencies=[Depends(require_csrf)])
    async def admin_content_save(
        request: Request, news_articles: str = Form("")
    ) -> RedirectResponse:
        request.app.state.engine.set_news_articles_raw(news_articles)
        return RedirectResponse(url="/admin/content?notice=Saved", status_code=303)

    @router.get("/preview", response_class=HTMLResponse)
    async def admin_preview(request: Request) -> HTMLResponse:
        current = request.cookies.get(PREVIEW_COOKIE)
        if current not in PREVIEW_STATES:
            current = None
        cards = [
            {
                "code": code,
                "label": label,
                "sub": _PREVIEW_SUBS[code],
                "selected": code == current,
            }
            for code, label in PREVIEW_STATES.items()
        ]
        return templates.TemplateResponse(
            request,
            "admin/preview.html",
            _ctx(request, "preview", cards=cards, current=current),
        )

    @router.post("/preview", dependencies=[Depends(require_csrf)])
    async def admin_preview_set(
        request: Request, state: str = Form(...)
    ) -> RedirectResponse:
        if state not in PREVIEW_STATES:
            raise HTTPException(status_code=400, detail="Unknown preview state")
        repo = _repo(request)
        admin_user = request.state.current_user
        previous = request.cookies.get(PREVIEW_COOKIE)
        repo.write_audit(
            AuditEntry(
                admin_user_id=str(admin_user.id),
                action="preview_enter",
                target_user_id=str(admin_user.id),
                target_type="preview",
                before_state={"state": previous},
                after_state={"state": state},
            )
        )
        response = RedirectResponse(url="/admin/preview", status_code=303)
        # Session-scoped (no max_age): closing the browser exits the preview.
        response.set_cookie(
            PREVIEW_COOKIE,
            state,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @router.post("/preview/clear", dependencies=[Depends(require_csrf)])
    async def admin_preview_clear(request: Request) -> RedirectResponse:
        next_url = request.query_params.get("next") or "/admin/preview"
        if not next_url.startswith("/"):
            next_url = "/admin/preview"
        response = RedirectResponse(url=next_url, status_code=303)
        response.delete_cookie(PREVIEW_COOKIE, path="/")
        return response

    # ------------------------------------------------------------------ #
    # Audit                                                              #
    # ------------------------------------------------------------------ #
    @router.get("/audit", response_class=HTMLResponse)
    async def admin_audit(
        request: Request, target_user_id: str = "", offset: int = 0
    ) -> HTMLResponse:
        repo = _repo(request)
        offset = max(0, offset)
        target: UUID | None = None
        if target_user_id.strip():
            try:
                target = UUID(target_user_id.strip())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid user id")
        rows = repo.list_audit(target, limit=100, offset=offset)
        return templates.TemplateResponse(
            request,
            "admin/audit.html",
            _ctx(
                request,
                "audit",
                audit=_audit_display(rows),
                target_user_id=target_user_id.strip(),
                offset=offset,
            ),
        )

    return router
