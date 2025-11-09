# Check Transcript Cross-Environment Configuration
# This script verifies that transcripts can be found across environments

param(
    [string]$ProjectId = "podcast612",
    [string]$TranscriptsBucket = "ppp-transcripts-us-west1"
)

Write-Host "=== Transcript Cross-Environment Check ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Step 1: Checking transcript bucket configuration..." -ForegroundColor Yellow

# Check if bucket exists
$bucketExists = $false
try {
    gsutil ls "gs://$TranscriptsBucket" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $bucketExists = $true
        Write-Host "  ✅ Bucket exists: $TranscriptsBucket" -ForegroundColor Green
    }
} catch {
    Write-Host "  ❌ Bucket does not exist or is not accessible: $TranscriptsBucket" -ForegroundColor Red
}

Write-Host ""

Write-Host "Step 2: Checking bucket permissions..." -ForegroundColor Yellow

if ($bucketExists) {
    # Check if bucket is publicly readable (for transcripts)
    $policy = gsutil iam get "gs://$TranscriptsBucket" 2>$null
    if ($policy) {
        Write-Host "  ✅ Bucket permissions retrieved" -ForegroundColor Green
        # Note: Transcripts bucket should be readable by service accounts
    } else {
        Write-Host "  ⚠️  Could not retrieve bucket permissions" -ForegroundColor Yellow
    }
}

Write-Host ""

Write-Host "Step 3: Checking Cloud Run configuration..." -ForegroundColor Yellow

# Check API service
$apiConfig = gcloud run services describe podcast-api --region=us-west1 --project=$ProjectId --format=json 2>$null | ConvertFrom-Json
if ($apiConfig) {
    $envVars = $apiConfig.spec.template.spec.containers[0].env
    $hasTranscriptsBucket = $false
    foreach ($env in $envVars) {
        if ($env.name -eq "TRANSCRIPTS_BUCKET") {
            $hasTranscriptsBucket = $true
            $bucketValue = $env.value
            Write-Host "  ✅ API service has TRANSCRIPTS_BUCKET set: $bucketValue" -ForegroundColor Green
            if ($bucketValue -ne $TranscriptsBucket) {
                Write-Host "    ⚠️  Warning: API uses different bucket ($bucketValue) than expected ($TranscriptsBucket)" -ForegroundColor Yellow
            }
            break
        }
    }
    if (-not $hasTranscriptsBucket) {
        Write-Host "  ⚠️  API service does not have TRANSCRIPTS_BUCKET set" -ForegroundColor Yellow
        Write-Host "    It will fall back to MEDIA_BUCKET" -ForegroundColor Gray
    }
} else {
    Write-Host "  ⚠️  Could not retrieve API service configuration" -ForegroundColor Yellow
}

# Check Worker service
$workerConfig = gcloud run services describe podcast-worker --region=us-west1 --project=$ProjectId --format=json 2>$null | ConvertFrom-Json
if ($workerConfig) {
    $envVars = $workerConfig.spec.template.spec.containers[0].env
    $hasTranscriptsBucket = $false
    foreach ($env in $envVars) {
        if ($env.name -eq "TRANSCRIPTS_BUCKET") {
            $hasTranscriptsBucket = $true
            $bucketValue = $env.value
            Write-Host "  ✅ Worker service has TRANSCRIPTS_BUCKET set: $bucketValue" -ForegroundColor Green
            if ($bucketValue -ne $TranscriptsBucket) {
                Write-Host "    ⚠️  Warning: Worker uses different bucket ($bucketValue) than expected ($TranscriptsBucket)" -ForegroundColor Yellow
            }
            break
        }
    }
    if (-not $hasTranscriptsBucket) {
        Write-Host "  ⚠️  Worker service does not have TRANSCRIPTS_BUCKET set" -ForegroundColor Yellow
        Write-Host "    It will fall back to MEDIA_BUCKET" -ForegroundColor Gray
    }
} else {
    Write-Host "  ⚠️  Could not retrieve Worker service configuration" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Fix implemented: Transcript lookup now prioritizes stored GCS URIs" -ForegroundColor Green
Write-Host ""
Write-Host "To ensure cross-environment compatibility:" -ForegroundColor Yellow
Write-Host "1. Use the same TRANSCRIPTS_BUCKET in dev and production" -ForegroundColor White
Write-Host "2. Ensure both environments have read access to the transcript bucket" -ForegroundColor White
Write-Host "3. Verify transcripts are stored with complete GCS URIs in episode metadata" -ForegroundColor White
Write-Host ""
Write-Host "The fix ensures that even if environments use different buckets, transcripts" -ForegroundColor Gray
Write-Host "can be found by downloading directly from the stored GCS URI in metadata." -ForegroundColor Gray
Write-Host ""

