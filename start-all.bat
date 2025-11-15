@echo off
REM Batch file wrapper to start all services - bypasses PowerShell execution policy
powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\dev_start_all.ps1"
pause


