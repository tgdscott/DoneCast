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

# First verify gcloud is working
try {
  $null = & gcloud --version 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Error "gcloud command is not working properly. Try running 'gcloud --version' manually to diagnose."
  }
} catch {
  Write-Error "Cannot execute gcloud command. Error: $_"
}

if (Test-Path $adcPath) {
  # Try a quick gcloud command to verify credentials are valid
  try {
    $authTest = & gcloud auth application-default print-access-token 2>&1
    if ($LASTEXITCODE -eq 0 -and $authTest -match '^ya29\.') {
      Write-Host "   Existing credentials are valid" -ForegroundColor Green
      $needsAuth = $false
    } else {
      Write-Host "   Existing credentials are expired or invalid" -ForegroundColor Yellow
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
  Write-Host "   Using manual authentication method (avoids localhost port issues)..." -ForegroundColor Gray
  Write-Host "   A URL will be displayed - copy it and paste into your browser to authenticate." -ForegroundColor Gray
  Write-Host ""
  
  try {
    # Use --no-launch-browser to avoid localhost:8085 connection issues
    # This method is more reliable and avoids firewall/port binding problems
    & gcloud auth application-default login --no-launch-browser
    
    if ($LASTEXITCODE -ne 0) {
      Write-Host ""
      Write-Host "   Authentication failed (exit code: $LASTEXITCODE)" -ForegroundColor Red
      Write-Host ""
      Write-Host "   Troubleshooting tips:" -ForegroundColor Yellow
      Write-Host "   1. Make sure you completed the browser authentication flow" -ForegroundColor Gray
      Write-Host "   2. Try running manually: gcloud auth application-default login --no-launch-browser" -ForegroundColor Gray
      Write-Host "   3. Check Windows Firewall settings if using browser-based auth" -ForegroundColor Gray
      Write-Error "Cannot start API without valid Google Cloud credentials."
    } else {
      # Verify credentials actually work
      Write-Host ""
      Write-Host "   Verifying credentials..." -ForegroundColor Gray
      try {
        $verifyToken = & gcloud auth application-default print-access-token 2>&1
        if ($LASTEXITCODE -eq 0 -and $verifyToken -match '^ya29\.') {
          Write-Host "   Google Cloud authentication successful" -ForegroundColor Green
        } else {
          Write-Host "   Warning: Authentication completed but credentials may not be valid" -ForegroundColor Yellow
          Write-Host "   Try running: gcloud auth application-default login --no-launch-browser" -ForegroundColor Yellow
        }
      } catch {
        Write-Host "   Warning: Could not verify credentials: $($_.Exception.Message)" -ForegroundColor Yellow
      }
    }
  } catch {
    $errorDetails = $_.Exception.Message
    Write-Host ""
    Write-Host "   Authentication error: $errorDetails" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Troubleshooting tips:" -ForegroundColor Yellow
    Write-Host "   1. Try running manually: gcloud auth application-default login --no-launch-browser" -ForegroundColor Gray
    Write-Host "   2. Check Windows Firewall settings for localhost ports" -ForegroundColor Gray
    Write-Host "   3. Check if antivirus is blocking localhost connections" -ForegroundColor Gray
    Write-Error "Failed to authenticate with Google Cloud: $errorDetails"
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
  Write-Host ""

  $env:CELERY_EAGER = if ($env:CELERY_EAGER) { $env:CELERY_EAGER } else { '1' }

  & $pythonExe -m uvicorn api.app:app --host $apiHost --port $apiPort --env-file $envFile
} finally {
  Pop-Location
}
