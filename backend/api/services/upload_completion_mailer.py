"""Email notifications for audio upload completion with quality assessment and error reporting."""

from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from api.services.mailer import mailer
from api.models.user import User
from api.models.podcast import MediaItem

log = logging.getLogger("upload_completion_mailer")


def send_upload_success_email(
    user: User,
    media_item: MediaItem,
    quality_label: Optional[str] = None,
    processing_type: Optional[str] = None,
    audio_quality_metrics: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send email confirming successful audio upload and transcription.
    
    Args:
        user: User who uploaded the audio
        media_item: The uploaded MediaItem
        quality_label: Quality tier (e.g., "good", "abysmal")
        processing_type: "standard" (AssemblyAI) or "advanced" (Auphonic)
        audio_quality_metrics: Optional dict with audio analysis metrics
    
    Returns:
        True if email sent successfully, False otherwise
    """
    if not user.email:
        log.error("[upload_email] Cannot send email: user has no email address (user_id=%s)", user.id)
        return False

    # Get friendly audio name (strip UUID if present)
    audio_name = media_item.friendly_name or _strip_uuid_from_filename(media_item.filename)
    if not audio_name:
        audio_name = "Your audio"

    # Determine quality display text
    quality_display = _format_quality_label(quality_label)
    processing_display = _format_processing_type(processing_type)

    # Build email subject
    subject = f"✅ {audio_name} uploaded successfully"

    # Build email body (text version)
    text_body = f"""Congratulations!

Your audio "{audio_name}" has uploaded successfully.

Quality Assessment: {quality_display}
Processing Method: {processing_display}

You can now assemble it into an episode by visiting your Media Library.

If you have any questions or need help, feel free to reach out to our support team.

---
DoneCast Team
"""

    # Build HTML version with better formatting
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .success-icon {{ font-size: 48px; }}
        h1 {{ color: #10b981; margin: 10px 0; }}
        .content {{ background: #f9fafb; padding: 20px; border-radius: 8px; border-left: 4px solid #10b981; }}
        .details {{ margin: 20px 0; }}
        .detail-row {{ margin: 12px 0; display: flex; }}
        .detail-label {{ font-weight: 600; color: #374151; width: 140px; }}
        .detail-value {{ color: #111827; }}
        .quality-badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 14px; font-weight: 500; }}
        .quality-good {{ background: #d1fae5; color: #065f46; }}
        .quality-bad {{ background: #fed7aa; color: #92400e; }}
        .quality-abysmal {{ background: #fee2e2; color: #991b1b; }}
        .cta {{ text-align: center; margin-top: 30px; }}
        .cta-button {{ display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500; }}
        .footer {{ text-align: center; margin-top: 40px; font-size: 12px; color: #6b7280; }}
        .metrics {{ background: white; padding: 15px; border-radius: 6px; margin-top: 15px; font-size: 13px; }}
        .metrics-row {{ margin: 8px 0; display: flex; justify-content: space-between; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="success-icon">✅</div>
            <h1>Upload Successful!</h1>
        </div>

        <div class="content">
            <p>Congratulations! Your audio has been uploaded and is ready for assembly.</p>
            
            <div class="details">
                <div class="detail-row">
                    <div class="detail-label">Audio File:</div>
                    <div class="detail-value">{audio_name}</div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-label">Quality:</div>
                    <div class="detail-value">{quality_display}</div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-label">Processing:</div>
                    <div class="detail-value">{processing_display}</div>
                </div>
            </div>

            {_build_metrics_html(audio_quality_metrics) if audio_quality_metrics else ""}

            <p style="margin-top: 20px; font-size: 14px; color: #6b7280;">
                Your audio has been transcribed and is ready for episode creation. 
                Visit your Media Library to start assembling.
            </p>
        </div>

        <div class="cta">
            <a href="https://donecast.com/dashboard/media-library" class="cta-button">Open Media Library</a>
        </div>

        <div class="footer">
            <p>Questions? Visit our support center or contact us.</p>
            <p>© 2025 DoneCast. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""

    # Send email
    try:
        success = mailer.send(
            to=user.email,
            subject=subject,
            text=text_body,
            html=html_body,
        )
        
        if success:
            log.info(
                "[upload_email] Success email sent: user=%s media_id=%s audio_name=%s quality=%s processing=%s",
                user.email,
                media_item.id,
                audio_name,
                quality_label,
                processing_type,
            )
        else:
            log.warning(
                "[upload_email] Email rejected by SMTP: user=%s media_id=%s",
                user.email,
                media_item.id,
            )
        
        return success
    
    except Exception as e:
        log.exception(
            "[upload_email] Exception sending upload success email: user=%s media_id=%s error=%s",
            user.email,
            media_item.id,
            e,
        )
        return False


def send_upload_failure_email(
    user: User,
    filename: str,
    error_message: str,
    error_code: Optional[str] = None,
    request_id: Optional[str] = None,
) -> bool:
    """
    Send email notifying user of upload failure and automatic bug submission.
    
    Args:
        user: User whose upload failed
        filename: Name/path of file that failed
        error_message: Human-readable error description
        error_code: Optional error code for technical reference
        request_id: Optional request ID for support tracking
    
    Returns:
        True if email sent successfully, False otherwise
    """
    if not user.email:
        log.error("[upload_email] Cannot send error email: user has no email address (user_id=%s)", user.id)
        return False

    audio_name = _strip_uuid_from_filename(filename)
    if not audio_name:
        audio_name = "Your audio"

    # Build reference ID for user support
    reference_id = request_id or error_code or "unknown"

    # Build email subject
    subject = f"❌ Upload failed: {audio_name}"

    # Build text version
    text_body = f"""We encountered an issue uploading your audio.

File: {audio_name}
Status: Failed to upload and transcribe

Error: {error_message}
Reference ID: {reference_id}

What happened:
This has been automatically reported as a bug in our system. Our team has been notified and will investigate.

What you can do:
1. Try uploading again - sometimes this is a temporary network issue
2. Use a smaller file or different format if the problem persists
3. Contact our support team if the error continues

We apologize for the inconvenience. Your bug report will help us improve the system.

---
DoneCast Team
"""

    # Build HTML version
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .error-icon {{ font-size: 48px; }}
        h1 {{ color: #ef4444; margin: 10px 0; }}
        .alert {{ background: #fee2e2; padding: 20px; border-radius: 8px; border-left: 4px solid #ef4444; margin-bottom: 20px; }}
        .alert-title {{ font-weight: 600; color: #991b1b; margin-bottom: 10px; }}
        .alert-message {{ color: #7f1d1d; line-height: 1.5; }}
        .details {{ background: #f9fafb; padding: 15px; border-radius: 6px; margin: 20px 0; }}
        .detail-row {{ margin: 10px 0; display: flex; flex-direction: column; }}
        .detail-label {{ font-weight: 600; color: #374151; font-size: 13px; text-transform: uppercase; }}
        .detail-value {{ color: #111827; margin-top: 4px; word-break: break-all; }}
        .next-steps {{ background: #eff6ff; padding: 20px; border-radius: 8px; border-left: 4px solid #3b82f6; }}
        .next-steps-title {{ font-weight: 600; color: #1e40af; margin-bottom: 12px; }}
        .next-steps ol {{ margin: 0; padding-left: 20px; }}
        .next-steps li {{ margin: 8px 0; color: #1e3a8a; }}
        .cta {{ text-align: center; margin-top: 30px; }}
        .cta-button {{ display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500; }}
        .footer {{ text-align: center; margin-top: 40px; font-size: 12px; color: #6b7280; }}
        .reported {{ background: #ecfdf5; padding: 12px; border-radius: 6px; margin-top: 15px; text-align: center; color: #065f46; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="error-icon">❌</div>
            <h1>Upload Failed</h1>
        </div>

        <div class="alert">
            <div class="alert-title">Unable to process your upload</div>
            <div class="alert-message">
                We encountered an issue uploading <strong>{audio_name}</strong>. 
                This has been automatically reported to our team.
            </div>
        </div>

        <div class="details">
            <div class="detail-row">
                <div class="detail-label">Audio File</div>
                <div class="detail-value">{audio_name}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Error</div>
                <div class="detail-value">{error_message}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Reference ID</div>
                <div class="detail-value"><code>{reference_id}</code></div>
            </div>
        </div>

        <div class="reported">
            ✓ Automatically submitted as a bug report. Our team has been notified and will investigate.
        </div>

        <div class="next-steps">
            <div class="next-steps-title">What you can do:</div>
            <ol>
                <li>Try uploading the file again - it may have been a temporary network issue</li>
                <li>If it fails again, try a smaller file or different audio format</li>
                <li>Save your Reference ID above if you need to contact support</li>
                <li>Check our <a href="https://donecast.com/docs/troubleshooting" style="color: #3b82f6;">troubleshooting guide</a> for common solutions</li>
            </ol>
        </div>

        <div class="cta">
            <a href="https://donecast.com/dashboard/media-library" class="cta-button">Back to Media Library</a>
        </div>

        <div class="footer">
            <p>Need help? Reference ID <strong>{reference_id}</strong> when contacting support.</p>
            <p>© 2025 DoneCast. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""

    # Send email
    try:
        success = mailer.send(
            to=user.email,
            subject=subject,
            text=text_body,
            html=html_body,
        )
        
        if success:
            log.info(
                "[upload_email] Failure email sent: user=%s filename=%s error_code=%s reference_id=%s",
                user.email,
                filename,
                error_code,
                reference_id,
            )
        else:
            log.warning(
                "[upload_email] Failure email rejected by SMTP: user=%s filename=%s",
                user.email,
                filename,
            )
        
        return success
    
    except Exception as e:
        log.exception(
            "[upload_email] Exception sending upload failure email: user=%s filename=%s error=%s",
            user.email,
            filename,
            e,
        )
        return False


def _format_quality_label(label: Optional[str]) -> str:
    """Convert quality label to user-friendly text."""
    if not label:
        return "Unknown"
    
    label_lower = label.lower()
    
    quality_map = {
        "good": "🟢 Good - Crystal clear audio",
        "slightly_bad": "🟡 Fair - Acceptable quality",
        "fairly_bad": "🟡 Fair - Acceptable quality",
        "very_bad": "🟠 Poor - May need enhancement",
        "incredibly_bad": "🔴 Very Poor - Enhanced processing recommended",
        "abysmal": "🔴 Very Poor - Enhanced processing applied",
    }
    
    return quality_map.get(label_lower, "Unknown")


def _format_processing_type(processing_type: Optional[str]) -> str:
    """Convert processing type to user-friendly text."""
    if not processing_type:
        return "Standard Processing"
    
    processing_lower = processing_type.lower()
    
    if processing_lower == "advanced" or processing_lower == "auphonic":
        return "🎚️ Advanced Processing - Professional audio enhancement"
    elif processing_lower == "standard" or processing_lower == "assemblyai":
        return "📝 Standard Processing - Clean transcription"
    else:
        return "Standard Processing"


def _build_metrics_html(metrics: Optional[Dict[str, Any]]) -> str:
    """Build HTML for audio quality metrics."""
    if not metrics:
        return ""
    
    try:
        html = '<div class="metrics"><strong>Audio Analysis:</strong>'
        
        if "loudness_lufs" in metrics:
            lufs = metrics["loudness_lufs"]
            html += f'<div class="metrics-row"><span>Loudness (LUFS):</span><span>{lufs:.1f}</span></div>'
        
        if "loudness_max" in metrics:
            max_db = metrics["loudness_max"]
            html += f'<div class="metrics-row"><span>Peak Level:</span><span>{max_db:.1f} dB</span></div>'
        
        if "duration_seconds" in metrics:
            duration = metrics["duration_seconds"]
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            html += f'<div class="metrics-row"><span>Duration:</span><span>{minutes}:{seconds:02d}</span></div>'
        
        if "sample_rate" in metrics:
            sample_rate = metrics["sample_rate"]
            html += f'<div class="metrics-row"><span>Sample Rate:</span><span>{sample_rate} Hz</span></div>'
        
        html += '</div>'
        return html
    
    except Exception as e:
        log.warning("[upload_email] Error building metrics HTML: %s", e)
        return ""


def _strip_uuid_from_filename(filename: str) -> str:
    """Remove UUID prefix from filename for display to user."""
    if not filename:
        return ""
    
    # Handle GCS paths
    if filename.startswith("gs://"):
        # Extract just the filename from path
        parts = filename.split("/")
        filename = parts[-1] if parts else filename
    
    # Remove UUID prefix pattern (uuid_filename format)
    # Pattern: 8-4-4-4-12 hex digits followed by underscore
    import re
    uuid_pattern = r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_(.+)$"
    match = re.match(uuid_pattern, filename, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Remove hex prefix pattern (12charcode_filename format)
    hex_pattern = r"^[a-f0-9]{12,}_(.+)$"
    match = re.match(hex_pattern, filename, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return filename
