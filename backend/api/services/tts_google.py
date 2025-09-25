from typing import Optional
from pydub import AudioSegment
import io

try:
    from google.cloud import texttospeech
except ImportError:  # pragma: no cover
    texttospeech = None

class GoogleTTSNotConfigured(Exception):
    pass


def synthesize_google_tts(text: str, voice_name: str = "en-US-Neural2-C", speaking_rate: float = 1.0) -> AudioSegment:
    if texttospeech is None:
        raise GoogleTTSNotConfigured("google-cloud-texttospeech not installed")
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speaking_rate
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    audio_bytes = response.audio_content
    buf = io.BytesIO(audio_bytes)
    return AudioSegment.from_file(buf, format="mp3")
