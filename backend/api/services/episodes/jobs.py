from __future__ import annotations

from typing import Any, Dict, Optional

from worker.tasks import celery_app


def get_status(job_id: str) -> Dict[str, Any]:
    task = celery_app.AsyncResult(job_id)
    status_val = getattr(task, "status", "PENDING")
    result = getattr(task, "result", None)
    return {"raw_status": status_val, "raw_result": result}


def retry(job_id: str) -> bool:
    try:
        task = celery_app.AsyncResult(job_id)
        task.retry()
        return True
    except Exception:
        return False


def cancel(job_id: str) -> bool:
    try:
        celery_app.control.revoke(job_id, terminate=True)
        return True
    except Exception:
        return False
