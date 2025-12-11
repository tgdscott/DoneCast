# Quick deployment script for audio upload fix
# Deploys the fix for AttributeError: 'str' object has no attribute 'hex'

Write-Host "Deploying audio upload fix..." -ForegroundColor Cyan

# Navigate to backend directory
Set-Location -Path "c:\Users\windo\OneDrive\PodWebDeploy"

# Add the changed file
Write-Host "Staging changes..." -ForegroundColor Yellow
git add backend/api/routers/media.py

# Commit with descriptive message
Write-Host "Committing fix..." -ForegroundColor Yellow
git commit -m "fix: Handle current_user.id as string in presign_upload

Fixed AttributeError where current_user.id.hex failed because id is already
a string in some contexts. Now properly handles both UUID objects and strings
by converting to string and removing hyphens.

Fixes audio upload 500 error affecting all users."

# Push to trigger deployment
Write-Host "Pushing to production..." -ForegroundColor Yellow
git push

Write-Host "`nFix deployed! Audio uploads should work now." -ForegroundColor Green
Write-Host "Monitor logs at: https://console.cloud.google.com/logs" -ForegroundColor Cyan
