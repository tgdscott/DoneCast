# api/services/ai_enhancer.py
import os
from typing import Optional
from pydub import AudioSegment
import io

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None # type: ignore
    _HTTPX_AVAILABLE = False

from api.core.config import settings
from api.models.user import User

class AIEnhancerError(Exception):
    pass

def generate_speech_from_text(
    text: str,
    voice_id: str | None = None,
    provider: str = "elevenlabs",
    google_voice: str | None = None,
    speaking_rate: float = 1.0,
    user: Optional[User] = None,
) -> AudioSegment:
    """
    Generates speech from text using the specified provider (ElevenLabs or Google).
    """
    if provider == "elevenlabs":
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError:
            raise AIEnhancerError("ElevenLabs client is not installed. Run 'pip install elevenlabs'.")

        # Use user-specific key if available, otherwise fall back to system key
        api_key = (user and user.elevenlabs_api_key) or settings.ELEVENLABS_API_KEY
        if not api_key or api_key == "dummy":
            raise AIEnhancerError("ElevenLabs API key is not configured on the server or for your user account.")

        client = ElevenLabs(api_key=api_key)
        
        # Default voice if none provided.
        # The high-level `generate` helper can resolve names, but the core `text_to_speech.convert` needs an ID.
        # We'll hardcode the ID for the default "Rachel" voice.
        voice_id_to_use = voice_id
        if not voice_id_to_use:
            voice_id_to_use = "21m00Tcm4TlvDq8ikWAM" # Default to "Rachel"

        try:
            # The `client.generate` method is a helper that can be inconsistent across library versions.
            # Using the core `text_to_speech.convert` method is more stable.
            audio_iterator = client.text_to_speech.convert(
                voice_id=voice_id_to_use,
                text=text,
                model_id="eleven_multilingual_v2"
            )

            audio_bytes = b"".join(audio_iterator)

            if not isinstance(audio_bytes, bytes) or not audio_bytes:
                raise AIEnhancerError("ElevenLabs returned no audio data.")
            
            return AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        except Exception as e:
            # Try to extract a more specific error from httpx exceptions
            if _HTTPX_AVAILABLE and isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                try:
                    details = e.response.json().get("detail", {})
                    message = details.get("message", e.response.text)
                except Exception:
                    message = e.response.text
                
                if status_code == 401:
                    raise AIEnhancerError("The provided ElevenLabs API key is invalid or lacks permissions.")
                if status_code == 402:
                    raise AIEnhancerError("ElevenLabs API call failed due to a billing issue. Please check your ElevenLabs account.")
                if status_code == 422 and "voice_id" in message.lower():
                    raise AIEnhancerError(f"The voice ID '{voice_id_to_use}' could not be found or is invalid.")
                
                raise AIEnhancerError(f"ElevenLabs API error ({status_code}): {message}")

            # Fallback for other exception types
            err_str = str(e).lower()
            if "invalid api key" in err_str or "unauthorized" in err_str:
                 raise AIEnhancerError("The provided ElevenLabs API key is invalid or lacks permissions.")
            if "voice_id" in err_str and "not found" in err_str:
                 raise AIEnhancerError(f"The voice ID '{voice_id_to_use}' could not be found.")
            raise AIEnhancerError(f"ElevenLabs API error: {e}")

    elif provider == "google":
        raise AIEnhancerError("Google TTS provider is not yet implemented.")
    else:
        raise AIEnhancerError(f"Unsupported TTS provider: {provider}")