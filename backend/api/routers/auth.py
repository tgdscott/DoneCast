from datetime import datetime, timedelta
from uuid import uuid4
from typing import TYPE_CHECKING, Any, Mapping, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr
from typing import cast

from ..core.config import settings
from ..core.security import verify_password
from ..models.user import User, UserCreate, UserPublic
from ..models.verification import EmailVerification
from ..core.database import get_session
from ..core import crud
from ..models.settings import load_admin_settings
from ..services.mailer import mailer
from sqlalchemy import desc

try:  # pragma: no cover - executed only when python-jose is missing in prod builds
    from jose import JWTError, jwt
except ModuleNotFoundError as exc:  # pragma: no cover
    JWTError = Exception  # type: ignore[assignment]
    jwt = None  # type: ignore[assignment]
    _JOSE_IMPORT_ERROR: Optional[ModuleNotFoundError] = exc
else:
    _JOSE_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from authlib.integrations.starlette_client import OAuth as OAuthType
else:  # pragma: no cover - runtime alias for type checkers
    OAuthType = Any  # type: ignore[assignment]

try:  # pragma: no cover - executed only when authlib is missing in prod builds
    from authlib.integrations.starlette_client import OAuth as _OAuthFactory
except ModuleNotFoundError as exc:  # pragma: no cover
    _OAuthFactory = None  # type: ignore[assignment]
    _AUTHLIB_ERROR: Optional[ModuleNotFoundError] = exc
else:
    _AUTHLIB_ERROR = None

# --- Router Setup ---
logger = logging.getLogger(__name__)


def _raise_jwt_missing(context: str) -> None:
    """Raise a helpful HTTP error when python-jose is absent."""

    detail = (
        "Authentication service is misconfigured (missing JWT support). "
        "Please contact support."
    )
    if _JOSE_IMPORT_ERROR:
        logger.error("JWT dependency missing while %s: %s", context, _JOSE_IMPORT_ERROR)
    else:
        logger.error("JWT dependency missing while %s", context)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _verify_password_or_error(password: str, hashed_password: str) -> bool:
    """Wrapper around verify_password that surfaces configuration errors cleanly."""

    try:
        return verify_password(password, hashed_password)
    except RuntimeError as exc:
        logger.error("Password verification unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is misconfigured (password hashing unavailable).",
        )

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# --- Security Scheme ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# --- OAuth Client Setup ---
def _build_oauth_client() -> tuple[OAuthType, str]:
    """Construct a new OAuth client registered for Google."""

    if _OAuthFactory is None:
        message = "Google OAuth is unavailable because authlib is not installed."
        if _AUTHLIB_ERROR:
            logger.warning("%s Import error: %s", message, _AUTHLIB_ERROR)
        else:
            logger.warning(message)
        raise RuntimeError(message)

    oauth_client = _OAuthFactory()
    oauth_client.register(
        name='google',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        client_kwargs={'scope': 'openid email profile'},
    )
    return oauth_client, settings.GOOGLE_CLIENT_ID

# --- Helper Functions ---


def _is_admin_email(email: str | None) -> bool:
    admin_email = getattr(settings, "ADMIN_EMAIL", "") or ""
    return bool(email and admin_email and email.lower() == admin_email.lower())


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Creates a JWT access token."""
    if jwt is None:
        _raise_jwt_missing("creating access tokens")
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # jwt is ensured non-None above; cast for type-checkers
    jwt_mod = cast(Any, jwt)
    encoded_jwt = jwt_mod.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# --- Dependency for getting current user ---
async def get_current_user(
    request: Request, session: Session = Depends(get_session), token: str = Depends(oauth2_scheme)
) -> User:
    """Decodes the JWT token to get the current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if jwt is None:
        _raise_jwt_missing("validating credentials")
    try:
        jwt_mod = cast(Any, jwt)
        payload = jwt_mod.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not isinstance(email, str) or not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = crud.get_user_by_email(session=session, email=email)
    if user is None:
        raise credentials_exception
    return user

# --- Helper Functions (continued) ---


