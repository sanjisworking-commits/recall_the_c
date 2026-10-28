"""Postgres device registry. Isolation is application-level (ENABLE RLS, no policies)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from constitution_memorizer.admin.audit import (
    AuditEntry,
    PG_AUDIT_INSERT,
    pg_audit_params,
)
from constitution_memorizer.devices.models import (
    ACTION_CLEAR_DEVICE_REPLACEMENT_LIMIT,
    DEVICE_REPLACEMENT_LIMIT,
    DEVICE_REPLACEMENT_WINDOW_DAYS,
    DeviceReplacementClearSummary,
    DeviceResetSummary,
    REGISTER_CREATED,
    REGISTER_EXISTING,
    REGISTER_INVALID,
    REGISTER_LIMIT,
    REGISTER_REPLACEMENT_LIMIT,
    REGISTER_REVOKED,
    RegisterOutcome,
    UserDevice,
    UserDeviceSession,
    replacement_window_start,
    require_platform,
    safe_registry_state,
)
from constitution_memorizer.devices.repository import (
    device_from_mapping,
    session_from_mapping,
)
from constitution_memorizer.progress.user_ids import as_user_id

# Namespace for pg_advisory_xact_lock(namespace, key). Not a secret.
_DEVICE_LOCK_NS = 872011

_DEVICE_SELECT = """
SELECT id, user_id, device_key_hash, platform, display_name,
       first_registered_at, last_seen_at, revoked_at, created_at, updated_at
FROM user_device
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _lock_key(user_id: str) -> int:
    digest = hashlib.sha256(user_id.encode("utf-8")).digest()[:4]
    return int.from_bytes(digest, "big", signed=True)


