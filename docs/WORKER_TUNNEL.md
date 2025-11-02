# Worker & Tunnel Quickstart

This short guide explains how to start the office worker and expose it to your dev API using ngrok or Cloudflare Tunnel.

Prerequisites
- Repository checked out on the office machine
- Python venv installed and project dependencies available
- `/root/.env` contains the required variables (see `backend/.env.office.example`)
- ffmpeg installed on the office machine

Start the worker (Ubuntu example)

```bash
cd /path/to/repo/backend
# uses /root/.env by default
../.venv/bin/python -m uvicorn worker_service:app --host 0.0.0.0 --port 8081 --env-file /root/.env
```

Or use the included helper script (from repo root):

```bash
./scripts/start_worker_office.sh
```

Expose the worker

Quick test (ngrok)
1. Install ngrok and authenticate: `ngrok authtoken <your-token>`
2. Start a tunnel: `ngrok http 8081`
3. Use the `https://...ngrok.io` URL as `TASKS_URL_BASE` in your dev API.

Persistent (Cloudflare Tunnel)
1. Install `cloudflared` and authenticate with your Cloudflare account.
2. Create a tunnel and map a DNS name to localhost:8081 per Cloudflare docs.
3. Run: `cloudflared tunnel --url http://localhost:8081` or run the named tunnel service.

Point the API at the worker

On your dev machine (PowerShell example):

```powershell
# $env:TASKS_FORCE_HTTP_LOOPBACK = '1'
# $env:TASKS_URL_BASE = 'https://your-ngrok-or-cloudflared-hostname'
# $env:TASKS_AUTH = 'tsk_THE_SAME_SECRET_AS_OFFICE'
# & .\scripts\dev_start_api.ps1
```

Verify
- `GET https://<worker-host>/health` should return healthy JSON
- `POST https://<worker-host>/api/tasks/assemble` with header `X-Tasks-Auth: tsk_...` should trigger assembly

Security notes
- Use HTTPS. Ngrok/cloudflared provide TLS out of the box.
- Do not expose DB ports publicly.
- Use a long random `TASKS_AUTH` and do not commit it.
