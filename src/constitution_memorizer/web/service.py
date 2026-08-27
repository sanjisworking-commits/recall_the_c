"""Home / learn navigation helpers over ReminderEngine."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.repository import (
    LEARN_MODES,
    LEARN_MODES_SET,
    StudySession,
)
from constitution_memorizer.progress.scheduler import ReminderEngine

logger = logging.getLogger(__name__)

_CHIP_LABEL_RE = re.compile(r"\([^)]+\)")

REVISION_KIND = "revision"
AUTO_LEARNING_KIND = "auto_learning"
DAY_PLAN_KIND = "day_plan"
LEARNING_SESSION_KINDS = frozenset((AUTO_LEARNING_KIND, DAY_PLAN_KIND))
USER_TIMEZONE_KEY = "user_timezone"


def user_today(engine: ReminderEngine) -> date:
    """The user's local calendar date for schedule anchoring.

    With a stored IANA ``user_timezone`` the revision ladder anchors on the
    USER'S today, not the server's — a 00:30 IST completion lands on the IST
    date even though Railway's clock still reads yesterday (UTC). Unset or
    invalid → the historical server-local behavior.

    Every date that has to agree with a completion goes through here: the
    ladder anchor, a session's ``plan_date``, and the dashboard's decision
    about which hero to show. Otherwise they disagree across midnight.
    """
    tz_name = ""
    try:
        tz_name = engine.get_setting(USER_TIMEZONE_KEY) or ""
    except Exception:  # noqa: BLE001 — anchoring must never break Done
        pass
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except (KeyError, ValueError):
            pass
    return date.today()


# Deploys and migrations are separate manual steps in this project (the start
# command does not run Alembic), so there is always a window where new code is
# live against an older schema. Today must survive that window: a revision
# session is optional context, and the whole dashboard failing to build because
# an optional table is absent is a far worse outcome than showing no session.
# Narrow on purpose — anything that is not a missing relation/column still raises.
#
# Migration 0015 is one bundle: auto_plan_* tables AND
# user_learning_plan.target_effective_on. Code at #155 against a 0014
# database fails first on
# the column (named SELECT in get_learning_plan) before auto_plan_day is
# queried. The guard must recognize both.
_OPTIONAL_TABLES = frozenset(
    {
        "study_session",
        "user_learning_plan",
        "auto_plan_day",
        "auto_plan_item",
    }
)
_OPTIONAL_COLUMNS = frozenset({"target_effective_on"})


def _is_missing_optional_schema(error: Exception) -> bool:
    """True only for a known optional table or the 0015 audit column missing.

    Table errors: a known table identifier plus ``does not exist`` /
    ``no such table``. Column errors: ``target_effective_on`` plus a
    missing-column phrasing. Unrelated UndefinedColumn / UndefinedTable,
    connection, constraint, and syntax errors still raise.
    """
    message = str(error).lower()
    missing_column = "no such column" in message or (
        "column" in message and "does not exist" in message
    )
    if missing_column:
        return any(name in message for name in _OPTIONAL_COLUMNS)
    missing_table = "no such table" in message or (
        "does not exist" in message and "column" not in message
    )
    if not missing_table:
        return False
    return any(name in message for name in _OPTIONAL_TABLES)


def active_revision_session(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> StudySession | None:
    """Today's active revision session, if one is under way.

    Scoped to ``plan_date`` so yesterday's abandoned queue — built from due
    dates that have since moved — never resurfaces as today's work.

    Returns None when the study-session tables have not been migrated yet;
    the caller then renders Today exactly as it did before sessions existed,
    and starts working the moment the migration lands.
    """
    today = as_of or user_today(engine)
    try:
        return engine.active_study_session(kind=REVISION_KIND, plan_date=today)
    except Exception as error:  # noqa: BLE001 — re-raised unless it is the schema gap
        if not _is_missing_optional_schema(error):
            raise
        logger.warning(
            "study_session tables are missing; Today is falling back to the "
            "pre-session view. Run `alembic upgrade head` against this database."
        )
        return None


def start_or_resume_revision(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> StudySession | None:
    """Resume today's revision session, or snapshot the due list into a new one.

    Idempotent by construction: a double-tapped CTA resumes rather than
    duplicating, and a mid-session refresh keeps walking the original
    snapshot even though completing an item pushed its ``next_revision``
    forward and shrank the live due list.
    """
    today = as_of or user_today(engine)
    existing = active_revision_session(engine, as_of=today)
    if existing is not None:
        return existing
    unit_ids = [unit.id for unit in due_checklist(engine, as_of=today)]
    if not unit_ids:
        return None
    return engine.create_study_session(
        session_id=uuid.uuid4().hex,
        kind=REVISION_KIND,
        plan_date=today,
        unit_ids=unit_ids,
    )


def revision_position_label(session: StudySession, unit_id: str) -> str | None:
    """"Revision 2 of 6" / "Learning 2 of 5" — walk position, not lifetime mastery."""
    position = session.position_of(unit_id)
    if position is None or not session.items:
        return None
    if session.kind == REVISION_KIND:
        return f"Revision {position} of {len(session.items)}"
    return f"Learning {position} of {len(session.items)}"


def maybe_activate_auto_plan(engine: ReminderEngine, *, as_of: date) -> None:
    """Write activated_at on first persisted NEW Done while Auto is selected."""
    try:
        plan = engine.get_learning_plan()
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise
        return
    if plan.mode != "auto" or plan.activated_at is not None:
        return
    engine.activate_learning_plan(as_of)


def ensure_auto_roadmap(
    engine: ReminderEngine,
    *,
    as_of: date,
    auto_entitled: bool,
    claimed: set[str] | None = None,
    remaining_slots: int | None = None,
    entitlements_on: bool = False,
    force: bool = False,
) -> None:
    """Reconcile the rolling 15-day Auto window if Auto is selected.

    Read paths (Calendar / Dashboard GET) pass ``force=False`` and skip the
    durable rewrite when the persisted day coverage is already current.
    Write paths that change occupancy (Done, Skip, Again, target, split)
    pass ``force=True``.

    GET may still reconcile once when the window is genuinely stale: local
    day rollover needing a tail day, missing roadmap, target mismatch on
    mutable days, leftover rows beyond the horizon, or 0015 just landed.
    An ``auto_plan_day`` with zero items is valid and is not treated as stale.
    """
    from time import perf_counter

    from constitution_memorizer.planner.roadmap import (
        auto_roadmap_needs_reconcile,
        reconcile_auto_roadmap,
    )
    from constitution_memorizer.web.request_context import record_request_timing

    try:
        plan = engine.get_learning_plan()
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise
        return
    try:
        if not force and not auto_roadmap_needs_reconcile(
            engine,
            plan,
            as_of=as_of,
            auto_entitled=auto_entitled,
        ):
            return
        started = perf_counter()
        reconcile_auto_roadmap(
            engine,
            plan,
            as_of=as_of,
            auto_entitled=auto_entitled,
            claimed=claimed,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
        )
        record_request_timing("roadmap_sync", started)
    except Exception as error:  # noqa: BLE001
        if not _is_missing_optional_schema(error):
            raise


REVISION_INTENT_PRACTICE = "practice"
REVISION_INTENT_CONSUME = "consume"
VALID_REVISION_INTENTS = frozenset((REVISION_INTENT_PRACTICE, REVISION_INTENT_CONSUME))


def _progress_row(engine: ReminderEngine, unit_id: str):
    """Single-unit progress without forcing a list_all_progress preload."""
    cache = getattr(engine, "_progress_cache", None)
    if cache is not None:
        return cache.get(unit_id)
    return engine.repo.get_progress(engine.user_id, unit_id)


def early_revision_due(
    engine: ReminderEngine, unit_id: str, *, as_of: date
) -> date | None:
    """Scheduled due date when this unit is a not-yet-due review, else None."""
    progress = _progress_row(engine, unit_id)
    if progress is None or progress.status != "review":
        return None
    if progress.next_revision is None or progress.next_revision <= as_of:
        return None
    return progress.next_revision


def parse_revision_intent(raw: object) -> str | None:
    value = str(raw or "").strip().lower()
    if value in VALID_REVISION_INTENTS:
        return value
    return None


def may_persist_revision_modes(
    engine: ReminderEngine,
    unit_id: str,
    *,
    as_of: date,
    intent: str | None,
) -> bool:
    """False when an early review visit must not write persisted modes_seen."""
    if early_revision_due(engine, unit_id, as_of=as_of) is None:
        return True
    return intent == REVISION_INTENT_CONSUME


def persist_session_anchor_theme(engine: ReminderEngine, unit_ids: list[str]) -> None:
    """Record last_anchor_theme only when today's Auto session is created."""
    if not unit_ids:
        return
    from constitution_memorizer.planner.relationships import candidates_from_units

    unit = engine.get_unit(unit_ids[0])
    if unit is None:
        return
    mix = candidates_from_units([unit])
    if mix:
        try:
            engine.set_last_anchor_theme(mix[0].primary_theme)
        except Exception:  # noqa: BLE001
            pass


