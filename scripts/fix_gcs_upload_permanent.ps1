# Fix GCS Upload - Permanent Solution
# This script verifies and fixes the GCS signing credentials for direct uploads

param(
    [string]$ProjectId = "podcast612",
    [string]$Region = "us-west1",
    [string]$ServiceAccount = "",
    [string]$BucketName = "ppp-media-us-west1"
)

Write-Host "=== GCS Upload Permanent Fix ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Get Cloud Run service account
Write-Host "Step 1: Identifying Cloud Run service account..." -ForegroundColor Yellow
if ([string]::IsNullOrEmpty($ServiceAccount)) {
    Write-Host "  Getting service account from Cloud Run service..." -ForegroundColor Gray
    $serviceAccountName = gcloud run services describe podcast-api --region=$Region --project=$ProjectId --format="value(spec.template.spec.serviceAccountName)" 2>$null
    
    if ([string]::IsNullOrEmpty($serviceAccountName)) {
        # Use default compute service account
        $projectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)" 2>$null
        $ServiceAccount = "$projectNumber-compute@developer.gserviceaccount.com"
        Write-Host "  Using default compute service account: $ServiceAccount" -ForegroundColor Gray
    } else {
        $ServiceAccount = $serviceAccountName
        Write-Host "  Found service account: $ServiceAccount" -ForegroundColor Gray
    }
} else {
    Write-Host "  Using provided service account: $ServiceAccount" -ForegroundColor Gray
}

Write-Host ""

# Step 2: Check if gcs-signer-key secret exists
Write-Host "Step 2: Checking for gcs-signer-key secret..." -ForegroundColor Yellow
$secretExists = $false
try {
    $null = gcloud secrets describe gcs-signer-key --project=$ProjectId 2>&1
    if ($LASTEXITCODE -eq 0) {
        $secretExists = $true
        Write-Host "  ✅ Secret 'gcs-signer-key' exists" -ForegroundColor Green
        
        # Check if it has a version
        $versions = gcloud secrets versions list gcs-signer-key --project=$ProjectId --format="value(name)" 2>$null
        if ($versions) {
            Write-Host "  ✅ Secret has versions" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  Secret exists but has no versions" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "  ❌ Secret 'gcs-signer-key' does not exist" -ForegroundColor Red
}

Write-Host ""

# Step 3: Create service account key if needed
if (-not $secretExists -or $versions.Count -eq 0) {
    Write-Host "Step 3: Creating service account key for GCS signing..." -ForegroundColor Yellow
    
    # Create a dedicated service account for signing (or use existing one)
    $signerAccount = "gcs-signer@${ProjectId}.iam.gserviceaccount.com"
    $signerAccountExists = $false
    
    try {
        $null = gcloud iam service-accounts describe $signerAccount --project=$ProjectId 2>&1
        if ($LASTEXITCODE -eq 0) {
            $signerAccountExists = $true
            Write-Host "  ✅ Service account $signerAccount already exists" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Creating new service account: $signerAccount" -ForegroundColor Gray
        gcloud iam service-accounts create gcs-signer `
            --display-name="GCS URL Signer" `
            --description="Service account for signing GCS URLs for direct uploads" `
            --project=$ProjectId
        
        if ($LASTEXITCODE -eq 0) {
            $signerAccountExists = $true
            Write-Host "  ✅ Service account created" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Failed to create service account" -ForegroundColor Red
            exit 1
        }
    }
    
    # Grant storage permissions
    Write-Host "  Granting storage permissions..." -ForegroundColor Gray
    gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$signerAccount" `
        --role="roles/storage.objectAdmin" `
        --condition=None 2>&1 | Out-Null
    
    # Create key file
    $keyFile = "gcs-signer-key.json"
    Write-Host "  Creating service account key..." -ForegroundColor Gray
    gcloud iam service-accounts keys create $keyFile `
        --iam-account=$signerAccount `
        --project=$ProjectId
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ Failed to create service account key" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "  ✅ Service account key created: $keyFile" -ForegroundColor Green
    
    # Step 4: Upload to Secret Manager
    Write-Host ""
    Write-Host "Step 4: Uploading key to Secret Manager..." -ForegroundColor Yellow
    
    if (-not $secretExists) {
        Write-Host "  Creating secret 'gcs-signer-key'..." -ForegroundColor Gray
        gcloud secrets create gcs-signer-key `
            --data-file=$keyFile `
            --project=$ProjectId `
            --replication-policy="automatic"
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ❌ Failed to create secret" -ForegroundColor Red
            Remove-Item $keyFile -ErrorAction SilentlyContinue
            exit 1
        }
        Write-Host "  ✅ Secret created" -ForegroundColor Green
    } else {
        Write-Host "  Adding new version to existing secret..." -ForegroundColor Gray
        gcloud secrets versions add gcs-signer-key `
            --data-file=$keyFile `
            --project=$ProjectId
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ❌ Failed to add secret version" -ForegroundColor Red
            Remove-Item $keyFile -ErrorAction SilentlyContinue
            exit 1
        }
        Write-Host "  ✅ Secret version added" -ForegroundColor Green
    }
    
    # Grant Cloud Run service account access to the secret
    Write-Host "  Granting Cloud Run service account access to secret..." -ForegroundColor Gray
    gcloud secrets add-iam-policy-binding gcs-signer-key `
        --member="serviceAccount:$ServiceAccount" `
        --role="roles/secretmanager.secretAccessor" `
        --project=$ProjectId 2>&1 | Out-Null
    
    Write-Host "  ✅ Cloud Run service account can now access the secret" -ForegroundColor Green
    
    # Clean up local key file
    Write-Host "  Removing local key file for security..." -ForegroundColor Gray
    Remove-Item $keyFile -ErrorAction SilentlyContinue
    Write-Host "  ✅ Local key file removed" -ForegroundColor Green
    
} else {
    Write-Host "Step 3: Secret already exists, verifying configuration..." -ForegroundColor Yellow
    
    # Verify the secret is accessible by Cloud Run service account
    $policy = gcloud secrets get-iam-policy gcs-signer-key --project=$ProjectId --format=json 2>$null | ConvertFrom-Json
    $hasAccess = $false
    
    if ($policy.bindings) {
        foreach ($binding in $policy.bindings) {
            if ($binding.role -eq "roles/secretmanager.secretAccessor") {
                foreach ($member in $binding.members) {
                    if ($member -like "*$ServiceAccount*") {
                        $hasAccess = $true
                        break
                    }
                }
            }
        }
    }
    
    if ($hasAccess) {
        Write-Host "  ✅ Cloud Run service account has access to secret" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Cloud Run service account may not have access to secret" -ForegroundColor Yellow
        Write-Host "  Granting access..." -ForegroundColor Gray
        gcloud secrets add-iam-policy-binding gcs-signer-key `
            --member="serviceAccount:$ServiceAccount" `
            --role="roles/secretmanager.secretAccessor" `
            --project=$ProjectId 2>&1 | Out-Null
        Write-Host "  ✅ Access granted" -ForegroundColor Green
    }
}

