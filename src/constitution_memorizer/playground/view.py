"""Playground presentation models. Authorization stays in access.py / roster.

These types are request-scoped view models. They are not stored and they do
not change monthly capacity, device, or payment semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REPLACEMENT_LIMIT,
    BLOCK_DEVICE_REVOKED,
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
    BLOCK_SUBSCRIPTION_PAUSED,
)
from constitution_memorizer.playground.eligibility import (
    is_playground_eligible_law,
    playground_catalogue_law,
    playground_law_source_identity,
)
from constitution_memorizer.playground.roster.models import (
    BLOCK_PROGRESS_SAVED,
    BLOCK_ROSTER_FULL,
    RESULT_NEW_BLOCKED,
)
from constitution_memorizer.playground.roster.period import (
    PLAYGROUND_TZ,
    next_playground_month_bounds,
    playground_month_name,
    playground_today,
)
from constitution_memorizer.playground.lifecycle import (
    format_study_date,
    overdue_label,
)
from constitution_memorizer.playground.source_review import (
    batch_source_presentations,
    is_law_registry_outdated,
)
from constitution_memorizer.playground.urls import (
    add_path,
    home_path,
    law_path,
    learn_path,
    learn_path_for_locator,
    roster_next_path,
    roster_path,
    sections_path,
    source_review_path_for_locator,
    source_review_section_path,
)
from constitution_memorizer.subscriptions.catalog import (
    TIER_RANK,
    UnknownSubscriptionTier,
    get_subscription_product,
    list_subscription_products,
)

PLAYGROUND_BILLING_PATH = "/billing/subscriptions"
CONSTITUTION_HOME_PATH = "/dashboard"
MANAGE_DEVICES_PATH = "/profile/security/devices"
BROWSE_LAWS_PATH = "/laws"
SAVED_PROGRESS_HOME_LIMIT = 8

TRUST_MARK = "Verbatim, always."
TRUST_HOME = "Every provision you learn is the Bare Act text, word for word."
TRUST_WORKSPACE = "Verbatim, always. Bare Act wording, never rewritten."

HOW_PLAYGROUND_WORKS: tuple[tuple[str, str, str], ...] = (
    (
        "1",
        "Choose your laws each month",
        "Pick the laws you want to learn. Your Playground holds them for the calendar month.",
    ),
    (
        "2",
        "Progress never disappears",
        "What you learn stays saved, even when a law leaves your Playground.",
    ),
    (
        "3",
        "Next month, decide what to keep",
        "Carry laws forward, or make room for something new.",
    ),
    (
        "4",
        "Read the law, verbatim",
        "Every provision is the Bare Act text. Verbatim, always.",
    ),
)

# Law-level badges. Mastered > Due > Learned > Learning > Not started.
STATUS_NOT_STARTED = "not_started"
STATUS_LEARNING = "learning"
STATUS_LEARNED = "learned"
STATUS_DUE = "due"
STATUS_MASTERED = "mastered"

STATUS_LABELS = {
    STATUS_NOT_STARTED: "Not started",
    STATUS_LEARNING: "Learning",
    STATUS_LEARNED: "Learned",
    STATUS_DUE: "Due",
    STATUS_MASTERED: "Mastered",
}

MEMBERSHIP_IN = "in_playground"
MEMBERSHIP_SAVED = "progress_saved"
MEMBERSHIP_REMOVED = "removed_this_month"
MEMBERSHIP_FULL = "playground_full"

KIND_UNAVAILABLE = "unavailable"
KIND_GUEST = "guest"
KIND_SUBSCRIBE = "subscribe"
KIND_RESUME = "resume"
KIND_DEVICE_BLOCKED = "device_blocked"
KIND_PENDING = "pending"
KIND_ROSTER_FULL = "roster_full"
KIND_ALREADY_ACTIVE = "already_active"
KIND_RE_ADD = "re_add"
KIND_ELIGIBLE_TO_ADD = "eligible_to_add"

ACT_HEAD_KINDS = frozenset(
    {
        KIND_UNAVAILABLE,
        KIND_GUEST,
        KIND_SUBSCRIBE,
        KIND_RESUME,
        KIND_DEVICE_BLOCKED,
        KIND_PENDING,
        KIND_ROSTER_FULL,
        KIND_ALREADY_ACTIVE,
        KIND_RE_ADD,
        KIND_ELIGIBLE_TO_ADD,
    }
)

_DEVICE_BLOCK_REASONS = frozenset(
    {
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_CONFIG_ERROR,
        BLOCK_DEVICE_REPLACEMENT_LIMIT,
    }
)
_RESUME_REASONS = frozenset(
    {
        BLOCK_SUBSCRIPTION_PAUSED,
        BLOCK_PAYMENT_HALTED,
        BLOCK_PAID_PERIOD_ENDED,
    }
)


@dataclass(frozen=True)
class MembershipIndex:
    """Batched roster/overlay facts for law-state CTAs. Not stored."""

    active_ids: frozenset[str]
    removed_ids: frozenset[str]
    overlay_ids: frozenset[str]
    remaining: int | None
    month_name: str = ""


@dataclass(frozen=True)
class PaymentBannerView:
    kind: str
    title: str
    body: str = ""
    cta_label: str = ""
    cta_href: str = ""
    quiet: bool = False


@dataclass(frozen=True)
class CataloguePlanView:
    tier: str
    display_name: str
    price_inr: int
    price_label: str
    limit_label: str
    cta_label: str
    href: str


@dataclass(frozen=True)
class PlaygroundGateView:
    reason: str
    eyebrow: str
    title: str
    lines: tuple[str, ...]
    cta_label: str
    cta_href: str
    secondary_label: str = ""
    secondary_href: str = ""
    show_how: bool = False
    show_saved: bool = False
    consume_blocked: bool = False
    show_plans: bool = False
    show_included: bool = False
    plans: tuple[CataloguePlanView, ...] = ()
    from_price: str = ""
    hard_gate: bool = True


@dataclass(frozen=True)
class LawPlaygroundState:
    """CTA/badge for one eligible law. Not a DB row.

    ``kind`` is the discriminated Act-head / Add state. Templates switch on
    kind only — never on raw tier strings.
    """

    law_id: str
    kind: str
    eligible: bool
    active_this_period: bool
    removed_this_period: bool
    historical_overlay: bool
    can_consume_new: bool
    roster_full: bool
    guest: bool
    subscribed: bool
    primary_label: str
    primary_href: str
    badge: str
    badge_label: str
    secondary_copy: str = ""
    secondary_label: str = ""
    secondary_href: str = ""
    method: str = "get"
    opens_sheet: bool = False
    skip_confirm: bool = False


@dataclass(frozen=True)
class RosterCapacityView:
    month_name: str
    period_start: date
    used: int
    law_limit: int | None
    remaining: int | None
    active_count: int
    removed_consumed_count: int
    unlimited: bool
    full: bool
    used_label: str
    remaining_label: str
    legend_in: str
    legend_removed: str
    legend_available: str
    aria_label: str


@dataclass(frozen=True)
class LawCardView:
    law_id: str
    title: str
    short_title: str
    selected_count: int
    learned_count: int
    due_count: int
    overdue_count: int
    status: str
    status_label: str
    outdated: bool
    primary_label: str
    primary_href: str
    read_href: str
    manage_href: str
    is_next: bool = False
    membership: str = MEMBERSHIP_IN
    membership_label: str = "In Playground"
    add_href: str = ""
    add_label: str = ""
    learning_count: int = 0
    mastered_count: int = 0
    affected_learned_count: int = 0
    source_status: str = "unchanged"
    review_href: str = ""
    home_note: str = ""
    provisions_copy: str = ""
    learned_pct: int = 0


@dataclass(frozen=True)
class PlaygroundSubscriptionCard:
    """Profile SUBSCRIPTION card. Snapshot is the authority; no device ids."""

    title: str
    chip: str
    chip_kind: str
    body: str
    stat_big: str
    stat_label: str
    cta_label: str
    cta_href: str
    show: bool = True


@dataclass(frozen=True)
class PlaygroundHomeView:
    capacity: RosterCapacityView
    browse_href: str
    manage_href: str
    manage_label: str
    plan_next_href: str
    plan_next_label: str
    next_month_name: str
    empty: bool
    due_today: int
    to_learn: int
    sections_learned: int
    sections_selected: int
    active: tuple[LawCardView, ...]
    removed: tuple[LawCardView, ...]
    saved: tuple[LawCardView, ...]
    banner: PaymentBannerView | None
    quiet: PaymentBannerView | None
    read_only: bool = False
    resume_label: str = ""
    resume_href: str = ""
    heading: str = "Playground"
    kicker: str = "My Playground"
    month_count_label: str = ""
    add_law_href: str = BROWSE_LAWS_PATH
    add_law_label: str = "Add a law"


def format_plan_end(value: datetime | date | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        local = value.astimezone(PLAYGROUND_TZ)
        return f"{local.day} {local.strftime('%B')}"
    return f"{value.day} {value.strftime('%B')}"


def display_status_for_summary(
    *,
    selected: int,
    learned: int,
    due: int,
    learning: int = 0,
    mastered: int = 0,
) -> str:
    """Law-card lifecycle: Mastered > Due > Learned > Learning > Not started.

    Cloze-complete is not as final Learned. Product Learned requires all six
    initial methods (M8).
    """

    if mastered > 0:
        return STATUS_MASTERED
    if due > 0:
        return STATUS_DUE
    if learned > 0:
        return STATUS_LEARNED
    if learning > 0:
        return STATUS_LEARNING
    del selected
    return STATUS_NOT_STARTED


def display_status_for_progress(
    progress: Any, *, as_of: date, mode_progress: Any = None
) -> str:
    status = str(getattr(progress, "status", "") or "") if progress is not None else ""
    if status == "mastered":
        return STATUS_MASTERED
    next_rev = getattr(progress, "next_revision", None) if progress is not None else None
    if next_rev and str(next_rev)[:10] <= as_of.isoformat():
        return STATUS_DUE
    if status in {"learned", "review"}:
        return STATUS_LEARNED
    completed = int(getattr(mode_progress, "completed_count", 0) or 0)
    if completed > 0:
        return STATUS_LEARNING
    if progress is not None and getattr(progress, "cloze_done", False):
        return STATUS_LEARNING
    return STATUS_NOT_STARTED


def catalog_titles(law_id: str) -> tuple[str, str]:
    catalog = playground_catalogue_law(law_id)
    if catalog is None:
        return law_id, law_id
    return catalog.title, catalog.short_title


def capacity_view(
    *,
    period_start: date,
    used: int,
    law_limit: int | None,
    remaining: int | None,
    active_count: int,
    removed_consumed_count: int,
    planned: bool = False,
    surface: str = "home",
) -> RosterCapacityView:
    month = playground_month_name(period_start)
    unlimited = law_limit is None
    full = (not unlimited) and remaining == 0
    if unlimited:
        noun = "law" if used == 1 else "laws"
        used_label = f"{used} {noun} this month" if planned is False else f"{used} planned"
        remaining_label = "Unlimited"
    elif surface == "roster":
        used_label = f"{used} of {law_limit} used"
        remaining_label = f"{remaining} remaining"
    elif full:
        used_label = f"{used} of {law_limit} laws"
        remaining_label = (
            f"Playground full for {month}"
            if not planned
            else f"{month} is full"
        )
    elif planned:
        used_label = f"{used} of {law_limit} planned"
        spaces = remaining or 0
        remaining_label = f"{spaces} space{'s' if spaces != 1 else ''} available"
    else:
        used_label = f"{used} of {law_limit} laws"
        spaces = remaining or 0
        remaining_label = f"{spaces} space{'s' if spaces != 1 else ''} available"
    legend_in = f"{active_count} in Playground"
    legend_removed = (
        f"{removed_consumed_count} removed this month · space still used"
        if removed_consumed_count
        else ""
    )
    avail = remaining if remaining is not None else 0
    legend_available = f"{avail} available" if not unlimited else "Unlimited"
    aria = (
        f"{used} laws this month, unlimited."
        if unlimited
        else f"{used} of {law_limit} {month} law spaces used. {remaining_label}."
    )
    return RosterCapacityView(
        month_name=month,
        period_start=period_start,
        used=used,
        law_limit=law_limit,
        remaining=remaining,
        active_count=active_count,
        removed_consumed_count=removed_consumed_count,
        unlimited=unlimited,
        full=full,
        used_label=used_label,
        remaining_label=remaining_label,
        legend_in=legend_in,
        legend_removed=legend_removed,
        legend_available=legend_available,
        aria_label=aria,
    )


def add_confirm_copy(
    *,
    short_title: str,
    month_name: str,
    law_limit: int | None,
    remaining_after: int | None,
    historical: bool,
    re_add: bool,
) -> tuple[str, tuple[str, ...]]:
    if re_add:
        title = f"Add {short_title} back to {month_name}?"
        lines = (
            "Your progress will be saved.",
            "No extra space used.",
        )
        return title, lines
    if law_limit is None:
        return f"Add {short_title} to {month_name} Playground?", ()
    remaining = 0 if remaining_after is None else remaining_after
    title = f"Add {short_title} to {month_name}?"
    lines = [
        f"This will use 1 of your {law_limit} law spaces for {month_name}.",
        f"You'll have {remaining} space{'s' if remaining != 1 else ''} remaining.",
    ]
    if historical:
        lines.append("Your saved progress comes with it.")
    return title, tuple(lines)


def device_count_copy(active_count: int, device_limit: int | None) -> str:
    """T26: 'n of limit' from the device service. Never a hard-coded 2 of 3."""

    count = max(0, int(active_count or 0))
    if device_limit is None:
        noun = "device" if count == 1 else "devices"
        return f"{count} {noun}"
    return f"{count} of {int(device_limit)}"


ROLLOVER_SUBMIT_CONTINUE = "Continue with these"
ROLLOVER_SUBMIT_DONE = "Done"
_RESOLVED_ROLLOVER = frozenset({"keep", "decline"})


def _rollover_decision(row: Any) -> str:
    if isinstance(row, dict):
        value = row.get("target_decision")
    else:
        value = getattr(row, "target_decision", None)
    return str(value or "").strip()


def rollover_candidates_resolved(candidates: Any) -> bool:
    """True when every candidate is Keep or Remove, or there are none."""

    rows = list(candidates or ())
    if not rows:
        return True
    return all(_rollover_decision(row) in _RESOLVED_ROLLOVER for row in rows)


def rollover_submit_label(
    candidates: Any,
    *,
    adjustment_required: bool = False,
) -> str:
    """Single server-derived CTA. Unresolved candidates never yield Done."""

    if adjustment_required or not rollover_candidates_resolved(candidates):
        return ROLLOVER_SUBMIT_CONTINUE
    return ROLLOVER_SUBMIT_DONE


def _scheduled_tier_display(tier: str) -> str:
    key = str(tier or "").strip()
    if not key:
        return ""
    try:
        return get_subscription_product(key).display_name
    except UnknownSubscriptionTier:
        return key.title()


def playground_subscription_card(snapshot: Any | None) -> PlaygroundSubscriptionCard:
    """T26: chip and stats from the entitlement snapshot only."""

    hidden = PlaygroundSubscriptionCard(
        title="",
        chip="",
        chip_kind="none",
        body="",
        stat_big="",
        stat_label="",
        cta_label="",
        cta_href=PLAYGROUND_BILLING_PATH,
        show=False,
    )
    if snapshot is None or not getattr(snapshot, "is_authenticated", False):
        return hidden
    reason = str(getattr(snapshot, "playground_block_reason", None) or "")
    tier = str(getattr(snapshot, "tier", None) or "").strip()
    title = f"RecallC {tier.title()}" if tier else "Playground"
    limit = getattr(snapshot, "playground_law_limit", None)
    limit_line = catalogue_limit_label(limit)
    period = format_plan_end(getattr(snapshot, "billing_period_end", None))
    if reason == BLOCK_SUBSCRIPTION_PAUSED:
        return PlaygroundSubscriptionCard(
            title=title,
            chip="PAUSED",
            chip_kind="paused",
            body="Playground is paused. Resume to keep learning this month’s laws.",
            stat_big="",
            stat_label=limit_line,
            cta_label="Resume Playground",
            cta_href=PLAYGROUND_BILLING_PATH,
        )
    if reason == BLOCK_PAYMENT_HALTED:
        return PlaygroundSubscriptionCard(
            title=title,
            chip="ON HOLD",
            chip_kind="hold",
            body="Payment retries have stopped. Resume Playground when you are ready.",
            stat_big="",
            stat_label=limit_line,
            cta_label="Resume Playground",
            cta_href=PLAYGROUND_BILLING_PATH,
        )
    if reason == BLOCK_PAID_PERIOD_ENDED:
        return PlaygroundSubscriptionCard(
            title=title,
            chip="PAUSED",
            chip_kind="paused",
            body="This paid period has ended. Playground stays saved until you resume.",
            stat_big="",
            stat_label=limit_line,
            cta_label="Resume Playground",
            cta_href=PLAYGROUND_BILLING_PATH,
        )
    status = str(getattr(snapshot, "subscription_status", None) or "")
    if status == "pending":
        return PlaygroundSubscriptionCard(
            title=title or "Playground",
            chip="PENDING",
            chip_kind="pending",
            body=(
                "Payment retry in progress. Existing Playground stays available. "
                "New laws are temporarily unavailable."
            ),
            stat_big="",
            stat_label=limit_line,
            cta_label="Manage subscription",
            cta_href=PLAYGROUND_BILLING_PATH,
        )
    if not getattr(snapshot, "is_subscribed", False) and reason in {
        BLOCK_NOT_SUBSCRIBED,
        "",
        None,
    }:
        if getattr(snapshot, "admin_override", False):
            return PlaygroundSubscriptionCard(
                title="Playground",
                chip="",
                chip_kind="none",
                body="Admin access. No billing attached.",
                stat_big="",
                stat_label="",
                cta_label="Manage Playground",
                cta_href=home_path(),
            )
        return PlaygroundSubscriptionCard(
            title="Playground",
            chip="",
            chip_kind="none",
            body="Subscribe to add Bare Acts to a monthly Playground.",
            stat_big="",
            stat_label="",
            cta_label="Subscribe",
            cta_href=PLAYGROUND_BILLING_PATH,
        )
    renew = f" Current paid period ends {period}." if period else ""
    stat_big = "∞" if limit is None else str(limit)
    cancel_at_end = bool(getattr(snapshot, "cancel_at_period_end", False))
    scheduled = str(getattr(snapshot, "scheduled_tier", None) or "").strip()
    if cancel_at_end:
        body = "ACTIVE. Cancels at the end of the current paid period."
    elif scheduled:
        next_name = _scheduled_tier_display(scheduled)
        body = f"ACTIVE. Changes to {next_name} at the end of the current paid period."
    else:
        body = f"This month’s Playground is open.{renew}"
    return PlaygroundSubscriptionCard(
        title=title or "Playground",
        chip="ACTIVE",
        chip_kind="active",
        body=body,
        stat_big=stat_big,
        stat_label=limit_line,
        cta_label="Manage plan",
        cta_href=PLAYGROUND_BILLING_PATH,
    )


def roster_law_cards(
    *,
    overlay: Any,
    roster: Any,
    user_id: Any,
) -> tuple[tuple[LawCardView, ...], tuple[LawCardView, ...]]:
    """Active / removed roster rows from Stage 1 summaries. Restyle only."""

    active_items = roster.active_roster_items(user_id)
    removed_items = roster.removed_roster_items(user_id)
    ids = [item.law_id for item in active_items] + [
        item.law_id for item in removed_items
    ]
    summaries = overlay.list_playground_summaries(
        user_id, as_of=playground_today(), law_ids=ids
    )
    by_id = {row.law_id: row for row in summaries}
    active: list[LawCardView] = []
    for item in active_items:
        row = by_id.get(item.law_id)
        href = law_path(item.law_id)
        label = "Continue"
        if row is None or row.selected_count == 0:
            href = sections_path(item.law_id)
            label = "Start learning"
        if row is None:
            card = _stub_card(
                item.law_id,
                membership=MEMBERSHIP_IN,
                membership_label="In Playground",
                primary_label=label,
                primary_href=href,
            )
        else:
            card = _card_from_summary(
                row,
                membership=MEMBERSHIP_IN,
                membership_label="In Playground",
                primary_label=label,
                primary_href=href,
            )
        if card is not None:
            active.append(card)
    removed: list[LawCardView] = []
    for item in removed_items:
        row = by_id.get(item.law_id)
        if row is None:
            card = _stub_card(
                item.law_id,
                membership=MEMBERSHIP_REMOVED,
                membership_label="Removed this month",
                primary_label="Add back",
                primary_href=add_path(item.law_id),
            )
        else:
            card = _card_from_summary(
                row,
                membership=MEMBERSHIP_REMOVED,
                membership_label="Removed this month",
                primary_label="Add back",
                primary_href=add_path(item.law_id),
            )
        if card is not None:
            removed.append(card)
    return tuple(active), tuple(removed)


def catalogue_from_price() -> str:
    products = list_subscription_products()
    if not products:
        return ""
    lowest = min(int(row.price_inr) for row in products)
    return f"from ₹{lowest}"


def catalogue_limit_label(limit: int | None) -> str:
    if limit is None:
        return "Unlimited laws / month"
    noun = "law" if limit == 1 else "laws"
    return f"{limit} {noun} / month"


def catalogue_plan_views(
    *,
    current_tier: str | None = None,
    href: str = PLAYGROUND_BILLING_PATH,
) -> tuple[CataloguePlanView, ...]:
    current_rank = TIER_RANK.get(str(current_tier or ""), 0)
    plans: list[CataloguePlanView] = []
    for product in list_subscription_products():
        rank = TIER_RANK.get(product.tier, 0)
        if current_rank and rank <= current_rank:
            continue
        cta = (
            f"Upgrade to {product.display_name}"
            if current_rank
            else f"Subscribe to {product.display_name}"
        )
        plans.append(
            CataloguePlanView(
                tier=product.tier,
                display_name=product.display_name,
                price_inr=product.price_inr,
                price_label=f"₹{product.price_inr}",
                limit_label=catalogue_limit_label(product.playground_law_limit),
                cta_label=cta,
                href=href,
            )
        )
    return tuple(plans)


def skips_add_confirm(access: Any) -> bool:
    """Max (unlimited) and local/admin skip the numeric confirm step."""

    if getattr(access, "local_owner", False):
        return True
    snapshot = getattr(access, "snapshot", None)
    if snapshot is None:
        return False
    if getattr(snapshot, "admin_override", False):
        return True
    return snapshot.playground_law_limit is None


def entire_act_meta(law_id: str, *, act: Any = None) -> str:
    from constitution_memorizer.playground.source import locators_for_act

    locators = locators_for_act(law_id, act=act)
    n = len(locators)
    noun = "section" if n == 1 else "sections"
    return f"{n} learnable {noun}"


def remove_confirm_copy(short_title: str, month_name: str) -> tuple[str, tuple[str, ...]]:
    return (
        f"Remove from {month_name}",
        (
            "Your progress will be saved.",
            "This does not free a law space this month.",
        ),
    )


def load_membership_index(access: Any, roster: Any, overlay: Any) -> MembershipIndex:
    """Three list queries plus peek_capacity. Never N+1. Never writes a period."""

    if access.user_id is None or roster is None:
        return MembershipIndex(frozenset(), frozenset(), frozenset(), None)
    active_ids = frozenset(
        item.law_id for item in roster.active_roster_items(access.user_id)
    )
    removed_ids = frozenset(
        item.law_id for item in roster.removed_roster_items(access.user_id)
    )
    overlay_ids = frozenset()
    if overlay is not None:
        overlay_ids = frozenset(item.law_id for item in overlay.list_items(access.user_id))
    cap = roster.peek_capacity(
        access.user_id, access.snapshot, local_owner=access.local_owner
    )
    return MembershipIndex(
        active_ids=active_ids,
        removed_ids=removed_ids,
        overlay_ids=overlay_ids,
        remaining=cap.remaining,
        month_name=playground_month_name(cap.period_start),
    )


def _commercial_kind(access: Any) -> str | None:
    """Hard-gate / resume kinds from commercial + device, before roster."""

    if access.user_id is None:
        return KIND_GUEST
    if access.local_owner or bool(getattr(access, "can_open", False)):
        return None
    snapshot = access.snapshot
    reason = (
        snapshot.playground_block_reason
        if snapshot is not None
        else BLOCK_NOT_SUBSCRIBED
    )
    if reason in _DEVICE_BLOCK_REASONS:
        return KIND_DEVICE_BLOCKED
    if reason in _RESUME_REASONS:
        return KIND_RESUME
    return KIND_SUBSCRIBE


def law_membership(
    *,
    law_id: str,
    access: Any,
    roster: Any,
    overlay: Any,
    index: MembershipIndex | None = None,
) -> LawPlaygroundState:
    """Public/Bare Act/home CTA for one law. Does not hydrate an Act."""

    guest = bool(access.user_id is None)
    eligible = is_playground_eligible_law(law_id)
    snapshot = access.snapshot
    subscribed = bool(
        access.local_owner
        or (snapshot is not None and (snapshot.is_subscribed or snapshot.admin_override))
    )
    can_consume = bool(access.can_consume_new_law or access.local_owner)
    skip = skips_add_confirm(access)

    def _state(
        kind: str,
        *,
        active: bool = False,
        removed: bool = False,
        historical: bool = False,
        roster_full: bool = False,
        primary_label: str = "",
        primary_href: str = "",
        badge: str = "",
        badge_label: str = "",
        secondary_copy: str = "",
        secondary_label: str = "",
        secondary_href: str = "",
        opens_sheet: bool = False,
        consume: bool | None = None,
    ) -> LawPlaygroundState:
        return LawPlaygroundState(
            law_id=law_id,
            kind=kind,
            eligible=eligible,
            active_this_period=active,
            removed_this_period=removed,
            historical_overlay=historical,
            can_consume_new=can_consume if consume is None else consume,
            roster_full=roster_full,
            guest=guest,
            subscribed=subscribed,
            primary_label=primary_label,
            primary_href=primary_href,
            badge=badge,
            badge_label=badge_label,
            secondary_copy=secondary_copy,
            secondary_label=secondary_label,
            secondary_href=secondary_href,
            opens_sheet=opens_sheet,
            skip_confirm=skip,
        )

    if not eligible:
        return _state(KIND_UNAVAILABLE)

    blocked = _commercial_kind(access)
    if blocked == KIND_GUEST:
        return _state(
            KIND_GUEST,
            primary_label="Sign in to use Playground",
            primary_href=add_path(law_id),
            secondary_copy="Sign in to add this law to Playground.",
            opens_sheet=True,
        )
    if blocked == KIND_SUBSCRIBE:
        return _state(
            KIND_SUBSCRIBE,
            primary_label="Subscribe to use Playground",
            primary_href=add_path(law_id),
            secondary_copy=f"Unlock Playground · {catalogue_from_price()} / month.",
            opens_sheet=True,
        )
    if blocked == KIND_RESUME:
        reason = (
            snapshot.playground_block_reason
            if snapshot is not None
            else BLOCK_SUBSCRIPTION_PAUSED
        )
        gate = gate_view(reason=reason or BLOCK_SUBSCRIPTION_PAUSED)
        return _state(
            KIND_RESUME,
            primary_label="Resume Playground",
            primary_href=gate.cta_href or PLAYGROUND_BILLING_PATH,
            secondary_copy=" ".join(part for part in (gate.title,) + gate.lines if part),
            opens_sheet=True,
        )
    if blocked == KIND_DEVICE_BLOCKED:
        reason = (
            snapshot.playground_block_reason
            if snapshot is not None
            else BLOCK_DEVICE_LIMIT
        )
        gate = gate_view(reason=reason or BLOCK_DEVICE_LIMIT)
        return _state(
            KIND_DEVICE_BLOCKED,
            primary_label=gate.cta_label,
            primary_href=gate.cta_href,
            secondary_copy=" ".join(part for part in (gate.title,) + gate.lines if part),
        )

    if index is not None:
        active = law_id in index.active_ids
        removed = law_id in index.removed_ids
        historical = law_id in index.overlay_ids
        remaining = index.remaining
        month = index.month_name or "this month"
    else:
        active = False
        removed = False
        consumed = False
        remaining = None
        month = "this month"
        if access.user_id is not None and roster is not None:
            active = roster.is_law_active_this_period(access.user_id, law_id)
            consumed = roster.already_consumed_this_period(access.user_id, law_id)
            removed = consumed and not active
            if snapshot is not None and snapshot.playground_laws_remaining is not None:
                remaining = snapshot.playground_laws_remaining
            else:
                cap = roster.peek_capacity(
                    access.user_id, snapshot, local_owner=access.local_owner
                )
                remaining = cap.remaining
                month = playground_month_name(cap.period_start)
        if snapshot is not None and snapshot.playground_period_start is not None:
            month = playground_month_name(snapshot.playground_period_start)
        historical = False
        if access.user_id is not None and overlay is not None:
            historical = overlay.get_item(access.user_id, law_id) is not None
    roster_full = remaining == 0 and not (active or removed)
    if active:
        if not subscribed:
            return _state(
                KIND_SUBSCRIBE,
                primary_label="Subscribe to use Playground",
                primary_href=add_path(law_id),
                secondary_copy=f"Unlock Playground · {catalogue_from_price()} / month.",
                opens_sheet=True,
            )
        href = law_path(law_id)
        label = "Continue"
        sections_href = sections_path(law_id)
        if overlay is not None and access.user_id is not None:
            item = overlay.get_item(access.user_id, law_id)
            selection = overlay.list_selection(access.user_id, law_id) if item else []
            if not selection:
                href = sections_href
                label = "Start learning"
        return _state(
            KIND_ALREADY_ACTIVE,
            active=True,
            historical=historical,
            primary_label=label,
            primary_href=href,
            badge=MEMBERSHIP_IN,
            badge_label="Already in Playground",
            secondary_label="Sections",
            secondary_href=sections_href,
        )
    if removed:
        return _state(
            KIND_RE_ADD,
            removed=True,
            historical=True,
            primary_label="Add back",
            primary_href=add_path(law_id),
            badge=MEMBERSHIP_REMOVED,
            badge_label="Removed this month",
            secondary_copy="No extra space used.",
            opens_sheet=True,
        )
    if roster_full:
        return _state(
            KIND_ROSTER_FULL,
            historical=historical,
            roster_full=True,
            primary_label="Playground full this month",
            primary_href=add_path(law_id),
            badge=MEMBERSHIP_FULL,
            badge_label="Playground full this month",
            secondary_copy="Plan next month",
            secondary_label="Plan next month",
            secondary_href=roster_next_path(),
            opens_sheet=True,
        )
    if historical:
        if not can_consume:
            return _state(
                KIND_PENDING,
                historical=True,
                consume=False,
                primary_label="Manage subscription",
                primary_href=PLAYGROUND_BILLING_PATH,
                badge=MEMBERSHIP_SAVED,
                badge_label="Progress saved",
                secondary_copy="Adding new laws is temporarily unavailable",
            )
        return _state(
            KIND_ELIGIBLE_TO_ADD,
            historical=True,
            consume=True,
            primary_label="Add to this month",
            primary_href=add_path(law_id),
            badge=MEMBERSHIP_SAVED,
            badge_label="Progress saved",
            opens_sheet=True,
            secondary_copy=(
                f"You studied this law previously. "
                f"Add it to {month} to continue where you left off."
            ),
        )
    if not can_consume:
        return _state(
            KIND_PENDING,
            consume=False,
            primary_label="Manage subscription",
            primary_href=PLAYGROUND_BILLING_PATH,
            secondary_copy="Adding new laws is temporarily unavailable",
        )
    return _state(
        KIND_ELIGIBLE_TO_ADD,
        primary_label="+ Add to Playground",
        opens_sheet=True,
        primary_href=add_path(law_id),
    )


def gate_view(
    *,
    reason: str,
    consume_blocked: bool = False,
    cta_href: str = "",
    secondary_href: str = "",
    month_name: str = "",
) -> PlaygroundGateView:
    if consume_blocked or reason == RESULT_NEW_BLOCKED:
        return PlaygroundGateView(
            reason=RESULT_NEW_BLOCKED,
            eyebrow="Playground",
            title="Adding new laws is temporarily unavailable",
            lines=(
                "You can continue your current Playground.",
                "Adding new laws is temporarily unavailable.",
            ),
            cta_label="Manage subscription",
            cta_href=cta_href or PLAYGROUND_BILLING_PATH,
            consume_blocked=True,
        )
    if reason == BLOCK_SIGN_IN_REQUIRED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground",
            title="Sign in to use Playground",
            lines=(
                "Turns any Act into a learning experience. Sign in to view plans.",
            ),
            cta_label="Sign in",
            cta_href=cta_href or f"/login?next={home_path()}",
            show_how=True,
            hard_gate=True,
        )
    if reason == BLOCK_NOT_SUBSCRIBED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground",
            title="Unlock Playground",
            lines=("Playground adds structured learning for laws.",),
            cta_label="View Playground plans",
            cta_href=cta_href or PLAYGROUND_BILLING_PATH,
            show_how=True,
            show_included=True,
            show_plans=True,
            plans=catalogue_plan_views(),
            from_price=catalogue_from_price(),
            hard_gate=True,
        )
    if reason == BLOCK_DEVICE_LIMIT:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground on this device",
            title="Device limit reached",
            lines=(
                "Your subscription supports Playground on up to 2 registered devices.",
            ),
            cta_label="Manage devices",
            cta_href=cta_href or MANAGE_DEVICES_PATH,
            secondary_label="Back to Constitution",
            secondary_href=secondary_href or CONSTITUTION_HOME_PATH,
        )
    if reason == BLOCK_DEVICE_REVOKED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground on this device",
            title="This device no longer has Playground access.",
            lines=(),
            cta_label="Manage devices",
            cta_href=cta_href or MANAGE_DEVICES_PATH,
        )
    if reason == BLOCK_DEVICE_REPLACEMENT_LIMIT:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground on this device",
            title="Too many recent device changes",
            lines=(
                "For account security, new Playground devices are temporarily limited after several replacements.",
                "Your Constitution access and saved progress are unaffected.",
            ),
            cta_label="Contact support" if cta_href else "Back to Constitution",
            cta_href=cta_href or CONSTITUTION_HOME_PATH,
            secondary_label="Back to Constitution" if cta_href else "",
            secondary_href=CONSTITUTION_HOME_PATH if cta_href else "",
        )
    if reason == BLOCK_DEVICE_CONFIG_ERROR:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground on this device",
            title="Playground is temporarily unavailable on this device",
            lines=("Constitution Learn stays available. Try again from this installation later.",),
            cta_label="Back to Constitution",
            cta_href=CONSTITUTION_HOME_PATH,
        )
    if reason == BLOCK_PAYMENT_HALTED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground subscription",
            title="Payment retries have stopped",
            lines=("Playground learning is paused. Your progress is saved.",),
            cta_label="Manage subscription",
            cta_href=cta_href or PLAYGROUND_BILLING_PATH,
            secondary_label="Back to Constitution",
            secondary_href=CONSTITUTION_HOME_PATH,
            show_saved=True,
        )
    if reason == BLOCK_SUBSCRIPTION_PAUSED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground subscription",
            title="Playground subscription paused",
            lines=("Your laws and learning progress are saved.",),
            cta_label="Manage subscription",
            cta_href=cta_href or PLAYGROUND_BILLING_PATH,
            show_saved=True,
        )
    if reason == BLOCK_PAID_PERIOD_ENDED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground subscription",
            title="Your Playground is paused",
            lines=(
                "Your roster and progress are still here. Resume a Playground plan to continue learning.",
            ),
            cta_label="View Playground plans",
            cta_href=cta_href or PLAYGROUND_BILLING_PATH,
            secondary_label="Back to Constitution",
            secondary_href=CONSTITUTION_HOME_PATH,
            show_saved=True,
        )
    if reason == BLOCK_ROSTER_FULL:
        month = month_name or "this month"
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground",
            title="Playground full this month",
            lines=(
                f"Existing {month} laws remain fully usable.",
                "Removing a law does not free a space this month.",
            ),
            cta_label="Plan next month",
            cta_href=roster_next_path(),
            secondary_label="Back to Playground",
            secondary_href=home_path(),
            hard_gate=False,
        )
    if reason == BLOCK_PROGRESS_SAVED:
        return PlaygroundGateView(
            reason=reason,
            eyebrow="Playground",
            title="Progress saved",
            lines=(
                "You studied this law previously.",
                f"Add it to {month_name or 'this month'} to continue where you left off.",
            ),
            cta_label="Add to this month",
            cta_href=cta_href,
            secondary_label="Back to Playground",
            secondary_href=home_path(),
            hard_gate=False,
        )
    return PlaygroundGateView(
        reason=reason,
        eyebrow="Playground",
        title="Playground",
        lines=(),
        cta_label="Back to Playground",
        cta_href=home_path(),
    )


def payment_banners(
    *,
    access: Any,
    notice: str = "",
    has_saved_progress: bool = False,
    current_used: int = 0,
    month_name: str = "",
) -> tuple[PaymentBannerView | None, PaymentBannerView | None]:
    """Return (shell banner, quiet hero line). Uses snapshot only."""

    snapshot = access.snapshot
    if snapshot is None:
        return None, None
    read_only = bool(getattr(access, "can_view_home", False) and not access.can_open)
    if not access.can_open and not read_only:
        return None, None
    banner: PaymentBannerView | None = None
    quiet: PaymentBannerView | None = None
    if read_only:
        reason = snapshot.playground_block_reason or BLOCK_SUBSCRIPTION_PAUSED
        if reason == BLOCK_PAYMENT_HALTED:
            banner = PaymentBannerView(
                kind="halted",
                title="Payment retries have stopped",
                body="Playground learning is paused. Your progress is saved.",
                cta_label="Resume Playground",
                cta_href=PLAYGROUND_BILLING_PATH,
            )
        elif reason == BLOCK_PAID_PERIOD_ENDED:
            banner = PaymentBannerView(
                kind="expired",
                title="Your Playground is paused",
                body="Your roster and progress are still here. Resume a Playground plan to continue learning.",
                cta_label="Resume Playground",
                cta_href=PLAYGROUND_BILLING_PATH,
            )
        else:
            banner = PaymentBannerView(
                kind="paused",
                title="Playground subscription paused",
                body="Your laws and learning progress are saved.",
                cta_label="Resume Playground",
                cta_href=PLAYGROUND_BILLING_PATH,
            )
        return banner, None
    status = snapshot.subscription_status
    if status == "pending" and not access.can_consume_new_law:
        banner = PaymentBannerView(
            kind="pending",
            title="Payment retry in progress",
            body="You can continue your current Playground. Adding new laws is temporarily unavailable.",
            cta_label="Manage subscription",
            cta_href=PLAYGROUND_BILLING_PATH,
        )
    if notice == "upgrade":
        limit = snapshot.playground_law_limit
        title = (
            f"Your Playground now supports {limit} laws."
            if limit is not None
            else "Your Playground now supports more laws."
        )
        banner = PaymentBannerView(kind="upgrade", title=title)
    if notice == "welcome" or (
        has_saved_progress and current_used == 0 and status == "active"
    ):
        banner = PaymentBannerView(
            kind="resubscribed",
            title="Welcome back",
            body=f"Your saved law progress is ready. Build your {month_name or 'monthly'} Playground.",
        )
    if snapshot.cancel_at_period_end:
        end = format_plan_end(snapshot.billing_period_end)
        quiet = PaymentBannerView(
            kind="cancel_at_period_end",
            title=f"Plan ends {end}" if end else "Cancels at period end",
            cta_label="Manage subscription",
            cta_href=PLAYGROUND_BILLING_PATH,
            quiet=True,
        )
    scheduled = snapshot.scheduled_tier or ""
    current_tier = snapshot.tier or ""
    if scheduled and current_tier and TIER_RANK.get(scheduled, 0) < TIER_RANK.get(current_tier, 0):
        try:
            current_name = get_subscription_product(current_tier).display_name
            next_name = get_subscription_product(scheduled).display_name
        except UnknownSubscriptionTier:
            current_name, next_name = current_tier, scheduled
        end = format_plan_end(snapshot.billing_period_end)
        until = f"{current_name} until {end}" if end else current_name
        quiet = PaymentBannerView(
            kind="scheduled_downgrade",
            title=until,
            body=f"Changes to {next_name} next billing cycle",
            cta_label="Manage subscription",
            cta_href=PLAYGROUND_BILLING_PATH,
            quiet=True,
        )
    return banner, quiet


def _card_from_summary(
    summary: Any,
    *,
    membership: str,
    membership_label: str,
    primary_label: str,
    primary_href: str,
    add_href: str = "",
    add_label: str = "",
    is_next: bool = False,
) -> LawCardView | None:
    if not is_playground_eligible_law(summary.law_id):
        return None
    title, short = catalog_titles(summary.law_id)
    identity = playground_law_source_identity(summary.law_id)
    outdated = is_law_registry_outdated(summary, identity)
    status = display_status_for_summary(
        selected=summary.selected_count,
        learned=summary.learned_count,
        due=summary.due_count,
        learning=int(getattr(summary, "learning_count", 0) or 0),
        mastered=int(getattr(summary, "mastered_count", 0) or 0),
    )
    selected = int(summary.selected_count or 0)
    learned = int(summary.learned_count or 0)
    pct = int(round((learned / selected) * 100)) if selected else 0
    return LawCardView(
        law_id=summary.law_id,
        title=title,
        short_title=short,
        selected_count=summary.selected_count,
        learned_count=summary.learned_count,
        due_count=summary.due_count,
        overdue_count=0,
        status=status,
        status_label=STATUS_LABELS[status],
        outdated=outdated,
        primary_label=primary_label,
        primary_href=primary_href,
        read_href=f"/laws/{summary.law_id}",
        manage_href=roster_path(),
        is_next=is_next,
        membership=membership,
        membership_label=membership_label,
        add_href=add_href,
        add_label=add_label,
        learning_count=int(getattr(summary, "learning_count", 0) or 0),
        mastered_count=int(getattr(summary, "mastered_count", 0) or 0),
        provisions_copy=provisions_label(selected),
        learned_pct=pct,
    )


def _with_source_state(card: LawCardView, presentations: dict[str, Any]) -> LawCardView:
    state = presentations.get(card.law_id)
    if state is None:
        return card
    active = card.membership == MEMBERSHIP_IN
    return replace(
        card,
        outdated=state.outdated_badge,
        affected_learned_count=state.pending_learned_count,
        source_status=state.status,
        review_href=state.review_href if active else "",
        home_note=state.home_note if active else (
            "Law updated" if state.outdated_badge else ""
        ),
    )


def _stub_card(law_id: str, *, membership: str, membership_label: str, primary_label: str, primary_href: str) -> LawCardView:
    title, short = catalog_titles(law_id)
    return LawCardView(
        law_id=law_id,
        title=title,
        short_title=short,
        selected_count=0,
        learned_count=0,
        due_count=0,
        overdue_count=0,
        status=STATUS_NOT_STARTED,
        status_label=STATUS_LABELS[STATUS_NOT_STARTED],
        outdated=False,
        primary_label=primary_label,
        primary_href=primary_href,
        read_href=f"/laws/{law_id}",
        manage_href=roster_path(),
        membership=membership,
        membership_label=membership_label,
    )


def build_home_view(
    *,
    access: Any,
    roster: Any,
    overlay: Any,
    notice: str = "",
) -> PlaygroundHomeView:
    read_only = bool(getattr(access, "can_view_home", False) and not access.can_open)
    if read_only:
        cap = roster.peek_capacity(
            access.user_id, access.snapshot, local_owner=access.local_owner
        )
    else:
        cap = roster.capacity(
            access.user_id, access.snapshot, local_owner=access.local_owner
        )
    active_items = roster.active_roster_items(access.user_id)
    removed_items = roster.removed_roster_items(access.user_id)
    active_ids = [item.law_id for item in active_items]
    removed_ids = [item.law_id for item in removed_items]
    as_of = playground_today()
    summaries = overlay.list_playground_summaries(
        access.user_id, as_of=as_of, law_ids=active_ids + removed_ids
    )
    by_id = {row.law_id: row for row in summaries}
    next_id = None
    for item in active_items:
        row = by_id.get(item.law_id)
        if row is not None and row.due_count > 0:
            next_id = item.law_id
            break
    if next_id is None and active_ids:
        next_id = active_ids[0]
    active_cards: list[LawCardView] = []
    for item in active_items:
        row = by_id.get(item.law_id)
        href = law_path(item.law_id)
        label = "Continue"
        if row is None or row.selected_count == 0:
            href = sections_path(item.law_id)
            label = "Start learning"
        elif item.law_id != next_id:
            label = "Continue"
        if row is None:
            card = _stub_card(
                item.law_id,
                membership=MEMBERSHIP_IN,
                membership_label="In Playground",
                primary_label=label,
                primary_href=href,
            )
        else:
            card = _card_from_summary(
                row,
                membership=MEMBERSHIP_IN,
                membership_label="In Playground",
                primary_label=label,
                primary_href=href,
                is_next=item.law_id == next_id,
            )
        if card is not None:
            active_cards.append(card)
    removed_cards: list[LawCardView] = []
    for item in removed_items:
        row = by_id.get(item.law_id)
        if row is None:
            card = _stub_card(
                item.law_id,
                membership=MEMBERSHIP_REMOVED,
                membership_label="Removed this month",
                primary_label="Add back",
                primary_href=add_path(item.law_id),
            )
        else:
            card = _card_from_summary(
                row,
                membership=MEMBERSHIP_REMOVED,
                membership_label="Removed this month",
                primary_label="Add back",
                primary_href=add_path(item.law_id),
                add_href=add_path(item.law_id),
                add_label="Add back",
            )
        if card is not None:
            removed_cards.append(card)

    current_ids = set(active_ids) | set(removed_ids)
    overlay_items = overlay.list_items(access.user_id)
    historical_ids = [
        item.law_id
        for item in sorted(overlay_items, key=lambda row: row.last_activity_at, reverse=True)
        if item.law_id not in current_ids and is_playground_eligible_law(item.law_id)
    ][:SAVED_PROGRESS_HOME_LIMIT]
    saved_cards: list[LawCardView] = []
    if historical_ids:
        hist_rows = overlay.list_playground_summaries(
            access.user_id, as_of=as_of, law_ids=historical_ids
        )
        hist_by = {row.law_id: row for row in hist_rows}
        month = playground_month_name(cap.period_start)
        can_add = access.can_consume_new_law or access.local_owner
        full = cap.remaining == 0
        for law_id in historical_ids:
            if full:
                label, href = "Plan next month", roster_next_path()
                membership, membership_label = MEMBERSHIP_FULL, "Playground full this month"
            elif can_add:
                label, href = "Add to this month", add_path(law_id)
                membership, membership_label = MEMBERSHIP_SAVED, "Progress saved"
            else:
                label, href = "Manage subscription", PLAYGROUND_BILLING_PATH
                membership, membership_label = MEMBERSHIP_SAVED, "Progress saved"
            row = hist_by.get(law_id)
            if row is None:
                card = _stub_card(
                    law_id,
                    membership=membership,
                    membership_label=membership_label,
                    primary_label=label,
                    primary_href=href,
                )
            else:
                card = _card_from_summary(
                    row,
                    membership=membership,
                    membership_label=membership_label,
                    primary_label=label,
                    primary_href=href,
                    add_href=href,
                    add_label=label,
                )
            if card is not None:
                saved_cards.append(card)
        del month

    presentations = batch_source_presentations(
        overlay,
        access.user_id,
        [card.law_id for card in (*active_cards, *removed_cards, *saved_cards)],
    )
    active_cards = [
        _with_source_state(card, presentations) for card in active_cards
    ]
    removed_cards = [
        _with_source_state(card, presentations) for card in removed_cards
    ]
    saved_cards = [
        _with_source_state(card, presentations) for card in saved_cards
    ]

    if read_only:
        active_cards = [
            replace(
                card,
                primary_label="Resume Playground",
                primary_href=PLAYGROUND_BILLING_PATH,
                add_href="",
                add_label="",
            )
            for card in active_cards
        ]
        removed_cards = [
            replace(
                card,
                primary_label="Resume Playground",
                primary_href=PLAYGROUND_BILLING_PATH,
                add_href="",
                add_label="",
            )
            for card in removed_cards
        ]

    due_today = sum(card.due_count for card in active_cards)
    sections_learned = sum(card.learned_count for card in active_cards)
    sections_selected = sum(card.selected_count for card in active_cards)
    to_learn = max(0, sections_selected - sections_learned)
    capacity = capacity_view(
        period_start=cap.period_start,
        used=cap.used,
        law_limit=cap.law_limit,
        remaining=cap.remaining,
        active_count=len(active_cards),
        removed_consumed_count=max(0, cap.used - len(active_cards)),
    )
    next_start, _end = next_playground_month_bounds()
    next_month = playground_month_name(next_start)
    banner, quiet = payment_banners(
        access=access,
        notice=notice,
        has_saved_progress=bool(saved_cards),
        current_used=cap.used,
        month_name=capacity.month_name,
    )
    used_n = len(active_cards)
    month_count = (
        f"{used_n} of {capacity.law_limit} · {capacity.month_name}"
        if capacity.law_limit is not None
        else f"{used_n} {'law' if used_n == 1 else 'laws'} · {capacity.month_name}"
    )
    return PlaygroundHomeView(
        capacity=capacity,
        browse_href=BROWSE_LAWS_PATH,
        manage_href=roster_path(),
        manage_label=f"Manage {capacity.month_name}",
        plan_next_href=roster_next_path(),
        plan_next_label=f"Manage {next_month} — choose what continues.",
        next_month_name=next_month,
        empty=not active_cards and not removed_cards,
        due_today=due_today,
        to_learn=to_learn,
        sections_learned=sections_learned,
        sections_selected=sections_selected,
        active=tuple(active_cards),
        removed=tuple(removed_cards),
        saved=tuple(saved_cards),
        banner=banner,
        quiet=quiet,
        read_only=read_only,
        resume_label="Resume Playground" if read_only else "",
        resume_href=PLAYGROUND_BILLING_PATH if read_only else "",
        heading="Playground",
        kicker="My Playground",
        month_count_label=month_count,
        add_law_href=BROWSE_LAWS_PATH,
        add_law_label="Add a law",
    )


def saved_progress_summary(overlay: Any, user_id: Any) -> tuple[int, int]:
    """Cheap gate footer: overlay law count and selected-progress learned count.

    Uses one batched summary query. Does not hydrate Acts.
    """

    if overlay is None or user_id is None:
        return 0, 0
    rows = overlay.list_playground_summaries(user_id, as_of=playground_today())
    laws = sum(1 for row in rows if row.learned_count > 0 or row.selected_count > 0)
    learned = sum(row.learned_count for row in rows)
    return laws, learned


def section_row_view(
    *,
    number: str,
    title: str,
    locator: str,
    progress: Any,
    outdated: bool,
    as_of: date,
    law_id: str,
    mode_progress: Any = None,
    revision_modes: Any = None,
    source_change: Any = None,
    missing: bool = False,
) -> dict[str, Any]:
    status = display_status_for_progress(
        progress, as_of=as_of, mode_progress=mode_progress
    )
    due = status == STATUS_DUE
    completed = int(getattr(mode_progress, "completed_count", 0) or 0)
    next_mode = getattr(mode_progress, "next_mode", None) or "read"
    interval = int(getattr(progress, "interval_days", 0) or 0) if progress is not None else 0
    next_rev = getattr(progress, "next_revision", None) if progress is not None else None
    due_label = ""
    schedule_label = ""
    revision = False
    href_revision = False
    if status == STATUS_MASTERED:
        cta = "Completed"
        methods_label = ""
        href_mode = "read"
    elif status == STATUS_DUE:
        cta = "Revise"
        methods_label = f"Revision · Day {interval}" if interval else "Revision"
        overdue_n = 0
        if next_rev:
            from constitution_memorizer.playground.lifecycle import days_overdue

            overdue_n = days_overdue(str(next_rev)[:10], as_of)
        due_label = overdue_label(overdue_n)
        href_mode = getattr(revision_modes, "next_mode", None) or "read"
        href_revision = True
        revision = True
    elif status == STATUS_LEARNED:
        cta = "Open"
        methods_label = ""
        if interval:
            when = format_study_date(next_rev) if next_rev else ""
            schedule_label = f"First revision · Day {interval}"
            if when:
                schedule_label = f"{schedule_label} · Due {when}"
            if interval != 1:
                schedule_label = f"Day {interval} · {when}".strip(" ·")
        href_mode = "read"
    elif completed > 0:
        cta = "Continue"
        methods_label = f"{completed} of 6 methods"
        href_mode = next_mode
    else:
        cta = "Start learning"
        methods_label = ""
        href_mode = "read"
    if missing:
        cta = "Review"
        href_revision = False
        revision = False
    source_outdated = bool(
        outdated
        or getattr(mode_progress, "source_outdated", False)
        or (
            source_change is not None
            and getattr(source_change, "status", "") == "pending"
        )
    )
    change_kind = getattr(source_change, "change_kind", "") if source_change else ""
    change_status = getattr(source_change, "status", "") if source_change else ""
    if missing or change_kind in {"missing", "omitted"}:
        try:
            href = source_review_path_for_locator(locator)
        except Exception:
            href = source_review_section_path(law_id, number)
    else:
        try:
            href = learn_path_for_locator(locator, href_mode, revision=href_revision)
        except Exception:
            href = learn_path(law_id, number, href_mode, revision=href_revision)
    from constitution_memorizer.playground.units import citation_label
    from constitution_memorizer.playground.locators import LocatorError, parse_locator, UnitLocator

    citation = f"Section {number}"
    unit_display = ""
    try:
        parsed = parse_locator(locator)
        citation = citation_label(parsed)
        if isinstance(parsed, UnitLocator):
            unit_display = parsed.display_label
    except LocatorError:
        pass
    review_href = ""
    if source_change:
        try:
            review_href = source_review_path_for_locator(locator)
        except Exception:
            review_href = source_review_section_path(law_id, number)
    return {
        "locator": locator,
        "number": number,
        "citation": citation,
        "unit_display": unit_display,
        "title": title,
        "progress": progress,
        "mode_progress": mode_progress,
        "revision_modes": revision_modes,
        "outdated": source_outdated,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "due": due,
        "due_label": due_label,
        "schedule_label": schedule_label,
        "cta": cta,
        "methods_label": methods_label,
        "completed_count": completed,
        "revision": revision,
        "href": href,
        "source_change_kind": change_kind,
        "source_change_status": change_status,
        "review_href": review_href,
        "missing": missing,
    }


def provisions_label(count: int) -> str:
    n = int(count or 0)
    return "1 provision" if n == 1 else f"{n} provisions"


def picker_cta_copy(*, section_count: int, partial_unit_count: int) -> str:
    if section_count <= 0:
        return "Select sections to add"
    noun = "section" if section_count == 1 else "sections"
    label = f"Add {section_count} {noun} →"
    if partial_unit_count:
        unit_noun = "clause" if partial_unit_count == 1 else "clauses"
        label = f"Add {section_count} {noun} ({partial_unit_count} {unit_noun} partial) →"
    return label


def picker_status_line(
    status: str,
    *,
    completed: int = 0,
    interval: int = 0,
    next_revision: str | None = None,
    as_of: date | None = None,
) -> str:
    if status == STATUS_LEARNING:
        return f"Learning · {int(completed or 0)} of 6 modes"
    if status == STATUS_DUE:
        return f"Due · Day {interval}" if interval else "Due"
    if status == STATUS_MASTERED:
        return "Mastered"
    if status == STATUS_LEARNED:
        if next_revision and as_of is not None:
            try:
                nxt = date.fromisoformat(str(next_revision)[:10])
            except ValueError:
                nxt = None
            if nxt == as_of + timedelta(days=1):
                return "Learned · first revision tomorrow"
            when = format_study_date(next_revision)
            if when:
                return f"Learned · first revision {when}"
        return "Learned"
    return "Not started"


def _aggregate_picker_status(
    locators: list[str],
    *,
    progress_map: dict[str, Any],
    mode_summaries: dict[str, Any],
    as_of: date,
) -> tuple[str, int, int, str | None]:
    if not locators:
        return STATUS_NOT_STARTED, 0, 0, None
    statuses = []
    completed_total = 0
    interval = 0
    next_rev = None
    for loc in locators:
        progress = progress_map.get(loc)
        modes = mode_summaries.get(loc)
        status = display_status_for_progress(progress, as_of=as_of, mode_progress=modes)
        statuses.append(status)
        completed_total = max(completed_total, int(getattr(modes, "completed_count", 0) or 0))
        if progress is not None:
            interval = max(interval, int(getattr(progress, "interval_days", 0) or 0))
            nxt = getattr(progress, "next_revision", None)
            if nxt and (next_rev is None or str(nxt) < str(next_rev)):
                next_rev = str(nxt)[:10]
    if STATUS_MASTERED in statuses and all(s == STATUS_MASTERED for s in statuses):
        return STATUS_MASTERED, completed_total, interval, next_rev
    if STATUS_DUE in statuses:
        return STATUS_DUE, completed_total, interval, next_rev
    if all(s == STATUS_LEARNED for s in statuses):
        return STATUS_LEARNED, completed_total, interval, next_rev
    if any(s == STATUS_LEARNING for s in statuses) or completed_total > 0:
        return STATUS_LEARNING, completed_total, interval, next_rev
    if any(s == STATUS_LEARNED for s in statuses):
        return STATUS_LEARNED, completed_total, interval, next_rev
    return STATUS_NOT_STARTED, completed_total, interval, next_rev


def picker_page_view(
    *,
    act: Any,
    law_id: str,
    selected: set[str],
    progress_map: dict[str, Any],
    mode_summaries: dict[str, Any],
    as_of: date,
    learnable: set[str],
) -> dict[str, Any]:
    from constitution_memorizer.playground.locators import (
        LocatorError,
        SectionLocator,
        UnitLocator,
        parse_locator,
        section_locator,
    )
    from constitution_memorizer.playground.units import enumerate_selectable_units

    selected_by_section: dict[str, list[Any]] = {}
    for raw in selected:
        try:
            loc = parse_locator(raw)
        except LocatorError:
            continue
        if loc.law_id != law_id:
            continue
        selected_by_section.setdefault(loc.section_number, []).append(loc)

    status_by_section: dict[str, list[str]] = {}
    for raw in set(progress_map) | set(mode_summaries):
        try:
            loc = parse_locator(raw)
        except LocatorError:
            continue
        if loc.law_id != law_id:
            continue
        status_by_section.setdefault(loc.section_number, []).append(raw)

    chapterless = not bool(getattr(act, "chapters", ()))
    if chapterless:
        bands_src = [{"number": "", "title": "", "sections": list(act.section_order)}]
    else:
        bands_src = [
            {"number": ch.number, "title": ch.title, "sections": list(ch.sections)}
            for ch in act.chapters
        ]
        extra = list(getattr(act, "unchaptered_sections", ()) or ())
        if extra:
            bands_src.append({"number": "", "title": "", "sections": extra})

    bands = []
    section_count = 0
    partial_unit_count = 0
    provision_count = 0
    aside_items = []
    for band in bands_src:
        rows = []
        for section in band["sections"]:
            section_loc = section_locator(law_id, section.number)
            learnable_row = section_loc.value in learnable
            omitted = bool(section.is_omitted)
            disabled = omitted or not learnable_row
            units = ()
            if learnable_row and not omitted:
                units = enumerate_selectable_units(section, law_id=law_id)
            chosen = selected_by_section.get(section.number, [])
            whole = any(isinstance(item, SectionLocator) for item in chosen)
            unit_locs = [item for item in chosen if isinstance(item, UnitLocator)]
            if whole:
                check_state = "all"
                aria_checked = "true"
                section_count += 1
                provision_count += 1
                aside_items.append(
                    {
                        "locator": section_loc.value,
                        "citation": f"Section {section.number}",
                        "title": section.list_title,
                    }
                )
            elif unit_locs:
                check_state = "some"
                aria_checked = "mixed"
                section_count += 1
                partial_unit_count += len(unit_locs)
                provision_count += len(unit_locs)
                for item in unit_locs:
                    aside_items.append(
                        {
                            "locator": item.value,
                            "citation": f"Section {section.number}{item.display_label}",
                            "title": section.list_title,
                        }
                    )
            else:
                check_state = "none"
                aria_checked = "false"
            status_locs = status_by_section.get(section.number, [])
            status, completed, interval, next_rev = _aggregate_picker_status(
                status_locs,
                progress_map=progress_map,
                mode_summaries=mode_summaries,
                as_of=as_of,
            )
            unit_rows = []
            checked_unit_values = {item.value for item in unit_locs}
            for unit in units:
                unit_rows.append(
                    {
                        "locator": unit.locator.value,
                        "kind": unit.kind,
                        "label": unit.label,
                        "ordinal": unit.ordinal,
                        "display_label": unit.display_label,
                        "preview": unit.preview,
                        "checked": unit.locator.value in checked_unit_values,
                    }
                )
            rows.append(
                {
                    "number": section.number,
                    "title": section.list_title,
                    "omitted": omitted,
                    "learnable": learnable_row,
                    "disabled": disabled,
                    "checked": check_state == "all",
                    "check_state": check_state,
                    "aria_checked": aria_checked,
                    "expandable": bool(unit_rows),
                    "units": unit_rows,
                    "status": status,
                    "status_label": picker_status_line(
                        status,
                        completed=completed,
                        interval=interval,
                        next_revision=next_rev,
                        as_of=as_of,
                    ),
                    "locator": section_loc.value,
                }
            )
        bands.append(
            {
                "chapter_number": band["number"],
                "chapter_title": band["title"],
                "has_chapter": bool(band["number"]),
                "sections": rows,
            }
        )
    cta = picker_cta_copy(
        section_count=section_count, partial_unit_count=partial_unit_count
    )
    aside_noun = "section selected" if section_count == 1 else "sections selected"
    return {
        "chapterless": chapterless,
        "bands": bands,
        "section_count": section_count,
        "partial_unit_count": partial_unit_count,
        "provision_count": provision_count,
        "provision_label": provisions_label(provision_count),
        "cta_label": cta,
        "zero_selection": section_count == 0,
        "aside_count": section_count,
        "aside_count_label": aside_noun,
        "aside_items": aside_items,
    }

