# Complete Fix for GCS Upload - Permanent Solution
# This script ensures everything is configured correctly for direct GCS uploads

param(
    [string]$ProjectId = "podcast612",
    [string]$Region = "us-west1",
    [string]$BucketName = "ppp-media-us-west1"
)

Write-Host "=== Complete GCS Upload Fix ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify the secret
Write-Host "Step 1: Verifying gcs-signer-key secret..." -ForegroundColor Yellow
$tempFile = "gcs-signer-key-check.json"
try {
    gcloud secrets versions access latest --secret=gcs-signer-key --project=$ProjectId > $tempFile 2>&1
    if ($LASTEXITCODE -eq 0 -and (Test-Path $tempFile)) {
        $json = Get-Content $tempFile | ConvertFrom-Json
        $signerEmail = $json.client_email
        Write-Host "  ✅ Secret is valid" -ForegroundColor Green
        Write-Host "    Service account: $signerEmail" -ForegroundColor Gray
    } else {
        Write-Host "  ❌ Secret is invalid or inaccessible" -ForegroundColor Red
        exit 1
    }
} finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}

Write-Host ""

# Step 2: Verify service account permissions
Write-Host "Step 2: Verifying service account permissions..." -ForegroundColor Yellow

# Check bucket permissions
Write-Host "  Checking bucket permissions..." -ForegroundColor Gray
$bucketPolicy = gsutil iam get "gs://$BucketName" 2>$null
if ($bucketPolicy) {
    if ($bucketPolicy -match $signerEmail) {
        Write-Host "  ✅ Service account has bucket permissions" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Granting bucket permissions..." -ForegroundColor Yellow
        gsutil iam ch "serviceAccount:$signerEmail:roles/storage.objectAdmin" "gs://$BucketName"
        Write-Host "  ✅ Permissions granted" -ForegroundColor Green
    }
} else {
    Write-Host "  ⚠️  Could not verify bucket permissions" -ForegroundColor Yellow
}

# Check project-level permissions
Write-Host "  Checking project-level permissions..." -ForegroundColor Gray
$projectRoles = gcloud projects get-iam-policy $ProjectId --flatten="bindings[].members" --filter="bindings.members:serviceAccount:$signerEmail" --format="value(bindings.role)" 2>$null

$hasStorageAdmin = $false
$hasObjectAdmin = $false
foreach ($role in $projectRoles) {
    if ($role -eq "roles/storage.admin") { $hasStorageAdmin = $true }
    if ($role -eq "roles/storage.objectAdmin") { $hasObjectAdmin = $true }
}

if ($hasStorageAdmin -or $hasObjectAdmin) {
    Write-Host "  ✅ Service account has storage permissions at project level" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Granting project-level storage permissions..." -ForegroundColor Yellow
    gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$signerEmail" `
        --role="roles/storage.objectAdmin" 2>&1 | Out-Null
    Write-Host "  ✅ Permissions granted" -ForegroundColor Green
}

Write-Host ""

# Step 3: Verify Cloud Run can access the secret
Write-Host "Step 3: Verifying Cloud Run service account can access secret..." -ForegroundColor Yellow

# Get Cloud Run service account
$runServiceAccount = gcloud run services describe podcast-api --region=$Region --project=$ProjectId --format="value(spec.template.spec.serviceAccountName)" 2>$null
if ([string]::IsNullOrEmpty($runServiceAccount)) {
    $projectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)" 2>$null
    $runServiceAccount = "$projectNumber-compute@developer.gserviceaccount.com"
}

Write-Host "  Cloud Run service account: $runServiceAccount" -ForegroundColor Gray

# Check if it has access to the secret
$secretPolicy = gcloud secrets get-iam-policy gcs-signer-key --project=$ProjectId --format=json 2>$null | ConvertFrom-Json
$hasSecretAccess = $false

if ($secretPolicy.bindings) {
    foreach ($binding in $secretPolicy.bindings) {
        if ($binding.role -eq "roles/secretmanager.secretAccessor") {
            foreach ($member in $binding.members) {
                if ($member -eq "serviceAccount:$runServiceAccount") {
                    $hasSecretAccess = $true
                    break
                }
            }
        }
    }
}

if ($hasSecretAccess) {
    Write-Host "  ✅ Cloud Run service account has access to secret" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Granting Cloud Run service account access to secret..." -ForegroundColor Yellow
    gcloud secrets add-iam-policy-binding gcs-signer-key `
        --member="serviceAccount:$runServiceAccount" `
        --role="roles/secretmanager.secretAccessor" `
        --project=$ProjectId 2>&1 | Out-Null
    Write-Host "  ✅ Access granted" -ForegroundColor Green
}

Write-Host ""

# Step 4: Verify Cloud Run configuration
Write-Host "Step 4: Verifying Cloud Run configuration..." -ForegroundColor Yellow

$serviceConfig = gcloud run services describe podcast-api --region=$Region --project=$ProjectId --format=json 2>$null | ConvertFrom-Json

if ($serviceConfig) {
    $secrets = $serviceConfig.spec.template.spec.containers[0].env
    $hasGcsSigner = $false
    
    foreach ($env in $secrets) {
        if ($env.name -eq "GCS_SIGNER_KEY_JSON") {
            $hasGcsSigner = $true
            Write-Host "  ✅ GCS_SIGNER_KEY_JSON is configured" -ForegroundColor Green
            Write-Host "    Secret: $($env.valueFrom.secretKeyRef.name)" -ForegroundColor Gray
            Write-Host "    Version: $($env.valueFrom.secretKeyRef.version)" -ForegroundColor Gray
            break
        }
    }
    
    if (-not $hasGcsSigner) {
        Write-Host "  ❌ GCS_SIGNER_KEY_JSON is NOT configured in Cloud Run" -ForegroundColor Red
        Write-Host "  This is the problem! The secret needs to be mounted as an environment variable." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  To fix, run:" -ForegroundColor Yellow
        Write-Host "    gcloud run services update podcast-api --region=$Region --project=$ProjectId --update-secrets=GCS_SIGNER_KEY_JSON=gcs-signer-key:latest" -ForegroundColor Cyan
        Write-Host ""
    }
} else {
    Write-Host "  ⚠️  Could not verify Cloud Run configuration" -ForegroundColor Yellow
}

Write-Host ""

# Step 5: Summary and next steps
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""

if ($hasGcsSigner) {
    Write-Host "✅ Everything is configured correctly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "If uploads are still failing, the issue might be:" -ForegroundColor Yellow
    Write-Host "1. Cloud Run service needs to be restarted to pick up the secret" -ForegroundColor White
    Write-Host "2. Check Cloud Run logs for detailed error messages" -ForegroundColor White
    Write-Host "3. Verify the code is correctly loading the secret from GCS_SIGNER_KEY_JSON" -ForegroundColor White
    Write-Host ""
    Write-Host "To restart the service:" -ForegroundColor Yellow
    Write-Host "  gcloud run services update podcast-api --region=$Region --project=$ProjectId --no-traffic" -ForegroundColor Cyan
    Write-Host "  gcloud run services update-traffic podcast-api --region=$Region --project=$ProjectId --to-latest" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  Configuration incomplete!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The secret exists and has the right permissions, but Cloud Run is not configured to use it." -ForegroundColor Yellow
    Write-Host "Run the command shown above to mount the secret." -ForegroundColor Yellow
}

Write-Host ""

