# Unified development environment startup script
# Starts Cloud SQL Proxy, Backend API, and Frontend in separate windows
# Usage: .\scripts\dev_start_all.ps1

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "Starting Podcast Plus Plus Development Environment" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# --- Check Google Cloud authentication status ---
Write-Host "Checking Google Cloud authentication..." -ForegroundColor Yellow

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
    Write-Host "   Authenticating with Google Cloud..." -ForegroundColor Yellow
    Write-Host "   (Required for Cloud SQL Proxy and GCS access)" -ForegroundColor Gray
    Write-Host ""
    
    try {
        & gcloud auth application-default login --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Google Cloud authentication failed. Cannot start dev environment."
        }
        Write-Host "   Google Cloud authentication successful" -ForegroundColor Green
    } catch {
        Write-Error "Failed to authenticate with Google Cloud: $_"
    }
}

Write-Host ""

$repoRoot = Split-Path -Parent $PSScriptRoot

# Check if Cloud SQL Proxy is already running
$proxyRunning = Get-Process -Name "cloud-sql-proxy" -ErrorAction SilentlyContinue
if ($null -eq $proxyRunning) {
    Write-Host "Starting Cloud SQL Proxy..." -ForegroundColor Yellow
    Write-Host "   Opening new window for proxy" -ForegroundColor Gray
    $proxyScript = Join-Path $repoRoot 'scripts\start_sql_proxy.ps1'
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-NoExit",
        "-File", $proxyScript
    )
    Write-Host "   Waiting for proxy to start..." -ForegroundColor Gray
    Start-Sleep -Seconds 3
} else {
    Write-Host "Cloud SQL Proxy already running (PID: $($proxyRunning.Id))" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting Backend API..." -ForegroundColor Yellow
Write-Host "   Opening new window for API server" -ForegroundColor Gray
$apiScript = Join-Path $repoRoot 'scripts\dev_start_api.ps1'
Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-File", $apiScript
)
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "Starting Frontend..." -ForegroundColor Yellow
Write-Host "   Opening new window for Vite dev server" -ForegroundColor Gray
$frontendScript = Join-Path $repoRoot 'scripts\dev_start_frontend.ps1'
Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-File", $frontendScript
)

Write-Host ""
Write-Host "All services starting!" -ForegroundColor Green
Write-Host ""
Write-Host "   Cloud SQL Proxy: localhost:5433 to podcast612:us-west1:podcast-db" -ForegroundColor Gray
Write-Host "   Backend API:     http://127.0.0.1:8000 (docs at /docs)" -ForegroundColor Gray
Write-Host "   Frontend:        http://127.0.0.1:5173" -ForegroundColor Gray
Write-Host ""
Write-Host "WARNING: PRODUCTION DATABASE ACTIVE" -ForegroundColor Red
Write-Host "   DEV_READ_ONLY mode recommended in .env.local" -ForegroundColor Red
Write-Host ""
Write-Host "Press any key to close this window (services will keep running)..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
