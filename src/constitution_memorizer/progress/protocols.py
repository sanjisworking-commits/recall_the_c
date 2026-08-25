"""Repository protocols for Constitution progress (ReminderEngine contract)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from constitution_memorizer.progress.repository import (
    BillingOrder,
    CompletionProgress,
    CompletionState,
    NotificationFrequency,
    ProgressRecord,
    ProgressStatus,
    RequestBootstrap,
    SplitMode,
    ThemePreference,
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

    def get_learning_plan(self, user_id: UUID | str): ...

    def upsert_learning_plan(
        self,
        user_id: UUID | str,
        *,
        mode: str,
        daily_target: int | None,
        activated_at: date | None = None,
        plan_prompt_dismissed_on: date | None = None,
    ): ...

    def get_study_session(self, user_id: UUID | str, session_id: str): ...

    def get_active_revision_session(self, user_id: UUID | str): ...

    def get_active_learning_session(self, user_id: UUID | str, plan_date: date): ...

    def insert_study_session(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        kind: str,
        plan_date: date,
        unit_ids: list[str],
    ): ...

    def set_study_session_status(
        self,
        user_id: UUID | str,
        session_id: str,
        status: str,
        *,
        completed_at: datetime | str | None = None,
    ) -> None: ...

    def abandon_stale_sessions(self, user_id: UUID | str, local_today: date) -> int: ...

    def abandon_unstarted_learning_sessions(self, user_id: UUID | str) -> int: ...

    def set_session_item_state(
        self,
        user_id: UUID | str,
        session_id: str,
        unit_id: str,
        state: str,
        *,
        completed_at: datetime | str | None = None,
        deferred_at: datetime | str | None = None,
    ): ...


# Backward-compatible name used in earlier plan wording.
class ProgressRepositoryProtocol(ReminderRepositoryProtocol, Protocol):
    """Alias of ReminderRepositoryProtocol (Constitution progress surface)."""