Write-Host ""

# Step 5: Verify Cloud Run configuration
Write-Host "Step 5: Verifying Cloud Run configuration..." -ForegroundColor Yellow
$serviceConfig = gcloud run services describe podcast-api --region=$Region --project=$ProjectId --format=json 2>$null | ConvertFrom-Json

if ($serviceConfig) {
    $secrets = $serviceConfig.spec.template.spec.containers[0].env
    $hasGcsSigner = $false
    
    foreach ($env in $secrets) {
        if ($env.name -eq "GCS_SIGNER_KEY_JSON" -and $env.valueFrom.secretKeyRef.name -eq "gcs-signer-key") {
            $hasGcsSigner = $true
            Write-Host "  ✅ GCS_SIGNER_KEY_JSON is configured in Cloud Run" -ForegroundColor Green
            break
        }
    }
    
    if (-not $hasGcsSigner) {
        Write-Host "  ⚠️  GCS_SIGNER_KEY_JSON is not configured in Cloud Run" -ForegroundColor Yellow
        Write-Host "  This should be set in cloudbuild.yaml - checking..." -ForegroundColor Gray
        
        # Check cloudbuild.yaml
        if (Test-Path "cloudbuild.yaml") {
            $cloudbuild = Get-Content "cloudbuild.yaml" -Raw
            if ($cloudbuild -match "GCS_SIGNER_KEY_JSON=gcs-signer-key:latest") {
                Write-Host "  ✅ cloudbuild.yaml has GCS_SIGNER_KEY_JSON configured" -ForegroundColor Green
                Write-Host "  You may need to redeploy for the change to take effect" -ForegroundColor Yellow
            } else {
                Write-Host "  ❌ cloudbuild.yaml is missing GCS_SIGNER_KEY_JSON" -ForegroundColor Red
                Write-Host "  Please add it to the --set-secrets parameter" -ForegroundColor Yellow
            }
        }
    }
} else {
    Write-Host "  ⚠️  Could not verify Cloud Run configuration" -ForegroundColor Yellow
}

Write-Host ""

# Step 6: Verify bucket permissions
Write-Host "Step 6: Verifying bucket permissions..." -ForegroundColor Yellow
$bucketPolicy = gsutil iam get "gs://$BucketName" 2>$null | ConvertFrom-Json

if ($bucketPolicy) {
    $hasPermission = $false
    if ($bucketPolicy.bindings) {
        foreach ($binding in $bucketPolicy.bindings) {
            if ($binding.role -eq "roles/storage.objectAdmin" -or $binding.role -eq "roles/storage.admin") {
                foreach ($member in $binding.members) {
                    if ($member -like "*$ServiceAccount*" -or $member -like "*gcs-signer@*") {
                        $hasPermission = $true
                        Write-Host "  ✅ Service account has storage permissions on bucket" -ForegroundColor Green
                        break
                    }
                }
            }
        }
    }
    
    if (-not $hasPermission) {
        Write-Host "  ⚠️  Service account may not have storage permissions" -ForegroundColor Yellow
        Write-Host "  Granting storage.objectAdmin role..." -ForegroundColor Gray
        gsutil iam ch "serviceAccount:$ServiceAccount:roles/storage.objectAdmin" "gs://$BucketName"
        Write-Host "  ✅ Permissions granted" -ForegroundColor Green
    }
} else {
    Write-Host "  ⚠️  Could not verify bucket permissions" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Configuration complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Redeploy the Cloud Run service to pick up the secret:" -ForegroundColor White
Write-Host "   gcloud builds submit --config=cloudbuild.yaml" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Or manually update the service to ensure the secret is mounted:" -ForegroundColor White
Write-Host "   gcloud run services update podcast-api --region=$Region --project=$ProjectId --update-secrets=GCS_SIGNER_KEY_JSON=gcs-signer-key:latest" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Test the upload after deployment" -ForegroundColor White
Write-Host ""
Write-Host "The secret 'gcs-signer-key' contains the service account key needed to sign GCS URLs." -ForegroundColor Gray
Write-Host "This allows direct uploads to GCS, bypassing Cloud Run's 32MB request body limit." -ForegroundColor Gray
Write-Host ""

