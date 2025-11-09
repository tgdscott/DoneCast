# Task Dispatch Refactor Summary

## Overview

This refactor centralizes all task dispatch through `backend/infrastructure/tasks_client.py`. All task dispatch now goes through `enqueue_http_task()`, ensuring consistent routing, logging, and error handling.

## Changes Made

### 1. Created Guard Test (`backend/infrastructure/task_client_guard.py`)

- **Purpose**: Ensures no unauthorized imports of task dispatch libraries
- **What it checks**:
  - Strictly forbids `google.cloud.tasks` imports (except in `tasks_client.py`)
  - Contextually flags `httpx`, `requests`, `multiprocessing` in task-related directories:
    - `api/services/episodes`
    - `api/routers`
    - `worker/tasks`
- **Status**: Wired into test suite, can be run with `pytest backend/infrastructure/task_client_guard.py`

### 2. Added TASKS_DRY_RUN Flag (`backend/infrastructure/tasks_client.py`)

- **Feature**: When `TASKS_DRY_RUN=true`, tasks are logged but not executed
- **Behavior**:
  - Logs `event=tasks.dry_run` with path and task ID
  - Returns fake task ID: `dry-run-<iso-timestamp>`
  - No actual task execution
- **Usage**: Set `TASKS_DRY_RUN=true` in environment variables

### 3. Enhanced Error Handling (`backend/infrastructure/tasks_client.py`)

- **No Silent Fallbacks**: All errors now raise exceptions with clear messages
- **Error Types**:
  - `ImportError`: google-cloud-tasks not installed
  - `ValueError`: Missing or invalid configuration
  - `RuntimeError`: Task creation or dispatch failed
- **Structured Logging**: All errors include `event=tasks.enqueue_http_task.*_failed` with clear context

### 4. Refactored `assembler.py` (`backend/api/services/episodes/assembler.py`)

- **Removed**: Direct `httpx` imports and HTTP calls for task dispatch
- **Replaced**: All task dispatch now uses `enqueue_http_task()`
- **Simplified**: Removed redundant worker routing logic (now handled by `tasks_client`)
- **Error Handling**: Raises `RuntimeError` on dispatch failure (no silent fallbacks)

### 5. Deleted Legacy Code (`backend/api/tasks/queue.py`)

- **Removed**: Unused `enqueue_task()` function that directly used Cloud Tasks API
- **Reason**: All dispatch now goes through `tasks_client.enqueue_http_task()`

### 6. Created Smoke Test (`tests/test_tasks_client_smoke.py`)

- **Tests**:
  - Dry-run mode functionality
  - Task dispatch routing through `tasks_client`
  - Error handling (no silent fallbacks)
- **Assertions**: Verifies expected log events are produced

### 7. Created Documentation (`backend/infrastructure/TASK_DISPATCH.md`)

- **Contents**:
  - Architecture overview
  - Environment variables
  - Task endpoints
  - Log events reference
  - Error handling guide
  - Migration guide
  - Troubleshooting

## Removed Call Sites

### Direct httpx/requests Calls Removed

1. **`backend/api/services/episodes/assembler.py`** (Lines 695-747, 853-909)
   - **Before**: Direct `httpx.Client()` calls to worker server
   - **After**: Uses `enqueue_http_task("/api/tasks/assemble", payload)`
   - **Impact**: Simplified code, consistent routing

### Direct Cloud Tasks Calls Removed

1. **`backend/api/tasks/queue.py`** (Entire file)
   - **Before**: Direct `CloudTasksClient()` usage
   - **After**: File deleted (unused)
   - **Impact**: Single dispatch path

## Log Events Added

### New Events

- `tasks.dry_run` - Task logged in dry-run mode
- `tasks.enqueue_http_task.cloud_tasks_unavailable` - Cloud Tasks unavailable
- `tasks.enqueue_http_task.cloud_tasks_client_failed` - Client creation failed
- `tasks.enqueue_http_task.config_missing` - Configuration missing
- `tasks.enqueue_http_task.queue_path_failed` - Queue path construction failed
- `tasks.enqueue_http_task.base_url_missing` - Base URL missing
- `tasks.enqueue_http_task.http_request_build_failed` - HTTP request build failed
- `tasks.enqueue_http_task.task_build_failed` - Task object build failed

## Files Modified

1. `backend/infrastructure/tasks_client.py`
   - Added `TASKS_DRY_RUN` support
   - Enhanced error handling (no silent fallbacks)
   - Improved structured logging

2. `backend/api/services/episodes/assembler.py`
   - Removed direct `httpx` imports
   - Replaced direct HTTP calls with `enqueue_http_task()`
   - Simplified routing logic

## Files Created

1. `backend/infrastructure/task_client_guard.py` - Guard test
2. `tests/test_tasks_client_smoke.py` - Smoke test
3. `backend/infrastructure/TASK_DISPATCH.md` - Documentation

## Files Deleted

1. `backend/api/tasks/queue.py` - Legacy dispatch code

## Testing

### Run Guard Test

```bash
pytest backend/infrastructure/task_client_guard.py::test_no_unauthorized_task_imports
```

### Run Smoke Test

```bash
pytest tests/test_tasks_client_smoke.py
```

### Test Dry-Run Mode

```bash
TASKS_DRY_RUN=true python -c "from infrastructure.tasks_client import enqueue_http_task; print(enqueue_http_task('/api/tasks/transcribe', {'filename': 'test.wav'}))"
```

## Migration Notes

### For Developers

1. **Always use `enqueue_http_task()`** for task dispatch
2. **Never import** `httpx`, `requests`, or `google.cloud.tasks` for task dispatch
3. **Handle errors** - `enqueue_http_task()` raises exceptions (no silent fallbacks)
4. **Check logs** - All dispatch events are logged with `event=tasks.*`

### Breaking Changes

- **None** - All changes are backward compatible
- **Error behavior** - Errors now raise instead of silently falling back (this is intentional)

## Next Steps

1. Run guard test in CI to prevent regressions
2. Monitor logs for `event=tasks.*` events
3. Update any remaining call sites (if found by guard test)
4. Consider deprecating `task_dispatcher.py` (Celery-based, separate system)

## Verification

To verify the refactor is complete:

1. Run guard test: `pytest backend/infrastructure/task_client_guard.py`
2. Run smoke test: `pytest tests/test_tasks_client_smoke.py`
3. Check logs for `event=tasks.enqueue_http_task.start` when dispatching tasks
4. Verify no direct `httpx`/`requests`/`google.cloud.tasks` imports in task-related code

## Questions?

See `backend/infrastructure/TASK_DISPATCH.md` for detailed documentation.

