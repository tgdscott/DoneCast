from __future__ import annotations

from typing import Any, Dict, Optional

# Celery has been removed - all background processing uses Cloud Tasks
# These functions remain for backward compatibility but return stub responses


def get_status(job_id: str) -> Dict[str, Any]:
    """Return stub status since Celery is no longer used.
    
    All episode assembly now uses Cloud Tasks, not Celery.
    Job status should be checked via episode.status field in database.
    """
    return {"raw_status": "PENDING", "raw_result": None, "note": "celery_removed"}


def retry(job_id: str) -> bool:
    """Celery removed - retries are handled via Cloud Tasks or episode retry endpoint."""
    return False


def cancel(job_id: str) -> bool:
    """Celery removed - job cancellation no longer supported."""
    return False
