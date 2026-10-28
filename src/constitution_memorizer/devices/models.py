"""Device registry types. Authorization metadata, not fingerprints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BLOCK_DEVICE_LIMIT = "device_limit"
BLOCK_DEVICE_REVOKED = "device_revoked"
BLOCK_DEVICE_CONFIG_ERROR = "device_config_error"
BLOCK_DEVICE_REPLACEMENT_LIMIT = "device_replacement_limit"

DEVICE_BLOCK_REASONS: frozenset[str] = frozenset(
    {
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_CONFIG_ERROR,
        BLOCK_DEVICE_REPLACEMENT_LIMIT,
    }
)

# Locked §21 replacement-churn policy. Rolling UTC window, not a calendar
# month, billing month, or Playground roster month.
DEVICE_REPLACEMENT_WINDOW_DAYS = 30
DEVICE_REPLACEMENT_LIMIT = 3
ACTION_CLEAR_DEVICE_REPLACEMENT_LIMIT = "clear_device_replacement_limit"

PLATFORM_WEB = "web"
PLATFORM_ANDROID = "android"
PLATFORM_IOS = "ios"
DEVICE_PLATFORMS: frozenset[str] = frozenset(
    {PLATFORM_WEB, PLATFORM_ANDROID, PLATFORM_IOS}
)

PLATFORM_LABELS: dict[str, str] = {
    PLATFORM_WEB: "Web",
    PLATFORM_ANDROID: "Android",
    PLATFORM_IOS: "iOS",
}


def require_platform(platform: str) -> str:
    """Canonical server values: web | android | ios. Reject aliases."""

    value = (platform or "").strip().lower()
    if value not in DEVICE_PLATFORMS:
        raise ValueError("unsupported device platform")
    return value


def platform_label(platform: str) -> str:
    """Presentation only. Unknown values render as the stored token, not 'invalid'."""

    return PLATFORM_LABELS.get(platform, platform)


REGISTER_CREATED = "created"
REGISTER_EXISTING = "existing"
REGISTER_REVOKED = "revoked"
REGISTER_LIMIT = "limit"
REGISTER_REPLACEMENT_LIMIT = "replacement_limit"
REGISTER_INVALID = "invalid"


def replacement_window_start(
    now: datetime,
    *,
    days: int = DEVICE_REPLACEMENT_WINDOW_DAYS,
) -> datetime:
    """Inclusive rolling floor: count events with occurred_at >= this instant."""

    clock = now
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock.replace(microsecond=0) - timedelta(days=int(days))


@dataclass(frozen=True)
class UserDevice:
    """One registered installation. ``device_key_hash`` is HMAC, never the raw token."""

    id: str
    user_id: str
    device_key_hash: str
    platform: str
    display_name: str | None
    first_registered_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


@dataclass(frozen=True)
class UserDeviceSession:
    """Binds a verified auth session to a registered device. Logout ends this row."""

    id: str
    user_id: str
    device_id: str
    auth_session_id: str
    started_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class DeviceAccess:
    """Inspection/ensure result. Commercial subscription facts live elsewhere."""

    device_limit: int
    registered_device_count: int
    current_device_id: str | None
    current_device_registered: bool
    current_device_allowed: bool
    current_device_revoked: bool
    device_slots_remaining: int
    block_reason: str | None


@dataclass(frozen=True)
class RegisterOutcome:
    """Atomic registration result. ``device`` is set for created/existing/revoked."""

    status: str
    device: UserDevice | None


@dataclass(frozen=True)
class DeviceSummary:
    """Owner/admin presentation. Never includes hashes, raw tokens, or HMAC secrets."""

    id: str
    platform: str
    platform_label: str
    display_name: str | None
    first_registered_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None
    is_current: bool
    is_active: bool

    @property
    def status_label(self) -> str:
        return "Active" if self.is_active else "Removed"

    @property
    def current_label(self) -> str | None:
        if not self.is_current:
            return None
        if self.is_active:
            return "This device"
        return "This device · Removed"


@dataclass(frozen=True)
class DeviceResetSummary:
    """Safe before/after counts for an audited admin reset. No credential fields."""

    before: dict
    after: dict
    revoked_device_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeviceReplacementClearSummary:
    """Safe before/after counts for an audited churn-history clear."""

    before: dict
    after: dict
    deleted_count: int


def device_summary(device: UserDevice, *, current_id: str | None) -> DeviceSummary:
    return DeviceSummary(
        id=device.id,
        platform=device.platform,
        platform_label=platform_label(device.platform),
        display_name=device.display_name,
        first_registered_at=device.first_registered_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
        is_current=current_id is not None and device.id == current_id,
        is_active=not device.is_revoked,
    )


def sort_device_summaries(items: list[DeviceSummary]) -> list[DeviceSummary]:
    """Active before revoked; current first in its group; most recently seen next."""

    def key(item: DeviceSummary) -> tuple:
        seen = item.last_seen_at.timestamp() if item.last_seen_at else 0.0
        return (
            0 if item.is_active else 1,
            0 if item.is_current else 1,
            -seen,
            item.id,
        )

    return sorted(items, key=key)


def safe_registry_state(devices: list[UserDevice]) -> dict:
    """Audit-safe summary. Device ids are allowed; hashes and tokens are not."""

    active = [row for row in devices if not row.is_revoked]
    revoked = [row for row in devices if row.is_revoked]
    return {
        "active_device_count": len(active),
        "revoked_device_count": len(revoked),
        "device_ids": [row.id for row in devices],
    }


def slots_remaining(limit: int, active_count: int) -> int:
    return max(0, int(limit) - int(active_count))


def device_access_from_state(
    *,
    limit: int,
    active_count: int,
    current: UserDevice | None,
    admin_bypass: bool = False,
    config_error: bool = False,
    replacement_limited: bool = False,
) -> DeviceAccess:
    remaining = slots_remaining(limit, active_count)
    if config_error:
        return DeviceAccess(
            device_limit=limit,
            registered_device_count=active_count,
            current_device_id=None,
            current_device_registered=False,
            current_device_allowed=False,
            current_device_revoked=False,
            device_slots_remaining=remaining,
            block_reason=BLOCK_DEVICE_CONFIG_ERROR,
        )
    revoked = current is not None and current.is_revoked
    registered = current is not None and not current.is_revoked
    current_id = current.id if current is not None else None
    if admin_bypass:
        return DeviceAccess(
            device_limit=limit,
            registered_device_count=active_count,
            current_device_id=current_id,
            current_device_registered=registered,
            current_device_allowed=True,
            current_device_revoked=revoked,
            device_slots_remaining=remaining,
            block_reason=None,
        )
    if revoked:
        return DeviceAccess(
            device_limit=limit,
            registered_device_count=active_count,
            current_device_id=current_id,
            current_device_registered=False,
            current_device_allowed=False,
            current_device_revoked=True,
            device_slots_remaining=remaining,
            block_reason=BLOCK_DEVICE_REVOKED,
        )
    if registered:
        return DeviceAccess(
            device_limit=limit,
            registered_device_count=active_count,
            current_device_id=current_id,
            current_device_registered=True,
            current_device_allowed=True,
            current_device_revoked=False,
            device_slots_remaining=remaining,
            block_reason=None,
        )
    if remaining <= 0:
        return DeviceAccess(
            device_limit=limit,
            registered_device_count=active_count,
            current_device_id=None,
            current_device_registered=False,
            current_device_allowed=False,
            current_device_revoked=False,
            device_slots_remaining=0,
            block_reason=BLOCK_DEVICE_LIMIT,
        )
    if replacement_limited:
        return DeviceAccess(
            device_limit=limit,
            registered_device_count=active_count,
            current_device_id=None,
            current_device_registered=False,
            current_device_allowed=False,
            current_device_revoked=False,
            device_slots_remaining=remaining,
            block_reason=BLOCK_DEVICE_REPLACEMENT_LIMIT,
        )
    return DeviceAccess(
        device_limit=limit,
        registered_device_count=active_count,
        current_device_id=None,
        current_device_registered=False,
        current_device_allowed=False,
        current_device_revoked=False,
        device_slots_remaining=remaining,
        block_reason=None,
    )
