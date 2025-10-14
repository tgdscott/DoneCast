# Quick restart script for testing the music upload fix
# Run this from the PodWebDeploy directory

Write-Host "Music Upload Fix - Restarting API Server" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

# Check if in correct directory
if (-not (Test-Path "backend\api\routers\admin\music.py")) {
    Write-Host "ERROR: Please run this from the PodWebDeploy root directory" -ForegroundColor Red
    exit 1
}

Write-Host "1. Checking for running API processes..." -ForegroundColor Yellow
$uvicornProcesses = Get-Process | Where-Object { $_.ProcessName -like "*python*" -or $_.ProcessName -like "*uvicorn*" }
if ($uvicornProcesses) {
    Write-Host "   Found running processes. You may need to stop them manually." -ForegroundColor Yellow
    $uvicornProcesses | Format-Table Id, ProcessName, CPU -AutoSize
}

Write-Host ""
Write-Host "2. To restart the API server:" -ForegroundColor Cyan
Write-Host "   Option A - If using VS Code tasks:" -ForegroundColor White
Write-Host "      Press Ctrl+Shift+P -> 'Tasks: Run Task' -> 'Start API (dev)'" -ForegroundColor White
Write-Host ""
Write-Host "   Option B - Manual start:" -ForegroundColor White
Write-Host "      cd backend" -ForegroundColor White
Write-Host "      uvicorn api.app:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host ""
Write-Host "3. After restart, test the upload:" -ForegroundColor Cyan
Write-Host "   - Go to Admin Panel -> Music Library" -ForegroundColor White
Write-Host "   - Click 'Add New'" -ForegroundColor White
Write-Host "   - Upload an MP3 file" -ForegroundColor White
Write-Host "   - Check browser console for any errors" -ForegroundColor White
Write-Host ""
Write-Host "4. What was fixed:" -ForegroundColor Green
Write-Host "   - File: backend/api/routers/admin/music.py" -ForegroundColor White
Write-Host "   - Changed endpoint from sync to async" -ForegroundColor White
Write-Host "   - Added proper file reading with await file.read()" -ForegroundColor White
Write-Host "   - Added temp file handling for GCS uploads" -ForegroundColor White
Write-Host "   - Enhanced error logging" -ForegroundColor White
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
