@echo off
setlocal
echo.
echo =======================================
echo  Stopping Dev Servers
echo =======================================
echo.

REM Try to close the API and Frontend windows started by start-dev.bat
echo [1/3] Stopping API window ("Podcast Plus Plus API")...
taskkill /F /T /FI "WINDOWTITLE eq Podcast Plus Plus API" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo   API window closed.
) else (
  echo   No API window found or already closed.
)

echo [2/3] Stopping Frontend window ("Podcast Plus Plus Frontend")...
taskkill /F /T /FI "WINDOWTITLE eq Podcast Plus Plus Frontend" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo   Frontend window closed.
) else (
  echo   No Frontend window found or already closed.
)

echo [3/3] Bringing down Docker services (if any)...
docker-compose down >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo   Docker services stopped.
) else (
  echo   No docker-compose services to stop or docker not running.
)

echo.
echo All done.
endlocal
