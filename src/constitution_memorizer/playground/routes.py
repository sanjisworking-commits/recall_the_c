"""Playground HTTP surface. Include from the app factory; do not grow app.py."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from constitution_memorizer.playground.access import (
    consume_blocked_response,
    is_add_confirmed,
    new_law_home_notice,
    require_eligible_law,
    require_law_active_this_period,
    require_playground_open,
)
from constitution_memorizer.playground.eligibility import (
    PlaygroundLawError,
    playground_catalogue_law,
)
from constitution_memorizer.playground.http import (
    require_playground_repo,
    require_roster_service,
)
from constitution_memorizer.playground.locators import LocatorError
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
from constitution_memorizer.playground.service import (
    activate_law,
    mark_outdated,
    parse_selected_locator,
    provision_for_learn,
    require_playground_law,
    selected_locator_set,
    selection_rows,
)
from constitution_memorizer.playground.source import canonical_body_text, locators_for_act, source_hash
from constitution_memorizer.playground.urls import (
    add_path,
    home_path,
    law_path,
    learn_complete_path,
    learn_path,
    roster_next_path,
    roster_path,
    sections_path,
)
from constitution_memorizer.playground.view import (
    add_confirm_copy,
    build_home_view,
    capacity_view,
    catalog_titles,
    section_row_view,
)

SUPPORTED_LEARN_MODE = "cloze"


def _section_source_hash(act, locator: str, law_id: str) -> str:
    loc = parse_selected_locator(locator, law_id)
    if loc is None:
        return ""
    section = act.section(loc.number)
    if section is None:
        return ""
    return source_hash(section)


def _denied(result: object) -> Response | None:
    if isinstance(result, Response):
        return result
    return None


def _require_csrf(request: Request, csrf_token: str) -> None:
    expected = request.cookies.get("rtc_csrf") or ""
    if expected and csrf_token != expected:
        raise HTTPException(status_code=403, detail="csrf")


def _after_active_redirect(overlay, user_id, law_id: str) -> RedirectResponse:
    if overlay.get_item(user_id, law_id) is not None and overlay.list_selection(
        user_id, law_id
    ):
        return RedirectResponse(url=law_path(law_id), status_code=303)
    return RedirectResponse(url=sections_path(law_id), status_code=303)


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


def _roster_law_card(item) -> dict:
    catalog = playground_catalogue_law(item.law_id)
    title = catalog.title if catalog is not None else item.law_id
    short = catalog.short_title if catalog is not None else item.law_id
    return {
        "law_id": item.law_id,
        "title": title,
        "short_title": short,
        "origin": item.origin,
        "removed": item.removed_at is not None,
    }


def create_playground_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/playground")

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def playground_home(request: Request) -> HTMLResponse:
        access = require_playground_open(
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
        active_cards = [
            _roster_law_card(item) for item in roster.active_roster_items(access.user_id)
        ]
        removed_cards = [
            _roster_law_card(item) for item in roster.removed_roster_items(access.user_id)
        ]
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
            overlay = require_playground_repo(request)
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
        opened = require_playground_open(
            request, templates, next_url=add_path(law_id)
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked
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
        if preview.status == RESULT_ALREADY_ACTIVE:
            return _after_active_redirect(overlay, opened.user_id, law_id)
        capacity = roster.capacity(
            opened.user_id,
            opened.snapshot,
            local_owner=opened.local_owner,
        )
        month = playground_month_name(capacity.period_start)
        _long, short = catalog_titles(law_id)
        del _long
        historical = overlay.get_item(opened.user_id, law_id) is not None
        re_add = preview.status == RESULT_RE_ADD_CONFIRM
        remaining_after = capacity.remaining
        if preview.status == RESULT_NEEDS_CONFIRM and remaining_after is not None:
            remaining_after = max(0, remaining_after - 1)
        confirm_title, confirm_lines = add_confirm_copy(
            short_title=short,
            month_name=month,
            law_limit=capacity.law_limit,
            remaining_after=remaining_after,
            historical=historical and not re_add,
            re_add=re_add,
        )
        blocked_pending = preview.status == RESULT_NEW_BLOCKED
        blocked_full = preview.status == RESULT_ROSTER_FULL
        if blocked_pending:
            confirm_title = "Adding new laws is temporarily unavailable"
            confirm_lines = (
                "You can continue your current Playground.",
                "Adding new laws is temporarily unavailable.",
            )
        if blocked_full:
            confirm_title = "Playground full this month"
            confirm_lines = (
                "Existing laws remain fully usable.",
                "Removing a law does not free a space this month.",
            )
        return templates.TemplateResponse(
            request,
            "playground_add.html",
            {
                "law_id": law_id,
                "title": confirm_title,
                "lines": confirm_lines,
                "month_name": month,
                "action_label": "Add back" if re_add else "Add to Playground",
                "confirm_value": ROSTER_ADD_CONFIRM,
                "cancel_href": home_path(),
                "blocked_pending": blocked_pending,
                "blocked_full": blocked_full,
            },
        )

    @router.post("/laws/{law_id}/add")
    async def playground_add(
        request: Request,
        law_id: str,
        csrf_token: str = Form(""),
        confirm: str = Form(""),
    ) -> RedirectResponse:
        next_reader = f"/laws/{law_id}"
        opened = require_playground_open(
            request, templates, next_url=next_reader
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
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
        if preview.status == RESULT_ALREADY_ACTIVE:
            return _after_active_redirect(overlay, opened.user_id, law_id)
        if not is_add_confirmed(confirm):
            if preview.status == RESULT_NEW_BLOCKED:
                denied = consume_blocked_response(
                    request, templates, opened, RESULT_NEW_BLOCKED
                )
                return denied  # type: ignore[return-value]
            return RedirectResponse(url=roster_path(add=law_id), status_code=303)
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
            return denied  # type: ignore[return-value]
        activate_law(overlay, opened.user_id, law_id)
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
        selections = overlay.list_selection(access.user_id, law_id)
        progress_map = {
            row.source_locator: mark_outdated(
                row, _section_source_hash(act, row.source_locator, law_id)
            )
            for row in overlay.list_progress(access.user_id, law_id)
        }
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
            section = act.section(loc.number)
            if section is None:
                continue
            progress = progress_map.get(sel.source_locator)
            rows.append(
                section_row_view(
                    number=loc.number,
                    title=section.list_title,
                    locator=sel.source_locator,
                    progress=progress,
                    outdated=bool(progress and progress.source_outdated),
                    as_of=as_of,
                    law_id=law_id,
                )
            )
        launch = None
        for row in rows:
            if row["due"]:
                launch = row
                break
        if launch is None and rows:
            launch = rows[0]
        launch_verbatim = ""
        if launch is not None:
            section = act.section(launch["number"])
            if section is not None:
                launch_verbatim = canonical_body_text(section)
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
        selected = selected_locator_set(overlay.list_selection(access.user_id, law_id))
        learnable = {loc.value for loc in locators_for_act(law_id, act=act)}
        sections = []
        for section in act.section_order:
            loc = f"{law_id}:section:{section.number}"
            sections.append(
                {
                    "number": section.number,
                    "title": section.list_title,
                    "omitted": section.is_omitted,
                    "learnable": loc in learnable,
                    "checked": loc in selected,
                }
            )
        return templates.TemplateResponse(
            request,
            "playground_select.html",
            {
                "act": act,
                "sections": sections,
                "entire_checked": bool(selected) and selected == learnable,
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
        if overlay.get_item(opened.user_id, law_id) is None:
            activate_law(overlay, opened.user_id, law_id)
        entire_raw = form.get("entire")
        entire_act = str(entire_raw or "") in {"1", "on", "true", "yes"}
        numbers = [str(value) for value in form.getlist("section")]
        rows = selection_rows(law_id, numbers, entire=entire_act, act=act)
        overlay.replace_selection(opened.user_id, law_id, rows)
        return RedirectResponse(url=law_path(law_id), status_code=303)

    @router.get(
        "/laws/{law_id}/sections/{number}/learn/{mode}",
        response_class=HTMLResponse,
    )
    async def playground_learn(
        request: Request, law_id: str, number: str, mode: str
    ) -> HTMLResponse:
        if mode != SUPPORTED_LEARN_MODE:
            raise HTTPException(status_code=404, detail="Learn mode not found")
        overlay = require_playground_repo(request)
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=learn_path(law_id, number, mode),
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        try:
            act = require_playground_law(law_id)
            loc, body, live_hash, source_version, cloze_available = provision_for_learn(
                law_id, number, act=act
            )
        except (PlaygroundLawError, LocatorError):
            raise HTTPException(status_code=404, detail="Section not found") from None
        selected = selected_locator_set(overlay.list_selection(access.user_id, law_id))
        if loc.value not in selected:
            return RedirectResponse(url=sections_path(law_id), status_code=303)
        section = act.section(number)
        progress = mark_outdated(
            overlay.get_progress(access.user_id, law_id, loc.value), live_hash
        )
        return templates.TemplateResponse(
            request,
            "playground_cloze.html",
            {
                "act": act,
                "section": section,
                "locator": loc.value,
                "canonical_body": body,
                "cloze_available": cloze_available,
                "progress": progress,
                "source_outdated": bool(progress and progress.source_outdated),
                "source_version": source_version,
                "complete_url": learn_complete_path(law_id, number, mode),
            },
        )

    @router.post("/laws/{law_id}/sections/{number}/learn/{mode}/complete")
    async def playground_cloze_complete(
        request: Request, law_id: str, number: str, mode: str
    ) -> JSONResponse:
        if mode != SUPPORTED_LEARN_MODE:
            raise HTTPException(status_code=404, detail="Learn mode not found")
        overlay = require_playground_repo(request)
        access = require_law_active_this_period(
            request,
            templates,
            overlay,
            law_id,
            next_url=learn_path(law_id, number, mode),
            json_mode=True,
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        try:
            loc, body, live_hash, source_version, cloze_available = provision_for_learn(
                law_id, number
            )
        except (PlaygroundLawError, LocatorError):
            raise HTTPException(status_code=404, detail="Section not found") from None
        if not cloze_available:
            return JSONResponse({"ok": False, "error": "cloze_unavailable"}, status_code=400)
        selected = selected_locator_set(overlay.list_selection(access.user_id, law_id))
        if loc.value not in selected:
            return JSONResponse({"ok": False, "error": "not_selected"}, status_code=400)
        stored = overlay.get_progress(access.user_id, law_id, loc.value)
        stored_hash = stored.source_hash if stored is not None else live_hash
        progress = overlay.complete_cloze(
            access.user_id,
            law_id,
            loc.value,
            source_version=source_version,
            source_hash=stored_hash,
            as_of=date.today(),
            live_hash=live_hash,
        )
        return JSONResponse(
            {
                "ok": True,
                "canonical_body": body,
                "source_locator": progress.source_locator,
                "status": progress.status,
                "interval_days": progress.interval_days,
                "next_revision": progress.next_revision,
                "source_outdated": progress.source_outdated,
                "revealed": body,
            }
        )

    return router
