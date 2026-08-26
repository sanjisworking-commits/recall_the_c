"""Multi-user application settings loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from constitution_memorizer.auth.exceptions import AuthConfigError

AppEnv = Literal["development", "staging", "production", "test"]


def load_env_file(path: Path | str | None = None, *, override: bool = False) -> Path | None:
    """
    Load KEY=VALUE pairs from a .env file into os.environ.

    Does not override existing non-empty environment variables unless override=True.
    Returns the path loaded, or None if no file was found.
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    else:
        cwd = Path.cwd() / ".env"
        candidates.append(cwd)
        # Also try repo-root-ish relative to this package (…/memorize_the_c/.env)
        pkg_root = Path(__file__).resolve().parents[3]
        candidates.append(pkg_root / ".env")

    env_path = next((p for p in candidates if p.is_file()), None)
    if env_path is None:
        return None

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not key:
            continue
        if override or key not in os.environ or os.environ.get(key, "") == "":
            os.environ[key] = value
    return env_path


class MultiUserSettings(BaseSettings):
    """Hosted multi-user configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: AppEnv = Field(default="development", alias="APP_ENV")
    app_base_url: str = Field(default="http://127.0.0.1:8010", alias="APP_BASE_URL")
    port: int = Field(default=8010, alias="PORT")

    database_url: str = Field(default="", alias="DATABASE_URL")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    session_secret: str = Field(default="", alias="SESSION_SECRET")

    auth_google_enabled: bool = Field(default=True, alias="AUTH_GOOGLE_ENABLED")
    # Phone OTP is paused until SMS provider registration completes. The login
    # page still shows the option with a "not currently available" tag.
    auth_phone_enabled: bool = Field(default=False, alias="AUTH_PHONE_ENABLED")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")

    # CAPTCHA integration point (optional; validated only when enabled).
    captcha_enabled: bool = Field(default=False, alias="CAPTCHA_ENABLED")
    captcha_secret: str = Field(default="", alias="CAPTCHA_SECRET")

    # Optional Resend admin email for issue reports (all three required to enable).
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    report_email_from: str = Field(default="", alias="REPORT_EMAIL_FROM")
    report_email_to: str = Field(default="", alias="REPORT_EMAIL_TO")

    # Optional Cloudflare Turnstile for POST /api/report-issue (not CAPTCHA_*).
    report_turnstile_enabled: bool = Field(
        default=False, alias="REPORT_TURNSTILE_ENABLED"
    )
    report_turnstile_site_key: str = Field(
        default="", alias="REPORT_TURNSTILE_SITE_KEY"
    )
    report_turnstile_secret_key: str = Field(
        default="", alias="REPORT_TURNSTILE_SECRET_KEY"
    )

    multiuser_enabled: bool = Field(default=False, alias="MULTIUSER_ENABLED")

    # V1 production: Memory Log and Relevant Laws stay off until Postgres-ready.
    memory_log_enabled: bool = Field(default=False, alias="MEMORY_LOG_ENABLED")
    relevant_laws_enabled: bool = Field(
        default=False, alias="RELEVANT_LAWS_ENABLED"
    )

    # 3-Free-Article entitlement boundary (claim prompts, Type/Recite locks,
    # cap gate, access-status surfaces). Stays dormant everywhere until the
    # full Article-aware Learn/Done flow has landed and been tested.
    article_entitlements_enabled: bool = Field(
        default=False, alias="ARTICLE_ENTITLEMENTS_ENABLED"
    )

    # Pricing page (/pricing). Default false everywhere; set true explicitly in
    # the environment where it should be visible. Public launch waits for a
    # working purchase flow.
    pricing_enabled: bool = Field(default=False, alias="PRICING_ENABLED")

    # Admin console (/admin/*) and the Admin nav link. Gates the console
    # ONLY: an admin identity's full Recall entitlement follows its
    # user_roles row and is unaffected by this flag — removing the role
    # (scripts/revoke_admin.py) is how admin access is revoked. Default
    # false everywhere; enable explicitly where the console should exist.
    admin_enabled: bool = Field(default=False, alias="ADMIN_ENABLED")

    # Razorpay Standard Checkout. Both keys present = checkout is live on the
    # purchase flow; either missing = the /subscribe/pay page keeps its
    # "opens soon" placeholder. The key secret never reaches a template or
    # client payload — it is used only server-side (order create + HMAC verify).
    razorpay_key_id: str = Field(default="", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="", alias="RAZORPAY_KEY_SECRET")

    # Google Calendar integration. A DEDICATED OAuth client (never the
    # Supabase sign-in client — the Calendar grant must be independently
    # revocable). GCAL_TOKEN_KEY is the Fernet key sealing refresh tokens at
    # rest; all three present = the feature exists, any missing = the
    # Revision-calendar settings section is hidden and routes 404.
    gcal_client_id: str = Field(default="", alias="GCAL_CLIENT_ID")
    gcal_client_secret: str = Field(default="", alias="GCAL_CLIENT_SECRET")
    gcal_token_key: str = Field(default="", alias="GCAL_TOKEN_KEY")

    # Deepgram Nova-3 for Letters/Recite. Missing key → app still starts;
    # speech routes return unavailable and the UI offers typed fallback.
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")

    legal_entity_name: str = Field(default="", alias="LEGAL_ENTITY_NAME")
    legal_business_address: str = Field(default="", alias="LEGAL_BUSINESS_ADDRESS")
    legal_jurisdiction: str = Field(default="", alias="LEGAL_JURISDICTION")
    legal_support_email: str = Field(default="", alias="LEGAL_SUPPORT_EMAIL")
    legal_privacy_email: str = Field(default="", alias="LEGAL_PRIVACY_EMAIL")
    legal_grievance_email: str = Field(default="", alias="LEGAL_GRIEVANCE_EMAIL")
    legal_grievance_officer: str = Field(default="", alias="LEGAL_GRIEVANCE_OFFICER")
    legal_privacy_contact: str = Field(default="", alias="LEGAL_PRIVACY_CONTACT")

    @property
    def gcal_configured(self) -> bool:
        return bool(
            self.gcal_client_id and self.gcal_client_secret and self.gcal_token_key
        )

    @field_validator(
        "auth_google_enabled",
        "auth_phone_enabled",
        "cookie_secure",
        "captcha_enabled",
        "report_turnstile_enabled",
        "multiuser_enabled",
        "memory_log_enabled",
        "relevant_laws_enabled",
        "article_entitlements_enabled",
        "pricing_enabled",
        "admin_enabled",
        mode="before",
    )
    @classmethod
    def _parse_bool(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return value

    def validate_for_startup(self, *, require_secrets: bool = False) -> None:
        """Raise AuthConfigError when multi-user config is incomplete."""
        staging = self.app_env in {"staging", "production"}
        if staging:
            require_secrets = True
            if not self.auth_google_enabled and not self.auth_phone_enabled:
                raise AuthConfigError(
                    "At least one of AUTH_GOOGLE_ENABLED or AUTH_PHONE_ENABLED "
                    "must be true in staging/production."
                )
        if not require_secrets:
            return

        required: list[tuple[str, str]] = [
            ("SUPABASE_URL", self.supabase_url),
            ("SUPABASE_ANON_KEY", self.supabase_anon_key),
            ("SESSION_SECRET", self.session_secret),
        ]
        if staging:
            required.insert(0, ("DATABASE_URL", self.database_url))

        missing = [name for name, val in required if not (val or "").strip()]
        if missing:
            raise AuthConfigError(
                "Missing required multi-user settings: "
                + ", ".join(missing)
                + ". Put them in .env (SUPABASE_URL must be "
                "https://<project-ref>.supabase.co, not the dashboard URL)."
            )
        if "supabase.com/dashboard" in (self.supabase_url or ""):
            raise AuthConfigError(
                "SUPABASE_URL looks like the dashboard link. Use the API URL "
                "instead, e.g. https://YOUR_PROJECT_REF.supabase.co"
            )
        if self.captcha_enabled and not self.captcha_secret:
            raise AuthConfigError(
                "CAPTCHA_SECRET is required when CAPTCHA_ENABLED=true"
            )

    def missing_supabase(self) -> list[str]:
        missing: list[str] = []
        if not (self.supabase_url or "").strip():
            missing.append("SUPABASE_URL")
        if not (self.supabase_anon_key or "").strip():
            missing.append("SUPABASE_ANON_KEY")
        return missing

    def issue_report_notify_configured(self) -> bool:
        """True only when Resend API key, from, and to are all non-empty."""
        return bool(
            (self.resend_api_key or "").strip()
            and (self.report_email_from or "").strip()
            and (self.report_email_to or "").strip()
        )

    def issue_report_turnstile_configured(self) -> bool:
        """True when Turnstile is enabled and both keys are non-empty."""
        return bool(
            self.report_turnstile_enabled
            and (self.report_turnstile_site_key or "").strip()
            and (self.report_turnstile_secret_key or "").strip()
        )

    def validate_issue_report_turnstile(self) -> None:
        """
        Fail closed when Turnstile is enabled without both keys.

        Independent of multi-user auth validate_for_startup(); call from create_app
        unconditionally so Report Issue wiring cannot skip this check.
        """
        if not self.report_turnstile_enabled:
            return
        missing: list[str] = []
        if not (self.report_turnstile_site_key or "").strip():
            missing.append("REPORT_TURNSTILE_SITE_KEY")
        if not (self.report_turnstile_secret_key or "").strip():
            missing.append("REPORT_TURNSTILE_SECRET_KEY")
        if missing:
            raise AuthConfigError(
                "REPORT_TURNSTILE_ENABLED=true requires: " + ", ".join(missing)
            )

    def issue_report_turnstile_allowed_hostnames(self) -> frozenset[str]:
        """Hostnames accepted from Turnstile Siteverify (production uses APP_BASE_URL)."""
        hosts: set[str] = set()
        parsed = urlparse((self.app_base_url or "").strip())
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
        if self.app_env in {"development", "test"}:
            hosts.update({"localhost", "127.0.0.1"})
        return frozenset(hosts)


@lru_cache(maxsize=1)
def get_multiuser_settings() -> MultiUserSettings:
    return MultiUserSettings()


def clear_settings_cache() -> None:
    get_multiuser_settings.cache_clear()
