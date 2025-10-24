# Start Cloud SQL Proxy for development
# Connects to production Cloud SQL database on localhost:5433
# Run this BEFORE starting the API in dev mode

$ErrorActionPreference = 'Stop'

Write-Host "Starting Cloud SQL Proxy..." -ForegroundColor Cyan
Write-Host ""

# --- Check Google Cloud authentication status ---
Write-Host "Checking Google Cloud authentication..." -ForegroundColor Cyan

$gcloudCmd = Get-Command gcloud -ErrorAction SilentlyContinue
if ($null -eq $gcloudCmd) {
    Write-Error "gcloud CLI not found. Install Google Cloud SDK first."
}

# Check if ADC credentials exist and are valid
$adcPath = "$env:APPDATA\gcloud\application_default_credentials.json"
$needsAuth = $true

if (Test-Path $adcPath) {
    # Try a quick gcloud command to verify credentials are valid
    try {
        $authTest = & gcloud auth application-default print-access-token 2>&1
        if ($LASTEXITCODE -eq 0 -and $authTest -match '^ya29\.') {
            Write-Host "   Existing credentials are valid" -ForegroundColor Green
            $needsAuth = $false
        }
    } catch {
        Write-Host "   Existing credentials are expired" -ForegroundColor Yellow
    }
}

if ($needsAuth) {
    Write-Host "   Authenticating with Google Cloud..." -ForegroundColor Cyan
    Write-Host "   (Required for Cloud SQL Proxy access)" -ForegroundColor Gray
    Write-Host ""
    
    try {
        & gcloud auth application-default login --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Google Cloud authentication failed. Cannot start proxy without credentials."
        }
        Write-Host "   Google Cloud authentication successful" -ForegroundColor Green
    } catch {
        Write-Error "Failed to authenticate with Google Cloud: $_"
    }
}

Write-Host ""

Write-Host "WARNING: Connecting to PRODUCTION database" -ForegroundColor Yellow
Write-Host "   Connection: podcast612:us-west1:podcast-db" -ForegroundColor Gray
Write-Host "   Local port: 127.0.0.1:5433" -ForegroundColor Gray
Write-Host ""
Write-Host "   Use DEV_READ_ONLY=true in .env.local for safe browsing" -ForegroundColor Red
Write-Host ""

# Check if proxy binary exists
$proxyPath = "C:\Tools\cloud-sql-proxy.exe"
if (-not (Test-Path $proxyPath)) {
    Write-Error "Cloud SQL Proxy not found at $proxyPath. Run setup first."
    exit 1
}

# Check if already running
$existing = Get-Process -Name "cloud-sql-proxy" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Warning "Cloud SQL Proxy already running (PID: $($existing.Id))"
    Write-Host "Stop it with: Stop-Process -Name cloud-sql-proxy" -ForegroundColor Gray
    exit 0
}

Write-Host "Starting proxy..." -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Start the proxy (this will block until stopped)
& $proxyPath --address 127.0.0.1 --port 5433 podcast612:us-west1:podcast-db
