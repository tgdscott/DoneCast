# Diagnostic Script for Worker Assembly Issues
# This script helps diagnose why episode assembly isn't reaching the worker server

Write-Host "🔍 Worker Assembly Diagnostic Tool" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# Check 1: Verify worker is accessible
Write-Host "1. Testing worker server connectivity..." -ForegroundColor Yellow
$workerUrl = "https://assemble.podcastplusplus.com"
$workerLocalUrl = "http://10.109.0.96:8080"

try {
    $response = Invoke-WebRequest -Uri "$workerUrl/" -Method Get -TimeoutSec 5 -UseBasicParsing
    Write-Host "   ✅ Worker accessible via Cloudflared: $workerUrl" -ForegroundColor Green
    Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
} catch {
    Write-Host "   ❌ Worker NOT accessible via Cloudflared: $workerUrl" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $response = Invoke-WebRequest -Uri "$workerLocalUrl/" -Method Get -TimeoutSec 5 -UseBasicParsing
    Write-Host "   ✅ Worker accessible via local IP: $workerLocalUrl" -ForegroundColor Green
    Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
} catch {
    Write-Host "   ❌ Worker NOT accessible via local IP: $workerLocalUrl" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Check 2: Verify worker health endpoint
Write-Host "2. Testing worker health endpoint..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-WebRequest -Uri "$workerUrl/health" -Method Get -TimeoutSec 5 -UseBasicParsing
    Write-Host "   ✅ Health check passed" -ForegroundColor Green
    Write-Host "   Response: $($healthResponse.Content)" -ForegroundColor Gray
} catch {
    Write-Host "   ❌ Health check failed" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Check 3: Check Cloud Tasks queue status
Write-Host "3. Checking Cloud Tasks queue..." -ForegroundColor Yellow
Write-Host "   Run this command to check queue status:" -ForegroundColor Gray
Write-Host "   gcloud tasks queues describe ppp-queue --location=us-west1 --project=podcast612" -ForegroundColor Cyan
Write-Host ""
Write-Host "   To list tasks in queue:" -ForegroundColor Gray
Write-Host "   gcloud tasks list --queue=ppp-queue --location=us-west1 --project=podcast612" -ForegroundColor Cyan

Write-Host ""

# Check 4: Check Cloud Tasks logs
Write-Host "4. Checking Cloud Tasks execution logs..." -ForegroundColor Yellow
Write-Host "   Run this command to see recent task executions:" -ForegroundColor Gray
Write-Host "   gcloud logging read 'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND resource.labels.location=us-west1' --limit=50 --project=podcast612 --format=json" -ForegroundColor Cyan
Write-Host ""
Write-Host "   To see task attempts and failures:" -ForegroundColor Gray
Write-Host "   gcloud logging read 'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND jsonPayload.status=FAILED' --limit=20 --project=podcast612" -ForegroundColor Cyan

Write-Host ""

# Check 5: Verify TASKS_AUTH secret exists
Write-Host "5. Checking TASKS_AUTH secret..." -ForegroundColor Yellow
Write-Host "   Run this command to verify secret exists:" -ForegroundColor Gray
Write-Host "   gcloud secrets versions access latest --secret=TASKS_AUTH --project=podcast612" -ForegroundColor Cyan
Write-Host ""
Write-Host "   ⚠️  IMPORTANT: The worker service on Proxmox must have the SAME TASKS_AUTH value" -ForegroundColor Yellow
Write-Host "   Set it as an environment variable when running the worker service" -ForegroundColor Gray

Write-Host ""

# Check 6: Test worker endpoint with auth
Write-Host "6. Testing worker assemble endpoint (requires TASKS_AUTH)..." -ForegroundColor Yellow
$tasksAuth = Read-Host "Enter TASKS_AUTH secret (or press Enter to skip)"
if ($tasksAuth) {
    try {
        $testPayload = @{
            episode_id = "test-diagnostic"
            template_id = "test-template"
            main_content_filename = "test.wav"
            user_id = "test-user"
        } | ConvertTo-Json
        
        $headers = @{
            "Content-Type" = "application/json"
            "X-Tasks-Auth" = $tasksAuth
        }
        
        # This will likely fail with validation error, but should return 400 not 401 if auth works
        $testResponse = Invoke-WebRequest -Uri "$workerUrl/api/tasks/assemble" -Method Post -Body $testPayload -Headers $headers -TimeoutSec 10 -UseBasicParsing -ErrorAction SilentlyContinue
        
        if ($testResponse.StatusCode -eq 400) {
            Write-Host "   ✅ Authentication successful (400 = auth passed, validation failed as expected)" -ForegroundColor Green
        } elseif ($testResponse.StatusCode -eq 401) {
            Write-Host "   ❌ Authentication FAILED - TASKS_AUTH mismatch" -ForegroundColor Red
        } else {
            Write-Host "   ⚠️  Unexpected status: $($testResponse.StatusCode)" -ForegroundColor Yellow
        }
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 401) {
            Write-Host "   ❌ Authentication FAILED - TASKS_AUTH mismatch" -ForegroundColor Red
        } elseif ($_.Exception.Response.StatusCode.value__ -eq 400) {
            Write-Host "   ✅ Authentication successful (400 = auth passed, validation failed as expected)" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "   ⏭️  Skipped (no TASKS_AUTH provided)" -ForegroundColor Gray
}

Write-Host ""

# Check 7: Check API service logs for assembly attempts
Write-Host "7. Checking API service logs for assembly attempts..." -ForegroundColor Yellow
Write-Host "   Run this command to see recent assembly attempts:" -ForegroundColor Gray
Write-Host "   gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~\"assemble\"' --limit=50 --project=podcast612" -ForegroundColor Cyan
Write-Host ""
Write-Host "   To see Cloud Tasks enqueue events:" -ForegroundColor Gray
Write-Host "   gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~\"tasks.cloud.enqueued\"' --limit=20 --project=podcast612" -ForegroundColor Cyan

Write-Host ""

# Check 8: Verify worker service configuration
Write-Host "8. Worker Service Configuration Checklist:" -ForegroundColor Yellow
Write-Host "   ☐ Worker service is running on Proxmox (port 8080)" -ForegroundColor Gray
Write-Host "   ☐ Cloudflared tunnel is running and routing assemble.podcastplusplus.com → localhost:8080" -ForegroundColor Gray
Write-Host "   ☐ TASKS_AUTH environment variable is set in worker service" -ForegroundColor Gray
Write-Host "   ☐ TASKS_AUTH value matches the secret in Google Cloud Secret Manager" -ForegroundColor Gray
Write-Host "   ☐ Worker service has APP_ENV=production set (or TASKS_AUTH check is enabled)" -ForegroundColor Gray
Write-Host "   ☐ Worker service can access database (Cloud SQL)" -ForegroundColor Gray
Write-Host "   ☐ Worker service has access to R2 storage credentials" -ForegroundColor Gray

Write-Host ""
Write-Host "✅ Diagnostic complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Verify TASKS_AUTH is configured in both API and worker services" -ForegroundColor White
Write-Host "2. Check Cloud Tasks queue for stuck/failed tasks" -ForegroundColor White
Write-Host "3. Review Cloud Tasks execution logs for HTTP errors" -ForegroundColor White
Write-Host "4. Verify worker service logs on Proxmox for incoming requests" -ForegroundColor White

