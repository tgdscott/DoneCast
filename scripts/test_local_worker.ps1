# Quick Test Script for Local Worker Setup
# Run this on your server to test the Celery worker

Write-Host "=== Podcast Plus Plus - Local Worker Test ===" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check if .env.worker exists
Write-Host ""
Write-Host "Checking environment file..." -ForegroundColor Yellow
if (Test-Path ".env.worker") {
    Write-Host "✅ .env.worker found" -ForegroundColor Green
} else {
    Write-Host "❌ .env.worker not found. Creating from template..." -ForegroundColor Red
    Copy-Item .env.worker.template .env.worker
    Write-Host "⚠️  Please edit .env.worker with your real values!" -ForegroundColor Yellow
    Write-Host "   Then run this script again." -ForegroundColor Yellow
    notepad .env.worker
    exit 1
}

# Check if gcp-key.json exists
Write-Host ""
Write-Host "Checking GCP key..." -ForegroundColor Yellow
if (Test-Path "gcp-key.json") {
    Write-Host "✅ gcp-key.json found" -ForegroundColor Green
} else {
    Write-Host "❌ gcp-key.json not found" -ForegroundColor Red
    Write-Host "   Please copy your GCP service account key to this directory:" -ForegroundColor Yellow
    Write-Host "   Copy-Item path\to\your\key.json .\gcp-key.json" -ForegroundColor Yellow
    exit 1
}

# Start services
Write-Host ""
Write-Host "Starting RabbitMQ + Celery worker..." -ForegroundColor Yellow
docker-compose -f docker-compose.worker.yml --env-file .env.worker up -d

# Wait for services to start
Write-Host ""
Write-Host "Waiting for services to start (30 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Check service status
Write-Host ""
Write-Host "Checking service status..." -ForegroundColor Yellow
docker-compose -f docker-compose.worker.yml ps

# Test RabbitMQ
Write-Host ""
Write-Host "Testing RabbitMQ connection..." -ForegroundColor Yellow
try {
    docker exec podcast_rabbitmq rabbitmqctl status | Out-Null
    Write-Host "✅ RabbitMQ is running" -ForegroundColor Green
} catch {
    Write-Host "❌ RabbitMQ is not responding" -ForegroundColor Red
}

# Test Celery worker
Write-Host ""
Write-Host "Testing Celery worker..." -ForegroundColor Yellow
try {
    $ping = docker exec podcast_worker celery -A worker.tasks.app inspect ping 2>&1
    if ($ping -match "pong") {
        Write-Host "✅ Celery worker is responding" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Celery worker may not be fully initialized yet" -ForegroundColor Yellow
        Write-Host "   Check logs: docker-compose -f docker-compose.worker.yml logs worker" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Celery worker is not responding" -ForegroundColor Red
    Write-Host "   Check logs: docker-compose -f docker-compose.worker.yml logs worker" -ForegroundColor Yellow
}

# Show next steps
Write-Host ""
Write-Host "=== NEXT STEPS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. View worker logs:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.worker.yml logs -f worker" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Access RabbitMQ dashboard:" -ForegroundColor White
Write-Host "   http://localhost:15672" -ForegroundColor Gray
Write-Host "   Username: podcast" -ForegroundColor Gray
Write-Host "   Password: (from .env.worker)" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Configure Cloud Run to use this worker:" -ForegroundColor White
Write-Host "   Set env var: RABBITMQ_URL=amqp://podcast:PASSWORD@YOUR_IP:5672//" -ForegroundColor Gray
Write-Host "   Set env var: ENABLE_LOCAL_WORKER=true" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Test Slack alerts (optional):" -ForegroundColor White
Write-Host "   docker exec podcast_worker python -c 'from api.services.slack_alerts import test_slack_integration; test_slack_integration()'" -ForegroundColor Gray
Write-Host ""
Write-Host "5. Process a test episode through your web app!" -ForegroundColor White
Write-Host ""
