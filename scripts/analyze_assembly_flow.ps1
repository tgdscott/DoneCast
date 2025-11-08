# Analyze Assembly Flow - Step by Step Diagnosis
# This script checks each step of the assembly flow to find where it's breaking

param(
    [string]$EpisodeId = "",
    [int]$Hours = 1
)

$project = "podcast612"
$service = "podcast-api"
$region = "us-west1"
$queue = "ppp-queue"

# Calculate time filter
$timeFilter = ""
if ($Hours -gt 0) {
    $timeAgo = (Get-Date).AddHours(-$Hours).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $timeFilter = " AND timestamp>='$timeAgo'"
}

# Episode filter
$episodeFilter = ""
if ($EpisodeId) {
    $episodeFilter = " AND textPayload=~'$EpisodeId'"
}

Write-Host "🔍 Assembly Flow Analysis" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Analyzing last $Hours hour(s) of logs..." -ForegroundColor Yellow
if ($EpisodeId) {
    Write-Host "Filtering for episode: $EpisodeId" -ForegroundColor Yellow
}
Write-Host ""

# Step 1: Check if assembly is being triggered
Write-Host "STEP 1: Is assembly being triggered?" -ForegroundColor Green
Write-Host "-------------------------------------" -ForegroundColor Green
$triggerQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND textPayload=~'assemble_or_queue'$timeFilter$episodeFilter"
$triggerLogs = gcloud logging read $triggerQuery --limit=10 --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($triggerLogs) {
    Write-Host "✅ Found assembly trigger events" -ForegroundColor Green
    $triggerLogs | ForEach-Object {
        $timestamp = $_.timestamp
        $payload = $_.textPayload
        Write-Host "   [$timestamp] $payload" -ForegroundColor Gray
    }
} else {
    Write-Host "❌ No assembly trigger events found" -ForegroundColor Red
    Write-Host "   This means assembly might not be getting called at all" -ForegroundColor Yellow
}
Write-Host ""

# Step 2: Check if Cloud Tasks is enabled
Write-Host "STEP 2: Is Cloud Tasks enabled?" -ForegroundColor Green
Write-Host "-------------------------------" -ForegroundColor Green
$enabledQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND textPayload=~'should_use_cloud_tasks'$timeFilter$episodeFilter"
$enabledLogs = gcloud logging read $enabledQuery --limit=10 --project=$project --format=json 2>&1 | ConvertFrom-Json
$disabledQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND (textPayload=~'tasks.cloud.disabled' OR textPayload=~'Cloud Tasks.*unavailable')$timeFilter$episodeFilter"
$disabledLogs = gcloud logging read $disabledQuery --limit=10 --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($disabledLogs) {
    Write-Host "⚠️  Cloud Tasks appears to be DISABLED" -ForegroundColor Red
    $disabledLogs | ForEach-Object {
        $timestamp = $_.timestamp
        $payload = $_.textPayload
        Write-Host "   [$timestamp] $payload" -ForegroundColor Gray
    }
} else {
    Write-Host "✅ No Cloud Tasks disabled messages found" -ForegroundColor Green
}
Write-Host ""

