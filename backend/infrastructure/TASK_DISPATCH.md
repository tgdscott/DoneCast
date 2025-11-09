# Task Dispatch System

## Overview

All task dispatch in the application goes through `tasks_client.enqueue_http_task()`. This centralized system ensures consistent routing, logging, and error handling across all task types.

## Architecture

### Single Dispatch Path

**All task dispatch must use:**
```python
from infrastructure.tasks_client import enqueue_http_task

task_info = enqueue_http_task("/api/tasks/transcribe", {
    "filename": "audio.wav",
    "user_id": "123"
})
```

**No other module should:**
- Import `httpx`, `requests`, or `google.cloud.tasks` for task dispatch
- Directly call Cloud Tasks API
- Make HTTP calls to task endpoints
- Use `multiprocessing` for task dispatch

### Dispatch Flow

1. **Dry-Run Mode** (if `TASKS_DRY_RUN=true`)
   - Logs the task path
   - Returns a fake task ID: `dry-run-<iso-timestamp>`
   - Does not execute the task

2. **Cloud Tasks** (production)
   - Requires: `GOOGLE_CLOUD_PROJECT`, `TASKS_LOCATION`, `TASKS_QUEUE`, `TASKS_URL_BASE`
   - Creates a Cloud Task that POSTs to the task endpoint
   - Returns Cloud Task name (e.g., `projects/.../tasks/...`)

3. **Local Dispatch** (dev/test)
   - Routes based on task path:
     - `/api/tasks/transcribe` → Local thread execution
     - `/api/tasks/assemble` → Worker server (if `USE_WORKER_IN_DEV=true`) or local thread
     - `/api/tasks/process-chunk` → Worker server (if `USE_WORKER_IN_DEV=true`) or local thread
   - Returns task identifier: `local-direct-dispatch` or `dev-worker-dispatch-<timestamp>`

## Environment Variables

### Required (Production)

- `GOOGLE_CLOUD_PROJECT`: Google Cloud project ID
- `TASKS_LOCATION`: Cloud Tasks location (e.g., `us-west1`)
- `TASKS_QUEUE`: Cloud Tasks queue name
- `TASKS_URL_BASE`: Base URL for task endpoints (e.g., `https://api.example.com`)

### Optional

- `TASKS_DRY_RUN`: If `true`, log tasks but don't execute (default: `false`)
- `TASKS_AUTH`: Authentication secret for task endpoints (default: `a-secure-local-secret`)
- `WORKER_URL_BASE`: Worker server URL for dev mode (e.g., `http://localhost:8001`)
- `USE_WORKER_IN_DEV`: If `true`, route assembly/chunk tasks to worker server in dev (default: `false`)
- `TASKS_FORCE_HTTP_LOOPBACK`: If `true`, use HTTP loopback instead of local threads (default: `false`)
- `APP_ENV`: Environment name (`dev`, `test`, `production`) - affects routing

## Task Endpoints

### Transcription
- **Path**: `/api/tasks/transcribe`
- **Payload**: `{"filename": "gs://bucket/file.wav", "user_id": "123"}`
- **Timeout**: 30 minutes (1800s)

### Assembly
- **Path**: `/api/tasks/assemble`
- **Payload**: `{"episode_id": "123", "template_id": "456", "main_content_filename": "gs://...", ...}`
- **Timeout**: 30 minutes (1800s)

### Chunk Processing
- **Path**: `/api/tasks/process-chunk`
- **Payload**: `{"episode_id": "123", "chunk_id": "chunk-1", ...}`
- **Timeout**: 30 minutes (1800s)

## Log Events

All log events use structured logging with `event=<name>` format.

### Dispatch Events

- `tasks.enqueue_http_task.start` - Task dispatch started
- `tasks.dry_run` - Task logged in dry-run mode (not executed)
- `tasks.enqueue_http_task.using_local_dispatch` - Using local dispatch
- `tasks.enqueue_http_task.using_cloud_tasks` - Using Cloud Tasks

### Cloud Tasks Events

- `tasks.cloud.enabled` - Cloud Tasks enabled (all checks passed)
- `tasks.cloud.disabled` - Cloud Tasks disabled (with reason)
- `tasks.enqueue_http_task.using_worker_url` - Routing to worker URL
- `tasks.enqueue_http_task.using_tasks_url` - Routing to tasks URL
- `tasks.enqueue_http_task.tasks_auth_missing` - TASKS_AUTH not set (warning)
- `tasks.enqueue_http_task.tasks_auth_set` - TASKS_AUTH configured
- `tasks.enqueue_http_task.creating_task` - Creating Cloud Task
- `tasks.cloud.enqueued` - Task successfully enqueued
- `tasks.enqueue_http_task.create_task_failed` - Task creation failed (error)