class PostgresDeviceRepository:
    """Production registration: advisory xact lock, then re-check, then insert."""

    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def get_by_hash(self, user_id: UUID | str, device_key_hash: str) -> UserDevice | None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _DEVICE_SELECT + " WHERE user_id = %s AND device_key_hash = %s",
                    (uid, device_key_hash),
                )
                row = cur.fetchone()
        return device_from_mapping(row) if row is not None else None

    def get_by_id(self, user_id: UUID | str, device_id: str) -> UserDevice | None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _DEVICE_SELECT + " WHERE user_id = %s AND id = %s",
                    (uid, device_id),
                )
                row = cur.fetchone()
        return device_from_mapping(row) if row is not None else None

    def list_devices(self, user_id: UUID | str) -> list[UserDevice]:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _DEVICE_SELECT
                    + " WHERE user_id = %s ORDER BY first_registered_at ASC",
                    (uid,),
                )
                rows = cur.fetchall()
        return [device_from_mapping(row) for row in rows]

    def count_active(self, user_id: UUID | str) -> int:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM user_device
                    WHERE user_id = %s AND revoked_at IS NULL
                    """,
                    (uid,),
                )
                row = cur.fetchone()
        return int(row["n"] if row is not None else 0)

    def register_if_under_cap(
        self,
        user_id: UUID | str,
        *,
        device_key_hash: str,
        platform: str,
        display_name: str | None,
        limit: int,
        now: datetime | None = None,
        replacement_limit: int = DEVICE_REPLACEMENT_LIMIT,
        replacement_window_days: int = DEVICE_REPLACEMENT_WINDOW_DAYS,
    ) -> RegisterOutcome:
        if limit < 1:
            return RegisterOutcome(status=REGISTER_INVALID, device=None)
        try:
            platform = require_platform(platform)
        except ValueError:
            return RegisterOutcome(status=REGISTER_INVALID, device=None)
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (_DEVICE_LOCK_NS, _lock_key(uid)),
                )
                cur.execute(
                    _DEVICE_SELECT + " WHERE user_id = %s AND device_key_hash = %s",
                    (uid, device_key_hash),
                )
                existing = cur.fetchone()
                if existing is not None:
                    device = device_from_mapping(existing)
                    if device.is_revoked:
                        conn.commit()
                        return RegisterOutcome(status=REGISTER_REVOKED, device=device)
                    cur.execute(
                        """
                        UPDATE user_device
                        SET last_seen_at = %s, updated_at = %s
                        WHERE user_id = %s AND id = %s
                        """,
                        (clock, clock, uid, device.id),
                    )
                    cur.execute(
                        _DEVICE_SELECT + " WHERE user_id = %s AND id = %s",
                        (uid, device.id),
                    )
                    row = cur.fetchone()
                    conn.commit()
                    return RegisterOutcome(
                        status=REGISTER_EXISTING,
                        device=device_from_mapping(row) if row else device,
                    )
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM user_device
                    WHERE user_id = %s AND revoked_at IS NULL
                    """,
                    (uid,),
                )
                count_row = cur.fetchone()
                active = int(count_row["n"] if count_row is not None else 0)
                if active >= limit:
                    conn.commit()
                    return RegisterOutcome(status=REGISTER_LIMIT, device=None)
                unpaired = self._unpaired_revoked_on_cursor(cur, uid)
                if unpaired is not None:
                    since = replacement_window_start(
                        clock, days=replacement_window_days
                    )
                    recent = self._count_recent_on_cursor(cur, uid, since)
                    if recent >= replacement_limit:
                        conn.commit()
                        return RegisterOutcome(
                            status=REGISTER_REPLACEMENT_LIMIT, device=None
                        )
                device_id = str(uuid4())
                cur.execute(
                    """
                    INSERT INTO user_device (
                        id, user_id, device_key_hash, platform, display_name,
                        first_registered_at, last_seen_at, revoked_at,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
                    """,
                    (
                        device_id,
                        uid,
                        device_key_hash,
                        platform,
                        display_name,
                        clock,
                        clock,
                        clock,
                        clock,
                    ),
                )
                if unpaired is not None:
                    self._insert_replacement_on_cursor(
                        cur,
                        uid,
                        revoked_device_id=unpaired.id,
                        replacement_device_id=device_id,
                        occurred_at=clock,
                        platform=platform,
                    )
                cur.execute(
                    _DEVICE_SELECT + " WHERE user_id = %s AND id = %s",
                    (uid, device_id),
                )
                row = cur.fetchone()
                conn.commit()
        return RegisterOutcome(
            status=REGISTER_CREATED,
            device=device_from_mapping(row) if row is not None else None,
        )

    def revoke_device(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> UserDevice | None:
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _DEVICE_SELECT + " WHERE user_id = %s AND id = %s",
                    (uid, device_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    """
                    UPDATE user_device
                    SET revoked_at = COALESCE(revoked_at, %s), updated_at = %s
                    WHERE user_id = %s AND id = %s
                    """,
                    (clock, clock, uid, device_id),
                )
                cur.execute(
                    """
                    UPDATE user_device_session
                    SET revoked_at = COALESCE(revoked_at, %s)
                    WHERE user_id = %s AND device_id = %s AND revoked_at IS NULL
                    """,
                    (clock, uid, device_id),
                )
                cur.execute(
                    _DEVICE_SELECT + " WHERE user_id = %s AND id = %s",
                    (uid, device_id),
                )
                updated = cur.fetchone()
                conn.commit()
        return device_from_mapping(updated) if updated is not None else None

    def revoke_all_devices(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> DeviceResetSummary:
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                summary = self._revoke_all_on_cursor(cur, uid, clock)
                conn.commit()
        return summary

    def reset_devices_audited(
        self,
        user_id: UUID | str,
        *,
        admin_user_id: UUID | str,
        reason: str,
        now: datetime | None = None,
    ) -> DeviceResetSummary:
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        with self._pool.connection() as conn:
            try:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    summary = self._revoke_all_on_cursor(cur, uid, clock)
                    entry = AuditEntry(
                        admin_user_id=as_user_id(admin_user_id),
                        action="reset_devices",
                        target_user_id=uid,
                        target_type="user_device",
                        target_id=None,
                        before_state=summary.before,
                        after_state=summary.after,
                        reason=reason,
                    )
                    cur.execute(PG_AUDIT_INSERT, pg_audit_params(entry, clock))
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
        return summary

    def _revoke_all_on_cursor(
        self, cur: Any, uid: str, clock: datetime
    ) -> DeviceResetSummary:
        cur.execute(
            _DEVICE_SELECT + " WHERE user_id = %s ORDER BY first_registered_at ASC",
            (uid,),
        )
        devices = [device_from_mapping(row) for row in cur.fetchall()]
        before = safe_registry_state(devices)
        cur.execute(
            """
            UPDATE user_device
            SET revoked_at = COALESCE(revoked_at, %s), updated_at = %s
            WHERE user_id = %s AND revoked_at IS NULL
            """,
            (clock, clock, uid),
        )
        cur.execute(
            """
            UPDATE user_device_session
            SET revoked_at = COALESCE(revoked_at, %s)
            WHERE user_id = %s AND revoked_at IS NULL
            """,
            (clock, uid),
        )
        cur.execute(
            _DEVICE_SELECT + " WHERE user_id = %s ORDER BY first_registered_at ASC",
            (uid,),
        )
        after_devices = [device_from_mapping(row) for row in cur.fetchall()]
        revoked_ids = tuple(row.id for row in devices if not row.is_revoked)
        return DeviceResetSummary(
            before=before,
            after=safe_registry_state(after_devices),
            revoked_device_ids=revoked_ids,
        )

    def touch_last_seen(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_device
                    SET last_seen_at = %s, updated_at = %s
                    WHERE user_id = %s AND id = %s AND revoked_at IS NULL
                    """,
                    (clock, clock, uid, device_id),
                )
                conn.commit()

    def bind_session(
        self,
        user_id: UUID | str,
        device_id: str,
        auth_session_id: str,
        *,
        now: datetime | None = None,
    ) -> UserDeviceSession | None:
        if not auth_session_id:
            return None
        uid = as_user_id(user_id)
        device = self.get_by_id(uid, device_id)
        if device is None or device.is_revoked:
            return None
        clock = now or _utc_now()
        session_row_id = str(uuid4())
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO user_device_session (
                        id, user_id, device_id, auth_session_id,
                        started_at, last_seen_at, revoked_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NULL)
                    ON CONFLICT (user_id, auth_session_id) DO UPDATE SET
                        device_id = EXCLUDED.device_id,
                        last_seen_at = EXCLUDED.last_seen_at,
                        revoked_at = NULL
                    """,
                    (session_row_id, uid, device_id, auth_session_id, clock, clock),
                )
                cur.execute(
                    """
                    SELECT id, user_id, device_id, auth_session_id,
                           started_at, last_seen_at, revoked_at
                    FROM user_device_session
                    WHERE user_id = %s AND auth_session_id = %s
                    """,
                    (uid, auth_session_id),
                )
                row = cur.fetchone()
                conn.commit()
        return session_from_mapping(row) if row is not None else None

    def end_session_binding(
        self,
        user_id: UUID | str,
        auth_session_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        if not auth_session_id:
            return
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_device_session
                    SET revoked_at = COALESCE(revoked_at, %s)
                    WHERE user_id = %s AND auth_session_id = %s AND revoked_at IS NULL
                    """,
                    (clock, uid, auth_session_id),
                )
                conn.commit()

    def list_sessions(self, user_id: UUID | str, device_id: str) -> list[UserDeviceSession]:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, user_id, device_id, auth_session_id,
                           started_at, last_seen_at, revoked_at
                    FROM user_device_session
                    WHERE user_id = %s AND device_id = %s
                    ORDER BY started_at ASC
                    """,
                    (uid, device_id),
                )
                rows = cur.fetchall()
        return [session_from_mapping(row) for row in rows]

    def count_recent_replacements(
        self,
        user_id: UUID | str,
        since: datetime,
    ) -> int:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                return self._count_recent_on_cursor(cur, uid, since)

    def find_unpaired_revoked(self, user_id: UUID | str) -> UserDevice | None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                return self._unpaired_revoked_on_cursor(cur, uid)

    def record_replacement(
        self,
        user_id: UUID | str,
        *,
        revoked_device_id: str,
        replacement_device_id: str,
        occurred_at: datetime | None = None,
        platform: str | None = None,
    ) -> None:
        uid = as_user_id(user_id)
        clock = occurred_at or _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                self._insert_replacement_on_cursor(
                    cur,
                    uid,
                    revoked_device_id=revoked_device_id,
                    replacement_device_id=replacement_device_id,
                    occurred_at=clock,
                    platform=platform,
                )
                conn.commit()

    def clear_device_replacement_limit_audited(
        self,
        user_id: UUID | str,
        *,
        admin_user_id: UUID | str,
        reason: str,
        now: datetime | None = None,
        replacement_window_days: int = DEVICE_REPLACEMENT_WINDOW_DAYS,
    ) -> DeviceReplacementClearSummary:
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        since = replacement_window_start(clock, days=replacement_window_days)
        with self._pool.connection() as conn:
            try:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(%s, %s)",
                        (_DEVICE_LOCK_NS, _lock_key(uid)),
                    )
                    recent = self._count_recent_on_cursor(cur, uid, since)
                    cur.execute(
                        """
                        DELETE FROM user_device_replacement
                        WHERE user_id = %s AND occurred_at >= %s
                        """,
                        (uid, since),
                    )
                    deleted = int(cur.rowcount or 0)
                    summary = DeviceReplacementClearSummary(
                        before={"recent_replacement_count": recent},
                        after={"recent_replacement_count": 0},
                        deleted_count=max(0, deleted),
                    )
                    entry = AuditEntry(
                        admin_user_id=as_user_id(admin_user_id),
                        action=ACTION_CLEAR_DEVICE_REPLACEMENT_LIMIT,
                        target_user_id=uid,
                        target_type="user_device_replacement",
                        target_id=None,
                        before_state=summary.before,
                        after_state=summary.after,
                        reason=reason,
                    )
                    cur.execute(PG_AUDIT_INSERT, pg_audit_params(entry, clock))
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
        return summary

    def _unpaired_revoked_on_cursor(self, cur: Any, uid: str) -> UserDevice | None:
        cur.execute(
            _DEVICE_SELECT
            + """
            WHERE user_id = %s AND revoked_at IS NOT NULL
              AND id NOT IN (
                  SELECT revoked_device_id FROM user_device_replacement
                  WHERE user_id = %s
              )
            ORDER BY revoked_at DESC, id DESC
            LIMIT 1
            """,
            (uid, uid),
        )
        row = cur.fetchone()
        return device_from_mapping(row) if row is not None else None

    def _count_recent_on_cursor(self, cur: Any, uid: str, since: datetime) -> int:
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM user_device_replacement
            WHERE user_id = %s AND occurred_at >= %s
            """,
            (uid, since),
        )
        row = cur.fetchone()
        return int(row["n"] if row is not None else 0)

    def _insert_replacement_on_cursor(
        self,
        cur: Any,
        uid: str,
        *,
        revoked_device_id: str,
        replacement_device_id: str,
        occurred_at: datetime,
        platform: str | None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO user_device_replacement (
                id, user_id, revoked_device_id, replacement_device_id,
                occurred_at, created_at, platform
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid4()),
                uid,
                revoked_device_id,
                replacement_device_id,
                occurred_at,
                occurred_at,
                platform,
            ),
        )
