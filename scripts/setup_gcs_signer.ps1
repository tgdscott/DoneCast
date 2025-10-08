# Setup GCS Signing Service Account
# This script creates a service account with permissions to sign GCS URLs

$ErrorActionPreference = "Stop"

$PROJECT_ID = "podcast612"
$SA_NAME = "gcs-media-signer"
$SA_EMAIL = "$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
$KEY_FILE = "gcs-signer-key.json"

Write-Host "=== GCS Signing Service Account Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check if gcloud is available
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "gcloud command not found. Please install Google Cloud SDK."
    exit 1
}

# Check if already logged in
$ErrorActionPreference = "Continue"
$account = (gcloud config get-value account 2>&1 | Select-Object -Last 1)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($account)) {
    Write-Error "Please login with: gcloud auth login"
    exit 1
}

Write-Host "Current account: $account" -ForegroundColor Green
Write-Host ""

# Check if service account already exists
Write-Host "Checking if service account exists..." -ForegroundColor Yellow
$ErrorActionPreference = "Continue"
$null = gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID 2>&1
$saExistsCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

if ($saExistsCode -eq 0) {
    Write-Host "Service account already exists: $SA_EMAIL" -ForegroundColor Green
} else {
    Write-Host "Creating service account..." -ForegroundColor Yellow
    gcloud iam service-accounts create $SA_NAME --display-name="GCS Media URL Signer" --description="Service account for generating signed URLs for media files" --project=$PROJECT_ID
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create service account"
        exit 1
    }
    Write-Host "Service account created: $SA_EMAIL" -ForegroundColor Green
}

Write-Host ""

# Grant Storage Object Viewer permission
Write-Host "Granting Storage Object Viewer role..." -ForegroundColor Yellow
$ErrorActionPreference = "Continue"
$null = gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SA_EMAIL" --role="roles/storage.objectViewer" --condition=None 2>&1
$iamCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

if ($iamCode -eq 0) {
    Write-Host "Storage Object Viewer role granted" -ForegroundColor Green
} else {
    Write-Warning "Role may already be granted (this is OK)"
}

Write-Host ""

# Check if key file already exists
if (Test-Path $KEY_FILE) {
    $response = Read-Host "Key file '$KEY_FILE' already exists. Overwrite? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "Using existing key file." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "=== Setup Complete ===" -ForegroundColor Green
        Write-Host "To use this key, run:" -ForegroundColor Cyan
        $fullPath = (Resolve-Path $KEY_FILE).Path
        Write-Host "  Set environment variable: GOOGLE_APPLICATION_CREDENTIALS=$fullPath"
        Write-Host ""
        Write-Host "Or add to backend\.env:" -ForegroundColor Cyan
        Write-Host "  GOOGLE_APPLICATION_CREDENTIALS=$fullPath"
        exit 0
    }
}

# Create and download key
Write-Host "Creating service account key..." -ForegroundColor Yellow
gcloud iam service-accounts keys create $KEY_FILE --iam-account=$SA_EMAIL --project=$PROJECT_ID

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create service account key"
    exit 1
}

Write-Host "Key file created: $KEY_FILE" -ForegroundColor Green
Write-Host ""

# Upload to Secret Manager for Cloud Run
Write-Host "Uploading key to Secret Manager for Cloud Run..." -ForegroundColor Yellow

# Check if secret exists
$ErrorActionPreference = "Continue"
$null = gcloud secrets describe gcs-signer-key --project=$PROJECT_ID 2>&1
$secretExistsCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

if ($secretExistsCode -eq 0) {
    Write-Host "Secret already exists. Creating new version..." -ForegroundColor Yellow
    gcloud secrets versions add gcs-signer-key --data-file=$KEY_FILE --project=$PROJECT_ID
} else {
    Write-Host "Creating new secret..." -ForegroundColor Yellow
    gcloud secrets create gcs-signer-key --data-file=$KEY_FILE --project=$PROJECT_ID
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "Secret uploaded to Secret Manager" -ForegroundColor Green
} else {
    Write-Warning "Failed to upload to Secret Manager (may need permissions)"
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "For local development, run:" -ForegroundColor Cyan
$fullPath = (Resolve-Path $KEY_FILE).Path
Write-Host "  Set environment variable: GOOGLE_APPLICATION_CREDENTIALS=$fullPath"
Write-Host ""
Write-Host "Or add to backend\.env:" -ForegroundColor Cyan
Write-Host "  GOOGLE_APPLICATION_CREDENTIALS=$fullPath"
Write-Host ""
Write-Host "For Cloud Run, the secret is already configured in Secret Manager." -ForegroundColor Green
Write-Host ""