def _to_user_public(user: User) -> UserPublic:
    # Build a safe public view from DB User without leaking hashed_password
    # Use Pydantic's model_validate with from_attributes to coerce fields safely.
    public = UserPublic.model_validate(user, from_attributes=True)
    # Enrich with computed flags
    public.is_admin = _is_admin_email(user.email) or bool(getattr(user, "is_admin", False))
    public.terms_version_required = getattr(settings, "TERMS_VERSION", None)
    return public


class UserRegisterPayload(UserCreate):
    # Terms acceptance moved to post-signup onboarding flow
    accept_terms: bool | None = None
    terms_version: str | None = None


# --- Standard Authentication Endpoints ---


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserRegisterPayload,
    request: Request,
    session: Session = Depends(get_session),
):
    """Register a new user with email and password."""
    # No longer require terms acceptance at sign-up; this is handled later in onboarding

    # Clean up any stale unverified accounts older than 30 minutes to free the email for reuse
    try:
        from datetime import datetime as _dt, timedelta as _td
        cutoff = _dt.utcnow() - _td(minutes=30)
        # Raw SQLModel select because we only need a quick purge
        stale = session.exec(
            select(User).where(User.email == user_in.email)
        ).first()
        if stale and not stale.is_active:
            # Find whether there is a verification that succeeded; if none & old => purge
            v = session.exec(
                select(EmailVerification)
                .where(EmailVerification.user_id == stale.id)
            ).first()
            if v and v.verified_at:
                pass  # already verified; treat as existing user
            else:
                # If account never verified and older than cutoff, delete it
                if stale.created_at < cutoff:
                    session.delete(stale)
                    session.commit()

        db_user = crud.get_user_by_email(session=session, email=user_in.email)
    except Exception:
        db_user = crud.get_user_by_email(session=session, email=user_in.email)
    if db_user:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    # Force inactive until email confirmed for email/password signups
    try:
        admin_settings = load_admin_settings(session)
        default_active = False
    except Exception:
        default_active = False

    base_user = UserCreate(**user_in.model_dump(exclude={"accept_terms", "terms_version"}))
    base_user.is_active = default_active

    user = crud.create_user(session=session, user_create=base_user)

    if _is_admin_email(user.email):
        user.is_admin = True
        session.add(user)
        session.commit()
        session.refresh(user)

    # Terms acceptance is deferred; do not record here

    # Create email verification code and send mail
    import random
    code = f"{random.randint(100000, 999999)}"
    expires = datetime.utcnow() + timedelta(minutes=15)
    token = create_access_token({"sub": user.email, "purpose": "email_verify"}, expires_delta=timedelta(minutes=15))
    ev = EmailVerification(user_id=user.id, code=code, jwt_token=token, expires_at=expires)
    session.add(ev)
    session.commit()

    # Rebrand: prefer new domain; keep legacy as fallback until full cut-over
    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    verify_url = f"{app_base}/verify?token={token}"
    subj = "Podcast++: Confirm your email"
    body = (
        f"Your Podcast++ verification code is: {code}\n\n"
        f"Click to verify instantly: {verify_url}\n\n"
        "This code expires in 15 minutes. If you didn’t request it, you can ignore this email."
    )
    html_body = f"""
    <div style='font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;padding:8px 4px;'>
      <h2 style='font-size:20px;margin:0 0 12px;'>Confirm your email</h2>
      <p style='font-size:15px;line-height:1.5;margin:0 0 16px;'>Use the code below or click the button to finish creating your Podcast++ account.</p>
      <div style='background:#111;color:#fff;font-size:26px;letter-spacing:4px;padding:12px 16px;text-align:center;border-radius:6px;font-weight:600;margin:0 0 20px;'>{code}</div>
      <p style='text-align:center;margin:0 0 24px;'>
        <a href='{verify_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 20px;border-radius:6px;font-weight:600;'>Verify Email</a>
      </p>
      <p style='font-size:13px;color:#555;margin:0 0 12px;'>This code expires in 15 minutes. If you did not request it, you can safely ignore this email.</p>
      <p style='font-size:12px;color:#777;margin:24px 0 0;'>© {datetime.utcnow().year} Podcast++</p>
    </div>
    """.strip()
    # Send email in a background thread so registration response is fast
    import threading
    def _send_verification():
        try:
            sent = mailer.send(to=user.email, subject=subj, text=body, html=html_body)
            if not sent:
                logger.error(
                    "Signup email send failed (returned False): to=%s host=%s user_set=%s", 
                    user.email, getattr(mailer, 'host', None), bool(getattr(mailer, 'user', None))
                )
        except Exception as e:
            logger.exception("Exception while sending signup email to %s: %s", user.email, e)
    threading.Thread(target=_send_verification, name="send_verification", daemon=True).start()

    return _to_user_public(user)

