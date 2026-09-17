"""Device registry types. Authorization metadata, not fingerprints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

BLOCK_DEVICE_LIMIT = "device_limit"
BLOCK_DEVICE_REVOKED = "device_revoked"
BLOCK_DEVICE_CONFIG_ERROR = "device_config_error"

DEVICE_BLOCK_REASONS: frozenset[str] = frozenset(
    {
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_CONFIG_ERROR,
    }
)

PLATFORM_WEB = "web"
PLATFORM_ANDROID = "android"
DEVICE_PLATFORMS: frozenset[str] = frozenset({PLATFORM_WEB, PLATFORM_ANDROID})

REGISTER_CREATED = "created"
REGISTER_EXISTING = "existing"
REGISTER_REVOKED = "revoked"
REGISTER_LIMIT = "limit"
REGISTER_INVALID = "invalid"


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


def slots_remaining(limit: int, active_count: int) -> int:
    return max(0, int(limit) - int(active_count))


def device_access_from_state(
    *,
    limit: int,
    active_count: int,
    current: UserDevice | None,
    admin_bypass: bool = False,
    config_error: bool = False,
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
