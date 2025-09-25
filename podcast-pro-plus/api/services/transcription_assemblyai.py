import logging
from pathlib import Path
from typing import List, Dict, Any

from ..core.config import settings
from api.core.paths import MEDIA_DIR

from api.services.transcription.transcription_runner import run_assemblyai_job
from api.services.transcription.assemblyai_client import AssemblyAITranscriptionError as _ClientError

ASSEMBLYAI_BASE = "https://api.assemblyai.com/v2"


class AssemblyAITranscriptionError(Exception):
    pass


def assemblyai_transcribe_with_speakers(filename: str, timeout_s: int = 1800) -> List[Dict[str, Any]]:
    """
    Thin façade: build cfg from settings/env, delegate to runner, return same shape as before.
    """
    api_key = settings.ASSEMBLYAI_API_KEY
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise AssemblyAITranscriptionError("AssemblyAI API key not configured")

    audio_path = MEDIA_DIR / filename
    if not audio_path.exists():
        raise AssemblyAITranscriptionError(f"Audio file not found: {filename}")

    webhook_cfg: Dict[str, Any] = {}
    webhook_secret = getattr(settings, "ASSEMBLYAI_WEBHOOK_SECRET", None)
    webhook_url = getattr(settings, "ASSEMBLYAI_WEBHOOK_URL", None)
    if webhook_secret:
        resolved_url: str | None = None
        if webhook_url:
            resolved_url = webhook_url.rstrip("/")
        else:
            base = (settings.APP_BASE_URL or "").strip()
            if base:
                resolved_url = f"{base.rstrip('/')}/api/assemblyai/webhook"
        if resolved_url:
            header_name = (settings.ASSEMBLYAI_WEBHOOK_HEADER or "X-AssemblyAI-Signature").strip() or "X-AssemblyAI-Signature"
            webhook_cfg = {
                "url": resolved_url,
                "secret": webhook_secret,
                "auth_header_name": header_name,
            }

    cfg: Dict[str, Any] = {
        "api_key": api_key,
        "base_url": ASSEMBLYAI_BASE,
        "params": {
            # Defaults mirror monolith payload; runner/client preserve logging
            "language_code": "en_us",
            "speaker_labels": True,
            "punctuate": True,
            "format_text": False,
            "disfluencies": True,
            "filter_profanity": False,
            "language_detection": False,
            "custom_spelling": [],
            "multichannel": False,
        },
        "polling": {
            "interval_s": 1.0,
            "max_interval_s": 8.0,
            "backoff": 1.5,
            "timeout_s": float(timeout_s or 1800),
        },
    }

    if webhook_cfg:
        cfg["webhook"] = webhook_cfg

    # Delegate to the runner; rewrap errors into legacy exception class to preserve type
    try:
        out = run_assemblyai_job(audio_path, cfg, log=[])
    except _ClientError as e:
        raise AssemblyAITranscriptionError(str(e))

    # Runner returns {"words": [...]}; legacy returned just the list
    words = list(out.get("words") or [])
    return words
