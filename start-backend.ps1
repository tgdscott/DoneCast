# PowerShell script to start the backend API development server
# Usage: .\start-backend.ps1
# Alternative: powershell -ExecutionPolicy Bypass -File .\start-backend.ps1

$ErrorActionPreference = 'Stop'

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Call the existing backend start script
& (Join-Path $scriptDir "scripts\dev_start_api.ps1")

