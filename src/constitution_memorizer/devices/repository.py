"""SQLite device registry. Owner methods always require ``user_id``."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Protocol
from uuid import UUID, uuid4

from constitution_memorizer.devices.models import (
    DEVICE_PLATFORMS,
    REGISTER_CREATED,
    REGISTER_EXISTING,
    REGISTER_INVALID,
    REGISTER_LIMIT,
    REGISTER_REVOKED,
    RegisterOutcome,
    UserDevice,
    UserDeviceSession,
)
from constitution_memorizer.progress.user_ids import as_user_id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _require_platform(platform: str) -> str:
    value = (platform or "").strip().lower()
    if value not in DEVICE_PLATFORMS:
        raise ValueError("unsupported device platform")
    return value


def device_from_mapping(row: Any) -> UserDevice:
    mapping = dict(row)
    return UserDevice(
        id=str(mapping["id"]),
        user_id=str(mapping["user_id"]),
        device_key_hash=str(mapping["device_key_hash"]),
        platform=str(mapping["platform"]),
        display_name=mapping.get("display_name"),
        first_registered_at=_parse_dt(mapping["first_registered_at"]),  # type: ignore[arg-type]
        last_seen_at=_parse_dt(mapping["last_seen_at"]),  # type: ignore[arg-type]
        revoked_at=_parse_dt(mapping.get("revoked_at")),
        created_at=_parse_dt(mapping["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_dt(mapping["updated_at"]),  # type: ignore[arg-type]
    )


def session_from_mapping(row: Any) -> UserDeviceSession:
    mapping = dict(row)
    return UserDeviceSession(
        id=str(mapping["id"]),
        user_id=str(mapping["user_id"]),
        device_id=str(mapping["device_id"]),
        auth_session_id=str(mapping["auth_session_id"]),
        started_at=_parse_dt(mapping["started_at"]),  # type: ignore[arg-type]
        last_seen_at=_parse_dt(mapping["last_seen_at"]),  # type: ignore[arg-type]
        revoked_at=_parse_dt(mapping.get("revoked_at")),
    )


class DeviceRepository(Protocol):
    def get_by_hash(self, user_id: UUID | str, device_key_hash: str) -> UserDevice | None: ...

    def get_by_id(self, user_id: UUID | str, device_id: str) -> UserDevice | None: ...

    def list_devices(self, user_id: UUID | str) -> list[UserDevice]: ...

    def count_active(self, user_id: UUID | str) -> int: ...

    def register_if_under_cap(
        self,
        user_id: UUID | str,
        *,
        device_key_hash: str,
        platform: str,
        display_name: str | None,
        limit: int,
        now: datetime | None = None,
    ) -> RegisterOutcome: ...

    def revoke_device(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> UserDevice | None: ...

    def touch_last_seen(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> None: ...

    def bind_session(
        self,
        user_id: UUID | str,
        device_id: str,
        auth_session_id: str,
        *,
        now: datetime | None = None,
    ) -> UserDeviceSession | None: ...

    def end_session_binding(
        self,
        user_id: UUID | str,
        auth_session_id: str,
        *,
        now: datetime | None = None,
    ) -> None: ...


_DEVICE_SELECT = """
SELECT id, user_id, device_key_hash, platform, display_name,
       first_registered_at, last_seen_at, revoked_at, created_at, updated_at