def start_or_resume_learning(
    engine: ReminderEngine,
    *,
    kind: str,
    unit_ids: list[str],
    as_of: date | None = None,
) -> StudySession | None:
    """Resume today's learning session, or snapshot ``unit_ids`` once.

    Opening Start does not activate Auto Plan. The snapshot is durable: a
    refresh walks the same list.
    """
    today = as_of or user_today(engine)
    existing = engine.active_study_session(kind=kind, plan_date=today)  # type: ignore[arg-type]
    if existing is not None:
        return existing
    if not unit_ids:
        return None
    return engine.create_study_session(
        session_id=uuid.uuid4().hex,
        kind=kind,  # type: ignore[arg-type]
        plan_date=today,
        unit_ids=unit_ids,
    )


def select_today_mix(
    engine: ReminderEngine,
    *,
    target: int,
    as_of: date,
    claimed: set[str] | None = None,
    remaining_slots: int | None = None,
    entitlements_on: bool = False,
    rng=None,
) -> list[str]:
    from constitution_memorizer.planner.eligibility import (
        article_slot_policy,
        eligible_candidates,
    )
    from constitution_memorizer.planner.selector import LearningMixSelector

    candidates = eligible_candidates(
        engine,
        as_of=as_of,
        claimed=claimed,
        remaining_slots=remaining_slots,
        entitlements_on=entitlements_on,
    )
    allow = article_slot_policy(
        claimed=claimed or set(),
        remaining_slots=0 if remaining_slots is None else remaining_slots,
        entitlements_on=entitlements_on,
    )
    recent_theme = None
    try:
        recent_theme = engine.get_learning_plan().last_anchor_theme
    except Exception:  # noqa: BLE001
        recent_theme = None
    mix = LearningMixSelector().select(
        candidates,
        target,
        rng=rng,
        allow=allow,
        recent_theme=recent_theme,
    )
    if mix:
        try:
            engine.set_last_anchor_theme(mix[0].primary_theme)
        except Exception:  # noqa: BLE001
            pass
    return [item.id for item in mix]


