# PowerShell helper to start the Vite dev server with correct proxy to 127.0.0.1:8000
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$feDir = Join-Path $repoRoot 'frontend'
Push-Location $feDir
try {
  if (Test-Path (Join-Path $feDir 'node_modules')) {
    npm run dev
  } else {
    npm install; npm run dev
  }
} finally {
  Pop-Location
}
