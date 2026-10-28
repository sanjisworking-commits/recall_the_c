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


class SubscriptionStateError(SubscriptionError):
    """The current row is not in a state that allows this action."""


class CheckoutInProgressError(SubscriptionStateError):
    """A creation reservation is current; do not start a second provider sub."""


class CheckoutSignatureError(SubscriptionError):
    """Checkout HMAC did not match the server-stored subscription id."""


class CheckoutMismatchError(SubscriptionError):
    """Client-returned provider subscription id is not the stored one."""


class SameTierChangeError(SubscriptionError):
    """Upgrade/downgrade target is the current paid tier."""


class ChangePlanRequiredError(SubscriptionError):
    """User already has a live subscription; use the plan-change flow."""


class ResubscribeUnavailableError(SubscriptionStateError):
    """Terminal current row; M2-B does not implement resubscribe."""


class WebhookSignatureError(SubscriptionError):
    """Webhook HMAC did not match the current or previous secret."""


class DuplicateWebhookEventError(SubscriptionError):
    """Provider event id is already stored."""
