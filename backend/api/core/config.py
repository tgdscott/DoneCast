from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings
try:
    from pydantic import AliasChoices  # pydantic v2
except Exception:  # pragma: no cover
    AliasChoices = None  # type: ignore
try:
    # pydantic-settings v2 preferred config style
    from pydantic_settings import SettingsConfigDict  # type: ignore
except Exception:  # pragma: no cover
    SettingsConfigDict = None  # type: ignore

log = logging.getLogger("api.core.config")

# Try to load .env.local explicitly using python-dotenv if available
# This ensures env vars are in os.environ before pydantic-settings reads them
# CRITICAL: This must happen BEFORE Settings class is instantiated
try:
    from dotenv import load_dotenv
    # Get the project root (backend/ directory)
    _PROJECT_ROOT = Path(__file__).parent.parent.parent
    _ENV_LOCAL = _PROJECT_ROOT / ".env.local"
    _ENV_FILE = _PROJECT_ROOT / ".env"
    
    # Load .env.local first, then .env (later files override earlier ones if override=True)
    # Use override=False so existing env vars take precedence (useful for CI/CD)
    if _ENV_LOCAL.exists():
        load_dotenv(_ENV_LOCAL, override=False)
        log.info(f"[config] Loaded .env.local from {_ENV_LOCAL}")
    elif _ENV_LOCAL.parent.exists():
        log.debug(f"[config] .env.local not found at {_ENV_LOCAL}")
    
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)
        log.info(f"[config] Loaded .env from {_ENV_FILE}")
except ImportError:
    # python-dotenv not installed, rely on pydantic-settings only
    log.debug("[config] python-dotenv not installed, skipping explicit .env loading")
except Exception as e:
    log.warning(f"[config] Failed to load .env files explicitly: {e}")

_PROD_ENVS = {"prod", "production", "stage", "staging"}
_DEV_ENVS = {"dev", "development", "local", "test", "testing"}


