# Frontend-Only Deployment Script
# Builds and deploys ONLY the frontend web service to Cloud Run
# Use this when you have frontend-only changes to avoid rebuilding the API

$ErrorActionPreference = "Stop"

Write-Host "==> Frontend-Only Deployment Starting..." -ForegroundColor Cyan
Write-Host ""

# Configuration
$PROJECT_ID = "podcast612"
$REGION = "us-west1"
$AR_REPO = "cloud-run"
$WEB_SERVICE = "podcast-web"
$WEB_DIR = "frontend"

# Build arguments
$VITE_API_BASE = "https://api.podcastplusplus.com/api"

Write-Host "==> Configuration:" -ForegroundColor Yellow
Write-Host "    Project: $PROJECT_ID"
Write-Host "    Region: $REGION"
Write-Host "    Service: $WEB_SERVICE"
Write-Host "    API Base: $VITE_API_BASE"
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path ".\$WEB_DIR\package.json")) {
    Write-Host "ERROR: Cannot find $WEB_DIR\package.json - are you in the project root?" -ForegroundColor Red
    exit 1
}

# Get GOOGLE_CLIENT_ID from Secret Manager
Write-Host "==> Fetching GOOGLE_CLIENT_ID from Secret Manager..." -ForegroundColor Cyan
try {
    $GOOGLE_CLIENT_ID = gcloud secrets versions access latest --secret="GOOGLE_CLIENT_ID" --project=$PROJECT_ID 2>$null
    if (-not $GOOGLE_CLIENT_ID) {
        Write-Host "WARNING: Could not fetch GOOGLE_CLIENT_ID from Secret Manager" -ForegroundColor Yellow
        $GOOGLE_CLIENT_ID = "724497178186-kdv8rp3loagl1me3e0v3udlctigq36g9.apps.googleusercontent.com"
        Write-Host "    Using fallback: $GOOGLE_CLIENT_ID" -ForegroundColor Yellow
    } else {
        Write-Host "    ✓ Retrieved from Secret Manager" -ForegroundColor Green
    }
} catch {
    Write-Host "WARNING: Error fetching secret: $_" -ForegroundColor Yellow
    $GOOGLE_CLIENT_ID = "724497178186-kdv8rp3loagl1me3e0v3udlctigq36g9.apps.googleusercontent.com"
    Write-Host "    Using fallback: $GOOGLE_CLIENT_ID" -ForegroundColor Yellow
}

# Get VITE_POSTHOG_KEY from Secret Manager
Write-Host "==> Fetching VITE_POSTHOG_KEY from Secret Manager..." -ForegroundColor Cyan
try {
    $VITE_POSTHOG_KEY = gcloud secrets versions access latest --secret="VITE_POSTHOG_KEY" --project=$PROJECT_ID 2>$null
    if (-not $VITE_POSTHOG_KEY) {
        Write-Host "WARNING: Could not fetch VITE_POSTHOG_KEY from Secret Manager" -ForegroundColor Yellow
        Write-Host "    PostHog analytics will be disabled" -ForegroundColor Yellow
        $VITE_POSTHOG_KEY = ""
    } else {
        Write-Host "    ✓ Retrieved from Secret Manager" -ForegroundColor Green
    }
} catch {
    Write-Host "WARNING: Error fetching VITE_POSTHOG_KEY: $_" -ForegroundColor Yellow
    $VITE_POSTHOG_KEY = ""
}

# Generate build ID (timestamp-based for local builds)
$BUILD_ID = "manual-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$IMG_LATEST = "$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO/${WEB_SERVICE}:latest"
$IMG_BUILD = "$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO/${WEB_SERVICE}:$BUILD_ID"

Write-Host ""
Write-Host "==> Building frontend Docker image..." -ForegroundColor Cyan
Write-Host "    Build ID: $BUILD_ID" -ForegroundColor Gray
Write-Host ""

# Build the Docker image
docker build $WEB_DIR `
    --file "$WEB_DIR\Dockerfile" `
    --build-arg VITE_GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" `
    --build-arg VITE_API_BASE="$VITE_API_BASE" `
    --build-arg VITE_POSTHOG_KEY="$VITE_POSTHOG_KEY" `
    --build-arg VITE_POSTHOG_HOST="https://us.i.posthog.com" `
    -t "$IMG_LATEST" `
    -t "$IMG_BUILD"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker build failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==> Pushing images to Artifact Registry..." -ForegroundColor Cyan

docker push "$IMG_LATEST"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to push :latest tag" -ForegroundColor Red
    exit 1
}

docker push "$IMG_BUILD"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to push :$BUILD_ID tag" -ForegroundColor Red
    exit 1
}

Write-Host "    ✓ Images pushed successfully" -ForegroundColor Green
Write-Host ""

Write-Host "==> Deploying to Cloud Run..." -ForegroundColor Cyan
Write-Host "    Service: $WEB_SERVICE"
Write-Host "    Image: $IMG_BUILD"
Write-Host ""

gcloud run deploy $WEB_SERVICE `
    --project=$PROJECT_ID `
    --image="$IMG_BUILD" `
    --region=$REGION `
    --platform=managed `
    --allow-unauthenticated

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Cloud Run deployment failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==> ✓ Frontend deployment complete!" -ForegroundColor Green
Write-Host ""

# Get the service URL
Write-Host "==> Service URL:" -ForegroundColor Cyan
gcloud run services describe $WEB_SERVICE `
    --project=$PROJECT_ID `
    --region=$REGION `
    --platform=managed `
    --format="value(status.url)"

Write-Host ""
Write-Host "Done! Your frontend changes are now live." -ForegroundColor Green