@dataclass(frozen=True)
class SiblingChip:
    """One chip in the Learn sibling / letter rail."""

    unit_id: str
    label: str
    state: str  # current | done | idle


def unit_visible_for_preference(engine: ReminderEngine, unit: LearningUnit) -> bool:
    """Hide clause-or-letter units that conflict with the chosen split mode."""
    if unit.type == LearningUnitType.SUBCLAUSE and unit.parent_clause_id:
        mode = engine.get_split_preference(unit.parent_clause_id) or "whole"
        return mode == "letters"
    if unit.allows_letter_split:
        mode = engine.get_split_preference(unit.id) or "whole"
        if mode == "letters":
            return False
    return True


def resolve_learn_target(engine: ReminderEngine, unit_id: str) -> str:
    """
    Map a requested unit id to the concrete learn target.

    Split-capable clauses with no preference should be handled by the choose route
    before calling this.
    """
    unit = engine.get_unit(unit_id)
    if unit is None:
        return unit_id
    if unit.allows_letter_split:
        mode = engine.get_split_preference(unit.id) or "whole"
        if mode == "letters":
            return engine.next_to_learn_from_clause(unit.id) or unit_id
    return unit_id


def needs_split_choice(engine: ReminderEngine, unit: LearningUnit) -> bool:
    return bool(
        unit.allows_letter_split
        and engine.get_split_preference(unit.id) is None
    )


