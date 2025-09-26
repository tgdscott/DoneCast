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
  Write-Host "[dev_start_api] Starting uvicorn on $apiHost:$apiPort"
  & $pythonExe -m uvicorn api.main:app --host $apiHost --port $apiPort --env-file $envFile
} finally {
  Pop-Location
}
