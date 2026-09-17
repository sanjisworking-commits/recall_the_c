"""Playground device registry. Separate from auth sessions and subscriptions.

``rtc_device`` identifies an installation. ``rtc_session`` authenticates a login.
Device restriction applies only to paid Playground, never Constitution or /laws.
"""

from constitution_memorizer.devices.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REVOKED,
    DEVICE_BLOCK_REASONS,
    PLATFORM_ANDROID,
    PLATFORM_WEB,
    DeviceAccess,
    UserDevice,
    UserDeviceSession,
)
from constitution_memorizer.devices.service import DeviceService
from constitution_memorizer.devices.token import (
    DEVICE_COOKIE_NAME,
    hash_device_token,
    mint_installation_token,
)

__all__ = [
    "BLOCK_DEVICE_CONFIG_ERROR",
    "BLOCK_DEVICE_LIMIT",
    "BLOCK_DEVICE_REVOKED",
    "DEVICE_BLOCK_REASONS",
    "DEVICE_COOKIE_NAME",
    "DeviceAccess",
    "DeviceService",
    "PLATFORM_ANDROID",
    "PLATFORM_WEB",
    "UserDevice",
    "UserDeviceSession",
    "hash_device_token",
    "mint_installation_token",
]
