# Diagnose GCS Upload Issues on Cloud Run
# This script checks GCS configuration and permissions for production uploads

Write-Host "=== GCS Upload Diagnosis ===" -ForegroundColor Cyan
Write-Host ""

# Check Cloud Run service configuration
Write-Host "1. Checking Cloud Run service configuration..." -ForegroundColor Yellow
$projectId = "podcast612"
$serviceName = "podcast-api"
$region = "us-west1"

Write-Host "   Project: $projectId"
Write-Host "   Service: $serviceName"
Write-Host "   Region: $region"
Write-Host ""

# Get service account
Write-Host "2. Checking Cloud Run service account..." -ForegroundColor Yellow
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
    Write-Host "   Service account: $serviceAccount"
}
Write-Host ""

# Check GCS bucket
Write-Host "3. Checking GCS bucket..." -ForegroundColor Yellow
$bucketName = "ppp-media-us-west1"
Write-Host "   Bucket: $bucketName"

# Check if bucket exists
$bucketExists = gsutil ls -b "gs://$bucketName" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ERROR: Bucket does not exist or is not accessible" -ForegroundColor Red
    Write-Host "   Output: $bucketExists" -ForegroundColor Red
} else {
    Write-Host "   ✅ Bucket exists"
}
Write-Host ""

# Check IAM permissions
Write-Host "4. Checking IAM permissions for service account..." -ForegroundColor Yellow
Write-Host "   Service account: $serviceAccount"
Write-Host "   Bucket: gs://$bucketName"
Write-Host ""

# Check bucket IAM policy
Write-Host "   Checking bucket IAM policy..."
$iamPolicy = gsutil iam get "gs://$bucketName" 2>&1 | ConvertFrom-Json

if ($iamPolicy) {
    $hasPermission = $false
    $roles = @()
    
    foreach ($binding in $iamPolicy.bindings) {
        if ($binding.members -contains "serviceAccount:$serviceAccount") {
            $hasPermission = $true
            $roles += $binding.role
            Write-Host "   ✅ Found role: $($binding.role)" -ForegroundColor Green
        }
    }
    
    if (-not $hasPermission) {
        Write-Host "   ❌ Service account does NOT have permissions on bucket" -ForegroundColor Red
        Write-Host ""
        Write-Host "   FIX: Grant storage.objectAdmin role:" -ForegroundColor Yellow
        Write-Host "   gsutil iam ch serviceAccount:$serviceAccount`:roles/storage.objectAdmin gs://$bucketName" -ForegroundColor Cyan
    } else {
        Write-Host "   ✅ Service account has permissions: $($roles -join ', ')"
    }
} else {
    Write-Host "   ⚠️  Could not retrieve IAM policy (may need gsutil permissions)" -ForegroundColor Yellow
}
Write-Host ""

# Check project-level IAM
Write-Host "5. Checking project-level IAM permissions..." -ForegroundColor Yellow
$projectPolicy = gcloud projects get-iam-policy $projectId --format=json 2>&1 | ConvertFrom-Json

if ($projectPolicy) {
    $hasProjectPermission = $false
    $projectRoles = @()
    
    foreach ($binding in $projectPolicy.bindings) {
        if ($binding.members -contains "serviceAccount:$serviceAccount") {
            $hasProjectPermission = $true
            $projectRoles += $binding.role
        }
    }
    
    if ($projectRoles.Count -gt 0) {
        Write-Host "   ✅ Service account has project roles: $($projectRoles -join ', ')"
    } else {
        Write-Host "   ⚠️  Service account has no project-level roles (may be fine if bucket-level permissions exist)" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ⚠️  Could not retrieve project IAM policy" -ForegroundColor Yellow
}
Write-Host ""

# Check environment variables
Write-Host "6. Checking Cloud Run environment variables..." -ForegroundColor Yellow
$envVars = gcloud run services describe $serviceName `
    --region=$region `
    --project=$projectId `
    --format="value(spec.template.spec.containers[0].env)" 2>&1

if ($envVars) {
    $hasGcsBucket = $envVars -match "MEDIA_BUCKET"
    $hasStorageBackend = $envVars -match "STORAGE_BACKEND"
    $hasGcsSigner = $envVars -match "GCS_SIGNER_KEY_JSON"
    
    Write-Host "   MEDIA_BUCKET: $(if ($hasGcsBucket) { '✅ Set' } else { '❌ Not set' })"
    Write-Host "   STORAGE_BACKEND: $(if ($hasStorageBackend) { '✅ Set' } else { '❌ Not set' })"
    Write-Host "   GCS_SIGNER_KEY_JSON: $(if ($hasGcsSigner) { '✅ Set' } else { '❌ Not set' })"
} else {
    Write-Host "   ⚠️  Could not retrieve environment variables" -ForegroundColor Yellow
}
Write-Host ""

# Summary and recommendations
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Most common issues:" -ForegroundColor Yellow
Write-Host "1. Service account lacks storage.objectAdmin on bucket"
Write-Host "2. GCS_BUCKET env var not set or incorrect"
Write-Host "3. STORAGE_BACKEND=r2 but uploads require GCS (force_gcs=True)"
Write-Host ""
Write-Host "Recommended fix:" -ForegroundColor Green
Write-Host "  gsutil iam ch serviceAccount:$serviceAccount`:roles/storage.objectAdmin gs://$bucketName" -ForegroundColor Cyan
Write-Host ""
Write-Host "Then verify:" -ForegroundColor Yellow
Write-Host "  gsutil iam get gs://$bucketName" -ForegroundColor Cyan
Write-Host ""

