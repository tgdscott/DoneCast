from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings
try:
    # pydantic-settings v2 preferred config style
    from pydantic_settings import SettingsConfigDict  # type: ignore
except Exception:  # pragma: no cover
    SettingsConfigDict = None  # type: ignore

class Settings(BaseSettings):
    # --- Core Infrastructure ---
    DB_USER: str
    DB_PASS: str
    DB_NAME: str
    INSTANCE_CONNECTION_NAME: str
    SECRET_KEY: str = "dev-secret-key-change-me"  # Used for signing JWTs
    SESSION_SECRET_KEY: str = "dev-session-secret-change-me"  # Used for signing session cookies

    # --- Service API Keys ---
    GEMINI_API_KEY: str
    # --- AI Provider Selection ---
    # AI_PROVIDER can be: "gemini" (public generativeai) or "vertex" (Vertex AI Gemini)
    AI_PROVIDER: str = "gemini"
    VERTEX_PROJECT: Optional[str] = None
    VERTEX_LOCATION: str = "us-central1"
    VERTEX_MODEL: Optional[str] = None  # e.g. "gemini-1.5-flash"
    ELEVENLABS_API_KEY: str
    ASSEMBLYAI_API_KEY: str
    ASSEMBLYAI_WEBHOOK_SECRET: Optional[str] = None
    ASSEMBLYAI_WEBHOOK_URL: Optional[str] = None
    ASSEMBLYAI_WEBHOOK_HEADER: str = "X-AssemblyAI-Signature"

    # --- Spreaker API ---
    SPREAKER_API_TOKEN: str
    SPREAKER_CLIENT_ID: str
    SPREAKER_CLIENT_SECRET: str
    SPREAKER_REDIRECT_URI: Optional[str] = None

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # --- Stripe Billing ---
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # --- Application Behavior ---
    ADMIN_EMAIL: str = ""
    MEDIA_ROOT: str = "/tmp"
    OAUTH_BACKEND_BASE: Optional[str] = None
    APP_BASE_URL: Optional[str] = None  # For frontend redirects
    CORS_ALLOWED_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    # --- Legal ---
    TERMS_VERSION: str = "2025-09-19"
    # Default legal / marketing URLs (rebranded from getpodcastplus.com -> podcastplusplus.com)
    TERMS_URL: str = "https://app.podcastplusplus.com/terms"

    # --- JWT Settings ---
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        raw = self.CORS_ALLOWED_ORIGINS or ""
        normalized = raw.replace(';', ',')
        configured = [origin.strip() for origin in normalized.split(',') if origin.strip()]

        # Always allow the marketing site to call the API; browsers enforce exact origin
        # matching, so include both the bare and www variants. These entries are appended
        # even when the operator forgets to list them explicitly, preventing the
        # "No 'Access-Control-Allow-Origin' header" failures seen on getpodcastplus.com.
        # Rebrand: keep BOTH old and new domains during transitional period so existing
        # deployed frontends or cached service workers on the old domain continue to
        # function. Old domain entries can be removed after DNS / marketing cut‑over.
        defaults = [
            # New brand (preferred)
            "https://podcastplusplus.com",
            "https://www.podcastplusplus.com",
            "https://app.podcastplusplus.com",
            "https://api.podcastplusplus.com",
            # Legacy (backward compatibility)
            "https://getpodcastplus.com",
            "https://www.getpodcastplus.com",
            "https://app.getpodcastplus.com",
            "https://api.getpodcastplus.com",
        ]

        seen: set[str] = set()
        merged: list[str] = []
        for origin in [*configured, *defaults]:
            if origin and origin not in seen:
                seen.add(origin)
                merged.append(origin)

        return merged

    @model_validator(mode="after")
    def _apply_spreaker_defaults(self):
        if not self.SPREAKER_REDIRECT_URI:
            base = (self.OAUTH_BACKEND_BASE or "https://api.podcastplusplus.com").rstrip("/")
            # Unified Spreaker OAuth callback route (popup flow)
            self.SPREAKER_REDIRECT_URI = f"{base}/api/auth/spreaker/callback"
        return self

    # pydantic-settings v2 uses model_config; keep fallback Config for older versions
    if SettingsConfigDict is not None:  # type: ignore
        model_config = SettingsConfigDict(env_file=(".env.local", ".env"), extra="ignore")  # type: ignore

# Create a single, immutable instance of the settings
settings = Settings()
