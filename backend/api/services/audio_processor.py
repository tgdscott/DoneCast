"""Compatibility wrapper for legacy imports.

Delegates to the modular implementation in api.services.audio.processor.
"""

from api.services.audio.processor import process_and_assemble_episode, AudioProcessingError  # noqa: F401