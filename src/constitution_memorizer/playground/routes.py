"""Playground HTTP surface. Include from the app factory; do not grow app.py."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from constitution_memorizer.playground.access import (
    ensure_playground_item,
    new_law_home_notice,
    require_playground_open,
)
from constitution_memorizer.playground.eligibility import PlaygroundLawError
from constitution_memorizer.playground.http import require_playground_repo
from constitution_memorizer.playground.locators import LocatorError
from constitution_memorizer.playground.service import (
    mark_outdated,
    parse_selected_locator,
    playground_home_cards,
    provision_for_learn,
    require_playground_law,
    selected_locator_set,
    selection_rows,
)
from constitution_memorizer.playground.source import locators_for_act, source_hash
from constitution_memorizer.playground.urls import (
    home_path,
    law_path,
    learn_complete_path,
    learn_path,
    sections_path,
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
        repo = require_playground_repo(request)
        summaries = repo.list_playground_summaries(access.user_id, as_of=date.today())
        cards = playground_home_cards(summaries)
        return templates.TemplateResponse(
            request,
            "playground.html",
            {
                "cards": cards,
                "new_law_notice": new_law_home_notice(request, access),
            },
        )

    @router.post("/laws/{law_id}/add")
    async def playground_add(
        request: Request,
        law_id: str,
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        next_reader = f"/laws/{law_id}"
        opened = require_playground_open(
            request, templates, next_url=next_reader
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        expected = request.cookies.get("rtc_csrf") or ""
        if expected and csrf_token != expected:
            raise HTTPException(status_code=403, detail="csrf")
        repo = require_playground_repo(request)
        existing = repo.get_item(opened.user_id, law_id)
        ensured = ensure_playground_item(
            request, templates, repo, law_id, next_url=next_reader
        )
        blocked_new = _denied(ensured)
        if blocked_new is not None:
            return blocked_new  # type: ignore[return-value]
        if existing is not None and repo.list_selection(ensured.user_id, law_id):
            return RedirectResponse(url=home_path(), status_code=303)
        return RedirectResponse(url=sections_path(law_id), status_code=303)

    @router.get("/laws/{law_id}", response_class=HTMLResponse)
    async def playground_law(request: Request, law_id: str) -> HTMLResponse:
        access = require_playground_open(
            request, templates, next_url=law_path(law_id)
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        repo = require_playground_repo(request)
        item = repo.get_item(access.user_id, law_id)
        if item is None:
            return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        selections = repo.list_selection(access.user_id, law_id)
        progress_map = {
            row.source_locator: mark_outdated(
                row, _section_source_hash(act, row.source_locator, law_id)
            )
            for row in repo.list_progress(access.user_id, law_id)
        }
        rows = []
        for sel in selections:
            loc = parse_selected_locator(sel.source_locator, law_id)
            if loc is None:
                continue
            section = act.section(loc.number)
            if section is None:
                continue
            progress = progress_map.get(sel.source_locator)
            rows.append(
                {
                    "locator": sel.source_locator,
                    "number": loc.number,
                    "title": section.list_title,
                    "progress": progress,
                    "outdated": bool(progress and progress.source_outdated),
                }
            )
        return templates.TemplateResponse(
            request,
            "playground_law.html",
            {"act": act, "item": item, "rows": rows},
        )

    @router.get("/laws/{law_id}/sections", response_class=HTMLResponse)
    async def playground_select_page(request: Request, law_id: str) -> HTMLResponse:
        access = require_playground_open(
            request, templates, next_url=sections_path(law_id)
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        repo = require_playground_repo(request)
        if repo.get_item(access.user_id, law_id) is None:
            return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        selected = selected_locator_set(repo.list_selection(access.user_id, law_id))
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
        opened = require_playground_open(
            request, templates, next_url=sections_path(law_id)
        )
        blocked = _denied(opened)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        form = await request.form()
        csrf_token = str(form.get("csrf_token") or "")
        expected = request.cookies.get("rtc_csrf") or ""
        if expected and csrf_token != expected:
            raise HTTPException(status_code=403, detail="csrf")
        repo = require_playground_repo(request)
        ensured = ensure_playground_item(
            request, templates, repo, law_id, next_url=sections_path(law_id)
        )
        blocked_new = _denied(ensured)
        if blocked_new is not None:
            return blocked_new  # type: ignore[return-value]
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        entire_raw = form.get("entire")
        entire_act = str(entire_raw or "") in {"1", "on", "true", "yes"}
        numbers = [str(value) for value in form.getlist("section")]
        rows = selection_rows(law_id, numbers, entire=entire_act, act=act)
        repo.replace_selection(ensured.user_id, law_id, rows)
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
        access = require_playground_open(
            request, templates, next_url=learn_path(law_id, number, mode)
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        repo = require_playground_repo(request)
        if repo.get_item(access.user_id, law_id) is None:
            return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
        try:
            act = require_playground_law(law_id)
            loc, body, live_hash, source_version, cloze_available = provision_for_learn(
                law_id, number, act=act
            )
        except (PlaygroundLawError, LocatorError):
            raise HTTPException(status_code=404, detail="Section not found") from None
        selected = selected_locator_set(repo.list_selection(access.user_id, law_id))
        if loc.value not in selected:
            return RedirectResponse(url=sections_path(law_id), status_code=303)
        section = act.section(number)
        progress = mark_outdated(
            repo.get_progress(access.user_id, law_id, loc.value), live_hash
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
        access = require_playground_open(
            request,
            templates,
            next_url=learn_path(law_id, number, mode),
            json_mode=True,
        )
        blocked = _denied(access)
        if blocked is not None:
            return blocked  # type: ignore[return-value]
        repo = require_playground_repo(request)
        if repo.get_item(access.user_id, law_id) is None:
            return JSONResponse({"ok": False, "error": "not_activated"}, status_code=400)
        try:
            loc, body, live_hash, source_version, cloze_available = provision_for_learn(
                law_id, number
            )
        except (PlaygroundLawError, LocatorError):
            raise HTTPException(status_code=404, detail="Section not found") from None
        if not cloze_available:
            return JSONResponse({"ok": False, "error": "cloze_unavailable"}, status_code=400)
        selected = selected_locator_set(repo.list_selection(access.user_id, law_id))
        if loc.value not in selected:
            return JSONResponse({"ok": False, "error": "not_selected"}, status_code=400)
        stored = repo.get_progress(access.user_id, law_id, loc.value)
        stored_hash = stored.source_hash if stored is not None else live_hash
        progress = repo.complete_cloze(
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
