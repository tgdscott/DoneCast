# Quick Start Guide for Development

## Starting Development Servers

You have **three easy options** to start the development servers:

### Option 1: Use Batch Files (Easiest - No PowerShell Issues)
Just double-click or run:
```batch
start-all.bat
```
Or individually:
```batch
start-frontend.bat
start-backend.bat
```

### Option 2: Run PowerShell with Bypass Flag
```powershell
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
```
Or individually:
```powershell
powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
```

### Option 3: Set Execution Policy (Permanent Fix)
If you want to run PowerShell scripts directly without flags:

1. Open PowerShell as Administrator (or just regular PowerShell for CurrentUser scope)
2. Run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```
3. Then you can run:
```powershell
.\start-all.ps1
```

## What Each Script Does

- **start-all.bat / start-all.ps1**: Starts Cloud SQL Proxy, Backend API, and Frontend in separate windows
- **start-backend.bat / start-backend.ps1**: Starts only the Backend API server (http://127.0.0.1:8000)
- **start-frontend.bat / start-frontend.ps1**: Starts only the Frontend dev server (http://127.0.0.1:5173)

## Recommended: Use the Batch Files
The `.bat` files bypass all PowerShell execution policy issues and work immediately!


