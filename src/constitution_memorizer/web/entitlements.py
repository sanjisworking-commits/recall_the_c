"""Central access / entitlement service.

Single source of truth for *who* a request belongs to (``guest`` / ``free`` /
``subscribed``) and, for a given parent Article, *what they may do* (which Learn
modes are open, what Done requires, whether pressing Done should claim a Free
Article or hit the subscription gate).

Every surface — Learn routes, Done, templates, and JS payloads — consumes the
result of :func:`compute_learn_access` / :func:`access_summary` rather than
re-deriving quota or mode rules. Feature code asks a capability; it never
branches on a specific paid duration.

Roadmap note: this module is pure logic + light request/engine resolvers. The
Learn locks (step 3) and Article-aware Done (step 4) wire it into the routes;
here (step 1) it powers only read-only status surfaces. ``is_subscribed`` is the
billing seam filled in step 6 — until then it is always ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from time import perf_counter
from typing import Iterable

from constitution_memorizer.admin.store import AccessOverride
from constitution_memorizer.progress.repository import LEARN_MODES

# Modes always available (guest / free-cap-reached still get these four).
OPEN_MODES: tuple[str, ...] = ("read", "cloze", "letters", "test")
# Subscriber-only modes (locked for guest and free-cap-reached).
SUBSCRIBER_ONLY_MODES: tuple[str, ...] = ("type", "recite")
# Canonical render order of all six modes (owned by progress.repository).
ALL_MODES: tuple[str, ...] = LEARN_MODES

# A signed-in Free account may permanently claim this many parent Articles.
FREE_ARTICLE_LIMIT = 3

# Access levels. Deliberately only these three: an administrator or a grant
# holder resolves to SUBSCRIBED capabilities with a distinguishing
# access_source, never a fourth level.
GUEST = "guest"
FREE = "free"
SUBSCRIBED = "subscribed"

# Why full access exists for this request. "admin" and the grant sources are
# real capability without a purchase — is_subscribed stays False for them so
# no surface (or table) ever claims a subscription that does not exist.
ACCESS_SOURCES: tuple[str, ...] = (
    "free",
    "payment",
    "subscription",
    "admin_grant",
    "promotion",
    "admin",
    "local_owner",
)


def _multiuser_enabled(request: object) -> bool:
    app_state = getattr(getattr(request, "app", None), "state", None)
    return bool(getattr(app_state, "multiuser_enabled", False))


def entitlements_active(request: object) -> bool:
    """Whether the 3-Free-Article boundary is switched on for this app.

    ``ARTICLE_ENTITLEMENTS_ENABLED`` defaults to false everywhere; steps 1–4 of
    the entitlement roadmap land progressively but stay dormant behind it. With
    the flag off, every caller sees legacy behavior (all six modes, no claim
    prompts, no gates, no status surfaces) and no entitlement DB reads happen.
    """
    app_state = getattr(getattr(request, "app", None), "state", None)
    return bool(getattr(app_state, "article_entitlements_enabled", False))


def article_key(article_number: object) -> str | None:
    """Normalize a parent Article number to the string key used everywhere.

    Returns ``None`` for units with no Article (nothing to claim / gate).
    """
    if article_number is None:
        return None
    key = str(article_number).strip()
    return key or None


# --------------------------------------------------------------------------- #
# Access level                                                                 #
# --------------------------------------------------------------------------- #
def is_subscribed(user: object) -> bool:
    """Billing seam. Always ``False`` until the payment layer lands (step 6)."""
    return False


def _request_override(request: object) -> AccessOverride:
    """Role + effective manual grant for this request (memoized per request).

    Empty override when multiuser is off, the user is a guest, or no access
    store is wired — the caller falls through to the normal level logic.
    """
    from constitution_memorizer.admin.dependencies import resolve_access_override

    try:
        return resolve_access_override(request)  # type: ignore[arg-type]
    except AttributeError:  # pragma: no cover - defensive; bare stub request
        return AccessOverride()


def has_active_recall_access(request: object) -> bool:
    """Capability reduction: admin role OR active manual grant.

    The billing layer (roadmap step 7) ORs paid entitlements into this same
    check; feature code keeps asking one question.
    """
    return _request_override(request).has_recall_access


def resolve_level(*, multiuser_enabled: bool, has_user: bool, subscribed: bool) -> str:
    """Pure access-level resolution (unit-testable without a request).

    - multiuser off  -> local single-user owner keeps full access (``subscribed``)
    - no signed-in user -> ``guest``
    - signed-in + active subscription -> ``subscribed``; else ``free``
    """
    if not multiuser_enabled:
        return SUBSCRIBED
    if not has_user:
        return GUEST
    return SUBSCRIBED if subscribed else FREE


def access_level(request: object) -> str:
    """Resolve the access level for a FastAPI request.

    Still returns only guest/free/subscribed. An admin role or an active
    manual grant resolves to ``subscribed`` (effective capabilities); the
    result objects carry ``access_source`` to say why. The override lookup
    only runs while the entitlement boundary is active, preserving the
    zero-DB-reads property of the dormant flag.
    """
    app_state = getattr(getattr(request, "app", None), "state", None)
    multiuser_enabled = bool(getattr(app_state, "multiuser_enabled", False))
    user = getattr(getattr(request, "state", None), "current_user", None)
    subscribed = user is not None and is_subscribed(user)
    if (
        multiuser_enabled
        and user is not None
        and not subscribed
        and entitlements_active(request)
    ):
        subscribed = has_active_recall_access(request)
    return resolve_level(
        multiuser_enabled=multiuser_enabled,
        has_user=user is not None,
        subscribed=subscribed,
    )


def can_use_auto_plan(request: object) -> bool:
    """Durable Auto Plan eligibility. Ignores admin entitlement preview.

    Auto Plan is a paid-tier capability. Feature code asks this question
    rather than ``is_subscribed`` alone so:

    * a genuine paid user may enable Auto Plan
    * an administrator with a real admin role may enable it for their own
      account without a billing record (``access_source`` stays ``admin``)
    * an active full-access grant follows the same full-Recall policy as
      other subscriber capabilities
    * a normal Free account cannot

    Entitlement preview is a UI/testing simulation. It is not consulted
    here and must not grant, revoke, or persist this entitlement.
    """
    if not entitlements_active(request):
        return True
    # Local single-user owner already has full Recall; keep Auto Plan open.
    if not _multiuser_enabled(request):
        return True
    if has_active_recall_access(request):
        return True
    user = getattr(getattr(request, "state", None), "current_user", None)
    return user is not None and is_subscribed(user)


def learning_entitlement_args(request: object, engine: object) -> dict:
    """Claimed-Article mix args. Full-access users skip the Free slot cap.

    Preview is not consulted. Feature code (mix generation, Dashboard
    new-learning availability) should ask this once rather than re-deriving
    Free vs full-access from ``is_subscribed``.
    """
    if not entitlements_active(request) or can_use_auto_plan(request):
        return {
            "claimed": set(),
            "remaining_slots": None,
            "entitlements_on": False,
        }
    getter = getattr(engine, "claimed_articles", None)
    claimed = set(getter()) if getter is not None else set()
    remaining = max(0, FREE_ARTICLE_LIMIT - len(claimed))
    return {
        "claimed": claimed,
        "remaining_slots": remaining,
        "entitlements_on": True,
    }


# --------------------------------------------------------------------------- #
# Per-Article Learn access                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LearnAccess:
    """What the current user may do on one parent Article.

    Persistence matrix (R2·3): claimed/subscribed Articles persist
    ``modes_seen`` server-side; a claimable-but-unclaimed Article is
    *provisional* Learn state (client-tracked until claim-on-Done);
    cap-reached unclaimed Articles and guests are local/exploratory only.
    """

    level: str
    article_claimed: bool
    free_slots_remaining: int
    allowed_modes: tuple[str, ...]
    required_modes: tuple[str, ...]
    locked_modes: tuple[str, ...]
    can_persist_modes_seen: bool
    can_persist_done: bool
    should_prompt_claim: bool
    cap_reached: bool
    # Identity/commerce split: an administrator has full capability with
    # is_admin=True and access_source="admin" while level stays "subscribed"
    # — no fake purchase anywhere. Keyword-with-default, appended last, so
    # existing constructions stay valid.
    is_admin: bool = False
    access_source: str | None = None

    def is_locked(self, mode: str) -> bool:
        return mode in self.locked_modes


def _full_access(
    level: str,
    *,
    article_claimed: bool,
    slots: int,
    is_admin: bool = False,
    access_source: str | None = None,
) -> LearnAccess:
    return LearnAccess(
        level=level,
        article_claimed=article_claimed,
        free_slots_remaining=slots,
        allowed_modes=ALL_MODES,
        required_modes=ALL_MODES,
        locked_modes=(),
        can_persist_modes_seen=True,
        can_persist_done=True,
        should_prompt_claim=False,
        cap_reached=False,
        is_admin=is_admin,
        access_source=access_source,
    )


def compute_learn_access(
    level: str,
    *,
    article_claimed: bool = False,
    free_slots_remaining: int = 0,
) -> LearnAccess:
    """Pure Article-aware access calculation (no request/DB dependency).

    Matrix:
      guest             -> 4 open modes, Type/Recite locked, Done local-only
      free + claimed    -> all 6, Done requires 6, persists
      free + claimable  -> all 6, Done requires 6, prompts claim, persists on confirm
      free + cap-reached-> 4 open modes, Type/Recite locked, Done -> gate, no persist
      subscribed        -> all 6 everywhere, persists
    """
    if level == SUBSCRIBED:
        return _full_access(SUBSCRIBED, article_claimed=article_claimed, slots=free_slots_remaining)

    if level == GUEST:
        return LearnAccess(
            level=GUEST,
            article_claimed=False,
            free_slots_remaining=0,
            allowed_modes=OPEN_MODES,
            required_modes=OPEN_MODES,
            locked_modes=SUBSCRIBER_ONLY_MODES,
            can_persist_modes_seen=False,
            can_persist_done=False,
            should_prompt_claim=False,
            cap_reached=False,
        )

    # level == FREE
    if article_claimed:
        return _full_access(FREE, article_claimed=True, slots=free_slots_remaining)
    if free_slots_remaining > 0:
        # Claimable: all six open, but nothing becomes permanent account
        # progress until the learner confirms the claim on Done — mode visits
        # stay provisional (client-tracked) until then.
        return LearnAccess(
            level=FREE,
            article_claimed=False,
            free_slots_remaining=free_slots_remaining,
            allowed_modes=ALL_MODES,
            required_modes=ALL_MODES,
            locked_modes=(),
            can_persist_modes_seen=False,
            can_persist_done=True,
            should_prompt_claim=True,
            cap_reached=False,
        )
    # Free, unclaimed, no slots left -> cap reached. The four open modes are
    # exploration only; they never quietly become saved progress.
    return LearnAccess(
        level=FREE,
        article_claimed=False,
        free_slots_remaining=0,
        allowed_modes=OPEN_MODES,
        required_modes=OPEN_MODES,
        locked_modes=SUBSCRIBER_ONLY_MODES,
        can_persist_modes_seen=False,
        can_persist_done=False,
        should_prompt_claim=False,
        cap_reached=True,
    )


# --------------------------------------------------------------------------- #
# Admin Entitlement Preview                                                    #
# --------------------------------------------------------------------------- #
# Simulates Learn access restrictions only — session, nav and account pages
# still show the real signed-in admin. States are Article-state-aware because
# Learn behaviour follows the claim state, not the slot count alone. Every
# previewed state forces both persistence flags off, so nothing an admin does
# while previewing is saved (the Done handlers check can_persist_done before
# any write, including the claim-confirm branch).

PREVIEW_COOKIE = "rtc_admin_preview"

PREVIEW_STATES: dict[str, str] = {
    "free_claimable": "Free — Article claimable",
    "free_claimed": "Free — claimed Article",
    "free_cap": "Free — 3/3 used",
    "subscribed": "Subscriber",
}


def preview_state(request: object) -> str | None:
    """The active preview state, honored only for a verified admin.

    Forging the cookie as a non-admin does nothing: the authoritative role
    bit from the access override gates it, so no signing is needed. Without
    the cookie there is zero extra cost on any request.
    """
    cookies = getattr(request, "cookies", None)
    raw = cookies.get(PREVIEW_COOKIE) if cookies else None
    if not raw or raw not in PREVIEW_STATES:
        return None
    if not _request_override(request).is_admin:
        return None
    return raw


def _preview_learn_access(state: str) -> LearnAccess:
    if state == "free_claimable":
        access = compute_learn_access(
            FREE, article_claimed=False, free_slots_remaining=2
        )
    elif state == "free_claimed":
        access = compute_learn_access(
            FREE, article_claimed=True, free_slots_remaining=1
        )
    elif state == "free_cap":
        access = compute_learn_access(
            FREE, article_claimed=False, free_slots_remaining=0
        )
    else:  # subscribed
        access = compute_learn_access(SUBSCRIBED)
    return replace(
        access, can_persist_modes_seen=False, can_persist_done=False
    )


def resolve_learn_access(request: object, engine: object, article_number: object) -> LearnAccess:
    """Resolve :class:`LearnAccess` from a request + the per-user engine.

    While ``ARTICLE_ENTITLEMENTS_ENABLED`` is off, every request resolves to
    full legacy access (all six modes, everything persists, no prompts) and no
    entitlement store reads happen.

    Order of authority once active: entitlement preview (verified admins
    only, checked before everything so gates can be tested even where the
    flag is off), then admin role, then active manual grant — both full
    access without reading the claim store, never consuming a free slot —
    then the normal guest/free/subscribed matrix.
    """
    previewed = preview_state(request)
    if previewed is not None:
        return _preview_learn_access(previewed)
    if not entitlements_active(request):
        return _full_access(
            access_level(request), article_claimed=False, slots=FREE_ARTICLE_LIMIT
        )
    override = _request_override(request)
    if override.is_admin:
        return _full_access(
            SUBSCRIBED,
            article_claimed=False,
            slots=0,
            is_admin=True,
            access_source="admin",
        )
    if override.effective_grant is not None:
        return _full_access(
            SUBSCRIBED,
            article_claimed=False,
            slots=0,
            access_source=override.effective_grant.source,
        )
    level = access_level(request)
    if level != FREE:
        access = compute_learn_access(level)
        if level == SUBSCRIBED and not _multiuser_enabled(request):
            access = replace(access, access_source="local_owner")
        return access
    claimed = _claimed_articles(engine)
    key = article_key(article_number)
    return compute_learn_access(
        FREE,
        article_claimed=key is not None and key in claimed,
        free_slots_remaining=max(0, FREE_ARTICLE_LIMIT - len(claimed)),
    )


# --------------------------------------------------------------------------- #
# Account / surface status                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AccessSummary:
    """Read-only access status shown on Profile / Settings / Dashboard."""

    level: str
    claimed_count: int
    free_slots_remaining: int
    claimed_articles: tuple[str, ...]
    cap_reached: bool
    is_subscribed: bool
    # False while ARTICLE_ENTITLEMENTS_ENABLED is off — surfaces render nothing.
    enabled: bool = True
    # Grandfathered accounts may hold more than the 3-slot limit permanently.
    legacy_over_cap: bool = False
    # Filled from the billing layer in step 7; None until then. For manual
    # grants this is the effective grant's end date (None = indefinite).
    subscription_label: str | None = None
    renews_or_expires_on: str | None = None
    # Identity/commerce split: real capability without a purchase keeps
    # is_subscribed False and says why here instead.
    is_admin: bool = False
    access_source: str | None = None

    @property
    def is_free(self) -> bool:
        return self.level == FREE

    @property
    def status_line(self) -> str:
        """Compact one-line status for Settings / Dashboard chip."""
        if self.access_source == "admin":
            return "Administrator access"
        if self.access_source in ("admin_grant", "promotion"):
            return "Recall access granted"
        if self.level == SUBSCRIBED:
            if self.subscription_label:
                return f"Recall active · {self.subscription_label}"
            return "Recall active"
        if self.level == GUEST:
            return "Guest"
        if self.legacy_over_cap:
            return f"Free · {self.claimed_count} saved Articles · Legacy access"
        return f"Free · {self.claimed_count} of {FREE_ARTICLE_LIMIT} Articles"


_DISABLED_SUMMARY = AccessSummary(
    level=FREE,
    claimed_count=0,
    free_slots_remaining=FREE_ARTICLE_LIMIT,
    claimed_articles=(),
    cap_reached=False,
    is_subscribed=False,
    enabled=False,
)


def build_access_summary(
    level: str,
    *,
    claimed_articles: Iterable[str] = (),
    subscribed: bool = False,
) -> AccessSummary:
    """Pure account-summary construction (unit-testable)."""
    claimed = tuple(claimed_articles)
    count = len(claimed)
    slots = max(0, FREE_ARTICLE_LIMIT - count)
    return AccessSummary(
        level=level,
        claimed_count=count,
        free_slots_remaining=slots,
        claimed_articles=claimed,
        cap_reached=(level == FREE and slots == 0),
        is_subscribed=subscribed,
        legacy_over_cap=(level == FREE and count > FREE_ARTICLE_LIMIT),
    )


def access_summary(request: object, engine: object) -> AccessSummary:
    """Resolve the account summary from a request + per-user engine.

    Returns a disabled marker (no DB reads) while the entitlement boundary is
    dormant, so status surfaces stay hidden and query load is unchanged.

    Admin and grant holders summarize as level=subscribed with
    ``is_subscribed=False`` — the capability is real, the purchase is not —
    and ``access_source`` carries the display. Their claimed Free Articles
    stay listed: claims are permanent and survive any grant ending.
    """
    if not entitlements_active(request):
        return _DISABLED_SUMMARY
    level = access_level(request)
    if level == GUEST:
        return build_access_summary(GUEST)
    claimed = sorted(_claimed_articles(engine), key=_article_sort_key)
    override = _request_override(request)
    if override.is_admin:
        return replace(
            build_access_summary(SUBSCRIBED, claimed_articles=claimed),
            is_admin=True,
            access_source="admin",
        )
    if override.effective_grant is not None:
        grant = override.effective_grant
        ends = grant.ends_at
        return replace(
            build_access_summary(SUBSCRIBED, claimed_articles=claimed),
            access_source=grant.source,
            # Long date for display ("30 September 2026"); indefinite grants
            # carry None and print no expiry at all.
            renews_or_expires_on=(
                f"{ends.day} {ends:%B %Y}" if ends is not None else None
            ),
        )
    summary = build_access_summary(
        level, claimed_articles=claimed, subscribed=(level == SUBSCRIBED)
    )
    if level == SUBSCRIBED and not _multiuser_enabled(request):
        summary = replace(summary, access_source="local_owner")
    return summary


# --------------------------------------------------------------------------- #
# Engine helpers (tolerant of an engine without the store yet)                  #
# --------------------------------------------------------------------------- #
def _claimed_articles(engine: object) -> set[str]:
    getter = getattr(engine, "claimed_articles", None)
    if getter is None:
        return set()
    try:
        return set(getter())
    except Exception:  # pragma: no cover - defensive; store not ready
        return set()


def _article_sort_key(value: str) -> tuple[int, object]:
    """Sort Article keys numerically when possible, else lexicographically."""
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


# --------------------------------------------------------------------------- #
# Subscription lifecycle (design 04) — one dated status object                  #
# --------------------------------------------------------------------------- #
# The five lifecycle presentations (active / expiring soon / renewal failed /
# cancelled / lapsed) all read from a single status object so the label and
# the action can never disagree. Until the billing layer (roadmap step 6)
# exists there is nothing to report and :func:`subscription_status` returns
# ``None`` — every lifecycle surface renders nothing.

SUBSCRIPTION_STATES: tuple[str, ...] = (
    "active",
    "expiring",
    "renewal_failed",
    "cancelled",
    "lapsed",
)


@dataclass(frozen=True)
class SubscriptionStatus:
    """Dated subscription state driving Profile / Dashboard lifecycle UI."""

    state: str  # one of SUBSCRIPTION_STATES
    plan_days: int
    plan_price_inr: int
    recurring: bool
    # ISO dates; which ones are set depends on the state.
    renews_on: str | None = None
    ends_on: str | None = None
    ended_on: str | None = None
    grace_until: str | None = None

    @property
    def is_lapsed(self) -> bool:
        return self.state == "lapsed"

    @property
    def is_expiring(self) -> bool:
        return self.state == "expiring"


def _format_day(value: date) -> str:
    return f"{value.day} {value.strftime('%b %Y')}"


def status_from_paid_order(
    *,
    plan_days: int,
    amount_paise: int,
    paid_on: date,
    today: date,
) -> SubscriptionStatus:
    """Pure pass-state calculation from the latest verified payment.

    Standard Checkout sells fixed-length access passes (a real auto-renewing
    subscription needs Razorpay's Subscriptions API later), so the only
    reachable states are active / expiring / lapsed and ``recurring`` is
    always False — the lifecycle copy shows "Access until", never "Renews".
    """
    ends = paid_on + timedelta(days=plan_days)
    if ends < today:
        state = "lapsed"
    elif (ends - today).days <= 7:
        state = "expiring"
    else:
        state = "active"
    return SubscriptionStatus(
        state=state,
        plan_days=plan_days,
        plan_price_inr=amount_paise // 100,
        recurring=False,
        ends_on=_format_day(ends) if state != "lapsed" else None,
        ended_on=_format_day(ends) if state == "lapsed" else None,
    )


def subscription_status(
    request: object, engine: object = None
) -> SubscriptionStatus | None:
    """Pass state from the latest verified Razorpay payment (None = no pass).

    Needs the request-bound engine to read billing rows; callers without one
    (or with the entitlement boundary dormant) get ``None`` and every
    lifecycle surface renders nothing.
    """
    if engine is None or not entitlements_active(request):
        return None
    user = getattr(getattr(request, "state", None), "current_user", None)
    if user is None:
        return None
    engine_getter = getattr(engine, "latest_paid_billing_order", None)
    if engine_getter is not None:
        order = engine_getter()
    else:
        repo_getter = getattr(
            getattr(engine, "repo", None), "latest_paid_billing_order", None
        )
        if repo_getter is None:
            return None
        from constitution_memorizer.web.request_context import record_request_timing

        started = perf_counter()
        order = repo_getter(getattr(engine, "user_id", None))
        record_request_timing("billing_status", started)
    if order is None or order.paid_at is None:
        return None
    return status_from_paid_order(
        plan_days=order.plan_days,
        amount_paise=order.amount_paise,
        paid_on=date.fromisoformat(str(order.paid_at)[:10]),
        today=date.today(),
    )
