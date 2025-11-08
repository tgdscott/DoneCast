# Assembly Logging Added

## Summary

Added comprehensive INFO-level logging throughout the assembly flow to diagnose why assembly requests aren't appearing in logs.

## Logging Added

### 1. API Endpoint (`backend/api/routers/episodes/assemble.py`)
- ✅ `event=assemble.endpoint.start` - When endpoint is called
- ✅ `event=assemble.endpoint.validation_failed` - If validation fails
- ✅ `event=assemble.endpoint.calling_service` - Before calling service
- ✅ `event=assemble.endpoint.service_complete` - After service returns
- ✅ `event=assemble.endpoint.service_error` - If service throws exception
- ✅ `event=assemble.endpoint.returning_eager_inline` - Returning inline result
- ✅ `event=assemble.endpoint.returning_queued` - Returning queued result

### 2. Assembler Service (`backend/api/services/episodes/assembler.py`)
- ✅ `event=assemble.service.checking_cloud_tasks` - Checking if Cloud Tasks should be used
- ✅ `event=assemble.service.cloud_tasks_check` - Result of Cloud Tasks check
- ✅ `event=assemble.service.cloud_tasks_import_failed` - If import fails
- ✅ `event=assemble.service.enqueueing_task` - Before enqueueing task
- ✅ `event=assemble.service.calling_enqueue_http_task` - Before calling enqueue function
- ✅ `event=assemble.service.task_enqueued` - After task is enqueued
- ✅ `event=assemble.service.metadata_saved` - After metadata is saved
- ✅ `event=assemble.service.metadata_save_failed` - If metadata save fails
- ✅ `event=assemble.service.cloud_task_success` - Cloud Tasks succeeded
- ✅ `event=assemble.service.cloud_tasks_dispatch_failed` - If dispatch fails
- ✅ `event=assemble.service.cloud_tasks_unavailable` - Falling back to inline
- ✅ `event=assemble.service.inline_fallback_success` - Inline fallback succeeded
- ✅ `event=assemble.service.inline_fallback_failed` - Inline fallback failed

### 3. Tasks Client (`backend/infrastructure/tasks_client.py`)
- ✅ `event=tasks.cloud.disabled` - Cloud Tasks disabled (with reason)
- ✅ `event=tasks.cloud.enabled` - Cloud Tasks enabled
- ✅ `event=tasks.enqueue_http_task.start` - Starting enqueue
- ✅ `event=tasks.enqueue_http_task.using_local_dispatch` - Using local dispatch
- ✅ `event=tasks.enqueue_http_task.using_cloud_tasks` - Using Cloud Tasks
- ✅ `event=tasks.enqueue_http_task.using_worker_url` - Using worker URL
- ✅ `event=tasks.enqueue_http_task.using_tasks_url` - Using tasks URL
- ✅ `event=tasks.enqueue_http_task.tasks_auth_missing` - TASKS_AUTH missing
- ✅ `event=tasks.enqueue_http_task.tasks_auth_set` - TASKS_AUTH is set
- ✅ `event=tasks.enqueue_http_task.creating_task` - Creating Cloud Task
- ✅ `event=tasks.cloud.enqueued` - Task successfully enqueued
- ✅ `event=tasks.enqueue_http_task.create_task_failed` - Task creation failed

## How to Check Logs

### Check if endpoint is being called:
```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"assemble.endpoint.start"' \
  --limit=20 --project=podcast612
```

### Check Cloud Tasks configuration:
```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND (textPayload=~"tasks.cloud.disabled" OR textPayload=~"tasks.cloud.enabled")' \
  --limit=20 --project=podcast612
```

### Check if tasks are being enqueued:
```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"tasks.cloud.enqueued"' \
  --limit=20 --project=podcast612
```

### Check for errors:
```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND (textPayload=~"assemble.*error" OR textPayload=~"assemble.*failed")' \
  --limit=20 --project=podcast612
```

### Full assembly flow (last hour):
```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND (textPayload=~"assemble" OR textPayload=~"tasks.enqueue") AND timestamp>="'$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)'"' \
  --limit=50 --project=podcast612 --format=json
```

## What to Look For

1. **If you see `assemble.endpoint.start`**: The endpoint is being called - check subsequent logs
2. **If you DON'T see `assemble.endpoint.start`**: The request isn't reaching the endpoint (routing issue, auth failure, etc.)
3. **If you see `tasks.cloud.disabled`**: Check the reason (dev_env, missing_config, etc.)
4. **If you see `tasks.enqueue_http_task.using_local_dispatch`**: Cloud Tasks is disabled, using local fallback
5. **If you see `tasks.enqueue_http_task.tasks_auth_missing`**: TASKS_AUTH is not set (even though we added it)
6. **If you see `tasks.cloud.enqueued`**: Task was successfully enqueued - check Cloud Tasks execution logs
7. **If you see `assemble.service.cloud_tasks_dispatch_failed`**: Check the error message

## Next Steps

1. **Redeploy** with these logging changes
2. **Try assembling an episode**
3. **Check the logs** using the commands above
4. **Share the log output** to identify where it's failing

The logs will now show exactly where in the flow the request is getting stuck or failing.

