"""Request-scoped entitlement snapshot. Memoized on ``request.state``."""

from __future__ import annotations

from datetime import datetime

from constitution_memorizer.entitlements.models import EntitlementSnapshot
from constitution_memorizer.entitlements.service import EntitlementService

_UNSET = object()


def get_entitlement_snapshot(
    request: object,
    *,
    now: datetime | None = None,
) -> EntitlementSnapshot:
    """Resolve once per request. Never calls a payment provider."""

    cached = getattr(getattr(request, "state", None), "entitlement_snapshot", _UNSET)
    if cached is not _UNSET:
        return cached  # type: ignore[return-value]
    service = getattr(getattr(request, "app", None), "state", None)
    resolver = getattr(service, "entitlement_service", None)
    if resolver is None:
        resolver = EntitlementService()
    snapshot = resolver.resolve_for_request(request, now=now)
    state = getattr(request, "state", None)
    if state is not None:
        state.entitlement_snapshot = snapshot
    return snapshot
