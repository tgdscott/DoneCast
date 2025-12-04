"""
Slack Alert System for Server Monitoring
Sends notifications when local worker goes down or processing fails
"""
import os
import logging
import requests
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

def send_slack_alert(
    message: str,
    severity: str = "warning",
    include_timestamp: bool = True
) -> bool:
    """
    Send alert to Slack channel
    
    Args:
        message: Alert message text
        severity: "info", "warning", "error", "critical"
        include_timestamp: Whether to prepend timestamp to message
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not SLACK_WEBHOOK_URL:
        logger.debug("[SlackAlert] No webhook URL configured, skipping alert")
        return False
    
    # Emoji mapping for severity
    emoji_map = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🚨",
    }
    emoji = emoji_map.get(severity, "📢")
    
    # Color mapping for Slack attachments
    color_map = {
        "info": "#36a64f",      # green
        "warning": "#ff9900",   # orange
        "error": "#ff0000",     # red
        "critical": "#990000",  # dark red
    }
    color = color_map.get(severity, "#808080")
    
    # Format message
    if include_timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"{emoji} *[{timestamp}]* {message}"
    else:
        formatted_message = f"{emoji} {message}"
    
    # Slack webhook payload
    payload = {
        "text": formatted_message,
        "attachments": [
            {
                "color": color,
                "fields": [
                    {
                        "title": "Service",
                        "value": "DoneCast Processing",
                        "short": True
                    },
                    {
                        "title": "Severity",
                        "value": severity.upper(),
                        "short": True
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=5
        )
        response.raise_for_status()
        logger.debug(f"[SlackAlert] Sent {severity} alert to Slack")
        return True
    except requests.RequestException as e:
        logger.error(f"[SlackAlert] Failed to send alert: {e}")
        return False


def alert_worker_down():
    """Alert that local Celery worker is unreachable"""
    send_slack_alert(
        "🔴 Local processing worker is DOWN! Falling back to Cloud Run (slower, memory constrained).",
        severity="critical"
    )
    
    # Send SMS notifications to admins who have opted in
    try:
        from api.services.sms import sms_service
        from api.core.database import session_scope, engine
        from api.models.user import User
        from sqlmodel import select
        
        # Check if SMS columns exist before querying (safe migration handling)
        try:
            from sqlalchemy import inspect as sql_inspect
            inspector = sql_inspect(engine)
            user_columns = {col['name'] for col in inspector.get_columns('user')}
            has_sms_columns = all(col in user_columns for col in [
                'sms_notifications_enabled', 'sms_notify_worker_down', 'phone_number'
            ])
            
            if not has_sms_columns:
                logger.debug("[SlackAlert] SMS columns not found in user table, skipping SMS alerts (migration may not have run)")
                return
        except Exception as check_err:
            # If we can't check columns, skip SMS (don't break worker monitoring)
            logger.debug("[SlackAlert] Could not check for SMS columns, skipping SMS alerts: %s", check_err)
            return
        
        # Use proper session context manager
        try:
            with session_scope() as session:
                # Find all admin users who have SMS notifications enabled for worker down alerts
                admin_users = session.exec(
                    select(User).where(
                        User.role.in_(["admin", "superadmin"]),
                        User.sms_notifications_enabled == True,  # noqa: E712
                        User.sms_notify_worker_down == True,  # noqa: E712
                        User.phone_number != None  # noqa: E711
                    )
                ).all()
                
                # Also check legacy is_admin flag and ADMIN_EMAIL
                from api.core.config import settings
                admin_email = getattr(settings, "ADMIN_EMAIL", "").lower() if hasattr(settings, "ADMIN_EMAIL") else ""
                
                legacy_admins = session.exec(
                    select(User).where(
                        User.is_admin == True,  # noqa: E712
                        User.sms_notifications_enabled == True,  # noqa: E712
                        User.sms_notify_worker_down == True,  # noqa: E712
                        User.phone_number != None  # noqa: E711
                    )
                ).all()
                
                # Combine and deduplicate
                all_admins = {user.id: user for user in admin_users}
                for user in legacy_admins:
                    if user.id not in all_admins:
                        all_admins[user.id] = user
                
                # Also check ADMIN_EMAIL match
                if admin_email:
                    email_match = session.exec(
                        select(User).where(
                            User.email.ilike(f"%{admin_email}%"),
                            User.sms_notifications_enabled == True,  # noqa: E712
                            User.sms_notify_worker_down == True,  # noqa: E712
                            User.phone_number != None  # noqa: E711
                        )
                    ).first()
                    if email_match and email_match.id not in all_admins:
                        all_admins[email_match.id] = email_match
                
                # Send SMS to all admins (outside of session context to avoid connection issues)
                admin_list = list(all_admins.values())
            
            # Send SMS notifications outside of database session
            for admin in admin_list:
                phone_number = getattr(admin, 'phone_number', None)
                if phone_number:
                    admin_name = getattr(admin, 'first_name', None) or getattr(admin, 'email', None) or "Admin"
                    sms_service.send_worker_down_notification(
                        phone_number=phone_number,
                        admin_name=admin_name
                    )
                    logger.info("[SlackAlert] SMS worker down alert sent to admin %s (%s)", admin.email, phone_number)
        except Exception as query_err:
            # If columns don't exist or query fails, log and continue (don't break worker monitoring)
            logger.debug("[SlackAlert] Could not send SMS alerts (query may have failed): %s", query_err)
    except Exception as e:
        # Don't fail the alert if SMS fails
        logger.warning("[SlackAlert] Failed to send SMS worker down alerts: %s", e, exc_info=True)


def alert_worker_up():
    """Alert that local Celery worker is back online"""
    send_slack_alert(
        "✅ Local processing worker is BACK UP! Switching to local processing.",
        severity="info"
    )


def alert_processing_failed(episode_id: int, error: str):
    """Alert that episode processing failed"""
    send_slack_alert(
        f"Episode {episode_id} processing FAILED: {error}",
        severity="error"
    )


def alert_disk_space_low(available_gb: float):
    """Alert that server disk space is running low"""
    send_slack_alert(
        f"⚠️ Server disk space LOW: {available_gb:.1f} GB remaining",
        severity="warning"
    )


def alert_memory_high(used_percent: float):
    """Alert that server memory usage is high"""
    send_slack_alert(
        f"⚠️ Server memory usage HIGH: {used_percent:.1f}% used",
        severity="warning"
    )


def test_slack_integration():
    """Test Slack webhook - call this to verify setup"""
    success = send_slack_alert(
        "🧪 Test alert from DoneCast monitoring system. If you see this, Slack integration is working!",
        severity="info"
    )
    if success:
        logger.info("[SlackAlert] Test alert sent successfully")
    else:
        logger.error("[SlackAlert] Test alert failed - check SLACK_WEBHOOK_URL")
    return success
