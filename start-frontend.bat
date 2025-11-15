@echo off
REM Batch file wrapper to start frontend - bypasses PowerShell execution policy
powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\dev_start_frontend.ps1"
pause


