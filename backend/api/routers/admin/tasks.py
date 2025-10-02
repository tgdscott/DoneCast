"""Administrative controls for Cloud Tasks queues."""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

try:  # pragma: no cover - optional dependency at import time
    from google.api_core import exceptions as gcloud_exceptions
    from google.cloud import tasks_v2
except ImportError:  # pragma: no cover - gracefully handle missing dependency
    tasks_v2 = None  # type: ignore
    gcloud_exceptions = None  # type: ignore

from api.models.user import User

from .deps import get_current_admin_user


router = APIRouter(prefix="/tasks")

_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
_LOCATION = os.getenv("TASKS_LOCATION", "us-west1")
_QUEUE_ID = os.getenv("TASKS_QUEUE", "ppp-queue")


def _ensure_client() -> "tasks_v2.CloudTasksClient":
    """Return a CloudTasksClient or raise an HTTP error if unavailable."""

    if tasks_v2 is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="google-cloud-tasks is not installed on this service.",
        )
    if not _PROJECT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_CLOUD_PROJECT is not configured for Cloud Tasks.",
        )
    return tasks_v2.CloudTasksClient()


def _queue_path(client: "tasks_v2.CloudTasksClient") -> str:
    return client.queue_path(_PROJECT_ID, _LOCATION, _QUEUE_ID)


def _response_state(obj: Any) -> str | None:
    state = getattr(obj, "state", None)
    try:
        return state.name  # type: ignore[union-attr]
    except AttributeError:
        return str(state) if state is not None else None


@router.post("/kill", response_model=Dict[str, Any])
def kill_tasks_queue(current_user: User = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Pause, purge, and resume the configured Cloud Tasks queue."""

    del current_user  # Access check handled by dependency

    client = _ensure_client()
    queue_name = _queue_path(client)

    try:
        paused = client.pause_queue(name=queue_name)
    except Exception as exc:  # pragma: no cover - network/env specific
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to pause queue '{_QUEUE_ID}': {exc}",
        ) from exc

    try:
        client.purge_queue(name=queue_name)
    except Exception as exc:  # pragma: no cover - network/env specific
        # If purge fails because the queue was recently purged, surface a helpful message
        if gcloud_exceptions and isinstance(exc, gcloud_exceptions.FailedPrecondition):
            detail = f"Queue '{_QUEUE_ID}' purge rejected: {exc.message or str(exc)}"
        else:
            detail = f"Failed to purge queue '{_QUEUE_ID}': {exc}"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc

    try:
        resumed = client.resume_queue(name=queue_name)
    except Exception as exc:  # pragma: no cover - network/env specific
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to resume queue '{_QUEUE_ID}': {exc}",
        ) from exc

    return {
        "queue": _QUEUE_ID,
        "location": _LOCATION,
        "paused_state": _response_state(paused),
        "resumed_state": _response_state(resumed),
        "message": f"Queue '{_QUEUE_ID}' paused, purged, and resumed.",
    }


__all__ = ["router"]
