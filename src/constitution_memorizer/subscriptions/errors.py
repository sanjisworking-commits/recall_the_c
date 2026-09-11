"""Domain and provider errors for Playground subscriptions."""

from __future__ import annotations


class SubscriptionError(Exception):
    """Base subscription-domain error. Message must never include secrets."""


class InvalidSubscriptionValue(SubscriptionError, ValueError):
    """Normalized tier or status is not in the locked set."""


class CurrentSubscriptionExistsError(SubscriptionError):
    """A current commercial subscription already exists for this user."""


class DuplicateProviderSubscriptionError(SubscriptionError):
    """Provider subscription id is already stored."""


class SubscriptionConfigError(SubscriptionError):
    """Deployment config is missing (plan IDs or API keys)."""


class SubscriptionValidationError(SubscriptionError, ValueError):
    """Caller omitted a required provider bound (total_count xor end_at)."""


class SubscriptionProviderError(SubscriptionError):
    """Razorpay Subscriptions HTTP boundary."""


class SubscriptionAuthError(SubscriptionProviderError):
    """Provider rejected API credentials."""


class SubscriptionRejectedError(SubscriptionProviderError):
    """Provider validation/rejection (4xx other than auth)."""


class SubscriptionNetworkError(SubscriptionProviderError):
    """Network, timeout, or DNS failure reaching the provider."""


class SubscriptionResponseError(SubscriptionProviderError):
    """Provider returned a payload that cannot be normalized."""