class Settings(BaseSettings):
    # --- Core Infrastructure ---
    APP_ENV: str = Field(
        default="dev",
        validation_alias=(
            AliasChoices("APP_ENV", "ENV", "PYTHON_ENV") if AliasChoices else "APP_ENV"
        ),
    )
    DB_USER: str = ""
    DB_PASS: str = ""
    DB_NAME: str = ""
    INSTANCE_CONNECTION_NAME: str = ""
    DATABASE_URL: Optional[str] = None
    SECRET_KEY: str = "dev-secret-key-change-me"  # Used for signing JWTs
    # Accept either SESSION_SECRET_KEY or legacy SESSION_SECRET from environment
    SESSION_SECRET_KEY: str = (
        Field(
            default="dev-session-secret-change-me",
            validation_alias=(AliasChoices("SESSION_SECRET_KEY", "SESSION_SECRET") if AliasChoices else None),
            description="Used for signing session cookies",
        )
    )

    # --- Service API Keys ---
    GEMINI_API_KEY: str = ""
    # --- AI Provider Selection ---
    # AI_PROVIDER can be: "gemini" (public generativeai) or "vertex" (Vertex AI Gemini)
    AI_PROVIDER: str = "gemini"
    VERTEX_PROJECT: Optional[str] = None
    VERTEX_LOCATION: str = "us-central1"
    VERTEX_MODEL: Optional[str] = None  # e.g. "gemini-1.5-flash"
    ELEVENLABS_API_KEY: str = ""
    ASSEMBLYAI_API_KEY: str = ""
    ASSEMBLYAI_WEBHOOK_SECRET: Optional[str] = None
    ASSEMBLYAI_WEBHOOK_URL: Optional[str] = None
    ASSEMBLYAI_WEBHOOK_HEADER: str = "X-AssemblyAI-Signature"
    
    # --- Auphonic API (Professional Audio Processing) ---
    AUPHONIC_API_KEY: str = ""
    
    # --- Audio Normalization (Non-Pro tiers) ---
    AUDIO_NORMALIZE_ENABLED: bool = Field(default=True, description="Enable program-loudness normalization for non-Pro tiers")
    AUDIO_NORMALIZE_TARGET_LUFS: float = Field(default=-16.0, description="Target loudness in LUFS (podcast standard)")
    AUDIO_NORMALIZE_TP_CEILING_DBTP: float = Field(default=-1.0, description="True-peak ceiling in dBTP")

    # --- Spreaker API ---
    SPREAKER_API_TOKEN: str = ""
    SPREAKER_CLIENT_ID: str = ""
    SPREAKER_CLIENT_SECRET: str = ""
    SPREAKER_REDIRECT_URI: Optional[str] = None

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # --- Stripe Billing ---
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # --- Application Behavior ---
    ADMIN_EMAIL: str = ""
    MEDIA_ROOT: str = "/tmp"
    OAUTH_BACKEND_BASE: Optional[str] = None
    APP_BASE_URL: Optional[str] = None  # For frontend redirects
    CORS_ALLOWED_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"
    PODCAST_WEBSITE_BASE_DOMAIN: str = "donecast.com"
    PODCAST_WEBSITE_GCS_BUCKET: str = "ppp-websites-us-west1"
    PODCAST_WEBSITE_CUSTOM_DOMAIN_MIN_TIER: str = "pro"
    
    # --- Cloud CDN (for faster media delivery and lower bandwidth costs) ---
    CDN_ENABLED: bool = True  # Set to False to bypass CDN and use direct GCS URLs
    CDN_IP: str = "34.120.53.200"  # Cloud CDN global load balancer IP

    # --- Legal ---
    # CRITICAL: Only change TERMS_VERSION when terms content actually changes!
    # Changing this forces ALL users to re-accept terms. See TERMS_VERSION_MANAGEMENT_CRITICAL.md
    # If you change this, run: python migrate_terms_version.py (if you don't need re-acceptance)
    TERMS_VERSION: str = "2025-10-22"
    # Default legal / marketing URLs (rebranded from getpodcastplus.com -> podcastplusplus.com -> donecast.com)
    TERMS_URL: str = "https://app.donecast.com/terms"

    # --- JWT Settings ---
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days (increased from 7 for better UX)

    # --- Dev Environment Safety (Cloud SQL Proxy) ---
    DEV_READ_ONLY: bool = Field(
        default=False,
        description="Prevent destructive operations in dev mode (for Cloud SQL Proxy safety)"
    )
    DEV_TEST_USER_EMAILS: str = Field(
        default="scott@scottgerhardt.com,test@example.com",
        description="Comma-separated dev test user emails (for filtering in dev mode)"
    )

    @property
    def is_dev_mode(self) -> bool:
        """Check if running in development mode"""
        env = (self.APP_ENV or "dev").strip().lower()
        return env in _DEV_ENVS

    @property
    def dev_test_users(self) -> list[str]:
        """Get list of test user emails for dev mode filtering"""
        return [email.strip() for email in self.DEV_TEST_USER_EMAILS.split(",") if email.strip()]

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        raw = self.CORS_ALLOWED_ORIGINS or ""
        normalized = raw.replace(';', ",")
        
        def _clean(origin: str) -> str:
            value = (origin or "").strip()
            if not value:
                return ""
            return value.rstrip('/')
        
        configured = [_clean(origin) for origin in normalized.split(',') if _clean(origin)]
        
        # Always allow the marketing site to call the API; browsers enforce exact origin
        # matching, so include both the bare and www variants. These entries are appended
        # even when the operator forgets to list them explicitly, preventing the
        # "No 'Access-Control-Allow-Origin' header" failures seen on getpodcastplus.com.
        # Rebrand: keep BOTH old and new domains during transitional period so existing
        # deployed frontends or cached service workers on the old domain continue to
        # function. Old domain entries can be removed after DNS / marketing cut-over.
        defaults = [
            # New brand (preferred)
            "https://donecast.com",
            "https://www.donecast.com",
            "https://app.donecast.com",
            "https://api.donecast.com",
            # Legacy (backward compatibility)
            "https://podcastplusplus.com",
            "https://www.podcastplusplus.com",
            "https://app.podcastplusplus.com",
            "https://api.podcastplusplus.com",
            "https://getpodcastplus.com",
            "https://www.getpodcastplus.com",
            "https://app.getpodcastplus.com",
            "https://api.getpodcastplus.com",
        ]
        
        seen: set[str] = set()
        merged: list[str] = []
        for origin in [*configured, *defaults]:
            cleaned = _clean(origin)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                merged.append(cleaned)
        
        return merged

    @model_validator(mode="after")
    def _apply_spreaker_defaults(self):
        if not self.SPREAKER_REDIRECT_URI:
            base = (self.OAUTH_BACKEND_BASE or "https://api.donecast.com").rstrip("/")
            # Unified Spreaker OAuth callback route (popup flow)
            self.SPREAKER_REDIRECT_URI = f"{base}/api/auth/spreaker/callback"
        return self

    @model_validator(mode="after")
    def _validate_and_warn(self):
        env = (self.APP_ENV or "dev").strip().lower()

        # PostgreSQL configuration required in all environments
        # BUT: Allow missing DB config during Docker builds and initial imports
        # The app will fail when it actually tries to use the database, but
        # this allows the module to be imported successfully
        has_discrete_db_config = all(
            getattr(self, key, "").strip()
            for key in ("DB_USER", "DB_PASS", "DB_NAME", "INSTANCE_CONNECTION_NAME")
        )
        has_database_url = bool((self.DATABASE_URL or "").strip())
        
        # Check if we're in a build/test environment where DB config isn't required yet
        skip_db_validation = os.getenv("SKIP_DB_VALIDATION", "false").lower() in ("true", "1", "yes")
        is_build_time = os.getenv("DOCKER_BUILD", "false").lower() in ("true", "1", "yes")

        if not (has_discrete_db_config or has_database_url) and not (skip_db_validation or is_build_time):
            # Only warn in dev/test, raise error in production
            if env in _PROD_ENVS:
                missing = "DATABASE_URL or DB_USER/DB_PASS/DB_NAME/INSTANCE_CONNECTION_NAME"
                raise ValueError(f"PostgreSQL configuration required: {missing}")
            else:
                # In dev/test, just log a warning but don't fail
                log.warning(
                    "[config] PostgreSQL configuration missing: DATABASE_URL or DB_USER/DB_PASS/DB_NAME/INSTANCE_CONNECTION_NAME. "
                    "Database operations will fail until configured."
                )

        # Surface optional secrets that default to blanks so operators know what's absent.
        optional_keys = [
            "AUPHONIC_API_KEY",
            "ELEVENLABS_API_KEY",
            "ASSEMBLYAI_API_KEY",
            "SPREAKER_API_TOKEN",
            "SPREAKER_CLIENT_ID",
            "SPREAKER_CLIENT_SECRET",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "GEMINI_API_KEY",
        ]
        missing_optional = [key for key in optional_keys if not getattr(self, key, "").strip()]
        if missing_optional:
            log.warning(
                "Missing/placeholder secrets%s: %s",
                " (dev allowed)" if env in _DEV_ENVS else "",
                ", ".join(sorted(missing_optional)),
            )

        # Ensure we do not accidentally run in production with placeholder secrets.
        if env in _PROD_ENVS:
            if not self.SECRET_KEY or self.SECRET_KEY == "dev-secret-key-change-me":
                raise ValueError("SECRET_KEY must be configured for production deployments")
            if not self.SESSION_SECRET_KEY or self.SESSION_SECRET_KEY.startswith("dev-"):
                raise ValueError(
                    "SESSION_SECRET_KEY must be configured for production deployments"
                )

        return self

    # pydantic-settings v2 uses model_config; keep fallback Config for older versions
    # Use absolute paths to ensure we find .env files regardless of working directory
    if SettingsConfigDict is not None:  # type: ignore
        _PROJECT_ROOT = Path(__file__).parent.parent.parent
        _ENV_LOCAL_ABS = str(_PROJECT_ROOT / ".env.local")
        _ENV_FILE_ABS = str(_PROJECT_ROOT / ".env")
        model_config = SettingsConfigDict(env_file=(_ENV_LOCAL_ABS, _ENV_FILE_ABS), extra="ignore")  # type: ignore
        log.debug(f"[config] pydantic-settings will look for .env files at: {_ENV_LOCAL_ABS}, {_ENV_FILE_ABS}")

