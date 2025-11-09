# Fix GCS Upload Permissions for Cloud Run
# This script grants the Cloud Run service account permission to upload to GCS

Write-Host "=== Fixing GCS Upload Permissions ===" -ForegroundColor Cyan
Write-Host ""

$projectId = "podcast612"
$serviceName = "podcast-api"
$region = "us-west1"
$bucketName = "ppp-media-us-west1"

# Get service account
Write-Host "1. Getting Cloud Run service account..." -ForegroundColor Yellow
$serviceAccount = gcloud run services describe $serviceName `
    --region=$region `
    --project=$projectId `
    --format="value(spec.template.spec.serviceAccountName)" 2>&1

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serviceAccount)) {
    # Use default compute service account
    $projectNumber = gcloud projects describe $projectId --format="value(projectNumber)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $serviceAccount = "$projectNumber-compute@developer.gserviceaccount.com"
        Write-Host "   Using default compute service account: $serviceAccount" -ForegroundColor Yellow
    } else {
        Write-Host "   ERROR: Could not determine service account" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "   Service account: $serviceAccount" -ForegroundColor Green
}
Write-Host ""

# Grant storage.objectAdmin role on bucket
Write-Host "2. Granting storage.objectAdmin role on bucket..." -ForegroundColor Yellow
Write-Host "   Bucket: gs://$bucketName"
Write-Host "   Service account: $serviceAccount"
Write-Host ""

# Use gcloud to set IAM policy (works better on Windows than gsutil)
Write-Host "   Running: gcloud storage buckets add-iam-policy-binding..." -ForegroundColor Cyan
gcloud storage buckets add-iam-policy-binding "gs://$bucketName" `
    --member="serviceAccount:$serviceAccount" `
    --role="roles/storage.objectAdmin" `
    --project=$projectId 2>&1 | Out-String

if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ Successfully granted storage.objectAdmin role" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Command returned exit code $LASTEXITCODE" -ForegroundColor Yellow
    Write-Host "   Trying alternative method with gsutil..." -ForegroundColor Yellow
    
    # Alternative: use gsutil
    $gsutilCmd = "gsutil iam ch serviceAccount:$serviceAccount`:roles/storage.objectAdmin gs://$bucketName"
    Write-Host "   Running: $gsutilCmd" -ForegroundColor Cyan
    Invoke-Expression $gsutilCmd 2>&1 | Out-String
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Successfully granted storage.objectAdmin role (via gsutil)" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Failed to grant permissions. You may need to run this manually:" -ForegroundColor Red
        Write-Host "   $gsutilCmd" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "   Or use the Cloud Console:" -ForegroundColor Yellow
        Write-Host "   1. Go to https://console.cloud.google.com/storage/browser/$bucketName" -ForegroundColor Cyan
        Write-Host "   2. Click 'Permissions' tab" -ForegroundColor Cyan
        Write-Host "   3. Click 'Grant Access'" -ForegroundColor Cyan
        Write-Host "   4. Add: $serviceAccount" -ForegroundColor Cyan
        Write-Host "   5. Role: Storage Object Admin" -ForegroundColor Cyan
        exit 1
    }
}
Write-Host ""

# Verify permissions
Write-Host "3. Verifying permissions..." -ForegroundColor Yellow
$iamPolicy = gcloud storage buckets get-iam-policy "gs://$bucketName" --project=$projectId --format=json 2>&1 | ConvertFrom-Json

if ($iamPolicy) {
    $hasPermission = $false
    foreach ($binding in $iamPolicy.bindings) {
        if ($binding.members -contains "serviceAccount:$serviceAccount" -and $binding.role -eq "roles/storage.objectAdmin") {
            $hasPermission = $true
            Write-Host "   ✅ Verified: Service account has storage.objectAdmin role" -ForegroundColor Green
            break
        }
    }
    
    if (-not $hasPermission) {
        Write-Host "   ⚠️  Warning: Could not verify permissions (may take a moment to propagate)" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ⚠️  Could not verify permissions (may need to check manually)" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service account: $serviceAccount" -ForegroundColor Green
Write-Host "Bucket: gs://$bucketName" -ForegroundColor Green
Write-Host "Role granted: roles/storage.objectAdmin" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Wait 1-2 minutes for IAM changes to propagate" -ForegroundColor Cyan
Write-Host "2. Try uploading a file again" -ForegroundColor Cyan
Write-Host "3. Check Cloud Run logs if upload still fails:" -ForegroundColor Cyan
Write-Host "   gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=$serviceName' --limit=50 --project=$projectId" -ForegroundColor Gray
Write-Host ""

