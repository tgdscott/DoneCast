"""Routes handling credential-based authentication flows."""

from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.models.settings import load_admin_settings
from api.models.user import User, UserCreate, UserPublic
from api.models.verification import EmailVerification
from api.services.mailer import mailer

from .utils import (
    create_access_token,
    get_current_user,
    is_admin_email,
    limiter,
    to_user_public,
    verify_password_or_error,
)

router = APIRouter()


class UserRegisterPayload(UserCreate):
    # Terms acceptance moved to post-signup onboarding flow
    accept_terms: bool | None = None
    terms_version: str | None = None


class UserRegisterResponse(BaseModel):
    """Response model for registration that includes verification status."""
    email: str
    requires_verification: bool


@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # coarse cap; relies on IP key func
async def register_user(
    user_in: UserRegisterPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> UserRegisterResponse:
    """Register a new user with email and password."""

    try:
        from datetime import datetime as _dt, timedelta as _td

        cutoff = _dt.utcnow() - _td(minutes=30)
        stale = session.exec(select(User).where(User.email == user_in.email)).first()
        if stale and not stale.is_active:
            v = session.exec(
                select(EmailVerification).where(
                    EmailVerification.user_id == stale.id,
                    EmailVerification.verified_at == None,  # noqa: E711
                )
            ).first()
            if v and v.verified_at:
                pass
            else:
                if stale.created_at < cutoff:
                    session.delete(stale)
                    session.commit()

        db_user = crud.get_user_by_email(session=session, email=user_in.email)
    except Exception:
        db_user = crud.get_user_by_email(session=session, email=user_in.email)
    if db_user:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    try:
        admin_settings = load_admin_settings(session)
        default_active = False
    except Exception:
        default_active = False

    base_user = UserCreate(**user_in.model_dump(exclude={"accept_terms", "terms_version"}))
    # Users must verify their email before they can log in
    base_user.is_active = False

    user = crud.create_user(session=session, user_create=base_user)

    if is_admin_email(user.email):
        user.is_admin = True
        session.add(user)
        session.commit()
        session.refresh(user)

    code = f"{random.randint(100000, 999999)}"
    expires = datetime.utcnow() + timedelta(minutes=15)
    token = create_access_token(
        {"sub": user.email, "purpose": "email_verify"},
        expires_delta=timedelta(minutes=15),
    )
    try:
        existing = session.exec(
            select(EmailVerification).where(
                EmailVerification.user_id == user.id,
                EmailVerification.verified_at == None,  # noqa: E711
            )
        ).all()
        for old in existing:
            old.used = True
            session.add(old)
        session.commit()
    except Exception:
        session.rollback()
    ev = EmailVerification(user_id=user.id, code=code, jwt_token=token, expires_at=expires)
    session.add(ev)
    session.commit()

    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    verify_url = f"{app_base}/verify?token={token}"
    subj = "Podcast Plus Plus: Confirm your email"
    body = (
        f"Your Podcast Plus Plus verification code is: {code}\n\n"
        f"Click to verify instantly: {verify_url}\n\n"
        "This code expires in 15 minutes. If you didn’t request it, you can ignore this email."
    )
    html_body = f"""
    <div style='font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;padding:8px 4px;'>
      <h2 style='font-size:20px;margin:0 0 12px;'>Confirm your email</h2>
    <p style='font-size:15px;line-height:1.5;margin:0 0 16px;'>Use the code below or click the button to finish creating your Podcast Plus Plus account.</p>
      <div style='background:#111;color:#fff;font-size:26px;letter-spacing:4px;padding:12px 16px;text-align:center;border-radius:6px;font-weight:600;margin:0 0 20px;'>{code}</div>
      <p style='text-align:center;margin:0 0 24px;'>
        <a href='{verify_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 20px;border-radius:6px;font-weight:600;'>Verify Email</a>
      </p>
      <p style='font-size:13px;color:#555;margin:0 0 12px;'>This code expires in 15 minutes. If you did not request it, you can safely ignore this email.</p>
    <p style='font-size:12px;color:#777;margin:24px 0 0;'>© {datetime.utcnow().year} Podcast Plus Plus</p>
    </div>
    """.strip()

    def _send_verification() -> None:
        try:
            sent = mailer.send(to=user.email, subject=subj, text=body, html=html_body)
            if not sent:
                logger = logging.getLogger(__name__)
                logger.error(
                    "Signup email send failed (returned False): to=%s host=%s user_set=%s",
                    user.email,
                    getattr(mailer, "host", None),
                    bool(getattr(mailer, "user", None)),
                )
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "Exception while sending signup email to %s: %s", user.email, exc
            )

    threading.Thread(target=_send_verification, name="send_verification", daemon=True).start()

    return UserRegisterResponse(
        email=user.email,
        requires_verification=True
    )


class LoginRequest(BaseModel):
    """Request body for JSON-based login."""

    email: EmailStr
    password: str


@router.post("/token")
@limiter.limit("10/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    session: Session = Depends(get_session),
) -> dict:
    """Login user with email/password and return an access token."""

    user = crud.get_user_by_email(session=session, email=form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password_or_error(form_data.password, user.hashed_password):
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
    if is_admin_email(user.email):
        user.is_admin = True
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=dict)
@limiter.limit("10/minute")
async def login_for_access_token_json(
    payload: LoginRequest,
    request: Request,
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
    if not verify_password_or_error(payload.password, user.hashed_password):
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
    if is_admin_email(user.email):
        user.is_admin = True
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserPublic)
async def auth_me_current_user(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Return the current user; compatibility alias for legacy clients."""

    return to_user_public(current_user)


class UserPrefsPatch(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None


@router.patch("/users/me/prefs", response_model=UserPublic)
async def patch_user_prefs(
    payload: UserPrefsPatch,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> UserPublic:
    changed = False
    if payload.first_name is not None:
        current_user.first_name = payload.first_name.strip() or None
        changed = True
    if payload.last_name is not None:
        current_user.last_name = payload.last_name.strip() or None
        changed = True
    if payload.timezone is not None:
        tz = payload.timezone.strip()
        # Allow "device" as special value for auto-detection, or standard IANA format
        if tz and tz != "UTC" and tz != "device" and "/" not in tz:
            raise HTTPException(status_code=400, detail="Invalid timezone format")
        current_user.timezone = tz or None
        changed = True
    if changed:
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
    return to_user_public(current_user)


@router.get("/users/me", response_model=UserPublic)
async def read_users_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Gets the details of the currently logged-in user."""

    return to_user_public(current_user)
