"""Routes for verification and password reset flows."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.core.security import get_password_hash
from api.models.user import User, UserPublic
from api.models.verification import EmailVerification, PasswordReset
from api.services.mailer import mailer

from .utils import create_access_token, limiter, to_user_public

router = APIRouter()


class ConfirmEmailPayload(BaseModel):
    email: Optional[str] = None
    code: Optional[str] = None
    token: Optional[str] = None


@router.post("/confirm-email", response_model=UserPublic)
@limiter.limit("20/hour")
async def confirm_email(
    payload: ConfirmEmailPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> UserPublic:
    """Confirm a user's email via 6-digit code or token."""

    user: Optional[User] = None
    ev: Optional[EmailVerification] = None

    if payload.email is not None and isinstance(payload.email, str) and not payload.email.strip():
        payload.email = None
    
    # Trim whitespace from code if provided and ensure it's a string
    if payload.code is not None and isinstance(payload.code, str):
        payload.code = payload.code.strip()
    elif payload.code is not None:
        # Coerce to string if it somehow came in as int/other type
        payload.code = str(payload.code).strip()

    if payload.token:
        ev = session.exec(
            select(EmailVerification).where(EmailVerification.jwt_token == payload.token)
        ).first()
        if not ev:
            raise HTTPException(status_code=400, detail="Invalid or expired verification")
        user = session.get(User, ev.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        if not payload.email:
            raise HTTPException(status_code=400, detail="Email is required when no token is provided")
        # Trim email whitespace
        email = payload.email.strip() if isinstance(payload.email, str) else payload.email
        try:
            EmailStr(email)  # type: ignore[arg-type]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid email format")
        user = crud.get_user_by_email(session=session, email=email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    if not ev and payload.code:
        # Query for matching code that hasn't been used yet
        print(f"[VERIFICATION] Looking for code '{payload.code}' (type={type(payload.code)}, repr={repr(payload.code)}) for user {user.email} (id={user.id})")
        ev = session.exec(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id)
            .where(EmailVerification.code == payload.code)
            .where(EmailVerification.used == False)  # noqa: E712
        ).first()
        if ev:
            print(f"[VERIFICATION] ✅ Found matching code: id={ev.id}, code={repr(ev.code)}, expires_at={ev.expires_at}")

    if not ev:
        # Log for debugging: check if code exists but is marked as used or expired
        all_matches = session.exec(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id)
            .where(EmailVerification.code == payload.code)
        ).all()
        if all_matches:
            match_details = []
            for e in all_matches:
                expired = "expired" if e.expires_at < now else "valid"
                match_details.append(f"id={e.id}, code={repr(e.code)}, used={e.used}, {expired}, expires_at={e.expires_at}")
            print(f"[VERIFICATION] ❌ User {user.email} tried code '{payload.code}' - found {len(all_matches)} matches but all invalid: {match_details}")
        else:
            # Check if there are ANY codes for this user
            user_codes = session.exec(
                select(EmailVerification)
                .where(EmailVerification.user_id == user.id)
                .where(EmailVerification.verified_at == None)  # noqa: E711
            ).all()
            if user_codes:
                codes_info = [(c.code, repr(c.code), c.expires_at, c.used) for c in user_codes]
                print(f"[VERIFICATION] ❌ User {user.email} tried WRONG code '{payload.code}' - they have {len(user_codes)} pending code(s): {codes_info}")
            else:
                print(f"[VERIFICATION] ❌ User {user.email} tried code '{payload.code}' - NO pending verification codes found in database")
        raise HTTPException(status_code=400, detail="Invalid or expired code. Please check and try again.")
    if ev.expires_at < now:
        raise HTTPException(status_code=400, detail="Verification expired")
    if ev.used:
        # This should never happen now that we filter by used=False in the query
        raise HTTPException(status_code=400, detail="Verification already used")

    ev.verified_at = now
    ev.used = True
    user.is_active = True
    session.add(ev)
    session.add(user)
    session.commit()
    session.refresh(user)
    return to_user_public(user)


class ResendVerificationPayload(BaseModel):
    email: EmailStr


