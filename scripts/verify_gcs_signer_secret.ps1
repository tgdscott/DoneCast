# Verify GCS Signer Secret
# This script verifies the gcs-signer-key secret exists and is valid JSON

param(
    [string]$ProjectId = "podcast612"
)

Write-Host "=== Verifying GCS Signer Secret ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check if secret exists
Write-Host "Step 1: Checking if secret exists..." -ForegroundColor Yellow
try {
    $secretInfo = gcloud secrets describe gcs-signer-key --project=$ProjectId --format=json 2>$null | ConvertFrom-Json
    if ($secretInfo) {
        Write-Host "  ✅ Secret 'gcs-signer-key' exists" -ForegroundColor Green
        Write-Host "    Name: $($secretInfo.name)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ❌ Secret 'gcs-signer-key' does not exist" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Get latest version
Write-Host "Step 2: Getting latest secret version..." -ForegroundColor Yellow
try {
    $versions = gcloud secrets versions list gcs-signer-key --project=$ProjectId --format=json 2>$null | ConvertFrom-Json
    if ($versions -and $versions.Count -gt 0) {
        $latestVersion = $versions[0]
        Write-Host "  ✅ Found $($versions.Count) version(s)" -ForegroundColor Green
        Write-Host "    Latest version: $($latestVersion.name)" -ForegroundColor Gray
    } else {
        Write-Host "  ❌ Secret has no versions" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ❌ Failed to list secret versions" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 3: Download and verify secret content
Write-Host "Step 3: Verifying secret content..." -ForegroundColor Yellow
$tempFile = "gcs-signer-key-verify.json"
try {
    # Download the secret to a temporary file
    gcloud secrets versions access latest --secret=gcs-signer-key --project=$ProjectId > $tempFile 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ Failed to access secret" -ForegroundColor Red
        exit 1
    }
    
    # Check if file exists and has content
    if (Test-Path $tempFile) {
        $content = Get-Content $tempFile -Raw
        $contentLength = $content.Length
        Write-Host "  ✅ Secret downloaded (length: $contentLength bytes)" -ForegroundColor Green
        
        # Try to parse as JSON
        try {
            $json = $content | ConvertFrom-Json
            Write-Host "  ✅ Secret is valid JSON" -ForegroundColor Green
            
            # Verify it's a service account key
            if ($json.type -eq "service_account") {
                Write-Host "  ✅ Secret is a service account key" -ForegroundColor Green
                Write-Host "    Project ID: $($json.project_id)" -ForegroundColor Gray
                Write-Host "    Client Email: $($json.client_email)" -ForegroundColor Gray
                
                # Check if it has a private key
                if ($json.private_key) {
                    Write-Host "  ✅ Secret contains a private key" -ForegroundColor Green
                } else {
                    Write-Host "  ❌ Secret does NOT contain a private key" -ForegroundColor Red
                    Write-Host "    This is the problem! The secret must contain the full service account key JSON." -ForegroundColor Red
                }
            } else {
                Write-Host "  ❌ Secret is not a service account key (type: $($json.type))" -ForegroundColor Red
            }
        } catch {
            Write-Host "  ❌ Secret is not valid JSON: $_" -ForegroundColor Red
            Write-Host "    First 200 chars: $($content.Substring(0, [Math]::Min(200, $contentLength)))" -ForegroundColor Gray
        }
    } else {
        Write-Host "  ❌ Failed to download secret" -ForegroundColor Red
    }
} finally {
    # Clean up temp file
    if (Test-Path $tempFile) {
        Remove-Item $tempFile -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "=== Verification Complete ===" -ForegroundColor Cyan
Write-Host ""

