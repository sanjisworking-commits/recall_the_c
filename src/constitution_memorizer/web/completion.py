"""Completion affirmation context for Learn Done (validated ``?done=``)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request

from constitution_memorizer.learning.schemas import LearningUnit
from constitution_memorizer.progress.repository import StudySession
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web.quotes import get_quote_for
from constitution_memorizer.web.service import maybe_record_daily_goal_met, needs_split_choice


def wants_json(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    requested = (request.headers.get("x-requested-with") or "").lower()
    return "application/json" in accept or requested == "xmlhttprequest"


def strip_done_param(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "done"]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def with_params(path: str, params: dict[str, str]) -> str:
    """Append query parameters to a path, dropping empty values.

    Hand-built f-string queries were the bug this replaces: a second
    parameter emitted ``?done=x?session=y``, which the next request reads as
    a single ``done`` value.
    """
    query = urlencode({k: v for k, v in params.items() if v})
    return f"{path}?{query}" if query else path


# Landing on a Learn URL with no `mode` shows the phone's six-card mode deck —
# a picker. Inside a revision queue that is one tap of friction per unit, so
# the queue opens its units straight into a mode instead. Read first: it is the
# design's own opening step ("Read it twice, then pick a recall mode"), and it
# needs no extra query to work out, unlike "first mode not yet seen".
def session_entry_mode(kind: str | None = None) -> str:
    """Recall mode to open when hopping to the next queued unit.

    Named for study sessions generally: revision, auto_learning, and day_plan
    all enter Read first so the phone deck is not an extra tap per item.
    """
    return "read"


# Back-compat alias used by older tests/imports.
REVISION_ENTRY_MODE = session_entry_mode("revision")


def next_learn_url(
    eng: ReminderEngine,
    next_unit_id: str | None,
    *,
    done_unit_id: str | None = None,
    multiuser: bool = False,
    session_id: str | None = None,
    mode: str | None = None,
) -> str:
    params = {"done": done_unit_id or ""}
    if next_unit_id and eng.get_unit(next_unit_id):
        nxt = eng.get_unit(next_unit_id)
        assert nxt is not None
        # `session` rides only on Learn URLs; the dashboard has no queue
        # position to keep.
        params["session"] = session_id or ""
        if needs_split_choice(eng, nxt):
            # `mode` is deliberately dropped: on /choose that key means
            # whole-vs-letters, not a recall mode.
            return with_params(f"/learn/{next_unit_id}/choose", params)
        params["mode"] = mode or ""
        return with_params(f"/learn/{next_unit_id}", params)
    if multiuser:
        return with_params("/dashboard", params)
    return with_params("/", params)


@dataclass(frozen=True)
class LearnNavigation:
    """Where Done / Again goes next — resolved once, used by HTML and JSON.

    The HTML redirect and the AJAX payload used to compute this separately
    (the payload from ``result.next_unit_id``), so a fix to one silently left
    the other walking the static Constitution graph.
    """

    next_unit_id: str | None
    next_url: str
    session_id: str | None
    remaining: int


def resolve_learn_navigation(
    *,
    eng: ReminderEngine,
    unit_id: str,
    fallback_next_unit_id: str | None,
    session: StudySession | None,
    outcome: Literal["completed", "deferred"],
    multiuser: bool,
    done_unit_id: str | None = None,
) -> LearnNavigation:
    """Advance the queue if there is one; otherwise keep sequential order.

    Writes the item's terminal status and closes an exhausted session — the
    only place either happens, so "what comes next" and "what was recorded"
    cannot drift apart.
    """
    if session is None or not session.contains(unit_id):
        return LearnNavigation(
            next_unit_id=fallback_next_unit_id,
            next_url=next_learn_url(
                eng,
                fallback_next_unit_id,
                done_unit_id=done_unit_id,
                multiuser=multiuser,
            ),
            session_id=None,
            remaining=0,
        )

    current = session.item_for(unit_id)
    if current is None or current.status == "pending":
        eng.set_study_item_status(
            session_id=session.id, unit_id=unit_id, status=outcome
        )
        items = tuple(
            item if item.learning_unit_id != unit_id else replace(item, status=outcome)
            for item in session.items
        )
        updated = replace(session, items=items)
    else:
        updated = session
    if outcome == "completed":
        maybe_record_daily_goal_met(eng, session=updated)
    next_unit_id = updated.next_pending_after(unit_id)
    if next_unit_id is None:
        if updated.status != "complete":
            eng.complete_study_session(session.id)
        return LearnNavigation(
            next_unit_id=None,
            next_url=with_params(
                "/dashboard" if multiuser else "/",
                {"done": done_unit_id or ""},
            ),
            session_id=session.id,
            remaining=0,
        )
    return LearnNavigation(
        next_unit_id=next_unit_id,
        next_url=next_learn_url(
            eng,
            next_unit_id,
            done_unit_id=done_unit_id,
            multiuser=multiuser,
            session_id=session.id,
            mode=session_entry_mode(session.kind),
        ),
        session_id=session.id,
        remaining=updated.remaining,
    )


def _quote_user_id(request: Request | None) -> str:
    if request is None:
        return str(LOCAL_USER_ID)
    user = getattr(request.state, "current_user", None)
    if user is not None and getattr(user, "id", None) is not None:
        return str(user.id)
    return str(LOCAL_USER_ID)


def _format_review_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _ledger_line(progress: Any) -> str:
    if progress.status == "mastered" or progress.next_revision is None:
        return "No further reviews scheduled"
    return f"Next review · {_format_review_date(progress.next_revision)}"


def build_completion(
    *,
    eng: ReminderEngine,
    quotes: list[dict[str, str]],
    done_id: str | None,
    request: Request | None = None,
    is_guest: bool = False,
    today: date | None = None,
    continue_href: str | None = None,
    continue_label: str | None = None,
) -> dict[str, Any] | None:
    """Return template/JSON context only for a persisted completion today."""
    if not done_id or is_guest:
        return None
    today = today or date.today()
    unit = eng.get_unit(done_id)
    if unit is None:
        return None
    progress = eng.get_progress(done_id)
    if progress is None or progress.last_completed != today or progress.times_completed < 1:
        return None
    uid = _quote_user_id(request)
    seed = f"{uid}:{done_id}:{progress.last_completed}:{progress.times_completed}"
    quote = get_quote_for(quotes, seed)
    mastered = progress.status == "mastered" or progress.next_revision is None
    return {
        "unit_id": done_id,
        "article_ref": unit.display_title,
        "next_review": progress.next_revision,
        "status": progress.status,
        "mastered": mastered,
        "eyebrow": "Mastered" if mastered else "Review complete",
        "ledger": _ledger_line(progress),
        "quote": quote,
        "continue_href": continue_href or strip_done_param(""),
        "continue_label": continue_label,
    }


def done_json_payload(
    *,
    eng: ReminderEngine,
    quotes: list[dict[str, str]],
    unit: LearningUnit,
    result: Any,
    request: Request | None,
    multiuser: bool,
    navigation: LearnNavigation | None = None,
) -> dict[str, Any]:
    progress = result.progress
    # Resolved navigation is authoritative when present — inside a session the
    # next unit is the next QUEUED one, not the sequentially adjacent one.
    if navigation is None:
        navigation = LearnNavigation(
            next_unit_id=result.next_unit_id,
            next_url=next_learn_url(
                eng, result.next_unit_id, done_unit_id=unit.id, multiuser=multiuser
            ),
            session_id=None,
            remaining=0,
        )
    next_url = navigation.next_url
    next_unit = (
        eng.get_unit(navigation.next_unit_id) if navigation.next_unit_id else None
    )
    uid = _quote_user_id(request)
    seed = f"{uid}:{unit.id}:{progress.last_completed}:{progress.times_completed}"
    mastered = progress.status == "mastered" or progress.next_revision is None
    return {
        "ok": True,
        "next_url": next_url,
        "article_ref": unit.display_title,
        "next_review": (
            progress.next_revision.isoformat() if progress.next_revision else None
        ),
        "status": progress.status,
        "quote": get_quote_for(quotes, seed),
        "eyebrow": "Mastered" if mastered else "Review complete",
        "ledger": _ledger_line(progress),
        "continue_label": next_unit.display_title if next_unit is not None else None,
        "session_id": navigation.session_id,
        "session_remaining": navigation.remaining,
    }


def caught_up_quote(quotes: list[dict[str, str]], today: date | None = None) -> dict[str, str] | None:
    today = today or date.today()
    return get_quote_for(quotes, today.isoformat())