class ConfirmEmailPayload(BaseModel):
    # Allow raw string so blank "" doesn't trigger EmailStr validation error when token-only confirmation happens
    email: Optional[str] = None
    code: Optional[str] = None
    token: Optional[str] = None

@router.post("/confirm-email", response_model=UserPublic)
async def confirm_email(payload: ConfirmEmailPayload, session: Session = Depends(get_session)):
    """Confirm a user's email via 6-digit code or token. Activates the user account."""
    user: Optional[User] = None
    ev: Optional[EmailVerification] = None

    # Normalize blank email to None
    if payload.email is not None and isinstance(payload.email, str) and not payload.email.strip():
        payload.email = None

    # If token is provided, prefer to look up by token (no email needed)
    if payload.token:
        ev = session.exec(
            select(EmailVerification)
            .where(EmailVerification.jwt_token == payload.token)
        ).first()
        if not ev:
            raise HTTPException(status_code=400, detail="Invalid or expired verification")
        user = session.get(User, ev.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        # Fallback: email + code path
        if not payload.email:
            raise HTTPException(status_code=400, detail="Email is required when no token is provided")
        # Validate email format manually
        try:
            EmailStr(payload.email)  # type: ignore[arg-type]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid email format")
        user = crud.get_user_by_email(session=session, email=payload.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    if not ev and payload.code:
        ev = session.exec(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id)
            .where(EmailVerification.code == payload.code)
        ).first()

    if not ev:
        raise HTTPException(status_code=400, detail="Invalid or expired verification")
    if ev.expires_at < now:
        raise HTTPException(status_code=400, detail="Verification expired")

    ev.verified_at = now
    user.is_active = True
    session.add(ev)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _to_user_public(user)

class ResendVerificationPayload(BaseModel):
    email: EmailStr

@router.post("/resend-verification")
async def resend_verification(payload: ResendVerificationPayload, session: Session = Depends(get_session)):
    """Resend the email verification code & link for a not-yet-active user.

    Creates a new code, invalidates prior codes by simply adding a new record (old ones still expire).
    Returns a generic success even if user doesn't exist to avoid user enumeration.
    """
    user = crud.get_user_by_email(session=session, email=payload.email)
    if not user or user.is_active:
        return {"status": "ok"}
    # Issue new token & code
    import random
    code = f"{random.randint(100000, 999999)}"
    token = create_access_token({"sub": user.email, "purpose": "email_verify"}, expires_delta=timedelta(minutes=15))
    ev = EmailVerification(user_id=user.id, code=code, jwt_token=token, expires_at=datetime.utcnow() + timedelta(minutes=15))
    session.add(ev)
    session.commit()
    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    verify_url = f"{app_base}/verify?token={token}"
    subj = "Podcast++: Confirm your email"
    body = (
        f"Your Podcast++ verification code is: {code}\n\n"
        f"Click to verify instantly: {verify_url}\n\n"
        "This code expires in 15 minutes. If you didn’t request it, you can ignore this email."
    )
    try:
        mailer.send(user.email, subj, body)
    except Exception:
        pass
    return {"status": "ok"}

class UpdatePendingEmailPayload(BaseModel):
    old_email: EmailStr
    new_email: EmailStr

@router.post("/update-pending-email")
async def update_pending_email(payload: UpdatePendingEmailPayload, session: Session = Depends(get_session)):
    """Allow a user who hasn't verified yet to change their registration email.

    Strategy: if old_email exists and is not active, update its email field (if new email unused)
    and issue fresh verification. If old email is active, reject. Returns generic status to limit enumeration.
    """
    user = crud.get_user_by_email(session=session, email=payload.old_email)
    if not user or user.is_active:
        raise HTTPException(status_code=400, detail="Cannot update email (not found or already active)")
    if crud.get_user_by_email(session=session, email=payload.new_email):
        raise HTTPException(status_code=400, detail="New email already in use")
    user.email = payload.new_email
    session.add(user)
    session.commit()
    session.refresh(user)
    # Issue new verification
    import random
    code = f"{random.randint(100000, 999999)}"
    token = create_access_token({"sub": user.email, "purpose": "email_verify"}, expires_delta=timedelta(minutes=15))
    ev = EmailVerification(user_id=user.id, code=code, jwt_token=token, expires_at=datetime.utcnow() + timedelta(minutes=15))
    session.add(ev)
    session.commit()
    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    verify_url = f"{app_base}/verify?token={token}"
    subj = "Podcast++: Confirm your email"
    body = (
        f"Your Podcast++ verification code is: {code}\n\n"
        f"Click to verify instantly: {verify_url}\n\n"
        "This code expires in 15 minutes. If you didn’t request it, you can ignore this email."
    )
    try:
        mailer.send(user.email, subj, body)
    except Exception:
        pass
    return {"status": "ok"}

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    """Login user with email/password and return an access token."""
    user = crud.get_user_by_email(session=session, email=form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not _verify_password_or_error(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please confirm your email to sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _is_admin_email(user.email):
        user.is_admin = True
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    """Request body for JSON-based login."""
    email: EmailStr
    password: str


@router.post("/login", response_model=dict)
async def login_for_access_token_json(
    payload: LoginRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Login user with email/password from a JSON body."""
    user = crud.get_user_by_email(session=session, email=payload.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not _verify_password_or_error(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please confirm your email to sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _is_admin_email(user.email):
        user.is_admin = True
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# --- Compatibility alias: some legacy SPA code calls /api/auth/me expecting { user: ... }
@router.get("/me", response_model=UserPublic)
async def auth_me_current_user(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Return the current user; mirrors /api/users/me but under /api/auth/me for older bundles."""
    return _to_user_public(current_user)

# --- User preference updates (first_name, last_name, timezone) ---

class UserPrefsPatch(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None

@router.patch("/users/me/prefs", response_model=UserPublic)
async def patch_user_prefs(payload: UserPrefsPatch, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    changed = False
    if payload.first_name is not None:
        current_user.first_name = payload.first_name.strip() or None
        changed = True
    if payload.last_name is not None:
        current_user.last_name = payload.last_name.strip() or None
        changed = True
    if payload.timezone is not None:
        tz = payload.timezone.strip()
        if tz and tz != 'UTC' and '/' not in tz:
            raise HTTPException(status_code=400, detail='Invalid timezone format')
        current_user.timezone = tz or None
        changed = True
    if changed:
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
    return _to_user_public(current_user)

# --- Google OAuth Endpoints ---
@router.get('/login/google')
async def login_google(request: Request):
    """Redirects the user to Google's login page."""
    backend_base = settings.OAUTH_BACKEND_BASE or "https://api.podcastplusplus.com"
    redirect_uri = f"{backend_base}/api/auth/google/callback"
    try:
        oauth_client, _ = _build_oauth_client()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is temporarily unavailable. Please contact support.",
        ) from exc
    client = getattr(oauth_client, 'google', None)
    if client is None:
        raise HTTPException(status_code=500, detail="OAuth client not configured")
    return await client.authorize_redirect(request, redirect_uri)

@router.get('/google/callback')
async def auth_google_callback(request: Request, session: Session = Depends(get_session)):
    """Handles the callback from Google, creates/updates the user, and redirects."""
    try:
        oauth_client, _ = _build_oauth_client()
    except RuntimeError as exc:
        logger.exception("Google OAuth unavailable during callback")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is temporarily unavailable. Please contact support.",
        ) from exc

    try:
        client = getattr(oauth_client, 'google', None)
        if client is None:
            raise RuntimeError("OAuth client not configured")
        token: Mapping[str, Any] | None = await client.authorize_access_token(request)
    except Exception as e:
        logger.exception("Google OAuth token exchange failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate Google credentials: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not isinstance(token, Mapping):
        logger.error("Google OAuth returned unexpected token payload type: %s", type(token))
        raise HTTPException(status_code=400, detail="Could not fetch user info from Google.")

    google_user_data = token.get('userinfo')
    if not isinstance(google_user_data, Mapping) or 'email' not in google_user_data:
        google_user_data = None
        # Try to recover user info via ID token or explicit userinfo call.
        id_token = token.get('id_token')
        if id_token:
            try:
                google_user_data = await client.parse_id_token(request, token)
            except Exception as parse_err:
                logger.warning("Failed to parse Google ID token: %s", parse_err)
        if not google_user_data:
            try:
                google_user_data = await client.userinfo(token=token)
            except Exception as userinfo_err:
                logger.warning("Failed to fetch Google userinfo: %s", userinfo_err)

    if not isinstance(google_user_data, Mapping) or 'email' not in google_user_data:
        raise HTTPException(status_code=400, detail="Could not fetch user info from Google.")

    user_email = str(google_user_data['email'])

    google_user_id = str(google_user_data.get('sub') or google_user_data.get('id') or "").strip() or None

    if not google_user_id:
        logger.warning("Google userinfo missing stable subject identifier for email %s", user_email)

    user = crud.get_user_by_email(session=session, email=user_email)

    if not user:
        user_create = UserCreate(
            email=user_email,
            password=str(uuid4()),
            google_id=google_user_id
        )
        try:
            admin_settings = load_admin_settings(session)
            user_create.is_active = bool(getattr(admin_settings, 'default_user_active', True))
        except Exception:
            user_create.is_active = True
        user = crud.create_user(session=session, user_create=user_create)

    if _is_admin_email(user.email):
        user.is_admin = True

    if google_user_id and not user.google_id:
        user.google_id = google_user_id

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    access_token = create_access_token(data={"sub": user.email})

    frontend_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    frontend_url = f"{frontend_base}/#access_token={access_token}&token_type=bearer"
    if user.is_admin:
        frontend_url = f"{frontend_base}/admin#access_token={access_token}&token_type=bearer"

    return RedirectResponse(url=frontend_url)

# --- User Test Endpoint ---
@router.get("/users/me", response_model=UserPublic)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Gets the details of the currently logged-in user."""
    return _to_user_public(current_user)

# --- Debug endpoint ---
@router.get("/debug/google-client", include_in_schema=False)
async def debug_google_client():
    """Reveals what Google client settings are active."""
    def _mask(val: str | None) -> str:
        v = (val or "").strip()
        return (v[:8] + "…" if len(v) > 8 else v) if v else ""

    backend_base = settings.OAUTH_BACKEND_BASE or "https://api.podcastplusplus.com"
    return {
        "client_id_hint": _mask(settings.GOOGLE_CLIENT_ID),
        "redirect_uri": f"{backend_base}/api/auth/google/callback",
        "oauth_backend_base_is_set": bool(settings.OAUTH_BACKEND_BASE),
        "authlib_available": _OAuthFactory is not None,
        "authlib_error": str(_AUTHLIB_ERROR) if _AUTHLIB_ERROR else "",
    }

# --- Terms of Use Endpoints ---

class TermsInfo(BaseModel):
    version: str
    url: str

class TermsAcceptRequest(BaseModel):
    version: str | None = None

@router.get("/terms/info", response_model=TermsInfo)
async def get_terms_info() -> TermsInfo:
    """Return the current Terms of Use version and URL."""
    return TermsInfo(version=str(getattr(settings, 'TERMS_VERSION', '')), url=str(getattr(settings, 'TERMS_URL', '/terms')))

@router.post("/terms/accept", response_model=UserPublic)
async def accept_terms(
    payload: TermsAcceptRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> UserPublic:
    """Record acceptance of the current Terms of Use for the authenticated user."""
    required = str(getattr(settings, 'TERMS_VERSION', ''))
    version = (payload.version or '').strip() or required
    if not required:
        raise HTTPException(status_code=500, detail="Server missing TERMS_VERSION configuration")
    if version != required:
        raise HTTPException(status_code=400, detail="Terms version mismatch. Please refresh and accept the latest terms.")
    try:
        ip = request.client.host if request and request.client else None
    except Exception:
        ip = None
    ua = request.headers.get('user-agent', '') if request and request.headers else None
    crud.record_terms_acceptance(session=session, user=current_user, version=version, ip=ip, user_agent=ua)
    session.refresh(current_user)
    return _to_user_public(current_user)
