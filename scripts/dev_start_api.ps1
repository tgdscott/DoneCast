# PowerShell helper to start FastAPI (uvicorn) with correct working directory and env file
# Usage: Run from any directory in the repo; it picks absolute paths and uses 127.0.0.1:8000

$ErrorActionPreference = 'Stop'

# Resolve paths
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot 'backend'
$envFile = Join-Path $apiDir '.env.local'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
  Write-Error "Python venv not found at $pythonExe. Activate your venv or run python -m venv .venv first."
}
if (-not (Test-Path $envFile)) {
  Write-Error "Env file not found at $envFile. Create it or copy from sample."
}

# --- Check Google Cloud authentication status ---
Write-Host ""
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
    # Credentials exist but invalid, need re-auth
    Write-Host "   Existing credentials are expired" -ForegroundColor Yellow
  }
}

if ($needsAuth) {
  Write-Host "   Authenticating with Google Cloud..." -ForegroundColor Cyan
  Write-Host "   (Required for Cloud SQL Proxy and GCS access)" -ForegroundColor Gray
  Write-Host ""
  
  try {
    & gcloud auth application-default login --quiet
    if ($LASTEXITCODE -ne 0) {
      Write-Error "Google Cloud authentication failed. Cannot start API without credentials."
    }
    Write-Host "   Google Cloud authentication successful" -ForegroundColor Green
  } catch {
    Write-Error "Failed to authenticate with Google Cloud: $_"
  }
}

Write-Host ""

