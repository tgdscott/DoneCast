# Dev Server - Using Proxmox Worker for Testing

## Overview

This configuration allows the dev server to send assembly tasks directly to the Proxmox worker server instead of running them locally. This is useful for testing the worker server without deploying to production.

## Setup

### 1. Add Environment Variables to Your Dev Environment

Add these to your `.env.local` or `.env` file in the `backend/` directory:

```bash
# Enable using worker server in dev mode
USE_WORKER_IN_DEV=true

# Worker server URL (your Proxmox server via Cloudflared)
WORKER_URL_BASE=https://assemble.podcastplusplus.com

# TASKS_AUTH must match the value on the worker server
TASKS_AUTH=<your-tasks-auth-secret>
```

### 2. Get TASKS_AUTH Value

Get the TASKS_AUTH value from Secret Manager:

```bash
gcloud secrets versions access latest --secret=TASKS_AUTH --project=podcast612
```

Or if you know it's the same as on the worker server, use that value.

### 3. Verify Worker Server is Accessible

Test that you can reach the worker server from your dev machine:

```bash
curl https://assemble.podcastplusplus.com/health
```

Should return: `{"status":"healthy","service":"worker"}`

### 4. Start Your Dev Server

Start your dev server as usual. Assembly tasks will now be sent to the worker server instead of running locally.

## How It Works

1. When `USE_WORKER_IN_DEV=true` is set, the dev server checks if `WORKER_URL_BASE` is configured
2. For assembly (`/api/tasks/assemble`) and chunk processing (`/api/tasks/process-chunk`) tasks, it makes a direct HTTP POST to the worker server
3. The request includes the `X-Tasks-Auth` header for authentication
4. The task runs on the worker server, and logs appear in the worker server logs

## Logging

You'll see these messages in your dev server console:

```
DEV MODE: Sending /api/tasks/assemble to worker server at https://assemble.podcastplusplus.com/api/tasks/assemble
DEV MODE: POST https://assemble.podcastplusplus.com/api/tasks/assemble with timeout 1800.0s
DEV MODE: Worker server responded with status 200
```

## Monitoring

### Dev Server Logs
Watch your dev server console for:
- `DEV MODE: Sending ... to worker server`
- `DEV MODE: Worker server responded with status ...`
- Any error messages if the worker call fails

### Worker Server Logs
On your Proxmox server, watch the worker logs:

```bash
docker-compose -f docker-compose.worker.yml logs -f worker
```

Or if running directly:
```bash
# Check application logs
tail -f /path/to/worker/logs
```

Look for:
- `event=worker.assemble.start` - Assembly started
- `event=worker.assemble.done` - Assembly completed
- `event=worker.assemble.error` - Assembly failed

## Troubleshooting

### Worker Server Not Responding

**Symptom**: Timeout or connection error

**Check**:
1. Worker server is running: `curl https://assemble.podcastplusplus.com/health`
2. Cloudflared tunnel is running on Proxmox
3. Worker service is listening on port 8080

### Authentication Failed

**Symptom**: `401 Unauthorized` error

**Check**:
1. `TASKS_AUTH` value matches between dev server and worker server
2. Worker server has `APP_ENV=production` set (so it requires auth)
3. Worker server has `TASKS_AUTH` environment variable set

### Wrong URL

**Symptom**: `404 Not Found` error

**Check**:
1. `WORKER_URL_BASE` is set correctly: `https://assemble.podcastplusplus.com`
2. No trailing slash in `WORKER_URL_BASE`
3. Worker server has the endpoint at `/api/tasks/assemble`

## Disabling

To disable and go back to local execution, either:

1. Remove `USE_WORKER_IN_DEV` from your `.env` file, or
2. Set `USE_WORKER_IN_DEV=false`

## Notes

- This only affects assembly and chunk processing tasks
- Transcription tasks still run locally in dev mode
- The HTTP call is made in a background thread to avoid blocking
- Timeout is set to 30 minutes (1800s) for assembly tasks
- This bypasses Cloud Tasks entirely - it's a direct HTTP call