FROM user_device
"""


class SqliteDeviceRepository:
    """SQLite persistence. Registration uses BEGIN IMMEDIATE, not check-then-insert."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()
        try:
            self._conn.execute("PRAGMA busy_timeout = 8000")
        except sqlite3.Error:
            pass

    def get_by_hash(self, user_id: UUID | str, device_key_hash: str) -> UserDevice | None:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            _DEVICE_SELECT + " WHERE user_id = ? AND device_key_hash = ?",
            (uid, device_key_hash),
        ).fetchone()
        return device_from_mapping(row) if row is not None else None

    def get_by_id(self, user_id: UUID | str, device_id: str) -> UserDevice | None:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            _DEVICE_SELECT + " WHERE user_id = ? AND id = ?",
            (uid, device_id),
        ).fetchone()
        return device_from_mapping(row) if row is not None else None

    def list_devices(self, user_id: UUID | str) -> list[UserDevice]:
        uid = as_user_id(user_id)
        rows = self._conn.execute(
            _DEVICE_SELECT + " WHERE user_id = ? ORDER BY first_registered_at ASC",
            (uid,),
        ).fetchall()
        return [device_from_mapping(row) for row in rows]

    def count_active(self, user_id: UUID | str) -> int:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS n FROM user_device
            WHERE user_id = ? AND revoked_at IS NULL
            """,
            (uid,),
        ).fetchone()
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
    ) -> RegisterOutcome:
        if limit < 1:
            return RegisterOutcome(status=REGISTER_INVALID, device=None)
        try:
            platform = _require_platform(platform)
        except ValueError:
            return RegisterOutcome(status=REGISTER_INVALID, device=None)
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        stamp = _dt_iso(clock)
        with self._exclusive():
            existing = self._conn.execute(
                _DEVICE_SELECT + " WHERE user_id = ? AND device_key_hash = ?",
                (uid, device_key_hash),
            ).fetchone()
            if existing is not None:
                device = device_from_mapping(existing)
                if device.is_revoked:
                    return RegisterOutcome(status=REGISTER_REVOKED, device=device)
                self._conn.execute(
                    """
                    UPDATE user_device
                    SET last_seen_at = ?, updated_at = ?
                    WHERE user_id = ? AND id = ?
                    """,
                    (stamp, stamp, uid, device.id),
                )
                refreshed = self.get_by_id(uid, device.id)
                return RegisterOutcome(status=REGISTER_EXISTING, device=refreshed)
            count_row = self._conn.execute(
                """
                SELECT COUNT(*) AS n FROM user_device
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (uid,),
            ).fetchone()
            active = int(count_row["n"] if count_row is not None else 0)
            if active >= limit:
                return RegisterOutcome(status=REGISTER_LIMIT, device=None)
            device_id = str(uuid4())
            self._conn.execute(
                """
                INSERT INTO user_device (
                    id, user_id, device_key_hash, platform, display_name,
                    first_registered_at, last_seen_at, revoked_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    device_id,
                    uid,
                    device_key_hash,
                    platform,
                    display_name,
                    stamp,
                    stamp,
                    stamp,
                    stamp,
                ),
            )
            created = self.get_by_id(uid, device_id)
            return RegisterOutcome(status=REGISTER_CREATED, device=created)

    def revoke_device(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> UserDevice | None:
        uid = as_user_id(user_id)
        clock = now or _utc_now()
        stamp = _dt_iso(clock)
        with self._exclusive():
            row = self._conn.execute(
                _DEVICE_SELECT + " WHERE user_id = ? AND id = ?",
                (uid, device_id),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                """
                UPDATE user_device
                SET revoked_at = COALESCE(revoked_at, ?), updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (stamp, stamp, uid, device_id),
            )
            self._conn.execute(
                """
                UPDATE user_device_session
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE user_id = ? AND device_id = ? AND revoked_at IS NULL
                """,
                (stamp, uid, device_id),
            )
            return self.get_by_id(uid, device_id)

    def touch_last_seen(
        self,
        user_id: UUID | str,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        uid = as_user_id(user_id)
        stamp = _dt_iso(now or _utc_now())
        self._conn.execute(
            """
            UPDATE user_device
            SET last_seen_at = ?, updated_at = ?
            WHERE user_id = ? AND id = ? AND revoked_at IS NULL
            """,
            (stamp, stamp, uid, device_id),
        )
        self._conn.commit()

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
        stamp = _dt_iso(clock)
        session_row_id = str(uuid4())
        self._conn.execute(
            """
            INSERT INTO user_device_session (
                id, user_id, device_id, auth_session_id,
                started_at, last_seen_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(user_id, auth_session_id) DO UPDATE SET
                device_id = excluded.device_id,
                last_seen_at = excluded.last_seen_at,
                revoked_at = NULL
            """,
            (session_row_id, uid, device_id, auth_session_id, stamp, stamp),
        )
        self._conn.commit()
        row = self._conn.execute(
            """
            SELECT id, user_id, device_id, auth_session_id,
                   started_at, last_seen_at, revoked_at
            FROM user_device_session
            WHERE user_id = ? AND auth_session_id = ?
            """,
            (uid, auth_session_id),
        ).fetchone()
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
        stamp = _dt_iso(now or _utc_now())
        self._conn.execute(
            """
            UPDATE user_device_session
            SET revoked_at = COALESCE(revoked_at, ?)
            WHERE user_id = ? AND auth_session_id = ? AND revoked_at IS NULL
            """,
            (stamp, uid, auth_session_id),
        )
        self._conn.commit()

    def list_sessions(self, user_id: UUID | str, device_id: str) -> list[UserDeviceSession]:
        uid = as_user_id(user_id)
        rows = self._conn.execute(
            """
            SELECT id, user_id, device_id, auth_session_id,
                   started_at, last_seen_at, revoked_at
            FROM user_device_session
            WHERE user_id = ? AND device_id = ?
            ORDER BY started_at ASC
            """,
            (uid, device_id),
        ).fetchall()
        return [session_from_mapping(row) for row in rows]

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        with self._lock:
            started = False
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                started = True
            except sqlite3.OperationalError as exc:
                if "within a transaction" not in str(exc).lower():
                    raise
                started = False
            try:
                yield
                self._conn.commit()
            except Exception:
                if started:
                    try:
                        self._conn.rollback()
                    except sqlite3.Error:
                        pass
                raise