Push-Location $apiDir
try {
  # Import .env variables into the current PowerShell environment so checks see them
  function Import-DotEnv([string]$path) {
    if (-not (Test-Path $path)) { return }
    Get-Content -Path $path | ForEach-Object {
      $line = $_.Trim()
      if (-not $line) { return }
      if ($line.StartsWith('#')) { return }
      if ($line.StartsWith('export ')) { $line = $line.Substring(7) }
      $idx = $line.IndexOf('=')
      if ($idx -lt 1) { return }
      $name = $line.Substring(0, $idx).Trim()
      $value = $line.Substring($idx + 1).Trim()
      if ($value.StartsWith('"') -and $value.EndsWith('"')) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      if (-not [string]::IsNullOrWhiteSpace($name)) {
        if (-not (Get-ChildItem Env:$name -ErrorAction SilentlyContinue)) {
          Set-Item -Path Env:$name -Value $value
        }
      }
    }
  }

  Import-DotEnv $envFile

  Write-Host "Google Cloud credentials ready" -ForegroundColor Green
  
  # Check if CELERY_EAGER is in .env.local file (even if not set as env var)
  $celeryEagerInFile = $false
  if (Test-Path $envFile) {
    try {
      $envLines = Get-Content -Path $envFile -ErrorAction SilentlyContinue
      foreach ($line in $envLines) {
        $trimmed = $line.Trim()
        if ($trimmed -and -not $trimmed.StartsWith('#')) {
          if ($trimmed -match '^CELERY_EAGER\s*=') {
            # Found CELERY_EAGER line - extract value and check if it's 1 or true
            $value = ($trimmed -split '=', 2)[1].Trim().Trim('"').Trim("'")
            if ($value -eq '1' -or $value -eq 'true') {
              $celeryEagerInFile = $true
              break
            }
          }
        }
      }
    } catch {
      # Ignore errors reading the file
    }
  }

  # Auto-whitelist current IP for Cloud SQL direct access (no proxy needed)
  Write-Host ""
  Write-Host "Checking Cloud SQL IP whitelist..." -ForegroundColor Cyan
  try {
    # Use /ip endpoint to get ONLY the IP address (not HTML)
    $myIP = (Invoke-WebRequest -Uri "https://ifconfig.me/ip" -UseBasicParsing -TimeoutSec 3).Content.Trim()
    if ($myIP -match '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$') {
      Write-Host "   Your public IP: $myIP" -ForegroundColor Gray
      
      # Get current authorized networks
      $currentNets = gcloud sql instances describe podcast-db --project=podcast612 --format="value(settings.ipConfiguration.authorizedNetworks[].value)" 2>&1
      
      if ($currentNets -match $myIP) {
        Write-Host "   IP already whitelisted" -ForegroundColor Green
      } else {
        Write-Host "   Adding IP to authorized networks..." -ForegroundColor Yellow
        # Append to existing networks (comma-separated list)
        $allNets = if ($currentNets) { "$currentNets,$myIP" } else { $myIP }
        $patchResult = gcloud sql instances patch podcast-db --authorized-networks="$allNets" --project=podcast612 --quiet 2>&1
        if ($LASTEXITCODE -eq 0) {
          Write-Host "   IP whitelisted successfully" -ForegroundColor Green
        } else {
          Write-Host "   Failed to whitelist IP (continuing anyway)" -ForegroundColor Yellow
        }
      }
    } else {
      Write-Host "   Could not detect valid public IP (continuing anyway)" -ForegroundColor Yellow
    }
  } catch {
    Write-Host "   Could not check/whitelist IP: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   (Continuing - you may need to manually whitelist)" -ForegroundColor Gray
  }
  Write-Host ""

  # Check for AI credentials
  $aiStubMode = $env:AI_STUB_MODE
  if ([string]::IsNullOrWhiteSpace($aiStubMode)) {
    $geminiKey = $env:GEMINI_API_KEY
    $vertexProject = $env:VERTEX_PROJECT
    $vertexProjectId = $env:VERTEX_PROJECT_ID
    
    $hasGemini = -not [string]::IsNullOrWhiteSpace($geminiKey)
    $hasVertex = (-not [string]::IsNullOrWhiteSpace($vertexProject)) -or (-not [string]::IsNullOrWhiteSpace($vertexProjectId))
    
    if ((-not $hasGemini) -and (-not $hasVertex)) {
      Write-Host "No Gemini/Vertex credentials - enabling AI stub mode" -ForegroundColor Yellow
      $env:AI_STUB_MODE = '1'
    }
  }

  # Set host and port
  $apiHost = if (-not [string]::IsNullOrWhiteSpace($env:API_HOST)) { $env:API_HOST } else { '127.0.0.1' }
  $apiPort = 8000
  if (-not [string]::IsNullOrWhiteSpace($env:API_PORT)) {
    try { $apiPort = [int]$env:API_PORT } catch { $apiPort = 8000 }
  }

  Write-Host ""
  Write-Host "Starting uvicorn" -ForegroundColor Cyan
  Write-Host "Host: $apiHost" -ForegroundColor Gray
  Write-Host "Port: $apiPort" -ForegroundColor Gray
  
  # Check worker server configuration
  $workerUrl = $env:WORKER_URL_BASE
  $useWorkerInDev = $env:USE_WORKER_IN_DEV
  $celeryEager = $env:CELERY_EAGER
  $allowInlineFallback = $env:ALLOW_ASSEMBLY_INLINE_FALLBACK
  
  Write-Host ""
  Write-Host "Episode Assembly Configuration:" -ForegroundColor Cyan
  
  # Check if worker server is properly configured
  $workerConfigured = $workerUrl -and ($useWorkerInDev -eq 'true' -or $useWorkerInDev -eq '1')
  
  Write-Host "  WORKER_URL_BASE: $(if ($workerUrl) { $workerUrl } else { 'not set' })" -ForegroundColor $(if ($workerUrl) { 'Green' } else { 'Yellow' })
  Write-Host "  USE_WORKER_IN_DEV: $(if ($useWorkerInDev) { $useWorkerInDev } else { 'not set (default: false)' })" -ForegroundColor $(if ($useWorkerInDev -eq 'true' -or $useWorkerInDev -eq '1') { 'Green' } else { 'Yellow' })
  
  # CELERY_EAGER is completely ignored - assembly code doesn't use it anymore
  # Episodes always go through worker server or Cloud Tasks when configured
  if ($workerConfigured) {
    # Worker is configured - episodes will go to worker server
    Write-Host ""
    Write-Host "  ✅ Worker server configured - episodes will be sent to worker server" -ForegroundColor Green
    if ($celeryEager -or $celeryEagerInFile) {
      $source = if ($celeryEagerInFile) { " (in .env.local file)" } else { " (environment variable)" }
      Write-Host "     Note: CELERY_EAGER is set$source but has no effect - worker server is used instead" -ForegroundColor Gray
    }
  } else {
    # Worker is NOT configured - CELERY_EAGER would matter, but inline processing is disabled anyway
    if ($celeryEager -or $celeryEagerInFile) {
      $source = if ($celeryEagerInFile) { " (found in .env.local file)" } else { " (from environment)" }
      Write-Host "  CELERY_EAGER: $(if ($celeryEager) { $celeryEager } else { '1' })$source" -ForegroundColor Yellow
    } else {
      Write-Host "  CELERY_EAGER: not set" -ForegroundColor Gray
    }
    
    if (-not $workerUrl) {
      Write-Host ""
      Write-Host "  ❌ No WORKER_URL_BASE configured - episodes will NOT process" -ForegroundColor Red
      Write-Host "     Inline processing is disabled. Set WORKER_URL_BASE to use worker server" -ForegroundColor Yellow
    } elseif ($useWorkerInDev -ne 'true' -and $useWorkerInDev -ne '1') {
      Write-Host ""
      Write-Host "  ❌ USE_WORKER_IN_DEV is not enabled - episodes will NOT process" -ForegroundColor Red
      Write-Host "     Set USE_WORKER_IN_DEV=true to enable worker server in dev mode" -ForegroundColor Yellow
    }
  }
  
  Write-Host ""

  & $pythonExe -m uvicorn api.app:app --host $apiHost --port $apiPort --env-file $envFile
} finally {
  Pop-Location
}
