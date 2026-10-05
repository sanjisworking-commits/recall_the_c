"""Playground HTTP surface. Include from the app factory; do not grow app.py."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from constitution_memorizer.playground.access import (
    SCOPE_ENTIRE,
    SCOPE_SECTIONS,
    add_scope_value,
    consume_blocked_response,
    is_add_confirmed,
    is_add_scope,
    new_law_home_notice,
    playground_access,
    playground_view_access,
    require_eligible_law,
    require_law_active_this_period,
    require_playground_home,
    require_playground_new_law,
    require_playground_open,
)
from constitution_memorizer.playground.source_review import (
    CHANGE_KIND_MISSING,
    CHANGE_KIND_OMITTED,
    STATUS_PENDING,
    STATUS_REVIEWED,
    StaleSourceReviewError,
    affected_provision_view,
    change_copy,
    detect_source_changes,
    is_law_registry_outdated,
    law_source_state,
    mark_source_change_reviewed,
    provenance_lines,
)
from constitution_memorizer.playground.eligibility import (
    PlaygroundLawError,
    playground_catalogue_law,
    playground_law_source_identity,
)
from constitution_memorizer.web.guest_bareact_head import guest_add_reading_name
from constitution_memorizer.playground.http import (
    local_next_path,
    playground_login_href,
    playground_user_id,
    require_playground_repo,
    require_roster_service,
)
from constitution_memorizer.playground.locators import LocatorError, UnitLocator, parse_locator
from constitution_memorizer.playground.roster.models import (
    RESULT_ALREADY_ACTIVE,
    RESULT_INVALID_CANDIDATE,
    RESULT_INELIGIBLE,
    RESULT_NEEDS_CONFIRM,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_RE_ADD_CONFIRM,
    RESULT_RE_ADDED,
    RESULT_ROSTER_FULL,
    ROSTER_ADD_CONFIRM,
)
from constitution_memorizer.playground.roster.period import (
    next_playground_month_bounds,
    playground_month_name,
    playground_today,
)
from constitution_memorizer.playground.learning.service import (
    LearnProvisionError,
    cloze_needs_fallback,
    coerce_quiz_answers,
    grade_section_quiz,
    is_playground_learn_mode,
    load_learn_provision,
    mode_definitions,
    provision_mode_view,
    quiz_for_attempt,
    summaries_for_locators,
)
from constitution_memorizer.playground.learning.recite import recite_alignment
from constitution_memorizer.playground.lifecycle import (
    REVISION_RUNGS_SET,
    RevisionNotDueError,
    StaleRevisionError,
    build_revision_mode_progress,
    format_study_date,
    revision_is_due,
)
from constitution_memorizer.playground.service import (
    SelectionRejected,
    activate_law,
    mark_outdated,
    parse_selected_locator,
    persist_entire_act_selection,
    require_playground_law,
    selected_locator_set,
    selection_rows,
)
from constitution_memorizer.playground.source import locators_for_act, source_hash
from constitution_memorizer.playground.units import (
    canonical_text_for_locator,
    citation_label,
    source_hash_for_locator,
)
from constitution_memorizer.playground.urls import (
    act_mastered_path,
    add_path,
    home_path,
    law_path,
    learn_complete_path_for_locator,
    learn_path,
    learn_path_for_locator,
    learn_quiz_path_for_locator,
    learn_speech_path_for_locator,
    learn_start_path_for_locator,
    learned_path_for_locator,
    mastered_path_for_locator,
    roster_next_path,
    roster_path,
    sections_path,
    source_review_path,
    source_review_path_for_locator,
    source_review_reviewed_path_for_locator,
    source_review_section_path,
)
from constitution_memorizer.playground.progress import (
    build_act_progress,
    choose_next_workspace_row,
)
from constitution_memorizer.entitlements.dependencies import request_is_active_plus
from constitution_memorizer.playground.view import (
    add_confirm_copy,
    build_home_view,
    capacity_view,
    catalog_titles,
    catalogue_from_price,
    catalogue_plan_views,
    entire_act_meta,
    law_membership,
    picker_page_view,
    plus_add_confirm_copy,
    roster_law_cards,
    rollover_submit_label,
    section_row_view,
    skips_add_confirm,
)

from constitution_memorizer.playground.learning.modes import PLAYGROUND_MODE_LABELS


def _section_source_hash(act, locator: str, law_id: str) -> str:
    loc = parse_selected_locator(locator, law_id)
    if loc is None:
        return ""
    section = act.section(loc.section_number)
    if section is None:
        return ""
    return source_hash_for_locator(loc, section, section_hash=source_hash)


logger = logging.getLogger(__name__)


def _schedule_playground_calendar_sync(request: Request, user_id) -> None:
    """Re-sync Google Calendar after Learned, revision, selection, roster change."""
    if user_id is None:
        return
    try:
        from constitution_memorizer.calendar_sync.routes import schedule_sync

        schedule_sync(request, user_id)
    except Exception:  # noqa: BLE001 — projection must never break Playground writes
        logger.exception("playground calendar sync scheduling failed")


def _denied(result: object) -> Response | None:
    if isinstance(result, Response):
        return result
    return None


def _require_csrf(request: Request, csrf_token: str) -> None:
    """Fail closed for signed-in multi-user mutations.

    Local single-user mode may have no CSRF cookie; that path is not a
    hosted session. A hosted session without a matching token is rejected
    even when the cookie is missing.
    """

    expected = request.cookies.get("rtc_csrf") or ""
    session = getattr(request.state, "auth_session", None)
    multiuser = bool(getattr(request.app.state, "multiuser_enabled", False))
    if not expected:
        if multiuser and session is not None:
            raise HTTPException(status_code=403, detail="csrf")
        return
    if csrf_token != expected:
        raise HTTPException(status_code=403, detail="csrf")


async def _mutation_payload(request: Request) -> dict:
    header = request.headers.get("X-CSRF-Token") or ""
    content_type = (request.headers.get("content-type") or "").lower()
    data: dict = {}
    if "application/json" in content_type:
        try:
            raw = await request.json()
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            data = raw
    elif content_type:
        form = await request.form()
        data = {str(key): form.get(key) for key in form.keys()}
    token = header or str(data.get("csrf_token") or "")
    _require_csrf(request, token)
    return data


def _revision_flag(request: Request, data: dict | None = None) -> tuple[bool, int | None]:
    raw_flag = request.query_params.get("revision")
    if data is not None and data.get("revision") not in (None, ""):
        raw_flag = data.get("revision")
    wants = str(raw_flag or "").strip().lower() in {"1", "true", "yes", "on"}
    raw_rung = request.query_params.get("rung_days")
    if data is not None and data.get("rung_days") not in (None, ""):
        raw_rung = data.get("rung_days")
    rung: int | None = None
    if raw_rung not in (None, ""):
        try:
            rung = int(raw_rung)
        except (TypeError, ValueError):
            rung = None
    return wants, rung


def _current_due_rung(progress, as_of, claimed: int | None) -> int:
    if progress is None or str(progress.status) == "mastered" or not progress.next_revision:
        raise StaleRevisionError("stale_revision")
    current = int(progress.interval_days or 0)
    if current not in REVISION_RUNGS_SET:
        raise StaleRevisionError("stale_revision")
    if claimed is not None and int(claimed) != current:
        raise StaleRevisionError("stale_revision")
    if as_of.isoformat() < str(progress.next_revision)[:10]:
        raise RevisionNotDueError("not_due")
    return current


def _revision_error(exc: BaseException) -> JSONResponse:
    if isinstance(exc, StaleRevisionError):
        return JSONResponse({"ok": False, "error": "stale_revision"}, status_code=409)
    if isinstance(exc, RevisionNotDueError):
        return JSONResponse({"ok": False, "error": "not_due"}, status_code=409)
    raise exc


def _after_six_payload(
    payload: dict,
    overlay,
    user_id,
    law_id: str,
    loc,
    *,
    revision: bool,
    rung: int | None = None,
) -> dict:
    if not payload.get("all_methods_complete"):
        return payload
    progress = overlay.get_progress(user_id, law_id, loc.value)
    status = str(getattr(progress, "status", "") or "")
    next_rev = getattr(progress, "next_revision", None) if progress is not None else None
    interval = int(getattr(progress, "interval_days", 0) or 0) if progress is not None else 0
    payload["lifecycle_status"] = status
    payload["next_revision"] = next_rev
    payload["interval_days"] = interval
    payload["completion_href"] = ""
    payload["mastered"] = status == "mastered"
    if revision:
        if status == "mastered":
            payload["completion_href"] = mastered_path_for_locator(loc)
            payload["methods_complete_label"] = "Mastered, verbatim."
        else:
            when = format_study_date(next_rev) if next_rev else ""
            day = int(rung or interval or 0)
            payload["methods_complete_label"] = f"Day {day} complete"
            nxt = f"Next · Day {interval}" if interval else "Next revision scheduled"
            if when:
                nxt = f"{nxt} · {when}"
            payload["revision_next_line"] = nxt
        return payload
    if status in {"learned", "review", "mastered"}:
        payload["learned"] = True
        payload["methods_complete_label"] = "Learned"
        payload["completion_href"] = (
            mastered_path_for_locator(loc)
            if status == "mastered"
            else learned_path_for_locator(loc)
        )
    return payload


def _after_active_redirect(overlay, user_id, law_id: str) -> RedirectResponse:
    if overlay.get_item(user_id, law_id) is not None and overlay.list_selection(
        user_id, law_id
    ):
        return RedirectResponse(url=law_path(law_id), status_code=303)
    return RedirectResponse(url=sections_path(law_id), status_code=303)


def _add_page_context(
    *,
    request: Request,
    law_id: str,
    access,
    overlay,
    roster,
    step: str = "",
    hydrate_scope: bool = False,
) -> dict:
    state = law_membership(
        law_id=law_id, access=access, roster=roster, overlay=overlay
    )
    _long, short = catalog_titles(law_id)
    del _long
    month = "this month"
    remaining_after = None
    law_limit = None
    preview = None
    historical = False
    if access.user_id is not None and roster is not None:
        capacity = roster.peek_capacity(
            access.user_id, access.snapshot, local_owner=access.local_owner
        )
        month = playground_month_name(capacity.period_start)
        remaining_after = capacity.remaining
        law_limit = capacity.law_limit
        preview = roster.preview_add_law(
            access.user_id,
            law_id,
            access.snapshot,
            local_owner=access.local_owner,
            can_consume_new_law=access.can_consume_new_law,
        )
        if preview.status == RESULT_NEEDS_CONFIRM and remaining_after is not None:
            remaining_after = max(0, remaining_after - 1)
    if access.user_id is not None and overlay is not None:
        historical = overlay.get_item(access.user_id, law_id) is not None
    re_add = state.kind == "re_add" or (
        preview is not None and preview.status == RESULT_RE_ADD_CONFIRM
    )
    skip = skips_add_confirm(access) or state.skip_confirm
    show_scope = step == "scope" or skip
    if state.kind not in {"eligible_to_add", "re_add"}:
        show_scope = False
        skip = False
    confirm_title, confirm_lines = add_confirm_copy(
        short_title=short,
        month_name=month,
        law_limit=law_limit,
        remaining_after=remaining_after,
        historical=historical and not re_add,
        re_add=re_add,
    )
    entire_meta = ""
    if hydrate_scope and show_scope and state.kind in {"eligible_to_add", "re_add"}:
        try:
            act = require_playground_law(law_id)
            entire_meta = entire_act_meta(law_id, act=act)
        except Exception:
            entire_meta = ""
    kind = state.kind
    login_href = playground_login_href(
        local_next_path(str(request.url.path), add_path(law_id))
    )
    plans = catalogue_plan_views(
        current_tier=getattr(access.snapshot, "tier", None) if access.snapshot else None
    )
    reading_name = guest_add_reading_name(law_id, short)
    plus_add = bool(
        law_id == "ndps"
        and kind == "eligible_to_add"
        and request_is_active_plus(request)
    )
    plus_title, plus_lede, plus_space, plus_footer = ("", "", "", "")
    if plus_add:
        plus_title, plus_lede, plus_space, plus_footer = plus_add_confirm_copy(
            reading_name=reading_name,
            month_name=month,
            law_limit=law_limit,
            remaining_after=remaining_after,
        )
    return {
        "law_id": law_id,
        "kind": kind,
        "state": state,
        "title": confirm_title,
        "lines": confirm_lines,
        "month_name": month,
        "short_title": short,
        "action_label": "Add back" if re_add else "Add to Playground",
        "confirm_value": ROSTER_ADD_CONFIRM,
        "cancel_href": f"/laws/{law_id}",
        "blocked_pending": kind == "pending" or (
            preview is not None and preview.status == RESULT_NEW_BLOCKED
        ),
        "blocked_full": kind == "roster_full" or (
            preview is not None and preview.status == RESULT_ROSTER_FULL
        ),
        "step": "scope" if show_scope else "confirm",
        "skip_confirm": skip,
        "re_add": re_add,
        "entire_meta": entire_meta,
        "login_href": login_href,
        "reading_name": reading_name,
        "from_price": catalogue_from_price(),
        "catalogue_plans": plans,
        "hard_gate": kind in {"guest", "subscribe", "device_blocked", "unavailable"},
        "plus_add": plus_add,
        "plus_add_title": plus_title,
        "plus_add_lede": plus_lede,
        "plus_add_space": plus_space,
        "plus_add_footer": plus_footer,
    }


def _rollover_ids(form) -> tuple[list[str], list[str]]:
    keep_ids = [str(value) for value in form.getlist("keep_ids") if str(value)]
    decline_ids = [str(value) for value in form.getlist("decline_ids") if str(value)]
    for key, value in form.multi_items():
        if not str(key).startswith("choice_"):
            continue
        law_id = str(key)[len("choice_") :]
        if value == "keep" and law_id not in keep_ids:
            keep_ids.append(law_id)
        elif value == "decline" and law_id not in decline_ids:
            decline_ids.append(law_id)
    return keep_ids, decline_ids


def create_playground_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/playground")

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def playground_home(request: Request) -> HTMLResponse:
        access = require_playground_home(
            request, templates, next_url=home_path()
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        overlay = require_playground_repo(request)
        roster = require_roster_service(request)
        home = build_home_view(
            access=access,
            roster=roster,
            overlay=overlay,
            notice=str(request.query_params.get("notice") or ""),
        )
        return templates.TemplateResponse(
            request,
            "playground.html",
            {
                "home_view": home,
                "cards": [
                    {
                        "law_id": card.law_id,
                        "title": card.title,
                        "short_title": card.short_title,
                        "selected_count": card.selected_count,
                        "learned_count": card.learned_count,
                        "to_learn": max(0, card.selected_count - card.learned_count),
                        "due": card.due_count,
                        "outdated": card.outdated,
                    }
                    for card in home.active
                ],
                "new_law_notice": new_law_home_notice(request, access),
                "roster_path": roster_path(),
                "hard_gate": False,
                "read_only": bool(getattr(access, "can_view_home", False) and not access.can_open),
            },
        )

    @router.get("/roster", response_class=HTMLResponse)
    async def playground_roster(request: Request) -> HTMLResponse:
        access = require_playground_open(
            request, templates, next_url=roster_path()
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        roster = require_roster_service(request)
        add_id = (request.query_params.get("add") or "").strip()
        notice_kind = (request.query_params.get("notice") or "").strip()
        preview = None
        if add_id and notice_kind != "readded":
            require_eligible_law(add_id)
            preview = roster.preview_add_law(
                access.user_id,
                add_id,
                access.snapshot,
                local_owner=access.local_owner,
                can_consume_new_law=access.can_consume_new_law,
            )
            if preview.status == RESULT_ALREADY_ACTIVE:
                overlay = require_playground_repo(request)
                return _after_active_redirect(overlay, access.user_id, add_id)
            if preview.status == RESULT_NEW_BLOCKED:
                denied = consume_blocked_response(
                    request, templates, access, RESULT_NEW_BLOCKED
                )
                return denied  # type: ignore[return-value]
        capacity = roster.capacity(
            access.user_id,
            access.snapshot,
            local_owner=access.local_owner,
        )
        month = playground_month_name(capacity.period_start)
        overlay = require_playground_repo(request)
        active_cards, removed_cards = roster_law_cards(
            overlay=overlay,
            roster=roster,
            user_id=access.user_id,
        )
        add_catalog = playground_catalogue_law(add_id) if add_id else None
        show_confirm = preview is not None and preview.status in {
            RESULT_NEEDS_CONFIRM,
            RESULT_RE_ADD_CONFIRM,
        }
        show_full = preview is not None and preview.status == RESULT_ROSTER_FULL
        add_title = add_catalog.title if add_catalog is not None else add_id
        add_short = add_catalog.short_title if add_catalog is not None else add_id
        historical = False
        if add_id:
            historical = overlay.get_item(access.user_id, add_id) is not None
        remaining_after = capacity.remaining
        re_add = preview is not None and preview.status == RESULT_RE_ADD_CONFIRM
        if show_confirm and not re_add and remaining_after is not None:
            remaining_after = max(0, remaining_after - 1)
        confirm_title, confirm_lines = ("", ())
        confirm_action = "Add to Playground"
        if show_confirm:
            confirm_title, confirm_lines = add_confirm_copy(
                short_title=add_short or add_id,
                month_name=month,
                law_limit=capacity.law_limit,
                remaining_after=remaining_after,
                historical=historical and not re_add,
                re_add=re_add,
            )
            if re_add:
                confirm_action = "Add back"
        next_start, _end = next_playground_month_bounds()
        cap_view = capacity_view(
            period_start=capacity.period_start,
            used=capacity.used,
            law_limit=capacity.law_limit,
            remaining=capacity.remaining,
            active_count=len(active_cards),
            removed_consumed_count=len(removed_cards),
            surface="roster",
        )
        notice = ""
        if request.query_params.get("notice") == "readded" and add_id:
            notice = f"{add_short} is back in {month}. No extra space used."
        return templates.TemplateResponse(
            request,
            "playground_roster.html",
            {
                "month_name": month,
                "tier_snapshot": capacity.tier_snapshot,
                "law_limit": capacity.law_limit,
                "used": capacity.used,
                "remaining": capacity.remaining,
                "capacity": cap_view,
                "next_month_name": playground_month_name(next_start),
                "active_laws": active_cards,
                "removed_laws": removed_cards,
                "add_law_id": add_id or None,
                "add_title": add_title,
                "add_short": add_short,
                "confirm_title": confirm_title,
                "confirm_lines": confirm_lines,
                "confirm_action": confirm_action,
                "show_confirm": show_confirm,
                "show_full": show_full,
                "confirmation_copy": preview.confirmation_copy if preview else "",
                "confirm_value": ROSTER_ADD_CONFIRM,
                "notice": notice,
                "full_copy": (
                    f"Playground full this month. You've used all {capacity.law_limit} law spaces for {month}. "
                    "Your current Playground laws remain available."
                    if show_full and capacity.law_limit is not None
                    else ""
                ),
            },
        )

    @router.get("/roster/next", response_class=HTMLResponse)
    async def playground_roster_next(request: Request) -> HTMLResponse:
        access = require_playground_open(
            request, templates, next_url=roster_next_path()
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        overlay = require_playground_repo(request)
        roster = require_roster_service(request)
        plan = roster.get_rollover_plan(
            access.user_id,
            access.snapshot,
            has_overlay=lambda law_id: overlay.get_item(access.user_id, law_id) is not None,
            local_owner=access.local_owner,
        )
        cards = []
        keep_slots_open = plan.law_limit is None or (
            plan.remaining is not None and plan.remaining > 0
        )
        for candidate in plan.candidates:
            catalog = playground_catalogue_law(candidate.law_id)
            already_keep = bool(candidate.target_consumed or candidate.target_decision == "keep")
            cards.append(
                {
                    "law_id": candidate.law_id,
                    "title": catalog.title if catalog is not None else candidate.law_id,
                    "previously_removed": candidate.previously_removed,
                    "target_decision": candidate.target_decision,
                    "target_consumed": candidate.target_consumed,
                    "can_decline": plan.target_status != "active" or not candidate.target_consumed,
                    "can_keep": already_keep or keep_slots_open,
                }
            )
        notice = request.query_params.get("blocked") or ""
        limit_label = (
            "unlimited" if plan.law_limit is None else str(plan.law_limit)
        )
        cap_view = capacity_view(
            period_start=plan.target_period_start,
            used=plan.used,
            law_limit=plan.law_limit,
            remaining=plan.remaining,
            active_count=sum(1 for row in cards if row["target_consumed"]),
            removed_consumed_count=0,
            planned=True,
        )
        return templates.TemplateResponse(
            request,
            "playground_roster_next.html",
            {
                "month_name": plan.month_name,
                "law_limit": plan.law_limit,
                "limit_label": limit_label,
                "used": plan.used,
                "remaining": plan.remaining,
                "capacity": cap_view,
                "candidates": cards,
                "adjustment_required": plan.adjustment_required,
                "target_status": plan.target_status or "",
                "blocked": notice,
                "manages_current": plan.manages_current_period,
                "planned_count": plan.used,
                "submit_label": rollover_submit_label(
                    cards, adjustment_required=plan.adjustment_required
                ),
            },
        )

    @router.post("/roster/next")
    async def playground_roster_next_submit(request: Request) -> Response:
        opened = require_playground_open(
            request, templates, next_url=roster_next_path()
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked
        form = await request.form()
        _require_csrf(request, str(form.get("csrf_token") or ""))
        keep_ids, decline_ids = _rollover_ids(form)
        overlay = require_playground_repo(request)
        roster = require_roster_service(request)
        result = roster.confirm_carry_forward(
            opened.user_id,
            keep_ids,
            decline_ids,
            opened.snapshot,
            has_overlay=lambda law_id: overlay.get_item(opened.user_id, law_id) is not None,
            local_owner=opened.local_owner,
            can_consume_new_law=opened.can_consume_new_law,
        )
        if result.status == RESULT_INVALID_CANDIDATE:
            raise HTTPException(status_code=400, detail=RESULT_INVALID_CANDIDATE)
        if result.status != RESULT_OK:
            return RedirectResponse(
                url=roster_next_path(blocked=result.status),
                status_code=303,
            )
        return RedirectResponse(url=roster_next_path(), status_code=303)

    @router.get("/laws/{law_id}/add", response_class=HTMLResponse)
    async def playground_add_confirm(request: Request, law_id: str) -> Response:
        require_eligible_law(law_id)
        uid = playground_user_id(request)
        access = playground_access(request) if uid is not None else playground_view_access(request)
        overlay = getattr(request.app.state, "playground", None)
        roster = getattr(request.app.state, "roster", None)
        if access.user_id is not None:
            overlay = require_playground_repo(request)
            roster = require_roster_service(request)
        if access.can_open and overlay is not None and roster is not None:
            preview = roster.preview_add_law(
                access.user_id,
                law_id,
                access.snapshot,
                local_owner=access.local_owner,
                can_consume_new_law=access.can_consume_new_law,
            )
            if preview.status == RESULT_ALREADY_ACTIVE:
                return _after_active_redirect(overlay, access.user_id, law_id)
        step = str(request.query_params.get("step") or "")
        ctx = _add_page_context(
            request=request,
            law_id=law_id,
            access=access,
            overlay=overlay,
            roster=roster,
            step=step,
            hydrate_scope=True,
        )
        return templates.TemplateResponse(request, "playground_add.html", ctx)

    @router.post("/laws/{law_id}/add")
    async def playground_add(
        request: Request,
        law_id: str,
        csrf_token: str = Form(""),
        confirm: str = Form(""),
        scope: str = Form(""),
    ) -> Response:
        next_reader = f"/laws/{law_id}"
        opened = require_playground_open(
            request, templates, next_url=next_reader
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked
        _require_csrf(request, csrf_token)
        require_eligible_law(law_id)
        overlay = require_playground_repo(request)
        roster = require_roster_service(request)
        preview = roster.preview_add_law(
            opened.user_id,
            law_id,
            opened.snapshot,
            local_owner=opened.local_owner,
            can_consume_new_law=opened.can_consume_new_law,
        )
        if preview.status == RESULT_INELIGIBLE:
            raise HTTPException(status_code=404, detail="Law not found")
        scope_value = add_scope_value(scope)
        re_add = preview.status == RESULT_RE_ADD_CONFIRM
        skip = skips_add_confirm(opened)
        confirmed = is_add_confirmed(confirm) or skip

        if preview.status == RESULT_ALREADY_ACTIVE:
            if scope_value == SCOPE_ENTIRE:
                try:
                    persist_entire_act_selection(overlay, opened.user_id, law_id)
                    _schedule_playground_calendar_sync(request, opened.user_id)
                except SelectionRejected:
                    raise HTTPException(status_code=400, detail="invalid_selection")
                except Exception:
                    raise
            return _after_active_redirect(overlay, opened.user_id, law_id)

        if not re_add:
            gated = require_playground_new_law(
                request, templates, next_url=next_reader
            )
            denied_new = _denied(gated)
            if denied_new is not None:
                return denied_new
            opened = gated  # type: ignore[assignment]

        if not confirmed:
            if preview.status == RESULT_NEW_BLOCKED:
                denied = consume_blocked_response(
                    request, templates, opened, RESULT_NEW_BLOCKED
                )
                return denied
            return RedirectResponse(url=roster_path(add=law_id), status_code=303)

        if not is_add_scope(scope_value):
            ctx = _add_page_context(
                request=request,
                law_id=law_id,
                access=opened,
                overlay=overlay,
                roster=roster,
                step="scope",
                hydrate_scope=True,
            )
            return templates.TemplateResponse(request, "playground_add.html", ctx)

        if scope_value == SCOPE_ENTIRE:
            try:
                act = require_playground_law(law_id)
                rows = selection_rows(law_id, None, entire=True, act=act)
                if not rows:
                    raise SelectionRejected("invalid_selection")
            except SelectionRejected:
                raise HTTPException(status_code=400, detail="invalid_selection")
            except PlaygroundLawError:
                raise HTTPException(status_code=404, detail="Law not found")
            except LocatorError:
                raise HTTPException(status_code=400, detail="invalid_selection")
            result = roster.confirm_add_law(
                opened.user_id,
                law_id,
                opened.snapshot,
                local_owner=opened.local_owner,
                can_consume_new_law=opened.can_consume_new_law,
                has_historical_overlay=overlay.get_item(opened.user_id, law_id) is not None,
            )
            if result.status == RESULT_INELIGIBLE:
                raise HTTPException(status_code=404, detail="Law not found")
            if not result.ok:
                denied = consume_blocked_response(
                    request, templates, opened, result.status
                )
                return denied
            persist_entire_act_selection(
                overlay, opened.user_id, law_id, act=act
            )
            _schedule_playground_calendar_sync(request, opened.user_id)
            if result.status == RESULT_RE_ADDED:
                return RedirectResponse(
                    url=f"{roster_path()}?notice=readded&add={law_id}",
                    status_code=303,
                )
            return RedirectResponse(url=law_path(law_id), status_code=303)

        if scope_value != SCOPE_SECTIONS:
            raise HTTPException(status_code=400, detail="invalid_selection")
        result = roster.confirm_add_law(
            opened.user_id,
            law_id,
            opened.snapshot,
            local_owner=opened.local_owner,
            can_consume_new_law=opened.can_consume_new_law,
            has_historical_overlay=overlay.get_item(opened.user_id, law_id) is not None,
        )
        if result.status == RESULT_INELIGIBLE:
            raise HTTPException(status_code=404, detail="Law not found")
        if not result.ok:
            denied = consume_blocked_response(
                request, templates, opened, result.status
            )
            return denied
        activate_law(overlay, opened.user_id, law_id)
        _schedule_playground_calendar_sync(request, opened.user_id)
        if result.status == RESULT_RE_ADDED:
            return RedirectResponse(
                url=f"{roster_path()}?notice=readded&add={law_id}",
                status_code=303,
            )
        return _after_active_redirect(overlay, opened.user_id, law_id)

    @router.get("/roster/{law_id}/remove", response_class=HTMLResponse)
    async def playground_remove_confirm(request: Request, law_id: str) -> Response:
        opened = require_playground_open(
            request, templates, next_url=roster_path()
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked
        require_eligible_law(law_id)
        roster = require_roster_service(request)
        if not roster.is_law_active_this_period(opened.user_id, law_id):
            return RedirectResponse(url=roster_path(), status_code=303)
        capacity = roster.capacity(
            opened.user_id,
            opened.snapshot,
            local_owner=opened.local_owner,
        )
        month = playground_month_name(capacity.period_start)
        _long, short = catalog_titles(law_id)
        del _long
        return templates.TemplateResponse(
            request,
            "playground_remove.html",
            {
                "law_id": law_id,
                "month_name": month,
                "short_title": short,
            },
        )

    @router.post("/roster/{law_id}/remove")
    async def playground_remove(
        request: Request,
        law_id: str,
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        opened = require_playground_open(
            request, templates, next_url=roster_path()
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        _require_csrf(request, csrf_token)
        require_eligible_law(law_id)
        roster = require_roster_service(request)
        roster.remove_law_this_period(
            opened.user_id,
            law_id,
            opened.snapshot,
            local_owner=opened.local_owner,
        )
        _schedule_playground_calendar_sync(request, opened.user_id)
        return RedirectResponse(url=roster_path(), status_code=303)

    @router.get("/laws/{law_id}", response_class=HTMLResponse)
    async def playground_law(request: Request, law_id: str) -> HTMLResponse:
        overlay = require_playground_repo(request)
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=law_path(law_id),
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        item = overlay.get_item(access.user_id, law_id)
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        identity = playground_law_source_identity(law_id)
        source_summary = None
        if is_law_registry_outdated(item, identity):
            source_summary = detect_source_changes(
                overlay, access.user_id, law_id, hydrate=lambda _lid: act
            )
        source_state = law_source_state(overlay, access.user_id, law_id)
        change_by = {
            row.source_locator: row
            for row in overlay.list_source_changes(
                access.user_id, law_id, status=STATUS_PENDING
            )
            if row.current_source_version == identity.source_version
            and row.current_law_source_hash == identity.identity_token
        }
        selections = overlay.list_selection(access.user_id, law_id)
        progress_map = {
            row.source_locator: mark_outdated(
                row, _section_source_hash(act, row.source_locator, law_id)
            )
            for row in overlay.list_progress(access.user_id, law_id)
        }
        live_hashes = {
            sel.source_locator: _section_source_hash(act, sel.source_locator, law_id)
            for sel in selections
        }
        mode_summaries = summaries_for_locators(
            overlay.list_mode_progress(access.user_id, law_id),
            [sel.source_locator for sel in selections],
            live_hashes=live_hashes,
        )
        revision_rows = overlay.list_revision_mode_progress(access.user_id, law_id)
        revision_by_key: dict[tuple[str, int], list] = {}
        for row in revision_rows:
            if row.rung_days is None:
                continue
            revision_by_key.setdefault((row.source_locator, row.rung_days), []).append(row)
        rows = []
        as_of = playground_today()
        month = ""
        if access.snapshot is not None and access.snapshot.playground_period_start is not None:
            month = playground_month_name(access.snapshot.playground_period_start)
        else:
            cap = require_roster_service(request).capacity(
                access.user_id, access.snapshot, local_owner=access.local_owner
            )
            month = playground_month_name(cap.period_start)
        for sel in selections:
            loc = parse_selected_locator(sel.source_locator, law_id)
            if loc is None:
                continue
            section = act.section(loc.section_number)
            missing = section is None
            progress = progress_map.get(sel.source_locator)
            interval = int(getattr(progress, "interval_days", 0) or 0) if progress else 0
            rev_modes = None
            if interval in REVISION_RUNGS_SET:
                rev_modes = build_revision_mode_progress(
                    sel.source_locator,
                    interval,
                    revision_by_key.get((sel.source_locator, interval), ()),
                    live_hash=live_hashes.get(sel.source_locator, ""),
                )
            change = change_by.get(sel.source_locator)
            pending_change = bool(change and change.status == STATUS_PENDING)
            rows.append(
                section_row_view(
                    number=loc.section_number,
                    title=(
                        section.list_title
                        if section is not None
                        else f"Section {loc.section_number}"
                    ),
                    locator=sel.source_locator,
                    progress=progress,
                    outdated=pending_change,
                    as_of=as_of,
                    law_id=law_id,
                    mode_progress=mode_summaries.get(sel.source_locator),
                    revision_modes=rev_modes,
                    source_change=change,
                    missing=missing or (
                        change is not None and change.change_kind == CHANGE_KIND_MISSING
                    ),
                )
            )
        launch = choose_next_workspace_row(rows)
        progress = build_act_progress(rows, law_id=law_id, act=act)
        launch_verbatim = ""
        if launch is not None:
            loc = parse_selected_locator(launch["locator"], law_id)
            section = act.section(launch["number"])
            if section is not None and loc is not None:
                launch_verbatim = canonical_text_for_locator(loc, section)
        learned_changed = (
            source_state.pending_learned_count if source_state.registry_outdated else 0
        )
        return templates.TemplateResponse(
            request,
            "playground_law.html",
            {
                "act": act,
                "item": item,
                "rows": rows,
                "month_name": month,
                "launch": launch,
                "launch_verbatim": launch_verbatim,
                "progress": progress,
                "source_state": source_state,
                "source_summary": source_summary,
                "provenance": provenance_lines(law_id),
                "source_review_href": source_review_path(law_id),
                "learned_changed": learned_changed,
            },
        )

    @router.get("/laws/{law_id}/sections", response_class=HTMLResponse)
    async def playground_select_page(request: Request, law_id: str) -> HTMLResponse:
        overlay = require_playground_repo(request)
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=sections_path(law_id),
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        item = overlay.get_item(access.user_id, law_id)
        identity = playground_law_source_identity(law_id)
        if is_law_registry_outdated(item, identity):
            detect_source_changes(
                overlay, access.user_id, law_id, hydrate=lambda _lid: act
            )
        selected = selected_locator_set(overlay.list_selection(access.user_id, law_id))
        learnable = {loc.value for loc in locators_for_act(law_id, act=act)}
        progress_map = {
            row.source_locator: row
            for row in overlay.list_progress(access.user_id, law_id)
        }
        mode_rows = overlay.list_mode_progress(access.user_id, law_id)
        status_locators = list(
            {
                *selected,
                *progress_map,
                *(row.source_locator for row in mode_rows),
            }
        )
        mode_summaries = summaries_for_locators(
            mode_rows,
            status_locators,
            live_hashes={
                loc: _section_source_hash(act, loc, law_id) for loc in status_locators
            },
        )
        picker = picker_page_view(
            act=act,
            law_id=law_id,
            selected=selected,
            progress_map=progress_map,
            mode_summaries=mode_summaries,
            as_of=playground_today(),
            learnable=learnable,
        )
        return templates.TemplateResponse(
            request,
            "playground_select.html",
            {
                "act": act,
                "picker": picker,
                "bands": picker["bands"],
                "chapterless": picker["chapterless"],
                "cta_label": picker["cta_label"],
                "zero_selection": picker["zero_selection"],
                "provision_label": picker["provision_label"],
                "aside_items": picker["aside_items"],
                "aside_count": picker["aside_count"],
                "aside_count_label": picker["aside_count_label"],
                "section_count": picker["section_count"],
                "partial_unit_count": picker["partial_unit_count"],
            },
        )

    @router.post("/laws/{law_id}/sections")
    async def playground_select_save(
        request: Request,
        law_id: str,
    ) -> RedirectResponse:
        overlay = require_playground_repo(request)
        opened = require_law_active_this_period(
            request, templates, overlay, law_id, next_url=sections_path(law_id)
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        form = await request.form()
        csrf_token = str(form.get("csrf_token") or "")
        _require_csrf(request, csrf_token)
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        entire_raw = form.get("entire")
        entire_act = str(entire_raw or "") in {"1", "on", "true", "yes"}
        numbers = [str(value) for value in form.getlist("section")]
        units = [str(value) for value in form.getlist("unit")]
        try:
            rows = selection_rows(
                law_id, numbers, entire=entire_act, act=act, units=units
            )
        except SelectionRejected:
            raise HTTPException(status_code=400, detail="invalid_selection") from None
        if overlay.get_item(opened.user_id, law_id) is None:
            activate_law(overlay, opened.user_id, law_id)
        overlay.replace_selection(opened.user_id, law_id, rows)
        _schedule_playground_calendar_sync(request, opened.user_id)
        return RedirectResponse(url=law_path(law_id), status_code=303)

    def _open_source_review(request: Request, law_id: str, *, json_mode: bool = False):
        overlay = require_playground_repo(request)
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=source_review_path(law_id),
            json_mode=json_mode,
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked, None, None, None, None
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        summary = detect_source_changes(
            overlay, access.user_id, law_id, hydrate=lambda _lid: act
        )
        return None, overlay, access, act, summary

    @router.get("/laws/{law_id}/source-review", response_class=HTMLResponse)
    async def playground_source_review(request: Request, law_id: str) -> HTMLResponse:
        opened = _open_source_review(request, law_id)
        blocked = opened[0]
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        _none, overlay, access, act, summary = opened
        progress_by = {
            row.source_locator: row
            for row in overlay.list_progress(access.user_id, law_id)
        }
        current = [
            row
            for row in summary.changes
            if row.current_source_version == summary.current_source_version
            and row.current_law_source_hash == summary.current_identity_token
        ]
        pending = [row for row in current if row.status == STATUS_PENDING]
        provisions = [
            affected_provision_view(
                row, progress=progress_by.get(row.source_locator), act=act
            )
            for row in current
        ]
        catalog = playground_catalogue_law(law_id)
        title = catalog.title if catalog is not None else law_id
        all_reviewed = bool(current) and not pending
        zero_affected = summary.affected_total == 0
        return templates.TemplateResponse(
            request,
            "playground_source_review.html",
            {
                "act": act,
                "title": title,
                "summary": summary,
                "provisions": provisions,
                "pending_count": len(pending),
                "all_reviewed": all_reviewed,
                "zero_affected": zero_affected,
                "provenance": provenance_lines(law_id),
                "change_copy": change_copy,
                "workspace_href": law_path(law_id),
                "read_href": f"/laws/{law_id}",
            },
        )

    @router.get(
        "/laws/{law_id}/source-review/sections/{number}",
        response_class=HTMLResponse,
    )
    async def playground_source_review_section(
        request: Request, law_id: str, number: str
    ) -> HTMLResponse:
        return await _source_review_detail(request, law_id, number, unit=None)

    @router.post("/laws/{law_id}/source-review/sections/{number}/reviewed")
    async def playground_source_review_mark(
        request: Request,
        law_id: str,
        number: str,
        csrf_token: str = Form(""),
        detected_source_version: str = Form(""),
        detected_law_source_hash: str = Form(""),
    ) -> Response:
        return await _source_review_mark(
            request,
            law_id,
            number,
            unit=None,
            csrf_token=csrf_token,
            detected_source_version=detected_source_version,
            detected_law_source_hash=detected_law_source_hash,
        )

    def _gate_learn(
        request: Request,
        law_id: str,
        number: str,
        mode: str,
        *,
        json_mode: bool,
        unit: str | None = None,
    ):
        if not is_playground_learn_mode(mode):
            raise HTTPException(status_code=404, detail="Learn mode not found")
        overlay = require_playground_repo(request)
        try:
            next_loc = (
                parse_selected_locator(f"{law_id}:section:{number}:{unit}", law_id)
                if unit
                else parse_selected_locator(f"{law_id}:section:{number}", law_id)
            )
        except Exception:
            next_loc = None
        next_url = (
            learn_path_for_locator(next_loc, mode)
            if next_loc is not None
            else learn_path(law_id, number, mode)
        )
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=next_url,
            json_mode=json_mode,
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked
        try:
            act = require_playground_law(law_id)
            loc, act, section, body, live_hash, source_version, lead_in = load_learn_provision(
                law_id, number, act=act, unit=unit
            )
        except (PlaygroundLawError, LocatorError, LearnProvisionError) as exc:
            loc_try = parse_selected_locator(
                f"{law_id}:section:{number}:{unit}" if unit else f"{law_id}:section:{number}",
                law_id,
            )
            selected = selected_locator_set(overlay.list_selection(access.user_id, law_id))
            has_history = bool(
                loc_try
                and (
                    loc_try.value in selected
                    or overlay.get_progress(access.user_id, law_id, loc_try.value)
                )
            )
            if has_history:
                if json_mode:
                    return JSONResponse(
                        {"ok": False, "error": "source_missing"},
                        status_code=404,
                    )
                review_url = (
                    source_review_path_for_locator(loc_try)
                    if loc_try is not None
                    else source_review_section_path(law_id, number)
                )
                return RedirectResponse(
                    url=review_url,
                    status_code=303,
                )
            raise HTTPException(status_code=404, detail="Section not found") from exc
        selected = selected_locator_set(overlay.list_selection(access.user_id, law_id))
        if loc.value not in selected:
            if json_mode:
                return JSONResponse({"ok": False, "error": "not_selected"}, status_code=400)
            return RedirectResponse(url=sections_path(law_id), status_code=303)
        return {
            "overlay": overlay,
            "access": access,
            "act": act,
            "section": section,
            "locator": loc,
            "body": body,
            "live_hash": live_hash,
            "source_version": source_version,
            "lead_in": lead_in,
        }

    def _mode_payload(summary, row, *, body: str, live_hash: str) -> dict:
        stored_hash = row.source_hash if row is not None else live_hash
        return {
            "ok": True,
            "mode": row.mode if row is not None else "",
            "status": row.status if row is not None else None,
            "attempt_count": row.attempt_count if row is not None else 0,
            "completed_count": summary.completed_count,
            "total_modes": summary.total_modes,
            "next_mode": summary.next_mode,
            "all_methods_complete": summary.all_methods_complete,
            "completed_modes": list(summary.completed_modes),
            "canonical_body": body,
            "revealed": body,
            "source_locator": summary.source_locator,
            "source_outdated": summary.source_outdated or (
                row is not None and row.source_hash != live_hash
            ),
            "stored_source_hash": stored_hash,
        }

    @router.get(
        "/laws/{law_id}/sections/{number}/learn/{mode}",
        response_class=HTMLResponse,
    )
    async def playground_learn(
        request: Request, law_id: str, number: str, mode: str
    ) -> HTMLResponse:
        return _render_learn(request, law_id, number, mode, unit=None)

    @router.get(
        "/laws/{law_id}/sections/{number}/u/{unit}/learn/{mode}",
        response_class=HTMLResponse,
    )
    async def playground_learn_unit(
        request: Request, law_id: str, number: str, unit: str, mode: str
    ) -> HTMLResponse:
        return _render_learn(request, law_id, number, mode, unit=unit)

    def _render_learn(
        request: Request,
        law_id: str,
        number: str,
        mode: str,
        *,
        unit: str | None,
    ):
        opened = _gate_learn(
            request, law_id, number, mode, json_mode=False, unit=unit
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        overlay = opened["overlay"]
        access = opened["access"]
        loc = opened["locator"]
        live_hash = opened["live_hash"]
        body = opened["body"]
        as_of = playground_today()
        wants_revision, _claimed = _revision_flag(request)
        progress = mark_outdated(
            overlay.get_progress(access.user_id, law_id, loc.value), live_hash
        )
        is_revision = bool(
            wants_revision
            and progress is not None
            and revision_is_due(
                status=progress.status,
                next_revision=progress.next_revision,
                today=as_of,
            )
            and int(progress.interval_days or 0) in REVISION_RUNGS_SET
        )
        rung = int(progress.interval_days) if is_revision and progress is not None else None
        if is_revision and rung is not None:
            mode_rows = overlay.list_revision_mode_progress(
                access.user_id, law_id, loc.value, rung
            )
            summary = build_revision_mode_progress(
                loc.value, rung, mode_rows, live_hash=live_hash
            )
        else:
            mode_rows = overlay.list_mode_progress(
                access.user_id, law_id, loc.value
            )
            summary = provision_mode_view(
                source_locator=loc.value, rows=mode_rows, live_hash=live_hash
            )
        source_outdated = bool(
            summary.source_outdated or (progress and progress.source_outdated)
        )
        test_row = next((row for row in mode_rows if row.mode == "test"), None)
        cycle = test_row.attempt_count if test_row is not None else 0
        quiz_questions = []
        if mode == "test":
            quiz_questions = [
                question.public_dict()
                for question in quiz_for_attempt(
                    law_id=law_id,
                    source_locator=loc.value,
                    canonical_body=body,
                    cycle=cycle,
                    source_hash=live_hash,
                    rung_days=rung,
                )
            ]
        current = next(
            (row for row in mode_rows if row.mode == mode),
            None,
        )
        current_status = current.status if current is not None else "not_started"
        definitions = mode_definitions()
        step_n = next(
            (item["ordinal"] for item in definitions if item["id"] == mode),
            1,
        )
        remaining = max(0, summary.total_modes - summary.completed_count)
        if remaining <= 0:
            methods_left = "Mark it Done"
        elif remaining == 1:
            methods_left = "1 method left"
        else:
            methods_left = f"{remaining} methods left"
        advance = next(
            (item.get("advance") for item in definitions if item["id"] == mode),
            "Mark as done",
        )
        lead_in = opened.get("lead_in") or ""
        speech_url = ""
        if mode in {"letters", "recite"}:
            speech_url = learn_speech_path_for_locator(loc, mode)
        return templates.TemplateResponse(
            request,
            "playground_learn.html",
            {
                "act": opened["act"],
                "section": opened["section"],
                "locator": loc.value,
                "canonical_body": body,
                "lead_in": lead_in,
                "learn_mode": mode,
                "learn_modes": definitions,
                "mode_label": PLAYGROUND_MODE_LABELS[mode],
                "step_n": step_n,
                "summary": summary,
                "methods_left": methods_left,
                "advance_label": advance,
                "current_status": current_status,
                "progress": progress,
                "source_outdated": source_outdated,
                "source_version": opened["source_version"],
                "provenance": provenance_lines(law_id),
                "citation": citation_label(loc),
                "learn_links": {
                    item["id"]: learn_path_for_locator(loc, item["id"])
                    for item in definitions
                },
                "complete_url": learn_complete_path_for_locator(loc, mode),
                "start_url": learn_start_path_for_locator(loc, mode),
                "quiz_url": learn_quiz_path_for_locator(loc),
                "speech_url": speech_url,
                "learned_url": learned_path_for_locator(loc),
                "mastered_url": mastered_path_for_locator(loc),
                "quiz_cycle": cycle,
                "quiz_questions": quiz_questions,
                "cloze_fallback": cloze_needs_fallback(body),
                "is_revision": is_revision,
                "revision_rung": rung,
                "revision_qs": "?revision=1" if is_revision else "",
            },
        )

    @router.post("/laws/{law_id}/sections/{number}/learn/{mode}/start")
    async def playground_learn_start(
        request: Request, law_id: str, number: str, mode: str
    ) -> JSONResponse:
        return await _learn_start(request, law_id, number, mode, unit=None)

    @router.post("/laws/{law_id}/sections/{number}/u/{unit}/learn/{mode}/start")
    async def playground_learn_start_unit(
        request: Request, law_id: str, number: str, unit: str, mode: str
    ) -> JSONResponse:
        return await _learn_start(request, law_id, number, mode, unit=unit)

    async def _learn_start(
        request: Request, law_id: str, number: str, mode: str, *, unit: str | None
    ) -> JSONResponse:
        data = await _mutation_payload(request)
        opened = _gate_learn(
            request, law_id, number, mode, json_mode=True, unit=unit
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        overlay = opened["overlay"]
        access = opened["access"]
        loc = opened["locator"]
        wants_revision, claimed = _revision_flag(request, data)
        as_of = playground_today()
        if wants_revision:
            try:
                row = overlay.start_revision_mode(
                    access.user_id,
                    law_id,
                    loc.value,
                    mode,
                    source_version=opened["source_version"],
                    source_hash=opened["live_hash"],
                    as_of=as_of,
                    claimed_rung=claimed,
                )
            except (StaleRevisionError, RevisionNotDueError) as exc:
                return _revision_error(exc)
            lifecycle = overlay.get_progress(access.user_id, law_id, loc.value)
            rung = int(lifecycle.interval_days) if lifecycle is not None else claimed
            summary = build_revision_mode_progress(
                loc.value,
                rung,
                overlay.list_revision_mode_progress(
                    access.user_id, law_id, loc.value, rung
                ),
                live_hash=opened["live_hash"],
            )
        else:
            row = overlay.start_mode(
                access.user_id,
                law_id,
                loc.value,
                mode,
                source_version=opened["source_version"],
                source_hash=opened["live_hash"],
            )
            summary = provision_mode_view(
                source_locator=loc.value,
                rows=overlay.list_mode_progress(access.user_id, law_id, loc.value),
                live_hash=opened["live_hash"],
            )
        return JSONResponse(
            _mode_payload(
                summary, row, body=opened["body"], live_hash=opened["live_hash"]
            )
        )

    @router.post("/laws/{law_id}/sections/{number}/learn/{mode}/complete")
    async def playground_learn_complete(
        request: Request, law_id: str, number: str, mode: str
    ) -> JSONResponse:
        return await _learn_complete(request, law_id, number, mode, unit=None)

    @router.post("/laws/{law_id}/sections/{number}/u/{unit}/learn/{mode}/complete")
    async def playground_learn_complete_unit(
        request: Request, law_id: str, number: str, unit: str, mode: str
    ) -> JSONResponse:
        return await _learn_complete(request, law_id, number, mode, unit=unit)

    async def _learn_complete(
        request: Request, law_id: str, number: str, mode: str, *, unit: str | None
    ) -> JSONResponse:
        if mode == "test":
            raise HTTPException(status_code=404, detail="Learn mode not found")
        data = await _mutation_payload(request)
        opened = _gate_learn(
            request, law_id, number, mode, json_mode=True, unit=unit
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        overlay = opened["overlay"]
        access = opened["access"]
        loc = opened["locator"]
        wants_revision, claimed = _revision_flag(request, data)
        as_of = playground_today()
        if wants_revision:
            try:
                row = overlay.complete_revision_mode_and_advance_if_ready(
                    access.user_id,
                    law_id,
                    loc.value,
                    mode,
                    source_version=opened["source_version"],
                    source_hash=opened["live_hash"],
                    as_of=as_of,
                    claimed_rung=claimed,
                )
            except (StaleRevisionError, RevisionNotDueError) as exc:
                return _revision_error(exc)
            rung = int(row.rung_days or claimed or 0)
            summary = build_revision_mode_progress(
                loc.value,
                rung,
                overlay.list_revision_mode_progress(
                    access.user_id, law_id, loc.value, rung
                ),
                live_hash=opened["live_hash"],
            )
            payload = _mode_payload(
                summary, row, body=opened["body"], live_hash=opened["live_hash"]
            )
            payload["revision"] = True
            if summary.all_methods_complete:
                payload["methods_complete_label"] = (
                    f"Day {row.rung_days} complete"
                )
            payload = _after_six_payload(
                payload,
                overlay,
                access.user_id,
                law_id,
                loc,
                revision=True,
                rung=rung,
            )
            _schedule_playground_calendar_sync(request, access.user_id)
            return JSONResponse(payload)
        row = overlay.complete_mode(
            access.user_id,
            law_id,
            loc.value,
            mode,
            source_version=opened["source_version"],
            source_hash=opened["live_hash"],
            as_of=as_of,
        )
        summary = provision_mode_view(
            source_locator=loc.value,
            rows=overlay.list_mode_progress(access.user_id, law_id, loc.value),
            live_hash=opened["live_hash"],
        )
        payload = _mode_payload(
            summary, row, body=opened["body"], live_hash=opened["live_hash"]
        )
        if summary.all_methods_complete:
            payload["methods_complete_label"] = "Learned"
            payload["learned"] = True
        payload = _after_six_payload(
            payload,
            overlay,
            access.user_id,
            law_id,
            loc,
            revision=False,
        )
        _schedule_playground_calendar_sync(request, access.user_id)
        return JSONResponse(payload)

    @router.post("/laws/{law_id}/sections/{number}/learn/test/quiz")
    async def playground_learn_quiz(
        request: Request, law_id: str, number: str
    ) -> JSONResponse:
        return await _learn_quiz(request, law_id, number, unit=None)

    @router.post("/laws/{law_id}/sections/{number}/u/{unit}/learn/test/quiz")
    async def playground_learn_quiz_unit(
        request: Request, law_id: str, number: str, unit: str
    ) -> JSONResponse:
        return await _learn_quiz(request, law_id, number, unit=unit)

    async def _learn_quiz(
        request: Request, law_id: str, number: str, *, unit: str | None
    ) -> JSONResponse:
        data = await _mutation_payload(request)
        opened = _gate_learn(
            request, law_id, number, "test", json_mode=True, unit=unit
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        overlay = opened["overlay"]
        access = opened["access"]
        loc = opened["locator"]
        live_hash = opened["live_hash"]
        body = opened["body"]
        wants_revision, claimed = _revision_flag(request, data)
        as_of = playground_today()
        if wants_revision:
            lifecycle = overlay.get_progress(access.user_id, law_id, loc.value)
            try:
                rung = _current_due_rung(lifecycle, as_of, claimed)
            except (StaleRevisionError, RevisionNotDueError) as exc:
                return _revision_error(exc)
            stored = overlay.get_revision_mode_progress(
                access.user_id, law_id, loc.value, rung, "test"
            )
            cycle = stored.attempt_count if stored is not None else 0
            try:
                submitted_cycle = int(data.get("cycle"))
            except (TypeError, ValueError):
                return JSONResponse({"ok": False, "error": "malformed"}, status_code=400)
            if submitted_cycle != cycle:
                return JSONResponse({"ok": False, "error": "stale"}, status_code=409)
            questions = quiz_for_attempt(
                law_id=law_id,
                source_locator=loc.value,
                canonical_body=body,
                cycle=cycle,
                source_hash=live_hash,
                rung_days=rung,
            )
            if not questions:
                return JSONResponse({"ok": False, "error": "quiz_unavailable"}, status_code=400)
            answers = coerce_quiz_answers(data.get("answers"), len(questions))
            if answers is None:
                return JSONResponse({"ok": False, "error": "malformed"}, status_code=400)
            graded = grade_section_quiz(questions, answers)
            try:
                row = overlay.complete_revision_mode_and_advance_if_ready(
                    access.user_id,
                    law_id,
                    loc.value,
                    "test",
                    source_version=opened["source_version"],
                    source_hash=live_hash,
                    as_of=as_of,
                    claimed_rung=rung,
                )
            except (StaleRevisionError, RevisionNotDueError) as exc:
                return _revision_error(exc)
            summary = build_revision_mode_progress(
                loc.value,
                rung,
                overlay.list_revision_mode_progress(
                    access.user_id, law_id, loc.value, rung
                ),
                live_hash=live_hash,
            )
            payload = _mode_payload(summary, row, body=body, live_hash=live_hash)
            payload["correct"] = graded["correct"]
            payload["total"] = graded["total"]
            payload["results"] = graded["results"]
            payload["revision"] = True
            if summary.all_methods_complete:
                payload["methods_complete_label"] = f"Day {rung} complete"
            payload = _after_six_payload(
                payload,
                overlay,
                access.user_id,
                law_id,
                loc,
                revision=True,
                rung=rung,
            )
            _schedule_playground_calendar_sync(request, access.user_id)
            return JSONResponse(payload)
        stored = overlay.get_mode_progress(
            access.user_id, law_id, loc.value, "test"
        )
        cycle = stored.attempt_count if stored is not None else 0
        try:
            submitted_cycle = int(data.get("cycle"))
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "malformed"}, status_code=400)
        if submitted_cycle != cycle:
            return JSONResponse({"ok": False, "error": "stale"}, status_code=409)
        questions = quiz_for_attempt(
            law_id=law_id,
            source_locator=loc.value,
            canonical_body=body,
            cycle=cycle,
            source_hash=live_hash,
        )
        if not questions:
            return JSONResponse({"ok": False, "error": "quiz_unavailable"}, status_code=400)
        answers = coerce_quiz_answers(data.get("answers"), len(questions))
        if answers is None:
            return JSONResponse({"ok": False, "error": "malformed"}, status_code=400)
        graded = grade_section_quiz(questions, answers)
        row = overlay.complete_mode(
            access.user_id,
            law_id,
            loc.value,
            "test",
            source_version=opened["source_version"],
            source_hash=live_hash,
            as_of=as_of,
        )
        summary = provision_mode_view(
            source_locator=loc.value,
            rows=overlay.list_mode_progress(access.user_id, law_id, loc.value),
            live_hash=live_hash,
        )
        payload = _mode_payload(summary, row, body=body, live_hash=live_hash)
        payload["correct"] = graded["correct"]
        payload["total"] = graded["total"]
        payload["results"] = graded["results"]
        if summary.all_methods_complete:
            payload["methods_complete_label"] = "Learned"
            payload["learned"] = True
        payload = _after_six_payload(
            payload,
            overlay,
            access.user_id,
            law_id,
            loc,
            revision=False,
        )
        _schedule_playground_calendar_sync(request, access.user_id)
        return JSONResponse(payload)

    async def _playground_speech(
        request: Request,
        law_id: str,
        number: str,
        mode: str,
        *,
        unit: str | None,
    ) -> JSONResponse:
        from constitution_memorizer.speech.align import align_text as letters_align
        from constitution_memorizer.speech.align import tokenize
        from constitution_memorizer.speech.limits import (
            SpeechTooLarge,
            mime_allowed,
            read_upload_limited,
        )
        from constitution_memorizer.speech.provider import (
            SpeechError,
            SpeechUnavailable,
            Transcript,
        )

        header = request.headers.get("X-CSRF-Token") or ""
        form = await request.form()
        token = header or str(form.get("csrf_token") or "")
        _require_csrf(request, token)
        opened = _gate_learn(
            request, law_id, number, mode, json_mode=True, unit=unit
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        if mode not in {"letters", "recite"}:
            return JSONResponse({"ok": False, "error": "invalid_mode"}, status_code=400)
        expected = str(form.get("expected") or "")
        del expected
        typed = str(form.get("text") or "").strip()
        body = opened["body"]
        transcript_text = typed
        words_payload: list[dict] = []
        if not typed:
            limiter = request.app.state.speech_rate_limiter
            user = getattr(request.state, "current_user", None)
            if user is not None:
                rate_key = f"user:{user.id}"
            elif request.client is not None:
                rate_key = f"ip:{request.client.host}"
            else:
                rate_key = "ip:unknown"
            if not limiter.allow(rate_key):
                return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429)
            audio = form.get("audio")
            if audio is None or not hasattr(audio, "read"):
                return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
            content_type = getattr(audio, "content_type", None) or ""
            if not mime_allowed(content_type):
                return JSONResponse({"ok": False, "error": "unsupported_type"}, status_code=400)
            try:
                audio_bytes = await read_upload_limited(audio)
            except SpeechTooLarge:
                return JSONResponse({"ok": False, "error": "too_large"}, status_code=413)
            if not audio_bytes:
                return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
            provider = request.app.state.speech_provider
            try:
                result: Transcript = await provider.transcribe(
                    audio_bytes,
                    mime_type=content_type.split(";")[0].strip() or "audio/webm",
                    keyterms=(),
                )
            except SpeechUnavailable:
                return JSONResponse({"ok": False, "error": "unavailable"}, status_code=503)
            except SpeechError as exc:
                return JSONResponse(
                    {"ok": False, "error": getattr(exc, "error_code", "provider_error")},
                    status_code=502,
                )
            transcript_text = result.text.strip()
            words_payload = [
                {"word": item.word, "confidence": item.confidence}
                for item in result.words
            ]
            if not transcript_text:
                return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
        payload: dict[str, object] = {
            "ok": True,
            "transcript": transcript_text,
            "words": words_payload,
        }
        if mode == "letters":
            raw_start = form.get("from_index") or 0
            try:
                start = max(0, int(raw_start))
            except (TypeError, ValueError):
                start = 0
            if start > len(tokenize(body)):
                start = 0
            hits = letters_align(body, transcript_text, from_index=start)
            payload["alignment"] = [
                {"index": hit.index, "status": hit.status} for hit in hits
            ]
        else:
            mapped = recite_alignment(body, transcript_text)
            payload["alignment"] = {
                "source_words": list(mapped.source_words),
                "hit_indices": sorted(mapped.hit_indices),
                "hits": mapped.hits,
                "total": mapped.total,
                "percent": mapped.percent,
                "stats_label": mapped.stats_label(),
            }
        return JSONResponse(payload)

    @router.post("/laws/{law_id}/sections/{number}/learn/{mode}/speech")
    async def playground_learn_speech(
        request: Request, law_id: str, number: str, mode: str
    ) -> JSONResponse:
        return await _playground_speech(request, law_id, number, mode, unit=None)

    @router.post("/laws/{law_id}/sections/{number}/u/{unit}/learn/{mode}/speech")
    async def playground_learn_speech_unit(
        request: Request, law_id: str, number: str, unit: str, mode: str
    ) -> JSONResponse:
        return await _playground_speech(request, law_id, number, mode, unit=unit)

    def _workspace_progress_rows(overlay, user_id, law_id: str, act):
        selections = overlay.list_selection(user_id, law_id)
        progress_map = {
            row.source_locator: row
            for row in overlay.list_progress(user_id, law_id)
        }
        pending = overlay.list_source_changes(
            user_id, law_id, status=STATUS_PENDING
        )
        kind_by = {row.source_locator: row.change_kind for row in pending}
        rows = []
        for sel in selections:
            loc = parse_selected_locator(sel.source_locator, law_id)
            section = act.section(loc.section_number) if loc is not None else None
            change_kind = str(kind_by.get(sel.source_locator) or "")
            missing = (
                section is None
                or bool(getattr(section, "is_omitted", False))
                or change_kind in {CHANGE_KIND_MISSING, CHANGE_KIND_OMITTED}
            )
            rows.append(
                {
                    "locator": sel.source_locator,
                    "missing": missing,
                    "source_change_kind": change_kind,
                    "progress": progress_map.get(sel.source_locator),
                    "completed_count": 0,
                    "status": str(
                        getattr(progress_map.get(sel.source_locator), "status", "") or ""
                    ),
                    "citation": citation_label(sel.source_locator),
                    "href": "",
                    "cta": "",
                    "due_label": "",
                }
            )
        return rows, bool(pending)

    def _whole_act_mastered(overlay, user_id, law_id: str, act):
        rows, source_pending = _workspace_progress_rows(
            overlay, user_id, law_id, act
        )
        facts = build_act_progress(rows, law_id=law_id, act=act)
        effective = [
            row
            for row in rows
            if not row["missing"]
            and row["source_change_kind"] not in {CHANGE_KIND_MISSING, CHANGE_KIND_OMITTED}
        ]
        ok = (
            facts.entire_act
            and bool(effective)
            and all(
                str(getattr(row["progress"], "status", "") or "") == "mastered"
                for row in effective
            )
        )
        return ok, facts, source_pending

    def _render_completion(
        request: Request,
        law_id: str,
        number: str,
        *,
        unit: str | None,
        want: str,
    ):
        from constitution_memorizer.playground.locators import SectionLocator

        opened = _gate_learn(
            request, law_id, number, "read", json_mode=False, unit=unit
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked
        overlay = opened["overlay"]
        access = opened["access"]
        loc = opened["locator"]
        act = opened["act"]
        progress = overlay.get_progress(access.user_id, law_id, loc.value)
        status = str(getattr(progress, "status", "") or "")
        if status == "review":
            return RedirectResponse(url=law_path(law_id), status_code=303)
        rows, source_pending = _workspace_progress_rows(
            overlay, access.user_id, law_id, act
        )
        facts = build_act_progress(rows, law_id=law_id, act=act)
        if want == "learned":
            if status == "mastered":
                return RedirectResponse(
                    url=mastered_path_for_locator(loc), status_code=303
                )
            if status != "learned":
                return RedirectResponse(
                    url=learn_path_for_locator(loc, "read"), status_code=303
                )
            variant = "learned"
        else:
            if status != "mastered":
                return RedirectResponse(url=law_path(law_id), status_code=303)
            whole, facts, source_pending = _whole_act_mastered(
                overlay, access.user_id, law_id, act
            )
            variant = "whole" if whole else "mastered"
        if variant == "whole":
            title = "The whole Act. By heart."
            kicker = act.short_name
            note = (
                "Completed all six review rungs through Day 60 on "
                f"{facts.completed_scope_count} of {facts.selected_count} provisions."
            )
        elif variant == "mastered":
            title = "Mastered, verbatim."
            kicker = citation_label(loc)
            note = "Completed all six review rungs through Day 60."
        else:
            title = (
                "Section learned."
                if isinstance(loc, SectionLocator)
                else f"{citation_label(loc)} learned."
            )
            kicker = citation_label(loc)
            when = ""
            if progress is not None and progress.next_revision:
                when = format_study_date(progress.next_revision)
            note = "First revision · Day 1"
            if when:
                note = f"{note} · {when}"
        return templates.TemplateResponse(
            request,
            "playground_learned.html",
            {
                "act": act,
                "locator": loc,
                "citation": citation_label(loc),
                "variant": variant,
                "title": title,
                "kicker": kicker,
                "note": note,
                "progress": facts,
                "lifecycle": progress,
                "source_pending": source_pending,
                "workspace_href": law_path(law_id),
                "rungs": (1, 3, 7, 15, 30, 60),
            },
        )

    @router.get("/laws/{law_id}/sections/{number}/learned", response_class=HTMLResponse)
    async def playground_learned(
        request: Request, law_id: str, number: str
    ) -> HTMLResponse:
        return _render_completion(request, law_id, number, unit=None, want="learned")

    @router.get(
        "/laws/{law_id}/sections/{number}/u/{unit}/learned",
        response_class=HTMLResponse,
    )
    async def playground_learned_unit(
        request: Request, law_id: str, number: str, unit: str
    ) -> HTMLResponse:
        return _render_completion(request, law_id, number, unit=unit, want="learned")

    @router.get("/laws/{law_id}/sections/{number}/mastered", response_class=HTMLResponse)
    async def playground_mastered(
        request: Request, law_id: str, number: str
    ) -> HTMLResponse:
        return _render_completion(request, law_id, number, unit=None, want="mastered")

    @router.get(
        "/laws/{law_id}/sections/{number}/u/{unit}/mastered",
        response_class=HTMLResponse,
    )
    async def playground_mastered_unit(
        request: Request, law_id: str, number: str, unit: str
    ) -> HTMLResponse:
        return _render_completion(request, law_id, number, unit=unit, want="mastered")

    @router.get("/laws/{law_id}/mastered", response_class=HTMLResponse)
    async def playground_act_mastered(request: Request, law_id: str) -> HTMLResponse:
        overlay = require_playground_repo(request)
        access = require_law_active_this_period(
            request, templates, overlay, law_id, next_url=act_mastered_path(law_id)
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        ok, facts, source_pending = _whole_act_mastered(
            overlay, access.user_id, law_id, act
        )
        if not ok:
            return RedirectResponse(url=law_path(law_id), status_code=303)
        return templates.TemplateResponse(
            request,
            "playground_learned.html",
            {
                "act": act,
                "locator": None,
                "citation": act.short_name,
                "variant": "whole",
                "title": "The whole Act. By heart.",
                "kicker": act.short_name,
                "note": (
                    "Completed all six review rungs through Day 60 on "
                    f"{facts.completed_scope_count} of {facts.selected_count} provisions."
                ),
                "progress": facts,
                "lifecycle": None,
                "source_pending": source_pending,
                "workspace_href": law_path(law_id),
                "rungs": (1, 3, 7, 15, 30, 60),
            },
        )

    def _source_review_locator(law_id: str, number: str, unit: str | None):
        if unit:
            return parse_locator(f"{law_id}:section:{number}:{unit}")
        return parse_locator(f"{law_id}:section:{number}")

    async def _source_review_detail(
        request: Request, law_id: str, number: str, *, unit: str | None
    ):
        opened = _open_source_review(request, law_id)
        blocked = opened[0]
        if blocked is not None:
            return blocked
        _none, overlay, access, act, summary = opened
        try:
            loc = _source_review_locator(law_id, number, unit)
        except LocatorError:
            raise HTTPException(status_code=404, detail="Source change not found") from None
        locator = loc.value
        record = next(
            (row for row in summary.changes if row.source_locator == locator),
            None,
        )
        if record is None:
            record = overlay.get_source_change(
                access.user_id,
                law_id,
                locator,
                current_source_version=summary.current_source_version,
                current_law_source_hash=summary.current_identity_token,
            )
        if record is None:
            raise HTTPException(status_code=404, detail="Source change not found")
        progress = overlay.get_progress(access.user_id, law_id, locator)
        provision = affected_provision_view(record, progress=progress, act=act)
        return templates.TemplateResponse(
            request,
            "playground_source_review_section.html",
            {
                "act": act,
                "provision": provision,
                "record": record,
                "summary": summary,
                "provenance": provenance_lines(law_id),
                "change_copy": change_copy(record.change_kind),
                "reviewed": record.status == STATUS_REVIEWED,
                "workspace_href": law_path(law_id),
                "list_href": source_review_path(law_id),
                "read_href": f"/laws/{law_id}",
                "reviewed_href": source_review_reviewed_path_for_locator(loc),
            },
        )

    async def _source_review_mark(
        request: Request,
        law_id: str,
        number: str,
        *,
        unit: str | None,
        csrf_token: str,
        detected_source_version: str,
        detected_law_source_hash: str,
    ):
        overlay = require_playground_repo(request)
        try:
            loc = _source_review_locator(law_id, number, unit)
        except LocatorError:
            raise HTTPException(status_code=404, detail="Source change not found") from None
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=source_review_path_for_locator(loc),
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked
        _require_csrf(request, csrf_token)
        try:
            mark_source_change_reviewed(
                overlay,
                access.user_id,
                law_id,
                loc.value,
                detected_source_version=detected_source_version,
                detected_law_source_hash=detected_law_source_hash,
            )
        except StaleSourceReviewError:
            raise HTTPException(status_code=409, detail="stale_source_review") from None
        except LookupError:
            raise HTTPException(status_code=404, detail="Source change not found") from None
        return RedirectResponse(url=source_review_path(law_id), status_code=303)

    @router.get(
        "/laws/{law_id}/source-review/sections/{number}/u/{unit}",
        response_class=HTMLResponse,
    )
    async def playground_source_review_unit(
        request: Request, law_id: str, number: str, unit: str
    ) -> HTMLResponse:
        return await _source_review_detail(request, law_id, number, unit=unit)

    @router.post("/laws/{law_id}/source-review/sections/{number}/u/{unit}/reviewed")
    async def playground_source_review_mark_unit(
        request: Request,
        law_id: str,
        number: str,
        unit: str,
        csrf_token: str = Form(""),
        detected_source_version: str = Form(""),
        detected_law_source_hash: str = Form(""),
    ) -> Response:
        return await _source_review_mark(
            request,
            law_id,
            number,
            unit=unit,
            csrf_token=csrf_token,
            detected_source_version=detected_source_version,
            detected_law_source_hash=detected_law_source_hash,
        )

    return router
