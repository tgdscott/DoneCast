# PowerShell helper to start FastAPI (uvicorn) with correct working directory and env file
# Usage: Run from any directory in the repo; it picks absolute paths and uses 127.0.0.1:8000

$ErrorActionPreference = 'Stop'

# Resolve paths
$repoRoot = Split-Path -Parent $PSScriptRoot
# Updated after directory rename
$apiDir = Join-Path $repoRoot 'backend'
$envFile = Join-Path $apiDir '.env.local'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
  Write-Error "Python venv not found at $pythonExe. Activate your venv or run python -m venv .venv first."
}
if (-not (Test-Path $envFile)) {
  Write-Error "Env file not found at $envFile. Create it or copy from sample."
}

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
        # Only populate if not already defined in the environment
        if (-not (Get-ChildItem Env:$name -ErrorAction SilentlyContinue)) {
          Set-Item -Path Env:$name -Value $value
        }
      }
    }
  }

  Import-DotEnv $envFile

  # --- Google ADC (Application Default Credentials) bootstrap ---
  # If the backend is likely to call Google services (Vertex, Cloud Tasks, GCS),
  # verify Application Default Credentials are available. If not, either auto-run
  # an interactive login (when AUTO_GCLOUD_ADC=1) or print a clear instruction.
  $needsGcp = ($env:VERTEX_PROJECT -or $env:VERTEX_PROJECT_ID -or $env:USE_CLOUD_TASKS -or $env:GCS_BUCKET -or $env:GOOGLE_CLOUD_PROJECT)
  $hasStubAI = ([string]::IsNullOrWhiteSpace($env:AI_STUB_MODE) -eq $false -and $env:AI_STUB_MODE -in @('1','true','yes','on'))
  if ($needsGcp -and -not $hasStubAI) {
    $adcOk = $false
    if (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_APPLICATION_CREDENTIALS) -and (Test-Path $env:GOOGLE_APPLICATION_CREDENTIALS)) {
      $adcOk = $true
      Write-Host "[dev_start_api] Using GOOGLE_APPLICATION_CREDENTIALS at $($env:GOOGLE_APPLICATION_CREDENTIALS)"
    } else {
      $gcloudCmd = Get-Command gcloud -ErrorAction SilentlyContinue
      if ($null -ne $gcloudCmd) {
        try {
          $prevEA = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
          $token = & gcloud auth application-default print-access-token
          $ErrorActionPreference = $prevEA
          if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($token)) { $adcOk = $true }
        } catch { $adcOk = $false }
        if (-not $adcOk) {
          if ($env:AUTO_GCLOUD_ADC -in @('1','true','yes','on')) {
            Write-Host "[dev_start_api] No ADC found. Launching 'gcloud auth application-default login'..." -ForegroundColor Yellow
            try {
              & gcloud auth application-default login
              if ($LASTEXITCODE -ne 0) { throw "gcloud ADC login failed with exit code $LASTEXITCODE" }
              $adcOk = $true
            } catch {
              Write-Warning "[dev_start_api] Could not complete ADC login automatically: $_"
            }
          } else {
            Write-Warning "[dev_start_api] Google ADC missing. To enable Google APIs locally, run:";
            Write-Host "    gcloud auth application-default login" -ForegroundColor Cyan
            Write-Host "  Or set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON path." -ForegroundColor Cyan
          }
        }
      } else {
        Write-Warning "[dev_start_api] 'gcloud' not found in PATH; Google APIs may fail locally. Install Google Cloud SDK or set GOOGLE_APPLICATION_CREDENTIALS."
      }
    }
    if ($adcOk) {
      Write-Host "[dev_start_api] Google ADC detected and ready."
    }
  }

  # If no Gemini or Vertex creds are present and developer hasn't explicitly opted out, enable stub mode
  if (-not $env:AI_STUB_MODE) {
    $hasGemini = -not [string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)
    $hasVertex = -not [string]::IsNullOrWhiteSpace($env:VERTEX_PROJECT) -or -not [string]::IsNullOrWhiteSpace($env:VERTEX_PROJECT_ID)
    if (-not $hasGemini -and -not $hasVertex) {
      Write-Host "[dev_start_api] No Gemini/Vertex credentials -> enabling AI_STUB_MODE=1 (stub AI responses)."
      $env:AI_STUB_MODE = '1'
    }
  }
  # Allow overriding API port/host via environment variables (defaults: 127.0.0.1:8000)
  $apiHost = if (-not [string]::IsNullOrWhiteSpace($env:API_HOST)) { $env:API_HOST } else { '127.0.0.1' }
  $apiPort = 8000
  if (-not [string]::IsNullOrWhiteSpace($env:API_PORT)) {
    try { $apiPort = [int]$env:API_PORT } catch { $apiPort = 8000 }
  }
  Write-Host ("[dev_start_api] Starting uvicorn on {0}:{1}" -f $apiHost, $apiPort)
  # In dev, prefer Celery eager mode so background tasks (publish, etc.) run synchronously
  $env:CELERY_EAGER = if ($env:CELERY_EAGER) { $env:CELERY_EAGER } else { '1' }
  & $pythonExe -m uvicorn api.app:app --host $apiHost --port $apiPort --env-file $envFile
} finally {
  Pop-Location
}
