# Local Server Celery Worker Setup Guide
# Hybrid Architecture: Cloud Run API + Local Processing

## Prerequisites
1. Windows Server with Docker Desktop installed
2. GCP service account key (gcp-key.json)
3. Network access to Cloud SQL database
4. 16GB+ RAM (you have this!)
5. ~100GB disk space for temp audio processing

## Quick Start (15 minutes)

### 1. Copy Repository to Server
```powershell
# On your server, clone the repo
git clone https://github.com/tgdscott/CloudPod.git
cd CloudPod
```

### 2. Set Up Environment Variables
```powershell
# Copy template and edit with your real values
Copy-Item .env.worker.template .env.worker
notepad .env.worker
```

**Required values (get from Google Cloud):**
- `DATABASE_URL` - Your Cloud SQL connection string
- `GCS_BUCKET` - Your GCS bucket name
- `R2_*` - Your R2 credentials
- `ASSEMBLYAI_API_KEY` - From AssemblyAI dashboard
- `AUPHONIC_API_TOKEN` - From Auphonic settings (Pro tier only)
- `GEMINI_API_KEY` - From Google AI Studio

### 3. Add GCP Service Account Key
```powershell
# Copy your GCP key to the project root
# This allows the worker to access GCS and Cloud SQL
Copy-Item path\to\your\gcp-key.json .\gcp-key.json
```

### 4. Start the Worker
```powershell
# Start RabbitMQ + Celery worker
docker-compose -f docker-compose.worker.yml --env-file .env.worker up -d

# Check status
docker-compose -f docker-compose.worker.yml ps

# View logs
docker-compose -f docker-compose.worker.yml logs -f worker
```

### 5. Configure Cloud Run API to Use Your Worker

**Option A: Public IP (Simple but less secure)**
- Get your server's public IP
- Open port 5672 on firewall
- Update Cloud Run env var: `RABBITMQ_URL=amqp://podcast:PASSWORD@YOUR_IP:5672//`

**Option B: Cloudflare Tunnel (Recommended - secure, no port forwarding)**
```powershell
# Install Cloudflare Tunnel
winget install Cloudflare.cloudflared

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create podcast-worker

# Configure tunnel (creates config file)
notepad C:\Users\YourUser\.cloudflared\config.yml
```

**Cloudflare config.yml:**
```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: C:\Users\YourUser\.cloudflared\YOUR_TUNNEL_ID.json

ingress:
  - hostname: podcast-worker.your-domain.com
    service: localhost:5672
  - service: http_status:404
```

```powershell
# Route DNS
cloudflared tunnel route dns podcast-worker podcast-worker.your-domain.com

# Start tunnel as service
cloudflared service install
```

**Then update Cloud Run:**
```bash
RABBITMQ_URL=amqp://podcast:PASSWORD@podcast-worker.your-domain.com:5672//
```

## Testing the Setup

### Test 1: Worker Health Check
```powershell
docker exec podcast_worker celery -A worker.tasks.app inspect ping
# Should return: {"celery@HOSTNAME": {"ok": "pong"}}
```

### Test 2: Queue a Test Task
```powershell
docker exec podcast_worker python -c "
from worker.tasks.app import celery_app
result = celery_app.send_task('maintenance.purge_expired_uploads')
print(f'Task queued: {result.id}')
"
```

### Test 3: Process a Real Episode
- Upload audio via your web app
- Check worker logs: `docker-compose -f docker-compose.worker.yml logs -f worker`
- Should see transcription → assembly → publish tasks

## Monitoring & Alerts

### View RabbitMQ Dashboard
```
http://YOUR_SERVER_IP:15672
Username: podcast
Password: (from .env.worker)
```

### Slack Alerts (TODO - we'll add this next)
- Alert on worker crash
- Alert on RabbitMQ unreachable
- Alert on processing failures

## Fallback to Cloud Run

**If your server goes down:**
1. Cloud Run API will timeout trying to connect to RabbitMQ
2. API automatically falls back to inline processing (current behavior)
3. Episodes still process (slower, memory constrained, but works)

**To implement auto-fallback:**
- Modify `backend/api/services/task_dispatcher.py` (we'll create this)
- Try to connect to your RabbitMQ with 2-second timeout
- If fails → run task inline on Cloud Run
- If succeeds → queue to your worker

## Troubleshooting

### Worker won't start
```powershell
# Check logs
docker-compose -f docker-compose.worker.yml logs worker

# Common issues:
# - DATABASE_URL incorrect (can't connect to Cloud SQL)
# - gcp-key.json missing or wrong permissions
# - RabbitMQ not healthy yet (wait 30 seconds and retry)
```

### Can't connect to Cloud SQL
```powershell
# Option 1: Cloud SQL Proxy (recommended)
docker run -d \
  -v C:\path\to\gcp-key.json:/config \
  -p 5432:5432 \
  gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest \
  --credentials-file=/config \
  PROJECT:REGION:INSTANCE

# Then use DATABASE_URL=postgresql://user:pass@host.docker.internal:5432/db
```

### RabbitMQ fills up with tasks
```powershell
# Check queue size
docker exec podcast_rabbitmq rabbitmqctl list_queues

# Purge queue if needed (emergency only)
docker exec podcast_rabbitmq rabbitmqctl purge_queue celery
```

## Performance Tuning

### Increase Worker Concurrency (if you have CPU cores)
```yaml
# In docker-compose.worker.yml, change:
command: celery -A worker.tasks.app worker --loglevel=info --concurrency=4
```

### Memory Limits (optional safety)
```yaml
services:
  worker:
    deploy:
      resources:
        limits:
          memory: 12G  # Leave 4GB for OS
```

## Next Steps

1. **Run the diagnostic script** to confirm server specs
2. **Set up the worker** following steps above
3. **Test with one episode** end-to-end
4. **Implement Slack alerts** for downtime monitoring
5. **Add auto-fallback logic** to Cloud Run API
6. **Monitor for a week** to ensure stability
7. **If stable:** Remove chunking from assembly code (huge simplification!)

## Questions for Scott

Before proceeding:
1. Do you have Docker Desktop on the server already?
2. Do you have the GCP service account key file?
3. What's the server's hostname/IP for Cloudflare Tunnel setup?
4. Do you want me to create the Slack alert integration now?
