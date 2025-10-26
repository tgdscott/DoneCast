"""
Transcription health monitoring and alerting.

Detects stuck transcriptions and sends Slack alerts to operations team.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import os
import httpx

from sqlmodel import Session, select, or_
from api.models.podcast import MediaItem
from api.models.transcription import TranscriptionWatch

log = logging.getLogger(__name__)

# Thresholds for alerting
TRANSCRIPTION_STUCK_THRESHOLD_MINUTES = 10  # Alert if transcription not done after 10 min
WEBHOOK_TIMEOUT_SECONDS = 5


class TranscriptionMonitor:
    """Monitor transcription health and send alerts."""
    
    def __init__(self, session: Session):
        self.session = session
        self.slack_webhook_url = os.getenv("SLACK_OPS_WEBHOOK_URL", "").strip()
    
    def find_stuck_transcriptions(self) -> List[Dict[str, Any]]:
        """
        Find transcriptions that are taking too long.
        
        Returns list of stuck items with details for alerting.
        """
        threshold_time = datetime.utcnow() - timedelta(minutes=TRANSCRIPTION_STUCK_THRESHOLD_MINUTES)
        
        stuck_items = []
        
        # Check TranscriptionWatch for items queued but not notified
        stmt = (
            select(TranscriptionWatch)
            .where(TranscriptionWatch.created_at < threshold_time)
            .where(TranscriptionWatch.notified_at == None)  # noqa: E711
            .where(or_(
                TranscriptionWatch.last_status == "queued",
                TranscriptionWatch.last_status == None,  # noqa: E711
            ))
        )
        
        watches = self.session.exec(stmt).all()
        
        for watch in watches:
            age_minutes = (datetime.utcnow() - watch.created_at).total_seconds() / 60
            
            # Get associated media item if exists
            media_stmt = select(MediaItem).where(MediaItem.filename == watch.filename)
            media_item = self.session.exec(media_stmt).first()
            
            stuck_items.append({
                "type": "transcription_watch",
                "user_id": str(watch.user_id),
                "filename": watch.filename,
                "friendly_name": watch.friendly_name,
                "age_minutes": round(age_minutes, 1),
                "created_at": watch.created_at.isoformat(),
                "notify_email": watch.notify_email,
                "last_status": watch.last_status,
                "media_item_id": str(media_item.id) if media_item else None,
            })
        
        return stuck_items
    
    def send_slack_alert(self, stuck_items: List[Dict[str, Any]]) -> bool:
        """
        Send Slack notification about stuck transcriptions.
        
        Returns True if alert sent successfully, False otherwise.
        """
        if not self.slack_webhook_url:
            log.warning("[monitor] SLACK_OPS_WEBHOOK_URL not configured - cannot send alerts")
            return False
        
        if not stuck_items:
            return True  # Nothing to alert about
        
        # Build Slack message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 {len(stuck_items)} Stuck Transcription{'s' if len(stuck_items) != 1 else ''}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Detected *{len(stuck_items)}* transcription(s) that have been queued for more than {TRANSCRIPTION_STUCK_THRESHOLD_MINUTES} minutes without completing."
                }
            },
            {"type": "divider"}
        ]
        
        for item in stuck_items[:10]:  # Limit to 10 items to avoid huge messages
            user_email = item.get("notify_email", "unknown")
            age = item["age_minutes"]
            filename = item.get("friendly_name") or item["filename"]
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*User:* `{user_email}`\n"
                        f"*File:* `{filename}`\n"
                        f"*Age:* {age:.1f} minutes\n"
                        f"*Status:* `{item.get('last_status', 'unknown')}`"
                    )
                }
            })
        
        if len(stuck_items) > 10:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"_... and {len(stuck_items) - 10} more_"
                }
            })
        
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Recommended Actions:*\n• Check AssemblyAI API status\n• Review Cloud Run logs for transcription errors\n• Verify Cloud Tasks queue is processing\n• Check database for TranscriptionWatch records"
            }
        })
        
        payload = {
            "blocks": blocks,
            "text": f"🚨 {len(stuck_items)} stuck transcription(s) detected"  # Fallback text
        }
        
        try:
            with httpx.Client(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
                response = client.post(self.slack_webhook_url, json=payload)
                response.raise_for_status()
            
            log.info("[monitor] Slack alert sent successfully for %d stuck transcription(s)", len(stuck_items))
            return True
        
        except Exception as e:
            log.error("[monitor] Failed to send Slack alert: %s", str(e), exc_info=True)
            return False
    
    def check_and_alert(self) -> Dict[str, Any]:
        """
        Check for stuck transcriptions and send alerts if needed.
        
        Returns summary of check results.
        """
        try:
            stuck_items = self.find_stuck_transcriptions()
            
            result = {
                "checked_at": datetime.utcnow().isoformat(),
                "stuck_count": len(stuck_items),
                "stuck_items": stuck_items,
                "alert_sent": False,
                "slack_configured": bool(self.slack_webhook_url)
            }
            
            if stuck_items and self.slack_webhook_url:
                result["alert_sent"] = self.send_slack_alert(stuck_items)
            
            return result
        
        except Exception as e:
            log.error("[monitor] Transcription health check failed: %s", str(e), exc_info=True)
            return {
                "checked_at": datetime.utcnow().isoformat(),
                "error": str(e),
                "stuck_count": 0,
                "stuck_items": [],
                "alert_sent": False
            }


def check_transcription_health(session: Session) -> Dict[str, Any]:
    """
    Convenience function to check transcription health.
    
    Usage:
        from api.services.monitoring.transcription_monitor import check_transcription_health
        result = check_transcription_health(session)
    """
    monitor = TranscriptionMonitor(session)
    return monitor.check_and_alert()


__all__ = ["TranscriptionMonitor", "check_transcription_health", "TRANSCRIPTION_STUCK_THRESHOLD_MINUTES"]
