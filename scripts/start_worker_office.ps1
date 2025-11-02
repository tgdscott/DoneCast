<#
PowerShell helper to start the worker on a Windows office machine.
Usage: Run from repository root or call directly. It will use /root/.env or backend/.env.office if present.
#>

Param()

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $repoRoot 'backend')
try {
    $envFile = '/root/.env'
    if (-not (Test-Path $envFile)) {
        $fallback = Join-Path $repoRoot 'backend\.env.office'
        if (Test-Path $fallback) {
            $envFile = $fallback
        } else {
            Write-Host "No /root/.env or backend/.env.office found — starting without --env-file" -ForegroundColor Yellow
            $envFile = ''
        }
    }

    # Prefer repo venv if present
    $pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = 'python'
    }

    $uvicornCmd = "$pythonExe -m uvicorn worker_service:app --host 0.0.0.0 --port 8081"
    if ($envFile -ne '' -and (Test-Path $envFile)) {
        Write-Host "Starting worker with env file: $envFile"
        & $pythonExe -m uvicorn worker_service:app --host 0.0.0.0 --port 8081 --env-file $envFile
    } else {
        Write-Host "Starting worker without env file (expect environment variables to be set)"
        & $pythonExe -m uvicorn worker_service:app --host 0.0.0.0 --port 8081
    }
} finally {
    Pop-Location
}
