"""Template context for a Bare Act's page: the generated Act head.

One builder for every eligible Act and every viewer. The Laws route renders
it directly; the Playground Add route renders the same context underneath
its dialog, so a directly opened Add URL is the Act page with the sheet open
(M2 decision Q4) rather than a page of its own.

Everything here is read off objects the request has already loaded — the
Act model, the catalogue entry, the entitlement snapshot. It holds no state,
reads no file of its own and never changes eligibility or entitlements.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import Request

from constitution_memorizer.web.act_info import build_act_info
from constitution_memorizer.web.bare_acts import BareAct
from constitution_memorizer.web.law_catalog import load_catalog
from constitution_memorizer.web.seo import (
    build_breadcrumb_schema,
    build_law_seo,
    law_canonical_url,
    laws_hub_canonical_url,
    serialize_structured_data,
)


def halted_law_presentation(request: Request, law_id: str, state):
    """Halted law CTA overlay for Laws index and Bare Act.

    Open-period Halted membership is KIND_RESUME without a badge. Retained
    roster laws reuse the Expired already_active presentation; the primary
    action is the Halted recovery CTA from gate_view(BLOCK_PAYMENT_HALTED).
    """

    from constitution_memorizer.entitlements.models import BLOCK_PAYMENT_HALTED
    from constitution_memorizer.playground.http import playground_user_id
    from constitution_memorizer.playground.urls import sections_path
    from constitution_memorizer.playground.view import (
        PLAYGROUND_BILLING_PATH,
        gate_view,
    )

    if state is None:
        return None
    gate = gate_view(reason=BLOCK_PAYMENT_HALTED)
    billed = gate.cta_href or PLAYGROUND_BILLING_PATH
    recover = gate.cta_label
    uid = playground_user_id(request)
    roster = getattr(request.app.state, "roster", None)
    hrefs = (state.primary_href or "", state.secondary_href or "")
    learn = any("/learn" in href for href in hrefs)
    active = bool(state.active_this_period)
    if not active and uid is not None and roster is not None:
        active = roster.is_law_active_this_period(uid, law_id)
    if active:
        return replace(
            state,
            kind="already_active",
            active_this_period=True,
            badge="in_playground",
            badge_label="Already in Playground",
            primary_label=recover,
            primary_href=billed,
            secondary_label="Sections",
            secondary_href=sections_path(law_id),
            secondary_copy="",
            opens_sheet=False,
        )
    if learn:
        primary_is_learn = "/learn" in (state.primary_href or "")
        secondary_is_learn = "/learn" in (state.secondary_href or "")
        return replace(
            state,
            primary_label=recover if primary_is_learn else state.primary_label,
            primary_href=billed if primary_is_learn else state.primary_href,
            secondary_href="" if secondary_is_learn else state.secondary_href,
            secondary_label="" if secondary_is_learn else state.secondary_label,
            opens_sheet=False,
        )
    return replace(
        state,
        primary_label=recover,
        primary_href=billed,
        opens_sheet=False,
    )


def bare_act_page_context(request: Request, bare: BareAct) -> dict[str, Any]:
    """Everything ``bare_act.html`` needs for one Act and the current viewer."""

    from constitution_memorizer.entitlements.dependencies import (
        get_entitlement_snapshot,
        request_is_active_plus,
        request_is_expired_subscriber,
        request_is_halted_subscriber,
    )
    from constitution_memorizer.playground.access import public_law_states
    from constitution_memorizer.playground.eligibility import (
        is_playground_eligible_law,
    )

    playground_state = None
    eligible = is_playground_eligible_law(bare.slug)
    if eligible:
        playground_state = public_law_states(request, (bare.slug,)).get(bare.slug)
    expired_bareact = request_is_expired_subscriber(request)
    halted_bareact = request_is_halted_subscriber(request)
    expired_header_status = ""
    halted_header_status = ""
    if expired_bareact or halted_bareact:
        from constitution_memorizer.playground.view import gate_view

        if expired_bareact:
            snap = get_entitlement_snapshot(request)
            expired_header_status = gate_view(
                reason=str(snap.playground_block_reason or "")
            ).title
        if halted_bareact:
            from constitution_memorizer.entitlements.models import (
                BLOCK_PAYMENT_HALTED,
            )

            # Presentation only: elapsed Halted keeps paid_period_ended as
            # the block reason, but the header stays Halted-family.
            halted_header_status = gate_view(reason=BLOCK_PAYMENT_HALTED).title
            playground_state = halted_law_presentation(
                request, bare.slug, playground_state
            )
    seo_title, seo_description = build_law_seo(
        law_name=bare.title, meta_label=bare.meta_label
    )
    breadcrumb = build_breadcrumb_schema(
        [
            ("Laws", laws_hub_canonical_url()),
            (bare.short_title, law_canonical_url(bare.slug)),
        ]
    )
    # The catalogue entry travels alongside the Act, not inside it: lifecycle
    # is editorial metadata and the statutory model stays statutory.
    # load_catalog() is a cached read of the static seed and hydrates no Act
    # JSON.
    catalog_law = load_catalog().by_full_act(bare.slug)
    return {
        "act": bare,
        "catalog_law": catalog_law,
        # Built per request from two already-loaded objects. It holds no
        # state and reads no file of its own.
        "act_info": build_act_info(bare, catalog_law),
        "seo_title": seo_title,
        "seo_description": seo_description,
        "canonical_url": law_canonical_url(bare.slug),
        "structured_data_json": serialize_structured_data(breadcrumb),
        "playground_eligible": eligible,
        "playground_state": playground_state,
        "in_playground": bool(
            playground_state and playground_state.active_this_period
        ),
        "plus_bareact": request_is_active_plus(request),
        "expired_bareact": expired_bareact,
        "halted_bareact": halted_bareact,
        "expired_header_status": expired_header_status,
        "halted_header_status": halted_header_status,
    }