def due_checklist(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> list[LearningUnit]:
    """Due review units, filtered by split preferences (no Part Overview)."""
    today = as_of or date.today()
    items: list[LearningUnit] = []
    for record in engine.due_today(as_of=today):
        unit = engine.get_unit(record.learning_unit_id)
        if unit is None:
            continue
        if unit.type == LearningUnitType.PART_OVERVIEW:
            continue
        if not unit_visible_for_preference(engine, unit):
            continue
        items.append(unit)
    return items


def continue_unit_id(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> str | None:
    """First non-mastered chain unit, skipping Part Overview; respects letter prefs."""
    today = as_of or date.today()
    chain = sorted(
        (u for u in engine.units.values() if u.revision_order > 0),
        key=lambda u: u.revision_order,
    )
    for unit in chain:
        if unit.type == LearningUnitType.PART_OVERVIEW:
            continue
        if not unit_visible_for_preference(engine, unit):
            continue
        target_id = unit.id
        if unit.allows_letter_split:
            mode = engine.get_split_preference(unit.id)
            if mode is None:
                return unit.id  # send to choose via /learn
            if mode == "letters":
                target_id = engine.next_to_learn_from_clause(unit.id) or unit.id
                target = engine.get_unit(target_id)
                if target is None:
                    continue
                unit = target

        progress = engine.get_progress(unit.id)
        if progress is None or progress.status == "new":
            return unit.id
        if progress.status == "mastered":
            continue
        if (
            progress.status == "review"
            and progress.next_revision is not None
            and progress.next_revision <= today
        ):
            return unit.id
        # In review but not yet due — keep scanning for a new unit further along.
        if progress.status == "review":
            continue
    return None


def unit_type_label(unit: LearningUnit) -> str:
    return unit.type.value if isinstance(unit.type, LearningUnitType) else str(unit.type)


def earliest_upcoming_revision(
    engine: ReminderEngine,
    *,
    as_of: date | None = None,
) -> date | None:
    """Soonest next_revision strictly after as_of (for Home 'caught up' copy)."""
    today = as_of or date.today()
    upcoming: list[date] = []
    for record in engine.repo.list_all_progress(engine.user_id):
        if record.status != "review" or record.next_revision is None:
            continue
        nxt = record.next_revision
        if not isinstance(nxt, date):
            nxt = date.fromisoformat(str(nxt)[:10])
        if nxt > today:
            upcoming.append(nxt)
    return min(upcoming) if upcoming else None


def home_lede(*, due_count: int, has_continue: bool) -> str:
    if due_count == 1:
        return "1 unit due for review."
    if due_count > 1:
        return f"{due_count} units due for review."
    if has_continue:
        return "Nothing due today — continue along the Constitution."
    return "Nothing due today."


def part_label_from_tags(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        if tag.lower().startswith("part "):
            return tag
    return None


def kind_badge_label(unit: LearningUnit) -> str:
    """Prototype badge: Article / Clause / Subclause (not enum SCREAMING)."""
    raw = unit_type_label(unit)
    mapping = {
        "ARTICLE": "Article",
        "CLAUSE": "Clause",
        "SUBCLAUSE": "Subclause",
        "PART_OVERVIEW": "Part",
        "SCHEDULE_ENTRY": "Schedule",
    }
    return mapping.get(raw, raw.replace("_", " ").title())


def unit_crumb(unit: LearningUnit) -> str:
    """Breadcrumb under the type badge (Part · Article …)."""
    parts: list[str] = []
    part = part_label_from_tags(unit.tags)
    if part:
        parts.append(part)
    title = (unit.title or "").strip()
    if unit.type == LearningUnitType.SUBCLAUSE and unit.article_number:
        parts.append(f"Article {unit.article_number}")
        if title:
            parts.append(title)
    elif unit.type == LearningUnitType.CLAUSE and unit.article_number:
        art = f"Article {unit.article_number}"
        if title:
            parts.append(f"{art} — {title}")
        else:
            parts.append(art)
    elif title and unit.type == LearningUnitType.ARTICLE:
        # Title already shown as lede; crumb stays Part-only when possible.
        pass
    elif title and not parts:
        parts.append(title)
    return " · ".join(parts)


def session_progress(
    engine: ReminderEngine,
    unit: LearningUnit,
) -> tuple[int, int, int]:
    """
    Return (completed_count, position_1based, chain_length) for the global
    revision chain (units with revision_order > 0).
    """
    chain = sorted(
        (u for u in engine.units.values() if u.revision_order > 0),
        key=lambda u: u.revision_order,
    )
    if not chain:
        return 0, 1, 1
    completed = 0
    position = 1
    for index, item in enumerate(chain, start=1):
        progress = engine.get_progress(item.id)
        if progress is not None and progress.status == "mastered":
            completed += 1
        if item.id == unit.id:
            position = index
    return completed, position, len(chain)


def learn_meta_line(
    unit: LearningUnit,
    progress: object | None,
) -> str:
    """Quiet footer meta: status · time · difficulty."""
    status = "new"
    if progress is not None:
        status = getattr(progress, "status", None) or "new"
        times = getattr(progress, "times_completed", 0) or 0
        nxt = getattr(progress, "next_revision", None)
        if status == "review" and times:
            bit = f"review · completed {times}×"
            if nxt is not None:
                bit += f" · next {nxt}"
            return (
                f"{bit} · ~{unit.estimated_learning_time}s · "
                f"difficulty {unit.difficulty}/5"
            )
        if status == "mastered":
            return (
                f"mastered · ~{unit.estimated_learning_time}s · "
                f"difficulty {unit.difficulty}/5"
            )
    return (
        f"{status} · ~{unit.estimated_learning_time}s · "
        f"difficulty {unit.difficulty}/5"
    )


def chip_label(unit: LearningUnit) -> str:
    """Clause/letter chip text from display_title — last `(…)` group."""
    matches = _CHIP_LABEL_RE.findall(unit.display_title)
    if matches:
        return matches[-1]
    return unit.display_title


def _chip_state(
    engine: ReminderEngine,
    *,
    unit_id: str,
    current_id: str,
    mark_done: bool,
) -> str:
    if unit_id == current_id:
        return "current"
    if mark_done:
        progress = engine.get_progress(unit_id)
        if progress is not None and progress.status in {"mastered", "review"}:
            return "done"
        if progress is not None and (progress.times_completed or 0) > 0:
            return "done"
    return "idle"


def sibling_chips(
    engine: ReminderEngine,
    unit: LearningUnit,
) -> list[SiblingChip]:
    """
    Learn rail chips.

    - CLAUSE: sibling numbered clauses of the same article (shown when >1)
    - SUBCLAUSE: letter children of the parent clause
    """
    siblings: list[LearningUnit] = []
    mark_done = False

    if unit.type == LearningUnitType.CLAUSE and unit.article_number:
        siblings = sorted(
            (
                u
                for u in engine.units.values()
                if u.type == LearningUnitType.CLAUSE
                and u.article_number == unit.article_number
            ),
            key=lambda u: (u.revision_order, u.display_title),
        )
    elif unit.type == LearningUnitType.SUBCLAUSE and unit.parent_clause_id:
        mark_done = True
        parent = engine.get_unit(unit.parent_clause_id)
        if parent is not None:
            for child_id in parent.child_unit_ids:
                child = engine.get_unit(child_id)
                if child is not None:
                    siblings.append(child)

    if len(siblings) <= 1:
        return []

    return [
        SiblingChip(
            unit_id=item.id,
            label=chip_label(item),
            state=_chip_state(
                engine,
                unit_id=item.id,
                current_id=unit.id,
                mark_done=mark_done,
            ),
        )
        for item in siblings
    ]


def subclause_stem_text(
    engine: ReminderEngine,
    unit: LearningUnit,
) -> str | None:
    """
    Gray stem above a letter unit: parent clause text with letter bodies removed.

    Bare Act wording only — no paraphrase.
    """
    if unit.type != LearningUnitType.SUBCLAUSE or not unit.parent_clause_id:
        return None
    parent = engine.get_unit(unit.parent_clause_id)
    if parent is None or not parent.text.strip():
        return None

    remainder = parent.text
    children = [
        child
        for child_id in parent.child_unit_ids
        if (child := engine.get_unit(child_id)) is not None and child.text.strip()
    ]
    for child in sorted(children, key=lambda c: len(c.text), reverse=True):
        if child.text in remainder:
            remainder = remainder.replace(child.text, "", 1)

    cleaned = "\n".join(
        line.rstrip() for line in remainder.splitlines() if line.strip()
    ).strip()
    return cleaned or None


def done_button_label(unit: LearningUnit) -> str:
    """Prototype CTA: next letter while walking a letter sequence."""
    if unit.type == LearningUnitType.SUBCLAUSE and unit.letter_sequence_next:
        return "Done — next letter"
    return "Done — next unit"


LEARN_MODE_LABELS: dict[str, str] = {
    "read": "Read",
    "cloze": "Cloze",
    "letters": "Letters",
    "type": "Type",
    "recite": "Recite",
    "test": "Test",
}

# Loosest cloze density threshold (heavy) — mirrors DENSITY_THRESH/letterLen
# in app.js. If no word clears it, no density can produce a blank.
_CLOZE_MIN_LETTER_LEN = 4


def _letter_len(word: str) -> int:
    # JS: word.replace(/[^A-Za-z]/g, "").length — ASCII letters only.
    return sum(1 for ch in word if ch.isascii() and ch.isalpha())


def has_cloze_blanks(text: str) -> bool:
    """Whether any cloze density can blank at least one word of ``text``.

    When False, cloze is omitted from the unit's effective required modes —
    it must never be fake-completed just because nothing could be revealed.
    """
    return any(_letter_len(word) >= _CLOZE_MIN_LETTER_LEN for word in text.split())


def methods_tracker_line(seen_count: int, required_count: int = 6) -> str:
    """Copy under the Learn mode tab bar (METHODS-THEME-HANDOFF).

    ``required_count`` reflects the entitlement-aware required set — six for
    claimed/claimable/subscribed Articles, four open methods for guests and
    cap-reached Articles.
    """
    if seen_count >= required_count:
        return (
            f"All {required_count} methods visited — revision complete, mark it Done"
        )
    word = "six" if required_count == 6 else str(required_count)
    return (
        f"{seen_count} of {required_count} methods visited · revision completes "
        f"when you've been through all {word}"
    )


def done_button_state(
    unit: LearningUnit,
    seen: set[str],
    required: set[str] | None = None,
) -> dict[str, object]:
    """Locked Done until the required modes are visited (entitlement-aware).

    Defaults to all six; guests / cap-reached Articles require only the four
    open modes to reach the Done affordance (which then gates server-side).
    """
    required_set = LEARN_MODES_SET if required is None else set(required)
    missing = required_set - set(seen)
    remaining = len(missing)
    if remaining > 0:
        label = f"{remaining} method{'s' if remaining != 1 else ''} left"
        return {
            "unlocked": False,
            "label": label,
            "disabled": True,
            "missing": sorted(missing),
        }
    return {
        "unlocked": True,
        "label": done_button_label(unit),
        "disabled": False,
        "missing": [],
    }


def free_article_slots(eng: ReminderEngine) -> list[dict[str, object]]:
    """Numbered Free-Article slot rows for the Profile (design 05).

    One row per claimed parent Article — title, saved date, clause count and
    the earliest upcoming review across that Article's units. Callers render
    remaining allowance as explicit empty-slot rows; legacy over-cap accounts
    simply produce more than three rows.
    """
    claimed_dates = eng.claimed_articles_with_dates()
    rows: list[dict[str, object]] = []

    def _sort_key(value: str) -> tuple[int, object]:
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            return (1, str(value))

    for article in sorted(claimed_dates, key=_sort_key):
        units = [
            u
            for u in eng.units.values()
            if u.article_number is not None and str(u.article_number) == article
        ]
        title = None
        for unit in units:
            if unit.type == LearningUnitType.ARTICLE and unit.title:
                title = unit.title
                break
        if title is None:
            for unit in units:
                if unit.title:
                    title = unit.title
                    break
        clause_count = sum(1 for u in units if u.type != LearningUnitType.ARTICLE)
        next_review: date | None = None
        for unit in units:
            record = eng.repo.get_progress(eng.user_id, unit.id)
            if record is not None and record.next_revision is not None:
                if next_review is None or record.next_revision < next_review:
                    next_review = record.next_revision

        meta_bits: list[str] = []
        claimed_at = claimed_dates[article]
        if claimed_at:
            try:
                saved = date.fromisoformat(claimed_at[:10])
                meta_bits.append(f"Saved {saved.day} {saved.strftime('%b %Y')}")
            except ValueError:
                pass
        if clause_count:
            meta_bits.append(
                f"{clause_count} clause{'s' if clause_count != 1 else ''}"
            )
        if next_review is not None:
            meta_bits.append(
                f"next review {next_review.day} {next_review.strftime('%b')}"
            )
        rows.append(
            {
                "article": article,
                "title": f"Article {article}" + (f" — {title}" if title else ""),
                "meta": " · ".join(meta_bits),
            }
        )
    return rows
