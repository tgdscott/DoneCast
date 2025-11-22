"""Routes handling credential-based authentication flows."""

from __future__ import annotations

import logging
import random
import sys
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
from api.models.promo_code import PromoCode
from api.models.affiliate_code import UserAffiliateCode
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
    promo_code: Optional[str] = None


class UserRegisterResponse(BaseModel):
    """Response model for registration that includes verification status."""
    email: str
    requires_verification: bool


@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
# @limiter.limit("5/minute")  # TEMPORARILY DISABLED FOR DEBUGGING
async def register_user(
    request: Request,
    user_in: UserRegisterPayload,
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
        # Use admin setting for default active status (but still require email verification)
        # Note: Users still need to verify email, but is_active controls whether they see the closed-alpha gate
        default_active = bool(getattr(admin_settings, "default_user_active", False))
        default_tier = admin_settings.default_user_tier
    except Exception:
        default_active = False
        default_tier = "trial"  # Fallback to trial if settings can't be loaded - all accounts start as trial

    base_user = UserCreate(**user_in.model_dump(exclude={"accept_terms", "terms_version", "promo_code"}))
    # Set active status from admin settings
    # Note: Email verification is still required, but is_active controls closed-alpha gate visibility
    base_user.is_active = default_active
    # Set tier from admin settings
    base_user.tier = default_tier

    user = crud.create_user(session=session, user_create=base_user)
    session.commit()
    session.refresh(user)
    
    # Validate and apply promo code or affiliate code if provided
    if user_in.promo_code:
        promo_code_upper = user_in.promo_code.strip().upper()
        if promo_code_upper:
            try:
                # First, check if it's an admin-created promo code
                promo_code_obj = session.exec(
                    select(PromoCode).where(PromoCode.code == promo_code_upper)
                ).first()
                
                if promo_code_obj:
                    # Validate promo code is active
                    if not promo_code_obj.is_active:
                        logging.getLogger(__name__).warning(
                            f"[REGISTRATION] User {user.email} attempted to use inactive promo code: {promo_code_upper}"
                        )
                    # Check if expired
                    elif promo_code_obj.expires_at and promo_code_obj.expires_at < datetime.utcnow():
                        logging.getLogger(__name__).warning(
                            f"[REGISTRATION] User {user.email} attempted to use expired promo code: {promo_code_upper}"
                        )
                    # Check if max uses reached
                    elif promo_code_obj.max_uses is not None and promo_code_obj.usage_count >= promo_code_obj.max_uses:
                        logging.getLogger(__name__).warning(
                            f"[REGISTRATION] User {user.email} attempted to use promo code that reached max uses: {promo_code_upper}"
                        )
                    else:
                        # Check if user already has a referral code (can only have one)
                        if user.promo_code_used:
                            logging.getLogger(__name__).warning(
                                f"[REGISTRATION] User {user.email} attempted to use promo code {promo_code_upper} "
                                f"but already has referral code: {user.promo_code_used}"
                            )
                        else:
                            # Valid promo code - save it to user and increment usage
                            user.promo_code_used = promo_code_upper
                            promo_code_obj.usage_count += 1
                            promo_code_obj.updated_at = datetime.utcnow()
                            
                            # Record usage to prevent reuse
                            from api.models.promo_code import PromoCodeUsage
                            try:
                                usage = PromoCodeUsage(
                                    user_id=user.id,
                                    promo_code_id=promo_code_obj.id,
                                    context="signup"
                                )
                                session.add(usage)
                            except Exception as e:
                                # If unique constraint violation, user already used this code
                                logging.getLogger(__name__).warning(
                                    f"[REGISTRATION] Failed to record promo code usage: {e}"
                                )
                            
                            session.add(user)
                            session.add(promo_code_obj)
                        
                        # Apply bonus credits if promo code has them
                        if promo_code_obj.bonus_credits and promo_code_obj.bonus_credits > 0:
                            try:
                                from api.services.billing.wallet import add_purchased_credits
                                from api.services.billing.credits import refund_credits
                                from api.models.usage import LedgerReason
                                
                                # Add credits to wallet
                                wallet = add_purchased_credits(session, user.id, float(promo_code_obj.bonus_credits))
                                
                                # Create ledger entry for bonus credits
                                refund_credits(
                                    session=session,
                                    user_id=user.id,
                                    credits=float(promo_code_obj.bonus_credits),
                                    reason=LedgerReason.PROMO_CODE_BONUS,
                                    notes=f"Bonus credits from promo code: {promo_code_obj.code} (signup)"
                                )
                                
                                logging.getLogger(__name__).info(
                                    f"[REGISTRATION] Applied {promo_code_obj.bonus_credits} bonus credits "
                                    f"from promo code {promo_code_obj.code} to user {user.email} at signup"
                                )
                            except Exception as e:
                                # Don't fail registration if credit application fails
                                logging.getLogger(__name__).warning(
                                    f"[REGISTRATION] Failed to apply bonus credits from promo code "
                                    f"{promo_code_obj.code} to user {user.email}: {e}",
                                    exc_info=True
                                )
                        
                        session.commit()
                        session.refresh(user)
                        logging.getLogger(__name__).info(
                            f"[REGISTRATION] User {user.email} registered with promo code: {promo_code_upper}"
                        )
                else:
                    # Not a promo code - check if it's a user affiliate code
                    affiliate_code_obj = session.exec(
                        select(UserAffiliateCode).where(UserAffiliateCode.code == promo_code_upper)
                    ).first()
                    
                    if affiliate_code_obj:
                        # Valid affiliate code - save it to user and track referral
                        user.promo_code_used = promo_code_upper  # Store the code for tracking
                        user.referred_by_user_id = affiliate_code_obj.user_id  # Track who referred them
                        session.add(user)
                        session.commit()
                        session.refresh(user)
                        logging.getLogger(__name__).info(
                            f"[REGISTRATION] User {user.email} registered with affiliate code: {promo_code_upper} (referred by user {affiliate_code_obj.user_id})"
                        )
                    else:
                        # Code not found - log but don't fail registration
                        logging.getLogger(__name__).info(
                            f"[REGISTRATION] User {user.email} attempted to use invalid code: {promo_code_upper}"
                        )
            except Exception as e:
                # Log error but don't fail registration if code validation fails
                logging.getLogger(__name__).error(
                    f"[REGISTRATION] Error validating code {promo_code_upper} for user {user.email}: {e}",
                    exc_info=True
                )
                # Don't rollback - user is already created, just skip code

    # Record terms acceptance if provided during registration
    # This prevents users from seeing TermsGate after email verification
    if user_in.accept_terms and user_in.terms_version:
        user.terms_version_accepted = user_in.terms_version
        session.add(user)
        session.commit()
        session.refresh(user)

    if is_admin_email(user.email):
        user.is_admin = True
        session.add(user)
        session.commit()
        session.refresh(user)

    # Generate 6-digit code as string (ensure it stays as string type)
    code = str(random.randint(100000, 999999))
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
    # Explicitly ensure code is string type
    ev = EmailVerification(user_id=user.id, code=str(code), jwt_token=token, expires_at=expires)
    session.add(ev)
    session.commit()
    
    # Log what we stored for debugging
    logging.getLogger(__name__).info(
        f"[REGISTRATION] Created verification code for {user.email}: "
        f"code={repr(code)} (type={type(code).__name__}), id={ev.id}, expires={expires}"
    )

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
      <div style='text-align:center;margin-bottom:30px;'>
        <img src='https://app.podcastplusplus.com/MikeCzech.png' alt='Podcast Plus Plus' style='width:80px;height:80px;border-radius:50%;object-fit:cover;margin-bottom:20px;' />
      </div>
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
                    "Signup email send failed (returned False): to=%s host=%s user_set=%s port=%s sender=%s",
                    user.email,
                    getattr(mailer, "host", None),
                    bool(getattr(mailer, "user", None)),
                    getattr(mailer, "port", None),
                    getattr(mailer, "sender", None),
                )
                # Also print to stderr for immediate visibility in logs
                print(f"[ERROR] Failed to send verification email to {user.email}. Check SMTP configuration.", file=sys.stderr)
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.exception(
                "Exception while sending signup email to %s: %s", user.email, exc
            )
            # Also print to stderr for immediate visibility
            print(f"[ERROR] Exception sending verification email to {user.email}: {exc}", file=sys.stderr)

    # Try sending synchronously first to catch immediate errors and provide better diagnostics
    # This helps catch configuration issues early and ensures we log detailed error information
    logger = logging.getLogger(__name__)
    email_sent = False
    email_error = None
    
    try:
        logger.info(
            "[REGISTRATION] Attempting to send verification email to %s (host=%s, user_set=%s, port=%s)",
            user.email,
            getattr(mailer, "host", None),
            bool(getattr(mailer, "user", None)),
            getattr(mailer, "port", None),
        )
        
        sent = mailer.send(to=user.email, subject=subj, text=body, html=html_body)
        if sent:
            email_sent = True
            logger.info("[REGISTRATION] Verification email sent successfully to %s", user.email)
        else:
            email_error = "Mailer returned False"
            logger.error(
                "[REGISTRATION] Email send failed (returned False): to=%s host=%s user_set=%s port=%s sender=%s",
                user.email,
                getattr(mailer, "host", None),
                bool(getattr(mailer, "user", None)),
                getattr(mailer, "port", None),
                getattr(mailer, "sender", None),
            )
            print(f"[ERROR] Failed to send verification email to {user.email}. Check SMTP configuration.", file=sys.stderr)
    except Exception as exc:
        email_error = str(exc)
        logger.exception(
            "[REGISTRATION] Exception during email send attempt to %s: %s", user.email, exc
        )
        print(f"[ERROR] Exception sending verification email to {user.email}: {exc}", file=sys.stderr)
    
    # If synchronous send failed, also try in background thread as fallback
    # (in case there was a transient issue)
    if not email_sent:
        logger.warning(
            "[REGISTRATION] Synchronous email send failed, attempting background retry for %s",
            user.email
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
    # Check if user is active BEFORE checking password
    # This ensures unverified users get the proper verification message
    # even if they enter the wrong password
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please verify your email to sign in. Check your inbox for the verification code, or request a new one if it expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password_or_error(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
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
# @limiter.limit("10/minute")  # DISABLED - breaks FastAPI param detection
async def login_for_access_token_json(
    request: Request,
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
    # Check if user is active BEFORE checking password
    # This ensures unverified users get the proper verification message
    # even if they enter the wrong password
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please verify your email to sign in. Check your inbox for the verification code, or request a new one if it expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password_or_error(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_admin_email(user.email):
        user.is_admin = True
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


class MagicLinkRequest(BaseModel):
    token: str


@router.post("/magic-link", response_model=dict)
@limiter.limit("10/minute")
async def exchange_magic_link_token(
    request: Request,
    payload: MagicLinkRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Exchange a magic link token (from email) for a regular access token."""
    from jose import JWTError, jwt
    
    try:
        # Decode and verify the magic link token
        token_payload = jwt.decode(
            payload.token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": True}
        )
        
        # Verify it's a magic link token
        if token_payload.get("type") != "magic_link":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        
        # Get user email from token
        email = token_payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        
        # Get user from database
        user = crud.get_user_by_email(session=session, email=email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is not active",
            )
        
        # Update last login
        user.last_login = datetime.utcnow()
        session.add(user)
        session.commit()
        
        # Create and return a regular access token
        access_token = create_access_token({"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


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
