# Fix Presigned Upload Permissions for Cloud Run
# This script ensures the Cloud Run service account has the necessary permissions
# for IAM-based signed URL generation (for large file uploads)

Write-Host "=== Fixing Presigned Upload Permissions ===" -ForegroundColor Cyan
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

# Grant iam.serviceAccountTokenCreator role (required for IAM-based signing)
Write-Host "2. Granting iam.serviceAccountTokenCreator role..." -ForegroundColor Yellow
Write-Host "   This allows the service account to use IAM Credentials API for signing URLs" -ForegroundColor Gray
Write-Host "   Service account: $serviceAccount"
Write-Host ""

gcloud projects add-iam-policy-binding $projectId `
    --member="serviceAccount:$serviceAccount" `
    --role="roles/iam.serviceAccountTokenCreator" `
    --condition=None 2>&1 | Out-String

if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ Successfully granted iam.serviceAccountTokenCreator role" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Command returned exit code $LASTEXITCODE (role may already be granted)" -ForegroundColor Yellow
}
Write-Host ""

# Ensure storage.objectAdmin role on bucket (already done, but verify)
Write-Host "3. Verifying storage.objectAdmin role on bucket..." -ForegroundColor Yellow
Write-Host "   Bucket: gs://$bucketName"
Write-Host ""

$iamPolicy = gcloud storage buckets get-iam-policy "gs://$bucketName" --project=$projectId --format=json 2>&1 | ConvertFrom-Json

if ($iamPolicy) {
    $hasPermission = $false
    foreach ($binding in $iamPolicy.bindings) {
        if ($binding.members -contains "serviceAccount:$serviceAccount" -and $binding.role -eq "roles/storage.objectAdmin") {
            $hasPermission = $true
            Write-Host "   ✅ Service account has storage.objectAdmin role" -ForegroundColor Green
            break
        }
    }
    
    if (-not $hasPermission) {
        Write-Host "   ⚠️  Service account does NOT have storage.objectAdmin role" -ForegroundColor Yellow
        Write-Host "   Granting storage.objectAdmin role..." -ForegroundColor Cyan
        gcloud storage buckets add-iam-policy-binding "gs://$bucketName" `
            --member="serviceAccount:$serviceAccount" `
            --role="roles/storage.objectAdmin" `
            --project=$projectId 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Granted storage.objectAdmin role" -ForegroundColor Green
        }
    }
} else {
    Write-Host "   ⚠️  Could not verify permissions (may need to check manually)" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service account: $serviceAccount" -ForegroundColor Green
Write-Host "Required roles:" -ForegroundColor Yellow
Write-Host "  ✅ roles/iam.serviceAccountTokenCreator (for IAM-based URL signing)" -ForegroundColor Green
Write-Host "  ✅ roles/storage.objectAdmin (for GCS bucket access)" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Wait 1-2 minutes for IAM changes to propagate" -ForegroundColor Cyan
Write-Host "2. Deploy the updated code (presign endpoint now uses _generate_signed_url)" -ForegroundColor Cyan
Write-Host "3. Test uploading a large file (>32MB)" -ForegroundColor Cyan
Write-Host "4. Check Cloud Run logs if upload still fails:" -ForegroundColor Cyan
Write-Host "   gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=$serviceName AND textPayload=~\"presign\"' --limit=50 --project=$projectId" -ForegroundColor Gray
Write-Host ""

