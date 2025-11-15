# PowerShell script to start the frontend development server
# Usage: .\start-frontend.ps1
# Alternative: powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1

$ErrorActionPreference = 'Stop'

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Call the existing frontend start script
& (Join-Path $scriptDir "scripts\dev_start_frontend.ps1")

