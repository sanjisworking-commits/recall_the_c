"""Deterministic reminder engine over learning units (user-scoped)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter
from typing import Iterable, Mapping
from uuid import UUID

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitsDocument
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.protocols import ReminderRepositoryProtocol
from constitution_memorizer.progress.repository import (
    LEARN_MODES,
    LEARN_MODES_SET,
    NEWS_ARTICLES_KEY,
    NOTIFICATION_FREQUENCY_KEY,
    THEME_KEY,
    AutoPlanDay,
    BillingOrder,
    CompletionProgress,
    NotificationFrequency,
    PLANNER_SESSION_KINDS,
    PlannerReadBundle,
    ProgressRecord,
    ProgressRepository,
    RequestBootstrap,
    SplitMode,
    StudyItemStatus,
    StudySession,
    StudySessionKind,
    ThemePreference,
    UserLearningPlan,
    LearningPlanMode,
    _frequency_from_raw,
    _news_from_raw,
    _theme_from_raw,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.utils.json_io import read_json

INTERVAL_LADDER: tuple[int, ...] = (1, 3, 7, 15, 30, 60)
DEFAULT_EASE_FACTOR = 2.5


def _record_timing(stage: str, started: float) -> None:
    # Lazy import: request_context lives under web, which imports this module.
    from constitution_memorizer.web.request_context import record_request_timing

    record_request_timing(stage, started)


def _record_counter(name: str, n: int = 1) -> None:
    from constitution_memorizer.web.request_context import record_request_counter

    record_request_counter(name, n)


def _record_note(name: str, value: str) -> None:
    from constitution_memorizer.web.request_context import record_request_note

    record_request_note(name, value)


def advance_interval(current_interval_days: int) -> int | None:
    if current_interval_days <= 0:
        return INTERVAL_LADDER[0]
    if current_interval_days in INTERVAL_LADDER:
        index = INTERVAL_LADDER.index(current_interval_days)
        if index + 1 >= len(INTERVAL_LADDER):
            return None
        return INTERVAL_LADDER[index + 1]
    for rung in INTERVAL_LADDER:
        if rung > current_interval_days:
            return rung
    return None


@dataclass(frozen=True)
class MarkDoneResult:
    unit_id: str
    progress: ProgressRecord
    next_unit_id: str | None
    modes_complete: bool = True


class ModesIncompleteError(ValueError):
    def __init__(self, unit_id: str, seen: set[str]) -> None:
        self.unit_id = unit_id
        self.seen = frozenset(seen)
        missing = sorted(LEARN_MODES_SET - self.seen)
        super().__init__(
            f"Unit {unit_id} still needs modes: {', '.join(missing)}"
        )


class ReminderEngine:
    """
    Schedule revisions by learning_unit_id using a fixed day ladder.

    The shared learning-unit catalog is read-only. Personal data is always
    scoped through ``user_id`` (default LOCAL_USER_ID for single-tenant mode).
    Use ``for_user`` to bind a different authenticated user without cloning the catalog.

    Each engine instance keeps request-scoped lazy caches for progress and split
    preferences so Dashboard/Browse loops do not issue one remote query per unit.
    ``for_user`` always returns a fresh empty cache for that request binding.
    """

    def __init__(
        self,
        repo: ReminderRepositoryProtocol,
        units: Mapping[str, LearningUnit],
        *,
        user_id: UUID = LOCAL_USER_ID,
    ) -> None:
        self.repo = repo
        self.units = dict(units)
        self.user_id = user_id
        # None = not loaded yet; dict/str = loaded for this request-bound engine.
        self._progress_cache: dict[str, ProgressRecord] | None = None
        self._split_cache: dict[str, SplitMode] | None = None
        self._theme_cache: ThemePreference | None = None
        self._news_cache: str | None = None
        self._claimed_cache: set[str] | None = None
        self._settings_cache: dict[str, str] | None = None
        self._modes_seen_cache: dict[str, set[str]] | None = None
        self._backfill_checked: bool = False
        self._billing_loaded: bool = False
        self._latest_paid_order: BillingOrder | None = None
        self._learning_plan_cache: UserLearningPlan | None = None
        self._session_day_cache: dict[tuple[str, date], StudySession | None] = {}
        self._auto_plan_days: list[AutoPlanDay] | None = None
        self._auto_plan_start: date | None = None
        self._auto_plan_until: date | None = None
        self._auto_plan_horizon: date | None = None
        self._auto_plan_tail: bool | None = None
        self._daily_goal_dates: list[date] | None = None
        self._daily_goal_until: date | None = None
        self._planner_bundle: PlannerReadBundle | None = None

    def clear_planner_request_caches(self) -> None:
        """Drop planner snapshot caches. Call at the start of each HTTP request.

        Single-user mode reuses one engine across requests. Without this, a
        prior upsert/GET would leak ``_learning_plan_cache`` into the next
        request and skip the schema-gap path on ``get_learning_plan``.
        """
        self._learning_plan_cache = None
        self._session_day_cache.clear()
        self._auto_plan_days = None
        self._auto_plan_start = None
        self._auto_plan_until = None
        self._auto_plan_horizon = None
        self._auto_plan_tail = None
        self._daily_goal_dates = None
        self._daily_goal_until = None
        self._planner_bundle = None

    def for_user(self, user_id: UUID) -> ReminderEngine:
        """Return a lightweight engine bound to ``user_id`` (shared units + repo)."""
        return ReminderEngine(self.repo, self.units, user_id=user_id)

    def _ensure_progress_cache(self) -> dict[str, ProgressRecord]:
        if self._progress_cache is None:
            started = perf_counter()
            rows = self.repo.list_all_progress(self.user_id)
            _record_timing("progress_preload", started)
            self._progress_cache = {row.learning_unit_id: row for row in rows}
        return self._progress_cache

    def preload_progress(self) -> None:
        """Load list_all_progress into the request cache if not already loaded."""
        self._ensure_progress_cache()

    def bootstrap_request(
        self,
        *,
        include_profile: bool = False,
        include_news: bool = False,
        include_modes: bool = False,
        include_account: bool = False,
    ) -> RequestBootstrap:
        """Load independent request data once and seed request-local caches."""
        started = perf_counter()
        bundle = self.repo.load_request_bootstrap(
            self.user_id,
            include_profile=include_profile,
            include_news=include_news,
            include_modes=include_modes,
            include_account=include_account,
        )
        _record_timing("request_bootstrap", started)
        self._progress_cache = {row.learning_unit_id: row for row in bundle.progress}
        self._split_cache = dict(bundle.split_preferences)
        self._theme_cache = bundle.theme
        self._settings_cache = dict(bundle.settings or {})
        if include_news:
            self._news_cache = (
                bundle.news_articles_raw if bundle.news_articles_raw is not None else ""
            )
        if bundle.modes_seen_by_unit is not None:
            self._modes_seen_cache = {
                unit_id: set(modes) for unit_id, modes in bundle.modes_seen_by_unit.items()
            }
            _record_counter(
                "modes_seen_rows",
                sum(len(modes) for modes in bundle.modes_seen_by_unit.values()),
            )
        if bundle.account is not None:
            self._claimed_cache = set(bundle.account.claimed_articles)
            self._billing_loaded = True
            self._latest_paid_order = bundle.account.latest_paid_billing_order
        if (
            self._settings_cache is not None
            and self._settings_cache.get(self._FREE_ARTICLES_BACKFILLED_KEY) == "1"
        ):
            self._backfill_checked = True
        return bundle

    def preload_account_claims(self) -> None:
        """Seed backfill + claimed caches without a full request bootstrap.

        Loads the grandfather-backfill setting and the claimed-Article set so
        ``claimed_articles()`` does not pay those SELECTs again. Does not
        preload progress, splits, or modes, and does not install a partial
        settings cache.
        """
        if not self._backfill_checked:
            if self._settings_cache is not None:
                flag = self._settings_cache.get(self._FREE_ARTICLES_BACKFILLED_KEY)
            else:
                flag = self.repo.get_setting(
                    self.user_id, self._FREE_ARTICLES_BACKFILLED_KEY
                )
            if flag == "1":
                self._backfill_checked = True
        if self._claimed_cache is None:
            started = perf_counter()
            self._claimed_cache = set(self.repo.claimed_articles(self.user_id))
            _record_timing("claimed_articles", started)

    def ensure_planner_bundle(
        self,
        *,
        as_of: date,
        auto_start: date | None = None,
        auto_until: date | None = None,
    ) -> PlannerReadBundle:
        """Load planner state once and seed request-local caches.

        Default window is the rolling 15-day Auto horizon. Calendar passes a
        wider ``auto_start``/``auto_until`` so month overlay and freshness share
        the same snapshot.
        """
        from constitution_memorizer.planner.roadmap import roadmap_horizon
        from constitution_memorizer.web.service import _is_missing_optional_schema

        horizon = roadmap_horizon(as_of)
        start = auto_start or as_of
        until = auto_until or horizon
        if until < horizon:
            until = horizon
        if self._planner_bundle is not None and self._planner_bundle.covering(
            as_of=as_of, auto_start=start, auto_until=until
        ):
            return self._planner_bundle

        started = perf_counter()
        try:
            bundle = self.repo.load_planner_read_bundle(
                self.user_id,
                as_of=as_of,
                auto_start=start,
                auto_until=until,
                horizon=horizon,
                daily_goal_until=as_of,
            )
        except Exception as error:  # noqa: BLE001 — schema-gap window
            if not _is_missing_optional_schema(error):
                raise
            bundle = self._planner_bundle_piecewise(
                as_of=as_of,
                auto_start=start,
                auto_until=until,
                horizon=horizon,
            )
        _record_counter("planner_selects", 6)
        _record_counter("planner_round_trips", 1 if bundle.pipelined else 6)
        _record_timing("planner_bundle", started)
        if bundle.pipeline_fallback_reason:
            _record_note(
                "planner_pipeline_fallback_reason", bundle.pipeline_fallback_reason
            )
        self._seed_planner_bundle(bundle)
        return bundle

    def _planner_bundle_piecewise(
        self,
        *,
        as_of: date,
        auto_start: date,
        auto_until: date,
        horizon: date,
    ) -> PlannerReadBundle:
        from constitution_memorizer.web.service import _is_missing_optional_schema

        plan = UserLearningPlan()
        sessions: dict[str, StudySession | None] = {
            kind: None for kind in PLANNER_SESSION_KINDS
        }
        days: list[AutoPlanDay] = []
        has_tail = False
        goals: list[date] = []
        try:
            plan = self.repo.get_learning_plan(self.user_id)
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise
        try:
            sessions = self.repo.study_sessions_for_day(self.user_id, as_of)
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise
            for kind in PLANNER_SESSION_KINDS:
                try:
                    sessions[kind] = self.repo.study_session_for_day(
                        self.user_id, kind=kind, plan_date=as_of
                    )
                except Exception as inner:  # noqa: BLE001
                    if not _is_missing_optional_schema(inner):
                        raise
        try:
            days = self.repo.list_auto_plan_window(self.user_id, auto_start, auto_until)
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise
        try:
            tail = self.repo.list_auto_plan_window(
                self.user_id,
                horizon + timedelta(days=1),
                horizon + timedelta(days=366),
            )
            has_tail = bool(tail)
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise
        try:
            goals = self.repo.list_daily_goal_dates(
                self.user_id, until=as_of, limit=400
            )
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise
        return PlannerReadBundle(
            as_of=as_of,
            learning_plan=plan,
            sessions_by_kind=sessions,
            auto_plan_days=tuple(days),
            auto_start=auto_start,
            auto_until=auto_until,
            horizon=horizon,
            has_auto_plan_tail=has_tail,
            daily_goal_dates=tuple(goals),
            pipelined=False,
        )

    def _seed_planner_bundle(self, bundle: PlannerReadBundle) -> None:
        self._planner_bundle = bundle
        self._learning_plan_cache = bundle.learning_plan
        for kind in PLANNER_SESSION_KINDS:
            self._session_day_cache[(kind, bundle.as_of)] = bundle.session(kind)
        self._auto_plan_days = list(bundle.auto_plan_days)
        self._auto_plan_start = bundle.auto_start
        self._auto_plan_until = bundle.auto_until
        self._auto_plan_horizon = bundle.horizon
        self._auto_plan_tail = bundle.has_auto_plan_tail
        self._daily_goal_dates = list(bundle.daily_goal_dates)
        self._daily_goal_until = bundle.as_of

    def _invalidate_learning_plan_cache(self) -> None:
        self._learning_plan_cache = None
        self._planner_bundle = None

    def _invalidate_session_cache(self) -> None:
        self._session_day_cache.clear()
        self._planner_bundle = None

    def _invalidate_auto_plan_cache(self) -> None:
        self._auto_plan_days = None
        self._auto_plan_start = None
        self._auto_plan_until = None
        self._auto_plan_horizon = None
        self._auto_plan_tail = None
        if self._planner_bundle is not None:
            self._planner_bundle = None

    def _invalidate_daily_goal_cache(self) -> None:
        self._daily_goal_dates = None
        self._daily_goal_until = None
        self._planner_bundle = None

    def _ensure_split_cache(self) -> dict[str, SplitMode]:
        if self._split_cache is None:
            started = perf_counter()
            self._split_cache = dict(self.repo.list_split_preferences(self.user_id))
            _record_timing("split_prefs", started)
        return self._split_cache

    def _store_progress(self, progress: ProgressRecord) -> None:
        if self._progress_cache is None:
            return
        self._progress_cache[progress.learning_unit_id] = progress

    def _drop_progress(self, unit_id: str) -> None:
        if self._progress_cache is not None:
            self._progress_cache.pop(unit_id, None)

    def _invalidate_progress_cache(self) -> None:
        self._progress_cache = None

    def _invalidate_split_cache(self) -> None:
        self._split_cache = None

    def _invalidate_theme_cache(self) -> None:
        self._theme_cache = None

    def _invalidate_news_cache(self) -> None:
        self._news_cache = None

    def _invalidate_settings_cache(self) -> None:
        self._settings_cache = None

    def _invalidate_modes_cache(self) -> None:
        self._modes_seen_cache = None

    def _invalidate_account_cache(self) -> None:
        self._claimed_cache = None
        self._backfill_checked = False
        self._billing_loaded = False
        self._latest_paid_order = None

    def _patch_settings_cache(self, key: str, value: str) -> None:
        if self._settings_cache is not None:
            self._settings_cache[key] = value

    @classmethod
    def from_repository(
        cls,
        repo: ReminderRepositoryProtocol,
        units: Mapping[str, LearningUnit] | Iterable[LearningUnit],
        *,
        user_id: UUID = LOCAL_USER_ID,
    ) -> ReminderEngine:
        """Bind an engine to an already-constructed repository (SQLite or Postgres)."""
        if isinstance(units, Mapping):
            catalog = dict(units)
        else:
            catalog = {u.id: u for u in units}
        return cls(repo, catalog, user_id=user_id)

    @classmethod
    def from_paths(
        cls,
        db_path: Path | str,
        units_path: Path | str,
        *,
        user_id: UUID = LOCAL_USER_ID,
    ) -> ReminderEngine:
        conn = open_progress_db(db_path)
        doc = LearningUnitsDocument.model_validate(read_json(Path(units_path)))
        catalog = {u.id: u for u in doc.units}
        return cls.from_repository(
            ProgressRepository(conn), catalog, user_id=user_id
        )

    @classmethod
    def from_units(
        cls,
        db_path: Path | str,
        units: Iterable[LearningUnit],
        *,
        user_id: UUID = LOCAL_USER_ID,
    ) -> ReminderEngine:
        conn = open_progress_db(db_path)
        catalog = {u.id: u for u in units}
        return cls.from_repository(
            ProgressRepository(conn), catalog, user_id=user_id
        )

    def get_unit(self, unit_id: str) -> LearningUnit | None:
        return self.units.get(unit_id)

    def get_progress(self, unit_id: str) -> ProgressRecord | None:
        return self._ensure_progress_cache().get(unit_id)

    def list_all_progress(self) -> list[ProgressRecord]:
        cache = self._ensure_progress_cache()
        return list(cache.values())

    def get_gloss(self, article_number: str) -> str | None:
        started = perf_counter()
        value = self.repo.get_gloss(self.user_id, article_number)
        _record_timing("gloss_read", started)
        return value

    def upsert_gloss(self, article_number: str, text: str) -> None:
        self.repo.upsert_gloss(self.user_id, article_number, text)

    def delete_gloss(self, article_number: str) -> None:
        self.repo.delete_gloss(self.user_id, article_number)

    def delete_progress(self, unit_id: str) -> None:
        self.repo.delete_progress(self.user_id, unit_id)
        self._drop_progress(unit_id)

    def reset_all_personal_data(self) -> None:
        self.repo.delete_all_progress(self.user_id)
        self.repo.clear_all_modes_seen(self.user_id)
        self._invalidate_progress_cache()
        self._invalidate_split_cache()
        self._invalidate_theme_cache()
        self._invalidate_news_cache()
        self._invalidate_settings_cache()
        self._invalidate_modes_cache()
        self._invalidate_account_cache()

    def reset_learning_progress(self) -> None:
        """Clear what has been learned; keep who the learner is.

        Progress, modes seen, study sessions, the stored plan and the
        daily-goal facts the streak is derived from all go. The profile, the
        settings, the memory log and the claimed Articles stay — claims are
        permanent by design, and handing free slots back on every reset would
        turn three free Articles into an unlimited supply.
        """
        self.repo.delete_all_progress(self.user_id)
        self.repo.clear_all_modes_seen(self.user_id)
        self.repo.delete_all_study_sessions(self.user_id)
        self.repo.delete_learning_plan(self.user_id)
        self.repo.clear_daily_goal_met(self.user_id)
        self._invalidate_progress_cache()
        self._invalidate_split_cache()
        self._invalidate_modes_cache()
        self._invalidate_learning_plan_cache()
        self._invalidate_daily_goal_cache()
        self.clear_planner_request_caches()

    def set_split_preference(self, parent_clause_id: str, mode: SplitMode) -> None:
        started = perf_counter()
        self.repo.set_split_preference(self.user_id, parent_clause_id, mode)
        _record_timing("split_write", started)
        if self._split_cache is not None:
            self._split_cache[parent_clause_id] = mode

    def get_split_preference(self, parent_clause_id: str) -> SplitMode | None:
        return self._ensure_split_cache().get(parent_clause_id)

    def delete_split_preference(self, parent_clause_id: str) -> None:
        self.repo.delete_split_preference(self.user_id, parent_clause_id)
        if self._split_cache is not None:
            self._split_cache.pop(parent_clause_id, None)

    def get_notification_frequency(self) -> NotificationFrequency:
        if self._settings_cache is not None:
            return _frequency_from_raw(
                self._settings_cache.get(NOTIFICATION_FREQUENCY_KEY)
            )
        started = perf_counter()
        value = self.repo.get_notification_frequency(self.user_id)
        _record_timing("settings_frequency", started)
        return value

    def set_notification_frequency(self, frequency: NotificationFrequency) -> None:
        self.repo.set_notification_frequency(self.user_id, frequency)
        self._patch_settings_cache(NOTIFICATION_FREQUENCY_KEY, frequency)

    def get_setting(self, key: str, *, stage: str | None = None) -> str | None:
        """Read one setting. ``stage`` times only the repo path, like get_theme."""
        if self._settings_cache is not None:
            return self._settings_cache.get(key)
        if stage is None:
            return self.repo.get_setting(self.user_id, key)
        started = perf_counter()
        value = self.repo.get_setting(self.user_id, key)
        _record_timing(stage, started)
        return value

    def set_setting(self, key: str, value: str) -> None:
        self.repo.set_setting(self.user_id, key, value)
        self._patch_settings_cache(key, value)

    def get_theme(self) -> ThemePreference:
        if self._theme_cache is not None:
            return self._theme_cache
        if self._settings_cache is not None:
            theme = _theme_from_raw(self._settings_cache.get(THEME_KEY))
            self._theme_cache = theme
            return theme
        started = perf_counter()
        theme = self.repo.get_theme(self.user_id)
        _record_timing("theme", started)
        self._theme_cache = theme
        return theme

    def set_theme(self, theme: ThemePreference) -> None:
        self.repo.set_theme(self.user_id, theme)
        self._theme_cache = theme
        self._patch_settings_cache(THEME_KEY, theme)

    def get_news_articles_raw(self) -> str:
        if self._news_cache is not None:
            return self._news_cache
        if self._settings_cache is not None:
            value = _news_from_raw(self._settings_cache.get(NEWS_ARTICLES_KEY))
            self._news_cache = value
            return value
        started = perf_counter()
        value = self.repo.get_news_articles_raw(self.user_id)
        _record_timing("news_setting", started)
        self._news_cache = value
        return value

    def set_news_articles_raw(self, value: str) -> None:
        self.repo.set_news_articles_raw(self.user_id, value)
        stripped = value.strip()
        self._news_cache = stripped
        self._patch_settings_cache(NEWS_ARTICLES_KEY, stripped)

    # ------------------------------------------------------------------ #
    # Free-Article entitlement slots (parent Article level)               #
    # ------------------------------------------------------------------ #
    _FREE_ARTICLES_BACKFILLED_KEY = "free_articles_backfilled"

    def claimed_articles(self) -> set[str]:
        """Parent Articles claimed as this user's permanent Free Articles.

        Runs the one-time grandfather backfill on first access: every distinct
        parent Article the user already has genuine Done progress on
        (``times_completed >= 1``) is claimed, even beyond the 3-slot limit —
        existing learning is never taken away. Request-scoped cache, same as
        the other engine caches (``for_user`` starts fresh).

        A bootstrap-seeded claim cache does not skip the grandfather check:
        ``_claimed_cache is not None`` is not the same as ``backfill checked``.
        """
        self._ensure_free_articles_backfilled()
        if self._claimed_cache is None:
            started = perf_counter()
            self._claimed_cache = set(self.repo.claimed_articles(self.user_id))
            _record_timing("claimed_articles", started)
        return set(self._claimed_cache)

    def claimed_articles_with_dates(self) -> dict[str, str]:
        """Claimed Articles → claimed_at ISO timestamps (runs the backfill)."""
        self.claimed_articles()  # ensures grandfather backfill has run
        return self.repo.claimed_articles_with_dates(self.user_id)

    def is_article_claimed(self, article_number: str | None) -> bool:
        if article_number is None or not str(article_number).strip():
            return False
        return str(article_number).strip() in self.claimed_articles()

    def claim_article(self, article_number: str) -> None:
        """Idempotently claim a parent Article as a permanent Free Article."""
        key = str(article_number).strip()
        if not key:
            raise ValueError("article_number is required to claim a Free Article")
        self._ensure_free_articles_backfilled()
        self.repo.claim_article(self.user_id, key)
        if self._claimed_cache is not None:
            self._claimed_cache.add(key)

    # ------------------------------------------------------------------ #
    # Study sessions — snapshotted queues the web layer navigates by.     #
    # The engine is a pass-through here: a session records what the user  #
    # set out to do, and never influences the revision ladder.            #
    # ------------------------------------------------------------------ #
    def active_study_session(
        self,
        *,
        kind: StudySessionKind,
        plan_date: date | None = None,
    ) -> StudySession | None:
        if plan_date is not None and (kind, plan_date) in self._session_day_cache:
            session = self._session_day_cache[(kind, plan_date)]
            if session is None or session.status != "active":
                return None
            return session
        started = perf_counter()
        _record_counter("study_session_reads")
        _record_counter("db_reads")
        session = self.repo.active_study_session(
            self.user_id, kind=kind, plan_date=plan_date
        )
        _record_timing("study_sessions_read", started)
        return session

    def get_study_session(self, session_id: str) -> StudySession | None:
        if not session_id:
            return None
        return self.repo.get_study_session(self.user_id, session_id)

    def create_study_session(
        self,
        *,
        session_id: str,
        kind: StudySessionKind,
        plan_date: date,
        unit_ids: list[str],
    ) -> StudySession:
        started = perf_counter()
        session = self.repo.create_study_session(
            self.user_id,
            session_id=session_id,
            kind=kind,
            plan_date=plan_date,
            unit_ids=unit_ids,
        )
        _record_timing("session_write", started)
        self._invalidate_session_cache()
        return session

    def set_study_item_status(
        self,
        *,
        session_id: str,
        unit_id: str,
        status: StudyItemStatus,
    ) -> None:
        self.repo.set_study_item_status(
            self.user_id, session_id=session_id, unit_id=unit_id, status=status
        )
        self._invalidate_session_cache()

    def replace_study_session_unit(
        self,
        *,
        session_id: str,
        old_unit_id: str,
        new_unit_ids: list[str],
    ) -> StudySession | None:
        session = self.repo.replace_study_session_unit(
            self.user_id,
            session_id=session_id,
            old_unit_id=old_unit_id,
            new_unit_ids=new_unit_ids,
        )
        self._invalidate_session_cache()
        return session

    def complete_study_session(self, session_id: str) -> None:
        self.repo.complete_study_session(self.user_id, session_id)
        self._invalidate_session_cache()

    def study_session_for_day(
        self,
        *,
        kind: StudySessionKind,
        plan_date: date,
    ) -> StudySession | None:
        key = (kind, plan_date)
        if key in self._session_day_cache:
            return self._session_day_cache[key]
        started = perf_counter()
        _record_counter("study_session_reads")
        _record_counter("db_reads")
        session = self.repo.study_session_for_day(
            self.user_id, kind=kind, plan_date=plan_date
        )
        _record_timing("study_sessions_read", started)
        self._session_day_cache[key] = session
        return session

    def record_daily_goal_met(self, goal_date: date) -> None:
        self.repo.record_daily_goal_met(self.user_id, goal_date)
        self._invalidate_daily_goal_cache()

    def is_daily_goal_met(self, goal_date: date) -> bool:
        if self._daily_goal_dates is not None and self._daily_goal_until is not None:
            if goal_date <= self._daily_goal_until:
                return goal_date in self._daily_goal_dates
        return self.repo.is_daily_goal_met(self.user_id, goal_date)

    def list_daily_goal_dates(self, *, until: date, limit: int = 400) -> list[date]:
        if (
            self._daily_goal_dates is not None
            and self._daily_goal_until is not None
            and until <= self._daily_goal_until
        ):
            return [day for day in self._daily_goal_dates if day <= until][:limit]
        started = perf_counter()
        _record_counter("daily_goal_reads")
        _record_counter("db_reads")
        dates = self.repo.list_daily_goal_dates(
            self.user_id, until=until, limit=limit
        )
        _record_timing("daily_goal_read", started)
        self._daily_goal_dates = list(dates)
        self._daily_goal_until = until
        return dates

    def get_learning_plan(self) -> UserLearningPlan:
        if self._learning_plan_cache is not None:
            return self._learning_plan_cache
        started = perf_counter()
        _record_counter("learning_plan_reads")
        _record_counter("db_reads")
        plan = self.repo.get_learning_plan(self.user_id)
        _record_timing("learning_plan_read", started)
        # Seeded by ensure_planner_bundle / writes on this engine only.
        # Do not cache a raw fetch: tests (and any long-lived engine) may
        # read after another request wrote through a different for_user().
        return plan

    def upsert_learning_plan(
        self,
        *,
        mode: LearningPlanMode,
        daily_target: int | None,
        prompt_dismissed_on: date | None = None,
        last_anchor_theme: str | None = None,
        as_of: date | None = None,
    ) -> UserLearningPlan:
        plan = self.repo.upsert_learning_plan(
            self.user_id,
            mode=mode,
            daily_target=daily_target,
            prompt_dismissed_on=prompt_dismissed_on,
            last_anchor_theme=last_anchor_theme,
            as_of=as_of,
        )
        self._learning_plan_cache = plan
        self._planner_bundle = None
        return plan

    def activate_learning_plan(self, as_of: date) -> UserLearningPlan:
        plan = self.repo.activate_learning_plan(self.user_id, as_of)
        self._learning_plan_cache = plan
        self._planner_bundle = None
        return plan

    def dismiss_plan_prompt(self, as_of: date) -> UserLearningPlan:
        plan = self.repo.dismiss_plan_prompt(self.user_id, as_of)
        self._learning_plan_cache = plan
        self._planner_bundle = None
        return plan

    def set_last_anchor_theme(self, theme: str | None) -> None:
        self.repo.set_last_anchor_theme(self.user_id, theme)
        self._invalidate_learning_plan_cache()

    def list_auto_plan_window(self, start: date, until: date) -> list[AutoPlanDay]:
        if (
            self._auto_plan_days is not None
            and self._auto_plan_start is not None
            and self._auto_plan_until is not None
            and start >= self._auto_plan_start
            and until <= self._auto_plan_until
        ):
            return [
                day
                for day in self._auto_plan_days
                if start <= day.plan_date <= until
            ]
        started = perf_counter()
        _record_counter("auto_plan_reads")
        _record_counter("db_reads")
        days = self.repo.list_auto_plan_window(self.user_id, start, until)
        _record_timing("auto_plan_read", started)
        return days

    def list_auto_plan_day(self, plan_date: date) -> AutoPlanDay | None:
        days = self.list_auto_plan_window(plan_date, plan_date)
        return days[0] if days else None

    def replace_auto_plan_day(
        self, plan_date: date, daily_target: int, unit_ids: list[str]
    ) -> AutoPlanDay:
        day = self.repo.replace_auto_plan_day(
            self.user_id, plan_date, daily_target, unit_ids
        )
        self._invalidate_auto_plan_cache()
        return day

    def clear_future_auto_plan(self, as_of: date) -> None:
        self.repo.clear_future_auto_plan(self.user_id, as_of)
        self._invalidate_auto_plan_cache()

    def delete_auto_plan_after(self, horizon: date) -> None:
        self.repo.delete_auto_plan_after(self.user_id, horizon)
        self._invalidate_auto_plan_cache()

    def replace_auto_plan_window_atomic(
        self, as_of: date, horizon: date, days
    ) -> None:
        self.repo.replace_auto_plan_window_atomic(
            self.user_id, as_of, horizon, days
        )
        self._invalidate_auto_plan_cache()

    def apply_auto_plan_reconcile(self, as_of: date, horizon: date, builder) -> None:
        self.repo.apply_auto_plan_reconcile(self.user_id, as_of, horizon, builder)
        self._invalidate_auto_plan_cache()

    def latest_paid_billing_order(self) -> BillingOrder | None:
        if self._billing_loaded:
            return self._latest_paid_order
        started = perf_counter()
        order = self.repo.latest_paid_billing_order(self.user_id)
        _record_timing("billing_status", started)
        self._billing_loaded = True
        self._latest_paid_order = order
        return order

    def _ensure_free_articles_backfilled(self) -> None:
        """One-time grandfather backfill, reusing the request progress cache.

        Uses ``_ensure_progress_cache`` so the dashboard/browse request flow
        (which preloads progress via ``bootstrap_request``) never pays an extra
        ``list_all_progress`` round trip for entitlement status.
        """
        if self._backfill_checked:
            return
        if self._settings_cache is not None:
            flag = self._settings_cache.get(self._FREE_ARTICLES_BACKFILLED_KEY)
        else:
            started = perf_counter()
            flag = self.repo.get_setting(self.user_id, self._FREE_ARTICLES_BACKFILLED_KEY)
            _record_timing("free_articles_backfill_check", started)
        if flag == "1":
            self._backfill_checked = True
            return
        for record in self._ensure_progress_cache().values():
            if record.times_completed < 1:
                continue
            unit = self.units.get(record.learning_unit_id)
            if unit is None or not unit.article_number:
                continue
            article = str(unit.article_number).strip()
            self.repo.claim_article(self.user_id, article)
            if self._claimed_cache is not None:
                self._claimed_cache.add(article)
        self.repo.set_setting(self.user_id, self._FREE_ARTICLES_BACKFILLED_KEY, "1")
        self._patch_settings_cache(self._FREE_ARTICLES_BACKFILLED_KEY, "1")
        self._backfill_checked = True

    def mark_mode_seen(self, unit_id: str, mode: str) -> set[str]:
        if unit_id not in self.units:
            raise KeyError(f"Unknown learning unit id: {unit_id}")
        started = perf_counter()
        seen = self.repo.mark_mode_seen(self.user_id, unit_id, mode)
        _record_timing("mode_seen_write", started)
        if self._modes_seen_cache is not None:
            self._modes_seen_cache[unit_id] = set(seen)
        return seen

    def modes_seen(self, unit_id: str) -> set[str]:
        if self._modes_seen_cache is not None:
            return set(self._modes_seen_cache.get(unit_id, set()))
        started = perf_counter()
        seen = self.repo.modes_seen(self.user_id, unit_id)
        _record_timing("modes_seen", started)
        return seen

    def mark_all_modes_seen(self, unit_id: str) -> set[str]:
        seen: set[str] = set()
        for mode in LEARN_MODES:
            seen = self.mark_mode_seen(unit_id, mode)
        return seen

    def clear_modes_seen(self, unit_id: str) -> None:
        self.repo.clear_modes_seen(self.user_id, unit_id)
        if self._modes_seen_cache is not None:
            self._modes_seen_cache[unit_id] = set()

    def modes_complete(self, unit_id: str) -> bool:
        return self.repo.modes_complete(self.user_id, unit_id)

    def mark_done(
        self,
        unit_id: str,
        *,
        as_of: date | None = None,
        require_all_modes: bool = True,
        required_modes: frozenset[str] | None = None,
        claim_article: str | None = None,
    ) -> MarkDoneResult:
        """Advance the ladder; optionally claim a Free Article in the same
        transaction (``claim_article`` rides inside ``commit_completion``).

        ``required_modes`` narrows the completion gate (entitlement- and
        unit-aware: modes a unit cannot produce are omitted); ``None`` keeps
        the historical all-six requirement.
        """
        if unit_id not in self.units:
            raise KeyError(f"Unknown learning unit id: {unit_id}")

        started = perf_counter()
        state = self.repo.load_completion_state(self.user_id, unit_id)
        _record_timing("completion_state", started)

        if self._split_cache is None:
            self._split_cache = dict(state.split_preferences)

        required = LEARN_MODES_SET if required_modes is None else required_modes
        if require_all_modes and not required.issubset(state.modes_seen):
            raise ModesIncompleteError(unit_id, state.modes_seen)

        today = as_of or date.today()
        current = state.progress
        if current is not None and current.status == "mastered":
            command = CompletionProgress(
                status=current.status,
                times_completed=current.times_completed,
                last_completed=current.last_completed,
                next_revision=current.next_revision,
                interval_days=current.interval_days,
                ease_factor=current.ease_factor,
            )
        else:
            interval = current.interval_days if current is not None else 0
            times = (current.times_completed if current is not None else 0) + 1
            nxt = advance_interval(interval)
            if nxt is None:
                command = CompletionProgress(
                    status="mastered",
                    times_completed=times,
                    last_completed=today,
                    next_revision=None,
                    interval_days=INTERVAL_LADDER[-1],
                    ease_factor=DEFAULT_EASE_FACTOR,
                )
            else:
                command = CompletionProgress(
                    status="review",
                    times_completed=times,
                    last_completed=today,
                    next_revision=today + timedelta(days=nxt),
                    interval_days=nxt,
                    ease_factor=DEFAULT_EASE_FACTOR,
                )

        started = perf_counter()
        if claim_article:
            progress = self.repo.commit_completion(
                self.user_id, unit_id, command, claim_article=str(claim_article)
            )
            if self._claimed_cache is not None:
                self._claimed_cache.add(str(claim_article))
        else:
            # Legacy call shape — keeps simple repo wrappers compatible.
            progress = self.repo.commit_completion(self.user_id, unit_id, command)
        _record_timing("completion_commit", started)
        self._store_progress(progress)
        if self._modes_seen_cache is not None:
            self._modes_seen_cache[unit_id] = set()

        started = perf_counter()
        next_unit_id = self.resolve_next_unit_id(unit_id)
        _record_timing("done_schedule", started)
        return MarkDoneResult(
            unit_id=unit_id,
            progress=progress,
            next_unit_id=next_unit_id,
            modes_complete=True,
        )

    def complete_revision_early(
        self,
        unit_id: str,
        *,
        as_of: date | None = None,
        require_all_modes: bool = True,
        required_modes: frozenset[str] | None = None,
        claim_article: str | None = None,
    ) -> MarkDoneResult:
        """Consume a future scheduled revision without re-anchoring off today.

        Reuses ``mark_done``'s completion pipeline. The only scheduling
        difference is ``next_revision = scheduled_due + next_interval``.
        """
        if unit_id not in self.units:
            raise KeyError(f"Unknown learning unit id: {unit_id}")

        started = perf_counter()
        state = self.repo.load_completion_state(self.user_id, unit_id)
        _record_timing("completion_state", started)

        if self._split_cache is None:
            self._split_cache = dict(state.split_preferences)

        required = LEARN_MODES_SET if required_modes is None else required_modes
        if require_all_modes and not required.issubset(state.modes_seen):
            raise ModesIncompleteError(unit_id, state.modes_seen)

        today = as_of or date.today()
        current = state.progress
        if (
            current is None
            or current.status != "review"
            or current.next_revision is None
            or current.next_revision <= today
        ):
            raise ValueError(
                f"Unit {unit_id} is not an early scheduled revision"
            )

        scheduled_due = current.next_revision
        times = current.times_completed + 1
        nxt = advance_interval(current.interval_days)
        if nxt is None:
            command = CompletionProgress(
                status="mastered",
                times_completed=times,
                last_completed=today,
                next_revision=None,
                interval_days=INTERVAL_LADDER[-1],
                ease_factor=DEFAULT_EASE_FACTOR,
            )
        else:
            command = CompletionProgress(
                status="review",
                times_completed=times,
                last_completed=today,
                next_revision=scheduled_due + timedelta(days=nxt),
                interval_days=nxt,
                ease_factor=DEFAULT_EASE_FACTOR,
            )

        started = perf_counter()
        if claim_article:
            progress = self.repo.commit_completion(
                self.user_id, unit_id, command, claim_article=str(claim_article)
            )
            if self._claimed_cache is not None:
                self._claimed_cache.add(str(claim_article))
        else:
            progress = self.repo.commit_completion(self.user_id, unit_id, command)
        _record_timing("completion_commit", started)
        self._store_progress(progress)
        if self._modes_seen_cache is not None:
            self._modes_seen_cache[unit_id] = set()

        started = perf_counter()
        next_unit_id = self.resolve_next_unit_id(unit_id)
        _record_timing("done_schedule", started)
        return MarkDoneResult(
            unit_id=unit_id,
            progress=progress,
            next_unit_id=next_unit_id,
            modes_complete=True,
        )

    def defer_until_tomorrow(
        self,
        unit_id: str,
        *,
        as_of: date | None = None,
    ) -> MarkDoneResult:
        if unit_id not in self.units:
            raise KeyError(f"Unknown learning unit id: {unit_id}")

        today = as_of or date.today()
        current = self.repo.ensure_progress(self.user_id, unit_id)
        self._store_progress(current)
        if current.status == "mastered":
            progress = current
        else:
            progress = self.repo.upsert_progress(
                self.user_id,
                unit_id=unit_id,
                status="review",
                times_completed=current.times_completed,
                last_completed=current.last_completed,
                next_revision=today + timedelta(days=1),
                interval_days=current.interval_days if current.interval_days > 0 else 1,
                ease_factor=current.ease_factor or DEFAULT_EASE_FACTOR,
            )
            self._store_progress(progress)

        return MarkDoneResult(
            unit_id=unit_id,
            progress=progress,
            next_unit_id=self.resolve_next_unit_id(unit_id),
        )

    def resolve_next_unit_id(self, unit_id: str) -> str | None:
        unit = self.units.get(unit_id)
        if unit is None:
            return None

        if unit.parent_clause_id:
            if unit.letter_sequence_next:
                return unit.letter_sequence_next
            parent = self.units.get(unit.parent_clause_id)
            return self._apply_entry_preference(parent.next_unit if parent else None)

        if unit.allows_letter_split and unit.child_unit_ids:
            mode = self.get_split_preference(unit.id) or "whole"
            if mode == "letters":
                return unit.child_unit_ids[0]

        return self._apply_entry_preference(unit.next_unit)

    def _apply_entry_preference(self, candidate_id: str | None) -> str | None:
        if not candidate_id:
            return None
        candidate = self.units.get(candidate_id)
        if candidate is None:
            return candidate_id
        if candidate.allows_letter_split and candidate.child_unit_ids:
            mode = self.get_split_preference(candidate.id) or "whole"
            if mode == "letters":
                return candidate.child_unit_ids[0]
        return candidate_id

    def next_to_learn_from_clause(
        self,
        parent_clause_id: str,
        *,
        mode: SplitMode | None = None,
    ) -> str | None:
        if mode is None:
            return self._apply_entry_preference(parent_clause_id) or parent_clause_id
        unit = self.units.get(parent_clause_id)
        if (
            mode == "letters"
            and unit is not None
            and unit.allows_letter_split
            and unit.child_unit_ids
        ):
            return unit.child_unit_ids[0]
        return parent_clause_id

    def due_today(
        self,
        as_of: date | None = None,
        *,
        include_new: bool = False,
    ) -> list[ProgressRecord]:
        today = as_of or date.today()
        if self._progress_cache is None:
            return self.repo.list_due(self.user_id, today, include_new=include_new)
        review = [
            row
            for row in self._progress_cache.values()
            if row.status == "review"
            and row.next_revision is not None
            and row.next_revision <= today
        ]
        review.sort(key=lambda row: (row.next_revision, row.learning_unit_id))
        if not include_new:
            return review
        new_rows = [
            row for row in self._progress_cache.values() if row.status == "new"
        ]
        new_rows.sort(key=lambda row: row.learning_unit_id)
        return review + new_rows

    def due_unit_ids(
        self,
        as_of: date | None = None,
        *,
        include_new: bool = False,
    ) -> list[str]:
        return [r.learning_unit_id for r in self.due_today(as_of, include_new=include_new)]

    def stats(self) -> dict[str, int]:
        if self._progress_cache is None:
            counts = self.repo.count_by_status(self.user_id)
        else:
            counts: dict[str, int] = {}
            for row in self._progress_cache.values():
                counts[row.status] = counts.get(row.status, 0) + 1
        return {
            "new": counts.get("new", 0),
            "review": counts.get("review", 0),
            "mastered": counts.get("mastered", 0),
            "tracked": sum(counts.values()),
            "split_preferences": len(self._ensure_split_cache()),
        }
