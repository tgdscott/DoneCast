"""
SMS Notification Service using Twilio
Sends SMS notifications for user and admin events
"""
import os
import logging
import re
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import Twilio, but handle gracefully if not available
try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioException
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio not installed. SMS notifications will be disabled.")


class SMSService:
    """SMS service for sending notifications via Twilio."""
    
    def __init__(self) -> None:
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER", "+18332320424")  # Default to provided number
        self.enabled = bool(self.account_sid and self.auth_token and TWILIO_AVAILABLE)
        
        if not self.enabled:
            if not TWILIO_AVAILABLE:
                logger.info("Twilio library not installed; SMS disabled")
            elif not self.account_sid:
                logger.info("TWILIO_ACCOUNT_SID not configured; SMS disabled")
            elif not self.auth_token:
                logger.info("TWILIO_AUTH_TOKEN not configured; SMS disabled")
        else:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("SMS service initialized with Twilio (from: %s)", self.from_number)
            except Exception as e:
                logger.error("Failed to initialize Twilio client: %s", e)
                self.enabled = False
                self.client = None
    
    def normalize_phone_number(self, phone: str) -> Optional[str]:
        """Normalize phone number to E.164 format (public method)."""
        return self._normalize_phone_number(phone)
    
    def _normalize_phone_number(self, phone: str) -> Optional[str]:
        """Normalize phone number to E.164 format."""
        if not phone:
            return None
        
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)
        
        # If it starts with 1 and is 11 digits, it's already US format
        if len(digits) == 11 and digits[0] == '1':
            return f"+{digits}"
        # If it's 10 digits, assume US number and add +1
        elif len(digits) == 10:
            return f"+1{digits}"
        # If it already starts with +, return as is (assume valid E.164)
        elif phone.startswith('+'):
            return phone
        else:
            logger.warning("Unable to normalize phone number: %s", phone)
            return None
    
    def send_sms(
        self,
        to: str,
        message: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Send an SMS message.
        
        Args:
            to: Recipient phone number (will be normalized to E.164)
            message: Message text (max 1600 characters for single SMS)
            user_id: Optional user ID for logging
        
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not self.client:
            logger.debug("SMS service disabled; not sending message to %s", to)
            return False
        
        if not message or not message.strip():
            logger.warning("Empty SMS message; not sending")
            return False
        
        # Normalize phone number
        normalized_to = self._normalize_phone_number(to)
        if not normalized_to:
            logger.error("Invalid phone number format: %s", to)
            return False
        
        # Truncate message if too long (Twilio supports up to 1600 chars, but we'll be conservative)
        if len(message) > 1600:
            logger.warning("SMS message too long (%d chars), truncating to 1600", len(message))
            message = message[:1597] + "..."
        
        try:
            result = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=normalized_to
            )
            logger.info(
                "SMS sent successfully: to=%s from=%s sid=%s user_id=%s",
                normalized_to,
                self.from_number,
                result.sid,
                user_id
            )
            return True
        except TwilioException as e:
            logger.error(
                "Twilio error sending SMS to %s: %s (code=%s)",
                normalized_to,
                str(e),
                getattr(e, 'code', 'unknown')
            )
            return False
        except Exception as e:
            logger.exception("Unexpected error sending SMS to %s: %s", normalized_to, e)
            return False
    
    def send_transcription_ready_notification(
        self,
        phone_number: str,
        episode_name: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Send notification that episode is ready to assemble."""
        message = (
            f"🎙️ Your episode '{episode_name}' is ready to assemble! "
            f"Visit https://app.podcastplusplus.com to continue. "
            f"Reply STOP to opt out."
        )
        return self.send_sms(phone_number, message, user_id)
    
    def send_publish_notification(
        self,
        phone_number: str,
        episode_name: str,
        publish_date: Optional[datetime] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """Send notification that episode is published or scheduled."""
        if publish_date:
            # Format date/time in a readable way
            try:
                # Convert to user's local time if timezone available, otherwise UTC
                formatted_date = publish_date.strftime("%B %d, %Y at %I:%M %p %Z")
                message = (
                    f"✅ Your episode '{episode_name}' is scheduled for {formatted_date}. "
                    f"View it at https://app.podcastplusplus.com "
                    f"Reply STOP to opt out."
                )
            except Exception:
                # Fallback to ISO format
                message = (
                    f"✅ Your episode '{episode_name}' is scheduled for {publish_date.isoformat()}. "
                    f"View it at https://app.podcastplusplus.com "
                    f"Reply STOP to opt out."
                )
        else:
            message = (
                f"✅ Your episode '{episode_name}' has been published! "
                f"View it at https://app.podcastplusplus.com "
                f"Reply STOP to opt out."
            )
        return self.send_sms(phone_number, message, user_id)
    
    def send_worker_down_notification(
        self,
        phone_number: str,
        admin_name: Optional[str] = None
    ) -> bool:
        """Send notification to admin that worker server is down."""
        message = (
            "🚨 ALERT: Worker server is DOWN! "
            "Processing has fallen back to Cloud Run (slower, memory constrained). "
            "Please check the worker server status."
        )
        return self.send_sms(phone_number, message, admin_name)
    
    def send_worker_down_critical(
        self,
        phone_number: str
    ) -> bool:
        """Send critical notification that worker server is down (for immediate admin alert)."""
        message = "WORKER SERVER IS DOWN!!!!"
        return self.send_sms(phone_number, message)


# Singleton instance
sms_service = SMSService()