# Step 3: Check if tasks are being enqueued
Write-Host "STEP 3: Are tasks being enqueued to Cloud Tasks?" -ForegroundColor Green
Write-Host "-------------------------------------------------" -ForegroundColor Green
$enqueueQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND textPayload=~'tasks.cloud.enqueued'$timeFilter$episodeFilter"
$enqueueLogs = gcloud logging read $enqueueQuery --limit=20 --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($enqueueLogs) {
    Write-Host "✅ Found task enqueue events" -ForegroundColor Green
    $enqueueLogs | ForEach-Object {
        $timestamp = $_.timestamp
        $payload = $_.textPayload
        Write-Host "   [$timestamp] $payload" -ForegroundColor Gray
        # Extract URL from log
        if ($payload -match 'url=([^\s]+)') {
            $url = $matches[1]
            Write-Host "      → URL: $url" -ForegroundColor Cyan
        }
        if ($payload -match 'task_name=([^\s]+)') {
            $taskName = $matches[1]
            Write-Host "      → Task: $taskName" -ForegroundColor Cyan
        }
    }
} else {
    Write-Host "❌ No task enqueue events found" -ForegroundColor Red
    Write-Host "   This means tasks are NOT being sent to Cloud Tasks" -ForegroundColor Yellow
    Write-Host "   Possible causes:" -ForegroundColor Yellow
    Write-Host "   - Cloud Tasks is disabled (check STEP 2)" -ForegroundColor Yellow
    Write-Host "   - enqueue_http_task() is throwing an exception" -ForegroundColor Yellow
    Write-Host "   - should_use_cloud_tasks() is returning False" -ForegroundColor Yellow
}
Write-Host ""

# Step 4: Check for enqueue errors
Write-Host "STEP 4: Are there errors when enqueueing?" -ForegroundColor Green
Write-Host "------------------------------------------" -ForegroundColor Green
$enqueueErrorQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND (textPayload=~'Cloud Tasks dispatch failed' OR textPayload=~'enqueue.*error' OR textPayload=~'enqueue.*exception')$timeFilter$episodeFilter"
$enqueueErrors = gcloud logging read $enqueueErrorQuery --limit=20 --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($enqueueErrors) {
    Write-Host "❌ Found enqueue errors!" -ForegroundColor Red
    $enqueueErrors | ForEach-Object {
        $timestamp = $_.timestamp
        $payload = $_.textPayload
        Write-Host "   [$timestamp] $payload" -ForegroundColor Red
    }
} else {
    Write-Host "✅ No enqueue errors found" -ForegroundColor Green
}
Write-Host ""

