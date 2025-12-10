"""Automatic bug report submission for system errors and upload failures."""

from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any
from uuid import UUID

from sqlmodel import Session

from api.core.config import settings
from api.models.user import User
from api.models.assistant import FeedbackSubmission
from api.services.mailer import mailer

log = logging.getLogger("bug_reporter")


def _report_to_sentry(
    error_message: str,
    error_code: Optional[str] = None,
    category: Optional[str] = None,
    user: Optional[User] = None,
    context: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> None:
    """Send error to Sentry for centralized error tracking and alerting.
    
    Args:
        error_message: Description of the error
        error_code: Optional error code
        category: Error category (upload, transcription, assembly, etc.)
        user: User who experienced the error (for context)
        context: Additional context dict
        request_id: Request ID for tracing
    """
    try:
        import sentry_sdk
        
        # Build context for Sentry
        sentry_context = {
            "error_code": error_code or "unknown",
            "category": category or "unknown",
            "message": error_message,
        }
        if request_id:
            sentry_context["request_id"] = str(request_id)
        if user:
            sentry_context["user_id"] = str(user.id)
            sentry_context["user_email"] = user.email
        if context:
            sentry_context.update(context)
        
        # Set Sentry context and capture message
        sentry_sdk.set_context("bug_report", sentry_context)
        if user:
            from api.config.sentry_context import set_user_context
            set_user_context(str(user.id), user.email)
        
        # Capture as error-level message so it appears in Sentry's error section
        sentry_sdk.capture_message(
            f"[{category or 'unknown'}] {error_message}",
            level="error"
        )
    except Exception as e:
        log.debug("[sentry] Failed to report to Sentry: %s", e)


def report_upload_failure(
    session: Session,
    user: User,
    filename: str,
    error_message: str,
    error_code: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Optional[UUID]:
    """
    Automatically submit an upload failure as a bug report.
    
    This creates a FeedbackSubmission with severity="critical" and type="bug",
    which automatically notifies admins.
    
    Args:
        session: Database session
        user: User who experienced the failure
        filename: Name of file that failed to upload
        error_message: Description of what went wrong
        error_code: Optional error code for classification
        context: Optional additional context (page_url, browser_info, etc.)
        request_id: Optional request ID for tracing
    
    Returns:
        UUID of created FeedbackSubmission, or None if creation failed
    """
    try:
        # Report to Sentry for centralized error tracking
        _report_to_sentry(
            error_message=error_message,
            error_code=error_code,
            category="upload",
            user=user,
            context=context,
            request_id=request_id,
        )
        
        # Build detailed bug report
        category = "upload"
        title = f"Upload failed: {_truncate(filename, 50)}"
        
        # Detailed description
        description = f"""
**Upload Failure Report**

File: {filename}
Error: {error_message}
Error Code: {error_code or 'N/A'}
Request ID: {request_id or 'N/A'}

This error was automatically reported by the system.
"""
        
        # Extract context
        page_url = context.get("page_url") if context else None
        user_action = context.get("user_action") if context else "Upload audio file"
        browser_info = context.get("browser_info") if context else None
        error_logs = json.dumps({"error_message": error_message, "error_code": error_code})
        
        # Create feedback submission
        feedback = FeedbackSubmission(
            user_id=user.id,
            type="bug",
            title=title,
            description=description,
            severity="critical",  # Upload failures are critical
            category=category,
            
            # Context
            page_url=page_url,
            user_action=user_action,
            browser_info=browser_info,
            error_logs=error_logs,
            
            # Status
            status="new",
            admin_notified=False,
        )
        
        session.add(feedback)
        session.flush()  # Get ID without committing yet
        
        log.info(
            "[bug_reporter] Created bug report: feedback_id=%s user=%s filename=%s error_code=%s",
            str(feedback.id),
            user.email,
            filename,
            error_code,
        )
        
        # Attempt to send admin notification email
        try:
            _send_admin_bug_notification(feedback, user, session)
            feedback.admin_notified = True
        except Exception as e:
            log.warning(
                "[bug_reporter] Failed to send admin notification for bug %s: %s",
                str(feedback.id),
                e,
            )
        
        # Commit the feedback record
        session.add(feedback)
        session.commit()
        session.refresh(feedback)
        
        return feedback.id
    
    except Exception as e:
        log.exception(
            "[bug_reporter] Exception creating bug report: user=%s filename=%s error=%s",
            user.email if user else "unknown",
            filename,
            e,
        )
        return None


def report_transcription_failure(
    session: Session,
    user: User,
    media_filename: str,
    transcription_service: str,
    error_message: str,
    request_id: Optional[str] = None,
) -> Optional[UUID]:
    """
    Automatically submit a transcription failure as a bug report.
    
    Args:
        session: Database session
        user: User who owns the media
        media_filename: Name of media that failed transcription
        transcription_service: Name of service that failed (AssemblyAI, etc.)
        error_message: Description of transcription error
        request_id: Optional request ID for tracing
    
    Returns:
        UUID of created FeedbackSubmission, or None if creation failed
    """
    try:
        # Report to Sentry for centralized error tracking
        _report_to_sentry(
            error_message=error_message,
            category="transcription",
            user=user,
            context={"transcription_service": transcription_service, "media_filename": media_filename},
            request_id=request_id,
        )
        
        category = "transcription"
        title = f"Transcription failed ({transcription_service}): {_truncate(media_filename, 40)}"
        
        description = f"""
**Transcription Failure Report**

Service: {transcription_service}
File: {media_filename}
Error: {error_message}
Request ID: {request_id or 'N/A'}

This error was automatically reported by the system during audio transcription processing.
"""
        
        error_logs = json.dumps({
            "service": transcription_service,
            "error_message": error_message,
            "request_id": request_id,
        })
        
        feedback = FeedbackSubmission(
            user_id=user.id,
            type="bug",
            title=title,
            description=description,
            severity="high",  # Transcription failures are important
            category=category,
            
            error_logs=error_logs,
            user_action=f"Transcribing audio file with {transcription_service}",
            
            status="new",
            admin_notified=False,
        )
        
        session.add(feedback)
        session.flush()
        
        log.info(
            "[bug_reporter] Created transcription bug report: feedback_id=%s user=%s service=%s",
            str(feedback.id),
            user.email,
            transcription_service,
        )
        
        # Attempt to send admin notification
        try:
            _send_admin_bug_notification(feedback, user, session)
            feedback.admin_notified = True
        except Exception as e:
            log.warning(
                "[bug_reporter] Failed to send admin notification for transcription bug %s: %s",
                str(feedback.id),
                e,
            )
        
        session.add(feedback)
        session.commit()
        session.refresh(feedback)
        
        return feedback.id
    
    except Exception as e:
        log.exception(
            "[bug_reporter] Exception creating transcription bug report: user=%s error=%s",
            user.email if user else "unknown",
            e,
        )
        return None


def report_assembly_failure(
    session: Session,
    user: User,
    episode_title: str,
    error_message: str,
    request_id: Optional[str] = None,
) -> Optional[UUID]:
    """
    Automatically submit an episode assembly failure as a bug report.
    
    Args:
        session: Database session
        user: User who owns the episode
        episode_title: Title of episode that failed assembly
        error_message: Description of assembly error
        request_id: Optional request ID for tracing
    
    Returns:
        UUID of created FeedbackSubmission, or None if creation failed
    """
    try:
        category = "assembly"
        title = f"Episode assembly failed: {_truncate(episode_title, 50)}"
        
        description = f"""
**Episode Assembly Failure Report**

Episode: {episode_title}
Error: {error_message}
Request ID: {request_id or 'N/A'}

This error was automatically reported by the system during episode assembly.
"""
        
        error_logs = json.dumps({
            "error_message": error_message,
            "request_id": request_id,
        })
        
        feedback = FeedbackSubmission(
            user_id=user.id,
            type="bug",
            title=title,
            description=description,
            severity="critical",  # Assembly failures are critical
            category=category,
            
            error_logs=error_logs,
            user_action=f"Assembling episode: {episode_title}",
            
            status="new",
            admin_notified=False,
        )
        
        session.add(feedback)
        session.flush()
        
        log.info(
            "[bug_reporter] Created assembly bug report: feedback_id=%s user=%s episode=%s",
            str(feedback.id),
            user.email,
            episode_title,
        )
        
        # Attempt to send admin notification
        try:
            _send_admin_bug_notification(feedback, user, session)
            feedback.admin_notified = True
        except Exception as e:
            log.warning(
                "[bug_reporter] Failed to send admin notification for assembly bug %s: %s",
                str(feedback.id),
                e,
            )
        
        session.add(feedback)
        session.commit()
        session.refresh(feedback)
        
        return feedback.id
    
    except Exception as e:
        log.exception(
            "[bug_reporter] Exception creating assembly bug report: user=%s episode=%s error=%s",
            user.email if user else "unknown",
            episode_title,
            e,
        )
        return None


def report_generic_error(
    session: Session,
    user: Optional[User],
    error_category: str,
    error_message: str,
    error_code: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[UUID]:
    """
    Automatically submit a generic system error as a bug report.
    
    Args:
        session: Database session
        user: Optional user (some errors may not have a user context)
        error_category: Category of error (e.g., "transcription", "upload", "database")
        error_message: Description of error
        error_code: Optional error code
        context: Optional additional context
    
    Returns:
        UUID of created FeedbackSubmission, or None if creation failed
    """
    if not user:
        log.warning(
            "[bug_reporter] Cannot report error without user context: category=%s error=%s",
            error_category,
            error_message,
        )
        return None
    
    try:
        title = f"System error: {error_category}"
        
        description = f"""
**System Error Report**

Category: {error_category}
Error: {error_message}
Error Code: {error_code or 'N/A'}

This error was automatically reported by the system.
"""
        
        error_logs = json.dumps({
            "category": error_category,
            "error_message": error_message,
            "error_code": error_code,
            **(context or {}),
        })
        
        feedback = FeedbackSubmission(
            user_id=user.id,
            type="bug",
            title=title,
            description=description,
            severity="medium",
            category=error_category,
            
            error_logs=error_logs,
            
            status="new",
            admin_notified=False,
        )
        
        session.add(feedback)
        session.flush()
        
        log.info(
            "[bug_reporter] Created generic error bug report: feedback_id=%s user=%s category=%s",
            str(feedback.id),
            user.email,
            error_category,
        )
        
        # Attempt to send admin notification (only for high severity)
        try:
            if feedback.severity in ["critical", "high"]:
                _send_admin_bug_notification(feedback, user, session)
                feedback.admin_notified = True
        except Exception as e:
            log.warning(
                "[bug_reporter] Failed to send admin notification for error bug %s: %s",
                str(feedback.id),
                e,
            )
        
        session.add(feedback)
        session.commit()
        session.refresh(feedback)
        
        return feedback.id
    
    except Exception as e:
        log.exception(
            "[bug_reporter] Exception creating generic error bug report: user=%s category=%s error=%s",
            user.email if user else "unknown",
            error_category,
            e,
        )
        return None


def _send_admin_bug_notification(
    feedback: FeedbackSubmission,
    user: User,
    session: Session,
) -> bool:
    """
    Send email notification to admins about critical bug report.
    
    Returns True if email sent successfully, False otherwise.
    """
    admin_email = settings.ADMIN_EMAIL
    if not admin_email:
        log.debug("[bug_reporter] ADMIN_EMAIL not configured, skipping notification")
        return False
    
    try:
        subject = f"🐛 [{feedback.severity.upper()}] {feedback.title}"
        
        # Build detailed admin notification
        text_body = f"""
NEW BUG REPORT - {feedback.severity.upper()}

User: {user.email} (ID: {user.id})
Type: {feedback.type}
Category: {feedback.category or 'N/A'}
Title: {feedback.title}

Description:
{feedback.description}

---
Error Logs:
{feedback.error_logs or 'None'}

---
Reported: {feedback.created_at.isoformat() if feedback.created_at else 'Unknown'}
Bug ID: {feedback.id}

Action Required:
1. Review in admin dashboard
2. Investigate and assign
3. Post updates to user
4. Mark resolved when fixed
"""
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: monospace; background: #f3f4f6; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #fee2e2; padding: 15px; border-radius: 6px; border-left: 4px solid #dc2626; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; color: #991b1b; }}
        .bug-id {{ color: #7f1d1d; font-size: 12px; }}
        .section {{ background: white; padding: 15px; margin: 10px 0; border-radius: 6px; border-left: 3px solid #3b82f6; }}
        .section-title {{ font-weight: bold; color: #1e40af; text-transform: uppercase; font-size: 12px; }}
        .section-content {{ margin-top: 10px; color: #374151; white-space: pre-wrap; word-break: break-word; }}
        .user-info {{ background: #e0e7ff; padding: 10px; border-radius: 4px; margin: 10px 0; }}
        .severity-critical {{ background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-weight: bold; }}
        .severity-high {{ background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px; font-weight: bold; }}
        .severity-medium {{ background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🐛 New Bug Report</h1>
            <div class="bug-id">Bug ID: {feedback.id}</div>
            <div class="severity-{feedback.severity}">{feedback.severity.upper()}</div>
        </div>

        <div class="user-info">
            <strong>User:</strong> {user.email}<br>
            <strong>User ID:</strong> {user.id}
        </div>

        <div class="section">
            <div class="section-title">Type & Category</div>
            <div class="section-content">Type: {feedback.type}
Category: {feedback.category or 'N/A'}</div>
        </div>

        <div class="section">
            <div class="section-title">Title</div>
            <div class="section-content">{feedback.title}</div>
        </div>

        <div class="section">
            <div class="section-title">Description</div>
            <div class="section-content">{feedback.description}</div>
        </div>

        {f'''<div class="section">
            <div class="section-title">Error Logs</div>
            <div class="section-content">{feedback.error_logs or 'None'}</div>
        </div>''' if feedback.error_logs else ''}

        <div class="footer">
            <p>Review and manage this bug in the admin dashboard.</p>
            <p>© 2025 DoneCast</p>
        </div>
    </div>
</body>
</html>
"""
        
        success = mailer.send(
            to=admin_email,
            subject=subject,
            text=text_body,
            html=html_body,
        )
        
        if success:
            log.info(
                "[bug_reporter] Admin notification sent: feedback_id=%s admin=%s",
                str(feedback.id),
                admin_email,
            )
        else:
            log.warning(
                "[bug_reporter] Admin notification rejected by SMTP: feedback_id=%s",
                str(feedback.id),
            )
        
        return success
    
    except Exception as e:
        log.exception(
            "[bug_reporter] Exception sending admin notification: feedback_id=%s error=%s",
            str(feedback.id) if feedback else "unknown",
            e,
        )
        return False


def _truncate(text: str, length: int) -> str:
    """Truncate text to specified length."""
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length - 3] + "..."
