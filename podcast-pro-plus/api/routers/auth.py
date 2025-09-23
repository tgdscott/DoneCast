from datetime import datetime, timedelta
from uuid import uuid4
from typing import TYPE_CHECKING, Any, Mapping, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import Session

from ..core.config import settings
from ..core.security import verify_password
from ..models.user import User, UserCreate, UserPublic
from ..core.database import get_session
from ..core import crud
from ..models.settings import load_admin_settings

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
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
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
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
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
    accept_terms: bool
    terms_version: str


# --- Standard Authentication Endpoints ---


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserRegisterPayload,
    request: Request,
    session: Session = Depends(get_session),
):
    """Register a new user with email and password."""
    if not user_in.accept_terms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the terms of use to create an account.",
        )
    if user_in.terms_version != getattr(settings, "TERMS_VERSION", ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Terms version mismatch. Please refresh and try again.",
        )

    db_user = crud.get_user_by_email(session=session, email=user_in.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists.",
        )

    try:
        admin_settings = load_admin_settings(session)
        default_active = bool(getattr(admin_settings, "default_user_active", True))
    except Exception:
        default_active = True

    base_user = UserCreate(**user_in.model_dump(exclude={"accept_terms", "terms_version"}))
    base_user.is_active = default_active

    user = crud.create_user(session=session, user_create=base_user)

    if _is_admin_email(user.email):
        user.is_admin = True
        session.add(user)
        session.commit()
        session.refresh(user)

    ip = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    crud.record_terms_acceptance(
        session=session,
        user=user,
        version=user_in.terms_version,
        ip=ip,
        user_agent=user_agent,
    )
    session.refresh(user)
    return _to_user_public(user)

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
    backend_base = settings.OAUTH_BACKEND_BASE or "https://api.getpodcastplus.com"
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

    frontend_base = (settings.APP_BASE_URL or "https://app.getpodcastplus.com").rstrip("/")
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

    backend_base = settings.OAUTH_BACKEND_BASE or "https://api.getpodcastplus.com"
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
