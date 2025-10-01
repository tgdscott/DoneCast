"""Text-to-speech helpers used by the AI enhancer features."""

from __future__ import annotations

import io
import logging
import re
from textwrap import dedent
from typing import Dict, Optional

from pydub import AudioSegment

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency at runtime
    httpx = None  # type: ignore[assignment]

from api.core.config import settings
from api.models.user import User
from api.services.ai_content import client_gemini


_DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"


_LOG = logging.getLogger(__name__)


class AIEnhancerError(Exception):
    """Raised when text-to-speech generation fails."""


def generate_speech_from_text(
    text: str,
    voice_id: str | None = None,
    provider: str = "elevenlabs",
    google_voice: str | None = None,
    speaking_rate: float = 1.0,
    user: Optional[User] = None,
    api_key: str | None = None,
) -> AudioSegment:
    """Generate speech from text using the requested provider."""

    if provider == "elevenlabs":
        return _generate_with_elevenlabs(text, voice_id=voice_id, user=user, api_key_override=api_key)
    if provider == "google":
        raise AIEnhancerError("Google TTS provider is not yet implemented.")
    raise AIEnhancerError(f"Unsupported TTS provider: {provider}")


def _generate_with_elevenlabs(
    text: str,
    *,
    voice_id: str | None,
    user: Optional[User],
    api_key_override: str | None,
) -> AudioSegment:
    api_key = (
        api_key_override
        or (user and user.elevenlabs_api_key)
        or settings.ELEVENLABS_API_KEY
    )
    if not api_key or api_key == "dummy":
        raise AIEnhancerError("ElevenLabs API key is not configured on the server or for your user account.")

    resolved_voice_id = voice_id or _DEFAULT_ELEVENLABS_VOICE_ID
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
    except ImportError:
        ElevenLabs = None  # type: ignore[assignment]

    if ElevenLabs is not None:
        client = ElevenLabs(api_key=api_key)

        try:
            iterator = client.text_to_speech.convert(
                voice_id=resolved_voice_id,
                text=text,
                model_id=_ELEVENLABS_MODEL_ID,
            )
            audio_bytes = b"".join(iterator)
        except Exception as exc:  # noqa: BLE001 - we normalise the error below
            raise _translate_elevenlabs_error(exc, resolved_voice_id)
    else:
        if httpx is None:
            raise AIEnhancerError(
                "ElevenLabs client is not installed and no HTTP client is available. Install 'elevenlabs' or 'httpx'."
            )
        try:
            with httpx.Client(timeout=60.0) as client:  # type: ignore[call-arg]
                response = client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}",
                    headers={
                        "xi-api-key": api_key,
                        "Accept": "audio/mpeg",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": _ELEVENLABS_MODEL_ID,
                    },
                )
                response.raise_for_status()
                audio_bytes = response.content
        except Exception as exc:  # noqa: BLE001 - normalised soon
            raise _translate_elevenlabs_error(exc, resolved_voice_id)

    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise AIEnhancerError("ElevenLabs returned no audio data.")

    return AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")


def _translate_elevenlabs_error(exc: Exception, voice_id: str) -> AIEnhancerError:
    """Convert ElevenLabs exceptions into human friendly messages."""

    if httpx is not None and isinstance(exc, httpx.HTTPStatusError):  # type: ignore[attr-defined]
        status_code = exc.response.status_code
        try:
            details = exc.response.json().get("detail", {})
            message = details.get("message", exc.response.text)
        except Exception:  # pragma: no cover - defensive guard
            message = exc.response.text

        lowered = message.lower()
        if status_code == 401 or "invalid api key" in lowered or "unauthorized" in lowered:
            return AIEnhancerError("The provided ElevenLabs API key is invalid or lacks permissions.")
        if status_code == 402:
            return AIEnhancerError(
                "ElevenLabs API call failed due to a billing issue. Please check your ElevenLabs account."
            )
        if status_code == 422 and "voice_id" in lowered:
            return AIEnhancerError(f"The voice ID '{voice_id}' could not be found or is invalid.")

        return AIEnhancerError(f"ElevenLabs API error ({status_code}): {message}")

    message = str(exc).lower()
    if "invalid api key" in message or "unauthorized" in message:
        return AIEnhancerError("The provided ElevenLabs API key is invalid or lacks permissions.")
    if "voice_id" in message and "not found" in message:
        return AIEnhancerError(f"The voice ID '{voice_id}' could not be found.")

    return AIEnhancerError(f"ElevenLabs API error: {exc}")


def interpret_intern_command(prompt_text: str) -> Dict[str, str]:
    """Lightweight interpretation for Intern commands.

    Determines whether the caller is requesting spoken audio or show-note style
    output and returns a normalized topic string for downstream AI prompts.
    """

    text = (prompt_text or "").strip()
    if not text:
        return {"action": "generate_audio", "topic": ""}

    lowered = text.lower()
    # Remove common lead-in phrases like "Hey intern," to keep the topic clean
    stripped = re.sub(r"^(?:hey\s+)?intern[:,\s]*", "", text, flags=re.IGNORECASE).strip()
    if not stripped:
        stripped = text

    shownote_keywords = {
        "show notes",
        "shownotes",
        "show-note",
        "note",
        "notes",
        "summary",
        "summarize",
        "recap",
        "bullet",
    }
    action = "generate_audio"
    if any(keyword in lowered for keyword in shownote_keywords):
        action = "add_to_shownotes"

    return {"action": action, "topic": stripped}


def get_answer_for_topic(
    topic: str,
    *,
    context: Optional[str] = None,
    mode: str = "audio",
) -> str:
    """Generate an intern answer using Gemini with graceful fallbacks."""

    topic_text = (topic or "").strip()
    context_text = (context or "").strip()
    if mode not in {"audio", "shownote"}:
        mode = "audio"

    if not topic_text and context_text:
        topic_text = context_text.splitlines()[0][:160]

    if mode == "shownote":
        guidance = "Produce concise bullet point show notes summarizing the key takeaways."
    else:
        guidance = "Draft a friendly spoken reply (2-3 sentences) the host can play in their show."

    prompt = dedent(
        f"""
        You are Podcast Pro Plus's helpful intern. {guidance}
        Topic: {topic_text or 'General request'}
        """
    ).strip()
    if context_text:
        prompt += "\nTranscript excerpt:\n" + context_text
    prompt += "\nResponse:"

    try:
        generated = client_gemini.generate(prompt, max_output_tokens=512, temperature=0.6)
    except Exception as exc:  # pragma: no cover - network/SDK issues downgraded to fallback
        _LOG.warning("[intern-ai] generation failed: %s", exc)
        generated = ""

    cleaned = (generated or "").strip()

    if mode == "shownote":
        if not cleaned:
            base = topic_text or context_text or "this segment"
            return f"- {base}"
        bullets = [re.sub(r"^[\s\-•]+", "", line).strip() for line in cleaned.splitlines() if line.strip()]
        if not bullets:
            bullets = [cleaned]
        return "\n".join(f"- {b}" for b in bullets[:6])

    if not cleaned:
        base = topic_text or context_text or "that topic"
        return f"Here's the update you requested about {base}."

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


__all__ = [
    "AIEnhancerError",
    "generate_speech_from_text",
    "interpret_intern_command",
    "get_answer_for_topic",
]