# Create a single, immutable instance of the settings
# During Docker builds, set SKIP_DB_VALIDATION to allow imports to succeed
# Settings will be validated, but DB config won't be required during build
try:
    settings = Settings()
except Exception as e:
    # If Settings validation fails, log the error but create a minimal instance
    # This allows the module to be imported even if config is incomplete
    log.error(
        "[config] Failed to initialize Settings: %s. "
        "Creating fallback settings. Some features may not work.",
        e,
        exc_info=True
    )
    # Create a minimal Settings instance with defaults
    # This is a last resort - normally Settings should always succeed
    class _FallbackSettings:
        APP_ENV = os.getenv("APP_ENV", "dev")
        DB_USER = ""
        DB_PASS = ""
        DB_NAME = ""
        INSTANCE_CONNECTION_NAME = ""
        DATABASE_URL = None
        SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
        SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "dev-session-secret-change-me")
        # Add other required fields with defaults
        GEMINI_API_KEY = ""
        AI_PROVIDER = "gemini"
        VERTEX_PROJECT = None
        VERTEX_LOCATION = "us-central1"
        VERTEX_MODEL = None
        ELEVENLABS_API_KEY = ""
        ASSEMBLYAI_API_KEY = ""
        AUPHONIC_API_KEY = ""
        SPREAKER_API_TOKEN = ""
        SPREAKER_CLIENT_ID = ""
        SPREAKER_CLIENT_SECRET = ""
        GOOGLE_CLIENT_ID = ""
        GOOGLE_CLIENT_SECRET = ""
        STRIPE_SECRET_KEY = ""
        STRIPE_PUBLISHABLE_KEY = ""
        STRIPE_WEBHOOK_SECRET = ""
    settings = _FallbackSettings()  # type: ignore