# Step 5: Check Cloud Tasks queue for actual tasks
Write-Host "STEP 5: What's in the Cloud Tasks queue?" -ForegroundColor Green
Write-Host "----------------------------------------" -ForegroundColor Green
Write-Host "Checking queue directly..." -ForegroundColor Yellow
$queueTasks = gcloud tasks list --queue=$queue --location=$region --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($queueTasks) {
    Write-Host "✅ Found $($queueTasks.Count) task(s) in queue" -ForegroundColor Green
    $queueTasks | ForEach-Object {
        $name = $_.name
        $createTime = $_.createTime
        $scheduleTime = $_.scheduleTime
        Write-Host "   Task: $name" -ForegroundColor Gray
        Write-Host "   Created: $createTime" -ForegroundColor Gray
        Write-Host "   Scheduled: $scheduleTime" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠️  No tasks in queue (or queue is empty)" -ForegroundColor Yellow
    Write-Host "   This could mean:" -ForegroundColor Yellow
    Write-Host "   - Tasks were already processed" -ForegroundColor Yellow
    Write-Host "   - Tasks were never enqueued (check STEP 3)" -ForegroundColor Yellow
    Write-Host "   - Tasks failed and were removed" -ForegroundColor Yellow
}
Write-Host ""

# Step 6: Check Cloud Tasks execution logs
Write-Host "STEP 6: What do Cloud Tasks execution logs show?" -ForegroundColor Green
Write-Host "------------------------------------------------" -ForegroundColor Green
$execQuery = "resource.type=cloud_tasks_queue AND resource.labels.queue_id=$queue AND resource.labels.location=$region$timeFilter"
$execLogs = gcloud logging read $execQuery --limit=20 --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($execLogs) {
    Write-Host "✅ Found Cloud Tasks execution logs" -ForegroundColor Green
    $execLogs | ForEach-Object {
        $timestamp = $_.timestamp
        $jsonPayload = $_.jsonPayload
        $textPayload = $_.textPayload
        
        if ($jsonPayload) {
            $status = $jsonPayload.status
            $responseCode = $jsonPayload.httpResponseCode
            $url = $jsonPayload.request?.url
            Write-Host "   [$timestamp] Status: $status, Response: $responseCode" -ForegroundColor Gray
            if ($url) {
                Write-Host "      URL: $url" -ForegroundColor Cyan
            }
            if ($status -eq "FAILED" -or $responseCode -ge 400) {
                Write-Host "      ❌ FAILED" -ForegroundColor Red
                if ($jsonPayload.responseBody) {
                    Write-Host "      Response: $($jsonPayload.responseBody)" -ForegroundColor Red
                }
            }
        } elseif ($textPayload) {
            Write-Host "   [$timestamp] $textPayload" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "⚠️  No Cloud Tasks execution logs found" -ForegroundColor Yellow
    Write-Host "   This means tasks might not be executing" -ForegroundColor Yellow
}
Write-Host ""

# Step 7: Check for fallback to inline execution
Write-Host "STEP 7: Is it falling back to inline execution?" -ForegroundColor Green
Write-Host "------------------------------------------------" -ForegroundColor Green
$fallbackQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND textPayload=~'falling back to inline'$timeFilter$episodeFilter"
$fallbackLogs = gcloud logging read $fallbackQuery --limit=20 --project=$project --format=json 2>&1 | ConvertFrom-Json
if ($fallbackLogs) {
    Write-Host "⚠️  Found fallback to inline execution!" -ForegroundColor Yellow
    $fallbackLogs | ForEach-Object {
        $timestamp = $_.timestamp
        $payload = $_.textPayload
        Write-Host "   [$timestamp] $payload" -ForegroundColor Yellow
    }
    Write-Host "   This means Cloud Tasks failed, so assembly ran inline (on API service)" -ForegroundColor Yellow
} else {
    Write-Host "✅ No fallback messages found" -ForegroundColor Green
}
Write-Host ""

# Step 8: Check worker service logs (if accessible)
Write-Host "STEP 8: Summary and Next Steps" -ForegroundColor Green
Write-Host "------------------------------" -ForegroundColor Green
Write-Host ""
Write-Host "Based on the analysis above:" -ForegroundColor Cyan
Write-Host ""
Write-Host "If STEP 3 shows NO enqueue events:" -ForegroundColor Yellow
Write-Host "  → Check API service environment variables:" -ForegroundColor White
Write-Host "     gcloud run services describe $service --region=$region --project=$project --format='value(spec.template.spec.containers[0].env)'" -ForegroundColor Gray
Write-Host "  → Verify WORKER_URL_BASE is set to: https://assemble.podcastplusplus.com" -ForegroundColor White
Write-Host "  → Verify TASKS_AUTH secret is configured" -ForegroundColor White
Write-Host ""
Write-Host "If STEP 3 shows enqueue events but STEP 6 shows failures:" -ForegroundColor Yellow
Write-Host "  → Check the HTTP response codes in Cloud Tasks logs" -ForegroundColor White
Write-Host "  → Verify worker service is accessible from Google Cloud" -ForegroundColor White
Write-Host "  → Check worker service logs on Proxmox for incoming requests" -ForegroundColor White
Write-Host ""
Write-Host "If STEP 7 shows fallback to inline:" -ForegroundColor Yellow
Write-Host "  → Assembly is running on API service instead of worker" -ForegroundColor White
Write-Host "  → Check why Cloud Tasks failed (see STEP 4 and STEP 6)" -ForegroundColor White
Write-Host ""
Write-Host "To check worker service logs on Proxmox:" -ForegroundColor Cyan
Write-Host "  docker-compose -f docker-compose.worker.yml logs -f worker" -ForegroundColor Gray
Write-Host "  # Look for: event=worker.assemble.start" -ForegroundColor Gray
Write-Host ""

Write-Host "✅ Analysis complete!" -ForegroundColor Green