### Local Dispatch Events

- `tasks.dev.checking_worker_config` - Checking worker configuration
- `tasks.dev.worker_config_valid` - Worker config valid, using worker server
- `tasks.dev.worker_config_invalid` - Worker config invalid, using local dispatch
- `tasks.dev.using_worker_server` - Using worker server for task
- `tasks.dev.worker_success` - Worker server call succeeded
- `tasks.dev.worker_timeout` - Worker server call timed out
- `tasks.dev.worker_error` - Worker server returned error
- `tasks.dev.worker_exception` - Worker server call exception
- `tasks.dev.dispatch` - Local thread dispatch completed

### Error Events

- `tasks.enqueue_http_task.cloud_tasks_unavailable` - Cloud Tasks unavailable
- `tasks.enqueue_http_task.cloud_tasks_client_failed` - CloudTasksClient creation failed
- `tasks.enqueue_http_task.config_missing` - Required configuration missing
- `tasks.enqueue_http_task.queue_path_failed` - Queue path construction failed
- `tasks.enqueue_http_task.base_url_missing` - Base URL missing
- `tasks.enqueue_http_task.http_request_build_failed` - HTTP request build failed
- `tasks.enqueue_http_task.task_build_failed` - Task object build failed
- `tasks.enqueue_http_task.create_task_failed` - Task creation failed

## Error Handling

**No Silent Fallbacks**: All errors raise exceptions with clear error messages. The calling code must handle errors and return appropriate HTTP responses (typically 5xx for server errors).

**Error Types**:
- `ImportError`: google-cloud-tasks not installed
- `ValueError`: Missing or invalid configuration
- `RuntimeError`: Task creation or dispatch failed

## Examples

### Basic Usage

```python
from infrastructure.tasks_client import enqueue_http_task

try:
    task_info = enqueue_http_task("/api/tasks/transcribe", {
        "filename": "gs://bucket/audio.wav",
        "user_id": "123"
    })
    print(f"Task enqueued: {task_info['name']}")
except Exception as e:
    # Handle error - return HTTP 5xx
    raise HTTPException(status_code=500, detail=str(e))
```

### Dry-Run Mode

```python
import os
os.environ["TASKS_DRY_RUN"] = "true"

task_info = enqueue_http_task("/api/tasks/transcribe", {
    "filename": "test.wav"
})
# Returns: {"name": "dry-run-2024-01-01T12:00:00"}
# Task is logged but not executed
```

## Testing

### Guard Test

Run the guard test to ensure no unauthorized imports:

```bash
pytest backend/infrastructure/task_client_guard.py::test_no_unauthorized_task_imports
```

### Smoke Test

Run the smoke test to verify dispatch routing:

```bash
pytest tests/test_tasks_client_smoke.py
```

## Migration Guide

### Replacing Direct HTTP Calls

**Before:**
```python
import httpx
import threading

def _call_worker():
    with httpx.Client(timeout=1800.0) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()

threading.Thread(target=_call_worker).start()
```

**After:**
```python
from infrastructure.tasks_client import enqueue_http_task

task_info = enqueue_http_task("/api/tasks/assemble", payload)
```

### Replacing Cloud Tasks Calls

**Before:**
```python
from google.cloud import tasks_v2

client = tasks_v2.CloudTasksClient()
parent = client.queue_path(project, location, queue)
task = tasks_v2.Task(http_request=http_request)
created = client.create_task(request={"parent": parent, "task": task})
```

**After:**
```python
from infrastructure.tasks_client import enqueue_http_task

task_info = enqueue_http_task("/api/tasks/assemble", payload)
```

## Troubleshooting

### Task Not Executing

1. Check logs for `event=tasks.enqueue_http_task.start`
2. Verify environment variables are set correctly
3. Check for error events: `event=tasks.enqueue_http_task.*_failed`
4. In dev mode, check `event=tasks.dev.*` events

### Cloud Tasks Not Working

1. Verify `GOOGLE_CLOUD_PROJECT`, `TASKS_LOCATION`, `TASKS_QUEUE` are set
2. Check `event=tasks.cloud.disabled` for reason
3. Verify `TASKS_URL_BASE` is set correctly
4. Check Cloud Tasks IAM permissions

### Worker Server Not Used in Dev

1. Set `USE_WORKER_IN_DEV=true`
2. Set `WORKER_URL_BASE=http://localhost:8001` (or your worker URL)
3. Check `event=tasks.dev.worker_config_valid` in logs
4. Verify task path contains `/assemble` or `/process-chunk`

