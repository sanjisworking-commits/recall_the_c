"""Playground tier-model activation flag (B1, §4.5 of the tier-revision plan).

``monthly`` is today's behaviour at ``3719b9f``: Free has no Playground,
Plus/Pro carry the 10/30 monthly caps, the Calendar and Visualize gates are
inert. ``choices`` activates the approved model: three permanent Free law
choices, unlimited Plus/Pro, Calendar create/edit for Plus and above,
Visualize for Pro and above. The flag changes permissions and copy only; it
never runs a migration, deletes a row or rewrites a row (§4.7).

The current model is published per request through a context variable so
that view helpers without a ``Request`` (plan cards, gate selectors) read
the same answer the resolvers used.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

TIER_MODEL_MONTHLY = "monthly"
TIER_MODEL_CHOICES = "choices"
TIER_MODELS: frozenset[str] = frozenset({TIER_MODEL_MONTHLY, TIER_MODEL_CHOICES})

# Free accounts under ``choices``: three distinct permanent law choices.
FREE_CHOICE_LIMIT = 3

_current_tier_model: ContextVar[str] = ContextVar(
    "playground_tier_model", default=TIER_MODEL_MONTHLY
)


def normalize_tier_model(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return TIER_MODEL_MONTHLY
    if text not in TIER_MODELS:
        raise ValueError("PLAYGROUND_TIER_MODEL must be 'monthly' or 'choices'")
    return text


def is_choice_model(value: object) -> bool:
    return str(value or "") == TIER_MODEL_CHOICES


def set_current_tier_model(value: object):
    """Publish the request's model. Returns the token for ``reset``."""

    return _current_tier_model.set(normalize_tier_model(value))


def reset_current_tier_model(token) -> None:
    _current_tier_model.reset(token)


def current_tier_model() -> str:
    return _current_tier_model.get()


def tier_model_for_app(app_state: Any) -> str:
    return normalize_tier_model(getattr(app_state, "playground_tier_model", None))
