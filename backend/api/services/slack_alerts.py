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
                        "value": "Podcast Plus Plus Processing",
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
        "🧪 Test alert from Podcast Plus Plus monitoring system. If you see this, Slack integration is working!",
        severity="info"
    )
    if success:
        logger.info("[SlackAlert] Test alert sent successfully")
    else:
        logger.error("[SlackAlert] Test alert failed - check SLACK_WEBHOOK_URL")
    return success
