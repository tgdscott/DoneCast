"""Compatibility shim redirecting to the canonical services.transcription.assemblyai_client.

This module existed historically in a duplicated location. Keep a minimal, explicit
re-export so any legacy imports like `from api.transcription.assemblyai_client import X`
continue to function without carrying the old duplicated implementation (which had
merge conflict artifacts).
"""

from __future__ import annotations

from api.services.transcription import assemblyai_client as _impl

# Explicit re-exports (avoid wildcard star to keep linting predictable).
AssemblyAITranscriptionError = _impl.AssemblyAITranscriptionError  # type: ignore[attr-defined]
upload_audio = _impl.upload_audio  # type: ignore[attr-defined]
start_transcription = _impl.start_transcription  # type: ignore[attr-defined]
get_transcription = _impl.get_transcription  # type: ignore[attr-defined]
cancel_transcription = _impl.cancel_transcription  # type: ignore[attr-defined]

# get_http_session is an internal helper; export if present for advanced callers.
get_http_session = getattr(_impl, "get_http_session", None)

__all__ = [
    "AssemblyAITranscriptionError",
    "upload_audio",
    "start_transcription",
    "get_transcription",
    "cancel_transcription",
    "get_http_session",
]

