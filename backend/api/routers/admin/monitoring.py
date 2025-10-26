"""
Admin monitoring endpoints for system health checks and alerting.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import Dict, Any

from api.core.database import get_session
from api.dependencies.auth import get_current_admin_user
from api.models.user import User
from api.services.monitoring import check_transcription_health

router = APIRouter(prefix="/api/admin/monitoring", tags=["admin", "monitoring"])


@router.get("/transcription-health", response_model=Dict[str, Any])
def check_transcription_health_endpoint(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Check for stuck transcriptions and optionally send Slack alerts.
    
    Requires admin authentication.
    
    Returns:
        - checked_at: ISO timestamp of check
        - stuck_count: Number of stuck transcriptions found
        - stuck_items: List of stuck transcription details
        - alert_sent: Whether Slack alert was sent
        - slack_configured: Whether Slack webhook is configured
    
    Environment Variables:
        - SLACK_OPS_WEBHOOK_URL: Slack incoming webhook URL for alerts
    """
    del admin_user  # Only need to verify admin status
    
    result = check_transcription_health(session)
    return result


@router.post("/transcription-health/alert", response_model=Dict[str, Any])
def force_transcription_alert(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Force-send a Slack alert about stuck transcriptions (even if none found).
    
    Useful for testing Slack integration.
    """
    del admin_user
    
    from api.services.monitoring.transcription_monitor import TranscriptionMonitor
    
    monitor = TranscriptionMonitor(session)
    stuck_items = monitor.find_stuck_transcriptions()
    
    if not monitor.slack_webhook_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLACK_OPS_WEBHOOK_URL not configured"
        )
    
    # Send alert even if no stuck items (for testing)
    test_message = stuck_items or [{
        "type": "test",
        "message": "Test alert - no actual stuck transcriptions",
        "age_minutes": 0,
        "filename": "test.wav"
    }]
    
    alert_sent = monitor.send_slack_alert(test_message)
    
    return {
        "alert_sent": alert_sent,
        "stuck_count": len(stuck_items),
        "stuck_items": stuck_items,
        "test_mode": len(stuck_items) == 0
    }
