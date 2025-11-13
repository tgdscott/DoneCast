# Apply CORS configuration to GCS bucket for direct browser uploads
# Run this script to enable browser-based uploads to Google Cloud Storage

# Check if gcloud is installed
if (!(Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: gcloud CLI not found. Please install Google Cloud SDK." -ForegroundColor Red
    Write-Host "Download from: https://cloud.google.com/sdk/docs/install" -ForegroundColor Yellow
    exit 1
}

# Get bucket name from environment or use default
$bucketName = $env:GCS_BUCKET
if (-not $bucketName) {
    $bucketName = "ppp-media-us-west1"
    Write-Host "No GCS_BUCKET env var set, using default: $bucketName" -ForegroundColor Yellow
}

Write-Host "`nApplying CORS configuration to bucket: gs://$bucketName" -ForegroundColor Cyan

# Apply CORS configuration
try {
    gcloud storage buckets update "gs://$bucketName" --cors-file="$PSScriptRoot\gcs-cors-config.json"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✅ SUCCESS: CORS configuration applied!" -ForegroundColor Green
        Write-Host "`nBucket now allows browser uploads from:" -ForegroundColor Cyan
        Write-Host "  - http://127.0.0.1:5173 (local dev)" -ForegroundColor White
        Write-Host "  - http://localhost:5173 (local dev)" -ForegroundColor White
        Write-Host "  - https://app.podcastplusplus.com (production)" -ForegroundColor White
        Write-Host "  - https://podcastplusplus.com (production)" -ForegroundColor White
        Write-Host "  - https://www.podcastplusplus.com (production)" -ForegroundColor White
        Write-Host "  - https://getpodcastplus.com (legacy production)" -ForegroundColor White
        Write-Host "  - https://www.getpodcastplus.com (legacy production)" -ForegroundColor White
        
        Write-Host "`nTo verify CORS configuration:" -ForegroundColor Cyan
        Write-Host "  gcloud storage buckets describe gs://$bucketName --format=`"json(cors_config)`"" -ForegroundColor White
    } else {
        Write-Host "`n❌ FAILED: gcloud command returned error code $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "`n❌ ERROR: Failed to apply CORS configuration" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
