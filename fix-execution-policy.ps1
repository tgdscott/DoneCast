# Helper script to fix PowerShell execution policy
# Run this script with: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
# Or run this command in an elevated PowerShell window

Write-Host "Checking current execution policy..." -ForegroundColor Cyan
$currentPolicy = Get-ExecutionPolicy -Scope CurrentUser
Write-Host "Current User Policy: $currentPolicy" -ForegroundColor Yellow

if ($currentPolicy -eq "Restricted") {
    Write-Host ""
    Write-Host "Execution policy is set to Restricted. Fixing..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To fix this, run the following command in PowerShell (as Administrator if needed):" -ForegroundColor Cyan
    Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" -ForegroundColor Green
    Write-Host ""
    Write-Host "This will allow you to run local scripts while still requiring downloaded scripts to be signed." -ForegroundColor Gray
    Write-Host ""
    
    # Try to set it for current user (doesn't require admin)
    try {
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
        Write-Host "Successfully set execution policy to RemoteSigned for CurrentUser!" -ForegroundColor Green
        Write-Host ""
        Write-Host "You can now run your start scripts:" -ForegroundColor Green
        Write-Host "  .\start-frontend.ps1" -ForegroundColor Gray
        Write-Host "  .\start-backend.ps1" -ForegroundColor Gray
        Write-Host "  .\start-all.ps1" -ForegroundColor Gray
    } catch {
        Write-Host "Could not automatically set policy. Please run manually:" -ForegroundColor Red
        Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" -ForegroundColor Yellow
    }
} else {
    Write-Host "Execution policy is already set to: $currentPolicy" -ForegroundColor Green
    Write-Host "You should be able to run scripts. If not, try:" -ForegroundColor Yellow
    Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" -ForegroundColor Gray
}


