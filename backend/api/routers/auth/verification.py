"""Routes for verification and password reset flows."""

from __future__ import annotations

import logging
import secrets
import string
import sys
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.core.ip_utils import get_client_ip
from api.core.security import get_password_hash
from api.models.user import User, UserPublic
from api.models.verification import EmailVerification, PasswordReset, PhoneVerification
from api.services.mailer import mailer
from api.services.sms import sms_service

from .utils import create_access_token, limiter, to_user_public, get_current_user

router = APIRouter()


class ConfirmEmailPayload(BaseModel):
    email: Optional[str] = None
    code: Optional[str] = None
    token: Optional[str] = None


class ConfirmEmailResponse(BaseModel):
    """Response model for email confirmation."""
    user: UserPublic
    access_token: Optional[str] = None  # Only returned when verifying via token link (secure)


@router.post("/confirm-email", response_model=ConfirmEmailResponse)
# @limiter.limit("20/hour")  # DISABLED - breaks FastAPI param detection
async def confirm_email(
    request: Request,
    payload: ConfirmEmailPayload,
    session: Session = Depends(get_session),
) -> ConfirmEmailResponse:
    """Confirm a user's email via 6-digit code or token.
    
    When verifying via token link, returns an access_token for automatic login.
    When verifying via code, user must log in manually.
    """

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
        # Email validation is already done by Pydantic in ConfirmEmailPayload model
        # No need to validate again here - just use it
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
    
    # If verifying via token link, generate access token for automatic login
    # This is secure because the token proves email ownership
    access_token = None
    if payload.token:
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(days=30)  # Standard token expiry
        )
    
    return ConfirmEmailResponse(
        user=to_user_public(user),
        access_token=access_token
    )


class ResendVerificationPayload(BaseModel):
    email: EmailStr


@router.post("/resend-verification")
# @limiter.limit("3/15minutes")  # DISABLED - breaks FastAPI param detection
async def resend_verification(
    request: Request,
    payload: ResendVerificationPayload,
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
        "This code expires in 15 minutes. If you didn't request it, you can ignore this email."
    )
    logger = logging.getLogger(__name__)
    try:
        logger.info(
            "[RESEND_VERIFICATION] Attempting to send verification email to %s (host=%s, user_set=%s, port=%s)",
            user.email,
            getattr(mailer, "host", None),
            bool(getattr(mailer, "user", None)),
            getattr(mailer, "port", None),
        )
        # CRITICAL: Log the exact email address being sent to prevent domain mixups
        logger.info("[RESEND_VERIFICATION] SENDING TO EMAIL: %s (type=%s, repr=%s)", user.email, type(user.email).__name__, repr(user.email))
        sent = mailer.send(to=user.email, subject=subj, text=body)
        if sent:
            logger.info("[RESEND_VERIFICATION] Verification email sent successfully to %s", user.email)
            return {"status": "ok", "message": "Verification email sent successfully"}
        else:
            logger.error(
                "[RESEND_VERIFICATION] Email send failed (returned False): to=%s host=%s user_set=%s port=%s sender=%s",
                user.email,
                getattr(mailer, "host", None),
                bool(getattr(mailer, "user", None)),
                getattr(mailer, "port", None),
                getattr(mailer, "sender", None),
            )
            print(f"[ERROR] Failed to send verification email to {user.email}. Check SMTP configuration.", file=sys.stderr)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send verification email to {user.email}. Check SMTP configuration and Mailgun domain verification."
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "[RESEND_VERIFICATION] Exception while sending verification email to %s: %s", user.email, exc
        )
        print(f"[ERROR] Exception sending verification email to {user.email}: {exc}", file=sys.stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send verification email: {str(exc)}"
        )


class SendPhoneVerificationPayload(BaseModel):
    phone_number: str


class VerifyPhonePayload(BaseModel):
    phone_number: str
    code: str


