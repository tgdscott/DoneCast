$ErrorActionPreference = "Stop"

Write-Host "==> Deploying Podcast Website Routing Fixes" -ForegroundColor Green
Write-Host ""

$PROJECT_ID = "podcast612"
$REGION = "us-west1"

# Step 1: Wildcard Domain Mapping
Write-Host "[1/2] Creating wildcard domain mapping..." -ForegroundColor Yellow
$setupDomain = Read-Host "Create wildcard domain mapping? (y/n)"

if ($setupDomain -eq 'y') {
  Write-Host "Creating domain mapping for *.podcastplusplus.com..." -ForegroundColor Cyan
  try {
    gcloud beta run domain-mappings create --service=podcast-web --domain="*.podcastplusplus.com" --region=$REGION --project=$PROJECT_ID --quiet
    Write-Host "Wildcard domain mapping created." -ForegroundColor Green
  }
  catch {
    Write-Host "Note: Domain mapping might already exist or failed. Check output above." -ForegroundColor Yellow
  }
}

Write-Host ""

# Step 2: Deploy Services
Write-Host "[2/2] Deploying Backend and Frontend..." -ForegroundColor Yellow
$deploy = Read-Host "Deploy services via Cloud Build? (y/n)"

if ($deploy -eq 'y') {
  Write-Host "Triggering Cloud Build deployment..." -ForegroundColor Cyan
  gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID
}

Write-Host ""
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "Next Steps:"
W"2.rTestisubdomain:thtte ://cersiacScfeboys.podcds/pluspluc.aop/"te-Host "2. Test subdomain: https://cardiac-cowboys.podcastplusplus.com/"
    "    proxy_set_header X-Forwarded-Proto `$scheme;",
    "  }",
    "",
    "  # SPA fallback",
    "  location / {",
    "    try_files `$uri /index.html;",
    "  }",
    "}"
)

$nginxLines | Set-Content -Path "frontend/nginx.conf" -Encoding utf8
Write-Host "Updated frontend/nginx.conf to proxy to $apiHost" -ForegroundColor Green

Write-Host ""

# Step 3: Wildcard Domain Mapping
Write-Host "[3/3] Checking Wildcard Domain Mapping..." -ForegroundColor Yellow
$setupDomain = Read-Host "Create wildcard domain mapping? (y/n)"

if ($setupDomain -eq 'y') {
    try {
        gcloud beta run domain-mappings create --service=podcast-web --domain="*.podcastplusplus.com" --region=$REGION --project=$PROJECT_ID --quiet
        Write-Host "Wildcard domain mapping created." -ForegroundColor Green
    }
    catch {
        Write-Host "Note: Domain mapping might already exist. Check output." -ForegroundColor Yellow
    }
}

Write-Host ""

# Step 4: Deploy
$deploy = Read-Host "Deploy updated frontend? (y/n)"

if ($deploy -eq 'y') {
    Write-Host "Triggering Cloud Build..." -ForegroundColor Cyan
    gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "1. RSS Feed should work IMMEDIATELY after deployment."
Write-Host "2. Subdomains (*.podcastplusplus.com) will take 10-15 mins for SSL."
