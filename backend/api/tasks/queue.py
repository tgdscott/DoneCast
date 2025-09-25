# api/tasks/queue.py
from __future__ import annotations

import json
import os
from typing import Dict, Any, Optional
from google.cloud import tasks_v2


PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
LOCATION = os.getenv("TASKS_LOCATION", "us-west1")
QUEUE_ID = os.getenv("TASKS_QUEUE", "ppp-queue")
TASKS_AUTH = os.getenv("TASKS_AUTH", "dev-secret")  # must match Cloud Run env


def _queue_path(client: tasks_v2.CloudTasksClient) -> str:
    if not PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT not set")
    return client.queue_path(PROJECT_ID, LOCATION, QUEUE_ID)


def enqueue_task(
    path: str,
    payload: Dict[str, Any],
    *,
    url_base: Optional[str] = None,
    schedule_seconds: Optional[int] = None,
) -> str:
    """
    Enqueue an HTTP task to POST JSON payload to the given internal path.
    path: e.g. '/internal/tasks/transcribe'
    """
    client = tasks_v2.CloudTasksClient()
    parent = _queue_path(client)

    # Cloud Run base URL — use the request host in prod if you prefer.
    base = url_base or os.getenv("TASKS_URL_BASE") or os.getenv("APP_BASE_URL") or ""
    if not base:
        # Fall back to default service URL via env (works on CR), else your custom
        base = os.getenv("K_SERVICE_URL") or f"https://{os.getenv('K_SERVICE')}-"
    url = (base.rstrip("/") + path) if base else (path)  # final absolute URL preferred

    http_request = tasks_v2.HttpRequest(
        http_method=tasks_v2.HttpMethod.POST,
        url=url,
        headers={
            "Content-Type": "application/json",
            "X-Tasks-Auth": TASKS_AUTH,
        },
        body=json.dumps(payload).encode("utf-8"),
    )

    task = tasks_v2.Task(http_request=http_request)

    if schedule_seconds and schedule_seconds > 0:
        from google.protobuf import timestamp_pb2
        import time
        ts = timestamp_pb2.Timestamp()
        ts.FromMilliseconds(int((time.time() + schedule_seconds) * 1000))
        task.schedule_time = ts

    resp = client.create_task(request={"parent": parent, "task": task})
    return resp.name
