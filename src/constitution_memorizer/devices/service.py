"""Playground device authorization. Does not re-derive subscription status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from constitution_memorizer.devices.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    DEVICE_REPLACEMENT_LIMIT,
    DEVICE_REPLACEMENT_WINDOW_DAYS,
    PLATFORM_WEB,
    REGISTER_CREATED,
    REGISTER_EXISTING,
    REGISTER_INVALID,
    REGISTER_LIMIT,
    REGISTER_REPLACEMENT_LIMIT,
    REGISTER_REVOKED,
    DeviceAccess,
    DeviceReplacementClearSummary,
    DeviceResetSummary,
    DeviceSummary,
    UserDevice,
    device_access_from_state,
    device_summary,
    replacement_window_start,
    sort_device_summaries,
)
from constitution_memorizer.devices.token import DeviceHmacConfigError, hash_device_token
from constitution_memorizer.progress.user_ids import as_user_id

DEFAULT_DEVICE_LIMIT = 2


def normalize_device_limit(value: Any) -> int:
    """Reject 0, negatives, and non-integers. Default is 2."""

    if value is None or value == "":
        return DEFAULT_DEVICE_LIMIT
    if isinstance(value, bool):
        raise ValueError("PLAYGROUND_DEVICE_LIMIT must be a positive integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError("PLAYGROUND_DEVICE_LIMIT must be a positive integer")
    if parsed < 1:
        raise ValueError("PLAYGROUND_DEVICE_LIMIT must be a positive integer")
    return parsed


class DeviceService:
    """Register, inspect, bind, and revoke installations for one account."""

    def __init__(
        self,
        repo: Any,
        *,
        hmac_secret: str = "",
        device_limit: int = DEFAULT_DEVICE_LIMIT,
        replacement_limit: int = DEVICE_REPLACEMENT_LIMIT,
        replacement_window_days: int = DEVICE_REPLACEMENT_WINDOW_DAYS,
    ) -> None:
        self._repo = repo
        self._hmac_secret = hmac_secret or ""
        self._replacement_limit = int(replacement_limit)
        self._replacement_window_days = int(replacement_window_days)
        try:
            self._limit = normalize_device_limit(device_limit)
            self._limit_error = False
        except ValueError:
            self._limit = DEFAULT_DEVICE_LIMIT
            self._limit_error = True

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"DeviceService(limit={self._limit})"

    @property
    def device_limit(self) -> int:
        return self._limit

    def inspect_current_device(
        self,
        user_id: UUID | str,
        token: str | None,
        *,
        admin_bypass: bool = False,
        now: datetime | None = None,
    ) -> DeviceAccess:
        if self._limit_error:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=None,
                admin_bypass=admin_bypass,
                config_error=True,
            )
        current, config_error = self._lookup(user_id, token)
        return device_access_from_state(
            limit=self._limit,
            active_count=self._safe_count(user_id),
            current=current,
            admin_bypass=admin_bypass,
            config_error=config_error,
            replacement_limited=self._replacement_limited(user_id, now=now),
        )

    def ensure_current_device(
        self,
        user_id: UUID | str,
        token: str | None,
        *,
        auth_session_id: str | None,
        commercially_eligible: bool,
        admin_override: bool = False,
        platform: str = PLATFORM_WEB,
        display_name: str | None = None,
        now: datetime | None = None,
    ) -> DeviceAccess:
        """Register on first eligible Playground use; never auto-unrevoke."""

        if admin_override:
            access = self.inspect_current_device(
                user_id, token, admin_bypass=True
            )
            if (
                access.current_device_registered
                and access.current_device_id
                and auth_session_id
            ):
                self._repo.bind_session(
                    user_id, access.current_device_id, auth_session_id, now=now
                )
                self._repo.touch_last_seen(
                    user_id, access.current_device_id, now=now
                )
            return access
        if not commercially_eligible:
            return self.inspect_current_device(user_id, token)
        if self._limit_error:
            return self.inspect_current_device(user_id, token)
        current, config_error = self._lookup(user_id, token)
        if config_error:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=current,
                config_error=True,
            )
        if current is not None and current.is_revoked:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=current,
            )
        if current is not None:
            if auth_session_id:
                self._repo.bind_session(
                    user_id, current.id, auth_session_id, now=now
                )
            self._repo.touch_last_seen(user_id, current.id, now=now)
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=self._repo.get_by_id(user_id, current.id) or current,
            )
        digest, config_error = self._hash(token)
        if config_error or digest is None:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=None,
                config_error=True,
            )
        outcome = self._repo.register_if_under_cap(
            user_id,
            device_key_hash=digest,
            platform=platform or PLATFORM_WEB,
            display_name=display_name,
            limit=self._limit,
            now=now,
            replacement_limit=self._replacement_limit,
            replacement_window_days=self._replacement_window_days,
        )
        if outcome.status == REGISTER_REVOKED:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=outcome.device,
            )
        if outcome.status in {REGISTER_CREATED, REGISTER_EXISTING}:
            device = outcome.device
            if device is not None and auth_session_id:
                self._repo.bind_session(
                    user_id, device.id, auth_session_id, now=now
                )
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=device,
            )
        if outcome.status == REGISTER_LIMIT:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=None,
            )
        if outcome.status == REGISTER_REPLACEMENT_LIMIT:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=None,
                replacement_limited=True,
            )
        if outcome.status == REGISTER_INVALID:
            return device_access_from_state(
                limit=self._limit,
                active_count=self._safe_count(user_id),
                current=None,
                config_error=True,
            )
        return self.inspect_current_device(user_id, token)

    def list_devices(self, user_id: UUID | str) -> list[UserDevice]:
        return list(self._repo.list_devices(user_id))

    def list_device_summaries(
        self,
        user_id: UUID | str,
        token: str | None,
    ) -> list[DeviceSummary]:
        """Request-scoped presentation. ``is_current`` is never persisted."""

        current, _config_error = self._lookup(user_id, token)
        current_id = current.id if current is not None else None
        summaries = [
            device_summary(row, current_id=current_id)
            for row in self.list_devices(user_id)
        ]
        return sort_device_summaries(summaries)

    def get_device(
        self, user_id: UUID | str, device_id: str
    ) -> UserDevice | None:
        return self._repo.get_by_id(user_id, device_id)

    def revoke_device(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> UserDevice | None:
        return self._repo.revoke_device(user_id, device_id, now=now)

    def revoke_all_devices(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> DeviceResetSummary:
        return self._repo.revoke_all_devices(user_id, now=now)

    def reset_devices_audited(
        self,
        user_id: UUID | str,
        *,
        admin_user_id: UUID | str,
        reason: str,
        now: datetime | None = None,
    ) -> DeviceResetSummary:
        cleaned = (reason or "").strip()
        if not cleaned:
            raise ValueError("Reason is required")
        return self._repo.reset_devices_audited(
            user_id,
            admin_user_id=admin_user_id,
            reason=cleaned,
            now=now,
        )

    def count_recent_replacements(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> int:
        clock = now or datetime.now(timezone.utc).replace(microsecond=0)
        since = replacement_window_start(
            clock, days=self._replacement_window_days
        )
        try:
            return int(self._repo.count_recent_replacements(user_id, since))
        except Exception:
            return 0

    def record_replacement(
        self,
        user_id: UUID | str,
        *,
        revoked_device_id: str,
        replacement_device_id: str,
        occurred_at: datetime | None = None,
        platform: str | None = None,
    ) -> None:
        self._repo.record_replacement(
            user_id,
            revoked_device_id=revoked_device_id,
            replacement_device_id=replacement_device_id,
            occurred_at=occurred_at,
            platform=platform,
        )

    def clear_device_replacement_limit_audited(
        self,
        user_id: UUID | str,
        *,
        admin_user_id: UUID | str,
        reason: str,
        now: datetime | None = None,
    ) -> DeviceReplacementClearSummary:
        cleaned = (reason or "").strip()
        if not cleaned:
            raise ValueError("Reason is required")
        return self._repo.clear_device_replacement_limit_audited(
            user_id,
            admin_user_id=admin_user_id,
            reason=cleaned,
            now=now,
            replacement_window_days=self._replacement_window_days,
        )

    def bind_session(
        self,
        user_id: UUID | str,
        device_id: str,
        auth_session_id: str,
        *,
        now: datetime | None = None,
    ) -> Any:
        return self._repo.bind_session(
            user_id, device_id, auth_session_id, now=now
        )

    def end_session_binding(
        self,
        user_id: UUID | str,
        auth_session_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        self._repo.end_session_binding(user_id, auth_session_id, now=now)

    def hash_token(self, token: str) -> str:
        return hash_device_token(self._hmac_secret, token)

    def _safe_count(self, user_id: UUID | str) -> int:
        try:
            return int(self._repo.count_active(user_id))
        except Exception:
            return 0

    def _replacement_limited(
        self, user_id: UUID | str, *, now: datetime | None = None
    ) -> bool:
        """True when a new installation would be a blocked replacement."""

        try:
            unpaired = self._repo.find_unpaired_revoked(user_id)
        except Exception:
            return False
        if unpaired is None:
            return False
        return self.count_recent_replacements(user_id, now=now) >= self._replacement_limit

    def _hash(self, token: str | None) -> tuple[str | None, bool]:
        if not token:
            return None, True
        try:
            return hash_device_token(self._hmac_secret, token), False
        except DeviceHmacConfigError:
            return None, True

    def _lookup(
        self, user_id: UUID | str, token: str | None
    ) -> tuple[UserDevice | None, bool]:
        digest, config_error = self._hash(token)
        if config_error or digest is None:
            # Missing token is not a config error during inspect of a cookie-less
            # request that has not minted yet; treat as unknown installation.
            if not token:
                return None, False
            return None, True
        device = self._repo.get_by_hash(as_user_id(user_id), digest)
        return device, False
