# PowerShell script to start all development services (Cloud SQL Proxy, Backend API, and Frontend)
# Usage: .\start-all.ps1
# Alternative: powershell -ExecutionPolicy Bypass -File .\start-all.ps1

$ErrorActionPreference = 'Stop'

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Call the existing all-in-one start script
& (Join-Path $scriptDir "scripts\dev_start_all.ps1")

