"""Slack helper utilities for fetching alerts and posting follow-up responses."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Iterable, List, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .models import Alert, AlertMetadata, AlertPayload

LOGGER = logging.getLogger(__name__)


class SlackAlertClient:
    """Lightweight wrapper around the Slack Web API."""

    def __init__(self, bot_token: str, channel_id: str) -> None:
        self._client = WebClient(token=bot_token)
        self._channel_id = channel_id

    def fetch_alerts(self, *, oldest: Optional[str] = None, limit: int = 10) -> List[Alert]:
        """Return the most recent alerts posted in the configured channel."""

        cursor: Optional[str] = None
        alerts: List[Alert] = []
        while True:
            params = {"channel": self._channel_id, "limit": limit}
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor
            try:
                response = self._client.conversations_history(**params)
            except SlackApiError as exc:
                LOGGER.error("Failed to fetch Slack history: %s", exc)
                break
            messages: Iterable[dict] = response.get("messages", [])
            for message in messages:
                ts = message.get("ts")
                if not ts:
                    continue
                text = message.get("text", "").strip()
                attachments_raw = message.get("attachments", [])
                attachments = [att.get("text", "") for att in attachments_raw]
                
                # Extract severity from Google Cloud Monitoring alert metadata
                severity = self._extract_severity(message, attachments_raw)
                
                permalink = self._build_permalink(ts)
                alert = Alert(
                    metadata=AlertMetadata(
                        channel=self._channel_id,
                        ts=ts,
                        sender=message.get("user") or message.get("bot_id"),
                        permalink=permalink,
                        severity=severity,
                    ),
                    payload=AlertPayload(text=text, attachments=attachments),
                    created_at=datetime.fromtimestamp(float(ts), tz=timezone.utc),
                )
                alerts.append(alert)
            cursor = response.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
        # Slack returns newest first; reverse for chronological processing.
        alerts.sort(key=lambda alert: float(alert.metadata.ts))
        return alerts

    def _build_permalink(self, ts: str) -> Optional[str]:
        try:
            response = self._client.chat_getPermalink(channel=self._channel_id, message_ts=ts)
        except SlackApiError:
            return None
        return response.get("permalink")

    def _extract_severity(self, message: dict, attachments: List[dict]) -> Optional[str]:
        """Extract severity from Google Cloud Monitoring alert metadata."""
        # Check attachment fields for severity (Google Cloud Monitoring format)
        for attachment in attachments:
            fields = attachment.get("fields", [])
            for field in fields:
                title = field.get("title", "").lower()
                value = field.get("value", "").lower()
                if "severity" in title:
                    # Normalize severity values: Warning -> medium, Error -> high, Critical -> critical
                    if "warning" in value:
                        return "medium"
                    elif "error" in value or "alert" in value:
                        return "high"
                    elif "critical" in value:
                        return "critical"
                    return value  # Return as-is if it's already normalized
        
        # Fallback: check message text for severity keywords
        text = message.get("text", "").lower()
        if "critical" in text:
            return "critical"
        elif "error" in text or "failed" in text:
            return "high"
        elif "warning" in text:
            return "medium"
        
        return None  # No severity detected, let AI decide

    def post_reply(self, thread_ts: str, *, text: Optional[str] = None, blocks: Optional[List[dict]] = None) -> None:
        """Post a message in a Slack thread."""

        if not text and not blocks:
            raise ValueError("Either text or blocks must be provided when posting to Slack.")
        try:
            self._client.chat_postMessage(
                channel=self._channel_id,
                thread_ts=thread_ts,
                text=text,
                blocks=blocks,
            )
        except SlackApiError as exc:
            LOGGER.error("Failed to post Slack reply: %s", exc)
            raise


__all__ = ["SlackAlertClient"]
