from __future__ import annotations

from typing import Any, Dict, Optional

try:  # Celery worker is optional in some environments
    from worker.tasks import celery_app  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - local/dev without worker package
    celery_app = None  # type: ignore


def get_status(job_id: str) -> Dict[str, Any]:
    """Return raw Celery status. If the broker is unavailable (common in dev),
    gracefully degrade to a pseudo status so callers can continue.
    """
    if celery_app is None:
        return {"raw_status": "PENDING", "raw_result": None, "note": "worker_unavailable"}

    try:
        task = celery_app.AsyncResult(job_id)
        status_val = getattr(task, "status", "PENDING")
        result = getattr(task, "result", None)
        return {"raw_status": status_val, "raw_result": result}
    except Exception:
        # Dev-safe fallback: when broker is down or not configured, report PENDING
        # and let router apply heuristics to map to processed/queued.
        return {"raw_status": "PENDING", "raw_result": None, "note": "broker_unavailable"}


def retry(job_id: str) -> bool:
    if celery_app is None:
        return False

    try:
        task = celery_app.AsyncResult(job_id)
        task.retry()
        return True
    except Exception:
        return False


def cancel(job_id: str) -> bool:
    if celery_app is None:
        return False

    try:
        celery_app.control.revoke(job_id, terminate=True)
        return True
    except Exception:
        return False
