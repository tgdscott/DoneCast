# PowerShell helper to stop common dev servers (uvicorn and vite) by port
# Note: This is best-effort and Windows-specific
$ErrorActionPreference = 'SilentlyContinue'

$ports = @(8000, 5173)
foreach ($p in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    try {
      $procId = $c.OwningProcess
      if ($procId) {
        Write-Host "Stopping process on port $p (PID $procId)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
      }
    } catch {}
  }
}
