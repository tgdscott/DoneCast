"""Compatibility shim for the legacy location of `transcription_runner`.

Canonical implementation: `api.services.transcription.transcription_runner`.

This module re-exports the public surface so legacy imports remain valid while
avoiding duplicated (and previously conflict-laden) code.
"""

from __future__ import annotations

from api.services.transcription.transcription_runner import (  # type: ignore
    run_assemblyai_job,
    normalize_transcript_payload,
)

__all__ = [
    "run_assemblyai_job",
    "normalize_transcript_payload",
]

