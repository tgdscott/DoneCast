@echo off
REM Batch file wrapper to start backend - bypasses PowerShell execution policy
powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\dev_start_api.ps1"
pause


