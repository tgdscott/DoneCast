"""Audio processing subpackage.

This package contains modularized pieces of the former monolithic
audio_processor.py to improve maintainability and testability.
"""

# Re-export main orchestration for convenience if importing from package
from .processor import process_and_assemble_episode  # noqa: F401