@router.post("/resend-verification")
@limiter.limit("3/15minutes")
async def resend_verification(
    payload: ResendVerificationPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Resend the email verification code & link for a not-yet-active user."""

    user = crud.get_user_by_email(session=session, email=payload.email)
    if not user or user.is_active:
        return {"status": "ok"}
    code = f"{secrets.randbelow(900000) + 100000}"
    token = create_access_token(
        {"sub": user.email, "purpose": "email_verify"},
        expires_delta=timedelta(minutes=15),
    )
    try:
        olds = session.exec(
            select(EmailVerification).where(
                EmailVerification.user_id == user.id,
                EmailVerification.verified_at == None,  # noqa: E711
            )
        ).all()
        for old in olds:
            old.used = True
            session.add(old)
        session.commit()
    except Exception:
        session.rollback()
    ev = EmailVerification(
        user_id=user.id,
        code=code,
        jwt_token=token,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
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
    try:
        mailer.send(user.email, subj, body)
    except Exception:
        pass
    return {"status": "ok"}


class UpdatePendingEmailPayload(BaseModel):
    old_email: EmailStr
    new_email: EmailStr


@router.post("/update-pending-email")
@limiter.limit("2/10minutes")
async def update_pending_email(
    payload: UpdatePendingEmailPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Allow a user who hasn't verified yet to change their registration email."""

    user = crud.get_user_by_email(session=session, email=payload.old_email)
    if not user or user.is_active:
        raise HTTPException(status_code=400, detail="Cannot update email (not found or already active)")
    if crud.get_user_by_email(session=session, email=payload.new_email):
        raise HTTPException(status_code=400, detail="New email already in use")
    user.email = payload.new_email
    session.add(user)
    session.commit()
    session.refresh(user)

    code = f"{secrets.randbelow(900000) + 100000}"
    token = create_access_token(
        {"sub": user.email, "purpose": "email_verify"},
        expires_delta=timedelta(minutes=15),
    )
    try:
        olds = session.exec(
            select(EmailVerification).where(
                EmailVerification.user_id == user.id,
                EmailVerification.verified_at == None,  # noqa: E711
            )
        ).all()
        for old in olds:
            old.used = True
            session.add(old)
        session.commit()
    except Exception:
        session.rollback()
    ev = EmailVerification(
        user_id=user.id,
        code=code,
        jwt_token=token,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
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
    try:
        mailer.send(user.email, subj, body)
    except Exception:
        pass
    return {"status": "ok"}


class PasswordResetRequestPayload(BaseModel):
    email: EmailStr


class PasswordResetPerformPayload(BaseModel):
    token: str
    new_password: str


def _random_token(n: int = 48) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


@router.post("/request-password-reset")
@limiter.limit("5/hour")
async def request_password_reset(
    payload: PasswordResetRequestPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Issue a short-lived password reset token and email it."""

    user = crud.get_user_by_email(session=session, email=payload.email)
    generic = {"status": "ok"}
    if not user or not user.is_active:
        return generic
    try:
        resets = session.exec(
            select(PasswordReset).where(
                PasswordReset.user_id == user.id,
                PasswordReset.used_at == None,  # noqa: E711
            )
        ).all()
        for reset in resets:
            reset.used_at = datetime.utcnow()
            session.add(reset)
        session.commit()
    except Exception:
        session.rollback()
    token = _random_token(40)
    expires = datetime.utcnow() + timedelta(minutes=30)
    ip = None
    ua = None
    try:
        ip = request.client.host if request and request.client else None
        ua = request.headers.get("user-agent", "") if request and request.headers else None
    except Exception:
        pass
    pr = PasswordReset(user_id=user.id, token=token, expires_at=expires, ip=ip, user_agent=ua)
    session.add(pr)
    session.commit()

    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    reset_url = f"{app_base}/reset-password?token={token}"
    subj = "Podcast Plus Plus: Password reset request"
    text_body = (
        "We received a request to reset your password.\n\n"
        f"Reset link (valid 30 minutes): {reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = f"""
    <div style='font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;padding:8px 4px;'>
      <h2 style='font-size:20px;margin:0 0 12px;'>Reset your password</h2>
      <p style='font-size:15px;line-height:1.5;margin:0 0 16px;'>Click the button below to choose a new password. This link expires in 30 minutes.</p>
      <p style='text-align:center;margin:0 0 24px;'>
        <a href='{reset_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 20px;border-radius:6px;font-weight:600;'>Choose New Password</a>
      </p>
      <p style='font-size:13px;color:#555;margin:0 0 12px;'>If you didn't request this, you can safely ignore this email.</p>
    <p style='font-size:12px;color:#777;margin:24px 0 0;'>&copy; {datetime.utcnow().year} Podcast Plus Plus</p>
    </div>
    """.strip()
    try:
        mailer.send(to=user.email, subject=subj, text=text_body, html=html_body)
    except Exception:
        pass
    return generic


@router.post("/reset-password")
@limiter.limit("10/hour")
async def reset_password(
    payload: PasswordResetPerformPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Reset password using a valid, single-use reset token."""

    pr = session.exec(select(PasswordReset).where(PasswordReset.token == payload.token)).first()
    if not pr or pr.used_at or pr.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user = session.get(User, pr.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid token")
    pw = payload.new_password or ""
    if len(pw) < 8:
        raise HTTPException(status_code=400, detail="Password too short (min 8 characters)")
    if pw.lower() == pw or pw.upper() == pw:
        pass
    user.hashed_password = get_password_hash(pw)
    pr.used_at = datetime.utcnow()
    session.add(user)
    session.add(pr)
    session.commit()
    session.refresh(user)
    return {"status": "ok"}

