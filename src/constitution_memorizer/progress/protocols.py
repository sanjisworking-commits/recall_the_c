"""Repository protocols for Constitution progress (ReminderEngine contract)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from constitution_memorizer.progress.repository import (
    AutoPlanDay,
    AutoPlanSnapshot,
    BillingOrder,
    CompletionProgress,
    CompletionState,
    NotificationFrequency,
    ProgressRecord,
    ProgressStatus,
    RequestBootstrap,
    SplitMode,
    StudyItemStatus,
    StudySession,
    StudySessionKind,
    ThemePreference,
    UserLearningPlan,
    LearningPlanMode,
)


class ReminderRepositoryProtocol(Protocol):
    """Constitution-facing persistence contract used by ReminderEngine.

    Both SQLite ProgressRepository and PostgresProgressRepository must satisfy
    this surface. Memory Log storage is intentionally out of scope.
    """

    def get_progress(
        self, user_id: UUID | str, unit_id: str
    ) -> ProgressRecord | None: ...

    def ensure_progress(
        self, user_id: UUID | str, unit_id: str
    ) -> ProgressRecord: ...

    def upsert_progress(
        self,
        user_id: UUID | str,
        *,
        unit_id: str,
        status: ProgressStatus,
        times_completed: int,
        last_completed: date | None,
        next_revision: date | None,
        interval_days: int,
        ease_factor: float = 2.5,
    ) -> ProgressRecord: ...

    def delete_progress(self, user_id: UUID | str, unit_id: str) -> None: ...

    def delete_all_progress(self, user_id: UUID | str) -> None: ...

    def list_due(
        self,
        user_id: UUID | str,
        as_of: date,
        *,
        include_new: bool = False,
    ) -> list[ProgressRecord]: ...

    def list_all_progress(self, user_id: UUID | str) -> list[ProgressRecord]: ...

    def count_by_status(self, user_id: UUID | str) -> dict[str, int]: ...

    def get_split_preference(
        self, user_id: UUID | str, parent_clause_id: str
    ) -> SplitMode | None: ...

    def set_split_preference(
        self,
        user_id: UUID | str,
        parent_clause_id: str,
        mode: SplitMode,
    ) -> None: ...

    def delete_split_preference(
        self, user_id: UUID | str, parent_clause_id: str
    ) -> None: ...

    def list_split_preferences(
        self, user_id: UUID | str
    ) -> dict[str, SplitMode]: ...

    def get_gloss(
        self, user_id: UUID | str, article_number: str
    ) -> str | None: ...

    def upsert_gloss(
        self, user_id: UUID | str, article_number: str, text: str
    ) -> None: ...

    def delete_gloss(self, user_id: UUID | str, article_number: str) -> None: ...

    def claimed_articles(self, user_id: UUID | str) -> set[str]: ...

    def claimed_articles_with_dates(self, user_id: UUID | str) -> dict[str, str]: ...

    def is_article_claimed(self, user_id: UUID | str, article_number: str) -> bool: ...

    def claim_article(self, user_id: UUID | str, article_number: str) -> None: ...

    def create_study_session(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        kind: StudySessionKind,
        plan_date: date,
        unit_ids: list[str],
    ) -> StudySession: ...

    def get_study_session(
        self, user_id: UUID | str, session_id: str
    ) -> StudySession | None: ...

    def active_study_session(
        self,
        user_id: UUID | str,
        *,
        kind: StudySessionKind,
        plan_date: date | None = None,
    ) -> StudySession | None: ...

    def set_study_item_status(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        unit_id: str,
        status: StudyItemStatus,
    ) -> None: ...

    def complete_study_session(
        self, user_id: UUID | str, session_id: str
    ) -> None: ...

    def replace_study_session_unit(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        old_unit_id: str,
        new_unit_ids: list[str],
    ) -> StudySession | None: ...

    def study_session_for_day(
        self,
        user_id: UUID | str,
        *,
        kind: StudySessionKind,
        plan_date: date,
    ) -> StudySession | None: ...

    def record_daily_goal_met(self, user_id: UUID | str, goal_date: date) -> None: ...

    def is_daily_goal_met(self, user_id: UUID | str, goal_date: date) -> bool: ...

    def list_daily_goal_dates(
        self, user_id: UUID | str, *, until: date, limit: int = 400
    ) -> list[date]: ...

    def get_learning_plan(self, user_id: UUID | str) -> UserLearningPlan: ...

    def upsert_learning_plan(
        self,
        user_id: UUID | str,
        *,
        mode: LearningPlanMode,
        daily_target: int | None,
        prompt_dismissed_on: date | None = None,
        last_anchor_theme: str | None = None,
        as_of: date | None = None,
    ) -> UserLearningPlan: ...

    def activate_learning_plan(
        self, user_id: UUID | str, as_of: date
    ) -> UserLearningPlan: ...

    def dismiss_plan_prompt(
        self, user_id: UUID | str, as_of: date
    ) -> UserLearningPlan: ...

    def set_last_anchor_theme(
        self, user_id: UUID | str, theme: str | None
    ) -> None: ...

    def list_auto_plan_window(
        self, user_id: UUID | str, start: date, until: date
    ) -> list[AutoPlanDay]: ...

    def list_auto_plan_day(
        self, user_id: UUID | str, plan_date: date
    ) -> AutoPlanDay | None: ...

    def replace_auto_plan_day(
        self,
        user_id: UUID | str,
        plan_date: date,
        daily_target: int,
        unit_ids: Sequence[str],
    ) -> AutoPlanDay: ...

    def clear_future_auto_plan(self, user_id: UUID | str, as_of: date) -> None: ...

    def delete_auto_plan_after(self, user_id: UUID | str, horizon: date) -> None: ...

    def replace_auto_plan_window_atomic(
        self,
        user_id: UUID | str,
        as_of: date,
        horizon: date,
        days: Sequence[AutoPlanDay],
    ) -> None: ...

    def apply_auto_plan_reconcile(
        self,
        user_id: UUID | str,
        as_of: date,
        horizon: date,
        builder: Callable[[AutoPlanSnapshot], Sequence[AutoPlanDay] | None],
    ) -> None: ...

    def create_billing_order(
        self,
        user_id: UUID | str,
        *,
        order_id: str,
        plan_days: int,
        amount_paise: int,
        currency: str = "INR",
    ) -> None: ...

    def get_billing_order(
        self, user_id: UUID | str, order_id: str
    ) -> BillingOrder | None: ...

    def latest_paid_billing_order(
        self, user_id: UUID | str
    ) -> BillingOrder | None: ...

    def mark_billing_order_paid(
        self,
        user_id: UUID | str,
        *,
        order_id: str,
        payment_id: str,
        grant_id: str,
        access_ends_at: str,
    ) -> bool: ...

    def get_setting(self, user_id: UUID | str, key: str) -> str | None: ...

    def set_setting(self, user_id: UUID | str, key: str, value: str) -> None: ...

    def get_notification_frequency(
        self, user_id: UUID | str
    ) -> NotificationFrequency: ...

    def set_notification_frequency(
        self, user_id: UUID | str, frequency: NotificationFrequency
    ) -> None: ...

    def get_notification_last_slot(
        self, user_id: UUID | str
    ) -> datetime | None: ...

    def set_notification_last_slot(
        self, user_id: UUID | str, when: datetime
    ) -> None: ...

    def get_theme(self, user_id: UUID | str) -> ThemePreference: ...

    def set_theme(self, user_id: UUID | str, theme: ThemePreference) -> None: ...

    def get_news_articles_raw(self, user_id: UUID | str) -> str: ...

    def set_news_articles_raw(self, user_id: UUID | str, value: str) -> None: ...

    def mark_mode_seen(
        self, user_id: UUID | str, unit_id: str, mode: str
    ) -> set[str]: ...

    def modes_seen(self, user_id: UUID | str, unit_id: str) -> set[str]: ...

    def clear_modes_seen(self, user_id: UUID | str, unit_id: str) -> None: ...

    def clear_all_modes_seen(self, user_id: UUID | str) -> None: ...

    def modes_complete(self, user_id: UUID | str, unit_id: str) -> bool: ...

    def upsert_profile(
        self,
        user_id: UUID | str,
        *,
        display_name: str | None,
        avatar_url: str | None,
    ) -> None: ...

    def record_identity(
        self,
        user_id: UUID | str,
        *,
        email: str | None,
        phone: str | None,
    ) -> None: ...

    def get_profile(self, user_id: UUID | str) -> dict[str, str | None] | None: ...

    def needs_welcome(self, user_id: UUID | str) -> bool: ...

    def load_request_bootstrap(
        self,
        user_id: UUID | str,
        *,
        include_profile: bool = False,
        include_news: bool = False,
        include_modes: bool = False,
        include_account: bool = False,
    ) -> RequestBootstrap: ...

    def load_completion_state(
        self, user_id: UUID | str, unit_id: str
    ) -> CompletionState: ...

    def commit_completion(
        self,
        user_id: UUID | str,
        unit_id: str,
        progress: CompletionProgress,
        *,
        claim_article: str | None = None,
    ) -> ProgressRecord: ...


# Backward-compatible name used in earlier plan wording.
class ProgressRepositoryProtocol(ReminderRepositoryProtocol, Protocol):
    """Alias of ReminderRepositoryProtocol (Constitution progress surface)."""
