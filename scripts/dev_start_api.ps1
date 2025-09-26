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
  # If no Gemini key is present and developer hasn't explicitly opted out, enable stub mode
  if (-not $env:GEMINI_API_KEY -and -not $env:AI_STUB_MODE) {
    Write-Host "[dev_start_api] GEMINI_API_KEY not set -> enabling AI_STUB_MODE=1 (stub AI responses)."
    $env:AI_STUB_MODE = '1'
  }
  # Standardize on port 8000 (was briefly 8010); frontend proxy and other scripts expect 8000
  & $pythonExe -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --env-file $envFile
} finally {
  Pop-Location
}
