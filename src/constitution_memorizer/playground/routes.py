"""Playground HTTP surface. Include from the app factory; do not grow app.py."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from constitution_memorizer.playground.eligibility import PlaygroundLawError
from constitution_memorizer.playground.http import (
    playground_login_redirect,
    playground_user_id,
    require_playground_repo,
)
from constitution_memorizer.playground.locators import LocatorError
from constitution_memorizer.playground.service import (
    activate_law,
    due_revision_count,
    live_source_hash,
    mark_outdated,
    parse_selected_locator,
    provision_for_learn,
    require_playground_law,
    selected_locator_set,
    selection_rows,
)
from constitution_memorizer.playground.source import locators_for_act
from constitution_memorizer.playground.urls import (
    home_path,
    law_path,
    learn_complete_path,
    learn_path,
    sections_path,
)

SUPPORTED_LEARN_MODE = "cloze"


def create_playground_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/playground")

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def playground_home(request: Request) -> HTMLResponse:
        uid = playground_user_id(request)
        if uid is None:
            return playground_login_redirect(home_path())
        repo = require_playground_repo(request)
        today = date.today()
        cards = []
        for item in repo.list_items(uid):
            try:
                act = require_playground_law(item.law_id)
            except PlaygroundLawError:
                continue
            selections = repo.list_selection(uid, item.law_id)
            progress_rows = [
                mark_outdated(row, live_source_hash(item.law_id, row.source_locator))
                for row in repo.list_progress(uid, item.law_id)
            ]
            progress_rows = [row for row in progress_rows if row is not None]
            selected = selected_locator_set(selections)
            learned = {
                row.source_locator
                for row in progress_rows
                if row.cloze_done and row.source_locator in selected
            }
            to_learn = len(selected - learned)
            cards.append(
                {
                    "item": item,
                    "act": act,
                    "selected_count": len(selections),
                    "to_learn": to_learn,
                    "due": due_revision_count(
                        [row for row in progress_rows if row.source_locator in selected],
                        today,
                    ),
                    "outdated": any(
                        row.source_outdated and row.source_locator in selected
                        for row in progress_rows
                    ),
                }
            )
        return templates.TemplateResponse(
            request,
            "playground.html",
            {"cards": cards},
        )

    @router.post("/laws/{law_id}/add")
    async def playground_add(
        request: Request,
        law_id: str,
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        uid = playground_user_id(request)
        next_reader = f"/laws/{law_id}"
        if uid is None:
            return playground_login_redirect(next_reader)
        expected = request.cookies.get("rtc_csrf") or ""
        if expected and csrf_token != expected:
            raise HTTPException(status_code=403, detail="csrf")
        try:
            require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        repo = require_playground_repo(request)
        existing = repo.get_item(uid, law_id)
        activate_law(repo, uid, law_id)
        if existing is not None and repo.list_selection(uid, law_id):
            return RedirectResponse(url=home_path(), status_code=303)
        return RedirectResponse(url=sections_path(law_id), status_code=303)

    @router.get("/laws/{law_id}", response_class=HTMLResponse)
    async def playground_law(request: Request, law_id: str) -> HTMLResponse:
        uid = playground_user_id(request)
        if uid is None:
            return playground_login_redirect(law_path(law_id))
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        repo = require_playground_repo(request)
        item = repo.get_item(uid, law_id)
        if item is None:
            return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
        selections = repo.list_selection(uid, law_id)
        progress_map = {
            row.source_locator: mark_outdated(
                row, live_source_hash(law_id, row.source_locator)
            )
            for row in repo.list_progress(uid, law_id)
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
        uid = playground_user_id(request)
        if uid is None:
            return playground_login_redirect(sections_path(law_id))
        try:
            act = require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        repo = require_playground_repo(request)
        if repo.get_item(uid, law_id) is None:
            return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
        selected = selected_locator_set(repo.list_selection(uid, law_id))
        learnable = {loc.value for loc in locators_for_act(law_id)}
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
        uid = playground_user_id(request)
        if uid is None:
            return playground_login_redirect(sections_path(law_id))
        form = await request.form()
        csrf_token = str(form.get("csrf_token") or "")
        expected = request.cookies.get("rtc_csrf") or ""
        if expected and csrf_token != expected:
            raise HTTPException(status_code=403, detail="csrf")
        try:
            require_playground_law(law_id)
        except PlaygroundLawError:
            raise HTTPException(status_code=404, detail="Law not found") from None
        repo = require_playground_repo(request)
        if repo.get_item(uid, law_id) is None:
            activate_law(repo, uid, law_id)
        entire_raw = form.get("entire")
        entire_act = str(entire_raw or "") in {"1", "on", "true", "yes"}
        numbers = [str(value) for value in form.getlist("section")]
        rows = selection_rows(law_id, numbers, entire=entire_act)
        repo.replace_selection(uid, law_id, rows)
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
        uid = playground_user_id(request)
        if uid is None:
            return playground_login_redirect(learn_path(law_id, number, mode))
        try:
            act = require_playground_law(law_id)
            loc, body, live_hash, source_version, cloze_available = provision_for_learn(
                law_id, number
            )
        except (PlaygroundLawError, LocatorError):
            raise HTTPException(status_code=404, detail="Section not found") from None
        repo = require_playground_repo(request)
        if repo.get_item(uid, law_id) is None:
            return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
        selected = selected_locator_set(repo.list_selection(uid, law_id))
        if loc.value not in selected:
            return RedirectResponse(url=sections_path(law_id), status_code=303)
        section = act.section(number)
        progress = mark_outdated(repo.get_progress(uid, law_id, loc.value), live_hash)
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
        uid = playground_user_id(request)
        if uid is None:
            return JSONResponse({"ok": False, "error": "auth_required"}, status_code=401)
        try:
            loc, body, live_hash, source_version, cloze_available = provision_for_learn(
                law_id, number
            )
        except (PlaygroundLawError, LocatorError):
            raise HTTPException(status_code=404, detail="Section not found") from None
        if not cloze_available:
            return JSONResponse({"ok": False, "error": "cloze_unavailable"}, status_code=400)
        repo = require_playground_repo(request)
        if repo.get_item(uid, law_id) is None:
            return JSONResponse({"ok": False, "error": "not_activated"}, status_code=400)
        selected = selected_locator_set(repo.list_selection(uid, law_id))
        if loc.value not in selected:
            return JSONResponse({"ok": False, "error": "not_selected"}, status_code=400)
        stored = repo.get_progress(uid, law_id, loc.value)
        stored_hash = stored.source_hash if stored is not None else live_hash
        progress = repo.complete_cloze(
            uid,
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