@router.post("/send-phone-verification")
async def send_phone_verification(
    request: Request,
    payload: SendPhoneVerificationPayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a verification code to a phone number via SMS."""
    import re
    from sqlalchemy import inspect as sql_inspect
    
    # Check if phone verification table exists
    try:
        inspector = sql_inspect(session.get_bind())
        tables = inspector.get_table_names()
        if 'phoneverification' not in tables:
            raise HTTPException(
                status_code=503,
                detail="Phone verification is not yet available. Database migration is pending."
            )
    except Exception as check_err:
        raise HTTPException(
            status_code=503,
            detail="Phone verification is not yet available. Database migration is pending."
        )
    
    phone = payload.phone_number.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")
    
    # Basic validation
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 10:
        raise HTTPException(status_code=400, detail="Phone number must contain at least 10 digits")
    
    # Generate 6-digit code
    code = f"{secrets.randbelow(900000) + 100000}"
    
    # Normalize phone number for storage
    normalized_phone = sms_service.normalize_phone_number(phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    
    # Mark old verifications as used
    try:
        old_verifications = session.exec(
            select(PhoneVerification).where(
                PhoneVerification.user_id == current_user.id,
                PhoneVerification.phone_number == normalized_phone,
                PhoneVerification.verified_at == None,  # noqa: E711
            )
        ).all()
        for old in old_verifications:
            old.used = True
            session.add(old)
        session.commit()
    except Exception:
        session.rollback()
    
    # Create new verification
    expires_at = datetime.utcnow() + timedelta(minutes=10)  # 10 minute expiry for phone codes
    pv = PhoneVerification(
        user_id=current_user.id,
        phone_number=normalized_phone,
        code=code,
        expires_at=expires_at,
    )
    session.add(pv)
    session.commit()
    
    # Send SMS with verification code
    message = f"Your Podcast Plus Plus verification code is: {code}. This code expires in 10 minutes."
    try:
        sms_service.send_sms(normalized_phone, message, str(current_user.id))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send phone verification SMS: {e}")
        # Don't fail the request if SMS fails, but log it
        # The code is still saved in DB, user can request another one
    
    return {"status": "ok", "message": "Verification code sent"}


@router.post("/verify-phone")
async def verify_phone(
    request: Request,
    payload: VerifyPhonePayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Verify a phone number with a code."""
    from sqlalchemy import inspect as sql_inspect
    
    # Check if phone verification table and user phone_number column exist
    try:
        inspector = sql_inspect(session.get_bind())
        tables = inspector.get_table_names()
        user_columns = {col['name'] for col in inspector.get_columns('user')}
        
        if 'phoneverification' not in tables:
            raise HTTPException(
                status_code=503,
                detail="Phone verification is not yet available. Database migration is pending."
            )
        if 'phone_number' not in user_columns:
            raise HTTPException(
                status_code=503,
                detail="Phone verification is not yet available. Database migration is pending."
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Phone verification is not yet available. Database migration is pending."
        )
    
    phone = payload.phone_number.strip()
    code = payload.code.strip()
    
    if not phone or not code:
        raise HTTPException(status_code=400, detail="Phone number and code are required")
    
    # Normalize phone number
    normalized_phone = sms_service.normalize_phone_number(phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    
    # Find verification record
    now = datetime.utcnow()
    pv = session.exec(
        select(PhoneVerification).where(
            PhoneVerification.user_id == current_user.id,
            PhoneVerification.phone_number == normalized_phone,
            PhoneVerification.code == code,
            PhoneVerification.used == False,  # noqa: E712
        )
    ).first()
    
    if not pv:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    
    if pv.expires_at < now:
        raise HTTPException(status_code=400, detail="Verification code has expired")
    
    if pv.used:
        raise HTTPException(status_code=400, detail="Verification code already used")
    
    # Mark as verified and used
    pv.verified_at = now
    pv.used = True
    
    # Update user's phone number (use setattr to be safe)
    setattr(current_user, 'phone_number', normalized_phone)
    
    session.add(pv)
    session.add(current_user)
    session.commit()
    
    return {"status": "ok", "message": "Phone number verified successfully"}


class UpdatePendingEmailPayload(BaseModel):
    old_email: EmailStr
    new_email: EmailStr


@router.post("/update-pending-email")
# @limiter.limit("2/10minutes")  # DISABLED - breaks FastAPI param detection
async def update_pending_email(
    request: Request,
    payload: UpdatePendingEmailPayload,
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
        "This code expires in 15 minutes. If you didn't request it, you can ignore this email."
    )
    logger = logging.getLogger(__name__)
    try:
        logger.info(
            "[UPDATE_PENDING_EMAIL] Attempting to send verification email to %s (host=%s, user_set=%s, port=%s)",
            user.email,
            getattr(mailer, "host", None),
            bool(getattr(mailer, "user", None)),
            getattr(mailer, "port", None),
        )
        sent = mailer.send(to=user.email, subject=subj, text=body)
        if sent:
            logger.info("[UPDATE_PENDING_EMAIL] Verification email sent successfully to %s", user.email)
        else:
            logger.error(
                "[UPDATE_PENDING_EMAIL] Email send failed (returned False): to=%s host=%s user_set=%s port=%s sender=%s",
                user.email,
                getattr(mailer, "host", None),
                bool(getattr(mailer, "user", None)),
                getattr(mailer, "port", None),
                getattr(mailer, "sender", None),
            )
            print(f"[ERROR] Failed to send verification email to {user.email}. Check SMTP configuration.", file=sys.stderr)
    except Exception as exc:
        logger.exception(
            "[UPDATE_PENDING_EMAIL] Exception while sending verification email to %s: %s", user.email, exc
        )
        print(f"[ERROR] Exception sending verification email to {user.email}: {exc}", file=sys.stderr)
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
    
    # Get the real client IP address (handles Cloud Run proxy)
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "") if request and request.headers else None
    
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


@router.get("/smtp-status")
async def check_smtp_status() -> dict:
    """Check SMTP configuration status (for debugging email issues)."""
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT", "587")
    user = os.getenv("SMTP_USER")
    password_set = bool(os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD"))
    sender = os.getenv("SMTP_FROM", "no-reply@podcastplusplus.com")
    
    status = {
        "configured": bool(host),
        "host": host or "NOT SET",
        "port": port,
        "user": user or "NOT SET",
        "password_configured": password_set,
        "sender": sender,
        "mailer_initialized": mailer is not None,
    }
    
    if mailer:
        status.update({
            "mailer_host": getattr(mailer, "host", None),
            "mailer_port": getattr(mailer, "port", None),
            "mailer_user_set": bool(getattr(mailer, "user", None)),
            "mailer_password_set": bool(getattr(mailer, "password", None)),
            "mailer_sender": getattr(mailer, "sender", None),
        })
    
    # Try a test connection if configured
    if host:
        try:
            import socket
            socket.create_connection((host, int(port)), timeout=5)
            status["connection_test"] = "SUCCESS"
        except Exception as e:
            status["connection_test"] = f"FAILED: {str(e)}"
    else:
        status["connection_test"] = "SKIPPED (no host configured)"
    
    # Don't actually send test emails - just verify connection/auth works
    # Actual test emails should use /test-email endpoint with real addresses
    if host and user and password_set:
        status["test_send"] = "SKIPPED (use /test-email endpoint to send real test emails)"
    else:
        status["test_send"] = "SKIPPED (missing configuration)"
    
    return status


@router.post("/test-email")
async def test_email_send(
    payload: dict,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a test email to verify SMTP configuration (admin only).
    
    This sends a REAL email and will show actual Mailgun errors if domain isn't verified.
    """
    from api.routers.auth.utils import is_admin_email
    import logging
    
    logger = logging.getLogger(__name__)
    
    if not is_admin_email(current_user.email):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    test_email = payload.get("email", current_user.email)
    
    logger.info(
        "[TEST_EMAIL] Admin %s requesting test email to %s (host=%s, sender=%s)",
        current_user.email,
        test_email,
        getattr(mailer, "host", None),
        getattr(mailer, "sender", None),
    )
    
    try:
        result = mailer.send(
            to=test_email,
            subject="Test Email from Podcast Plus Plus",
            text="This is a test email to verify SMTP configuration. If you receive this, SMTP is working correctly.",
            html="<p>This is a test email to verify SMTP configuration. If you receive this, SMTP is working correctly.</p>"
        )
        
        if result:
            logger.info("[TEST_EMAIL] Test email sent successfully to %s", test_email)
            return {
                "status": "success",
                "message": f"Test email sent successfully to {test_email}. Check your inbox (and spam folder).",
                "mailer_host": getattr(mailer, "host", None),
                "mailer_sender": getattr(mailer, "sender", None),
                "note": "If email doesn't arrive, check Mailgun dashboard for domain verification status."
            }
        else:
            logger.error("[TEST_EMAIL] Email send returned False for %s", test_email)
            return {
                "status": "failed",
                "message": "Email send returned False - check SMTP configuration and Mailgun domain verification",
                "mailer_host": getattr(mailer, "host", None),
                "mailer_sender": getattr(mailer, "sender", None),
                "troubleshooting": "Check Cloud Run logs for detailed SMTP errors. Common issue: FROM domain not verified in Mailgun."
            }
    except Exception as e:
        logger.exception("[TEST_EMAIL] Exception sending test email to %s: %s", test_email, e)
        return {
            "status": "error",
            "message": f"Failed to send test email: {str(e)}",
            "mailer_host": getattr(mailer, "host", None),
            "mailer_sender": getattr(mailer, "sender", None),
            "error_type": type(e).__name__,
        }

