@echo off
setlocal
set VENV_DIR=.venv

echo.
echo =======================================
echo  Starting Daily Development Servers
echo =======================================
echo.
 
echo [1/4] Activating virtual environment...
IF NOT EXIST %VENV_DIR%\Scripts\activate.bat (
    echo ERROR: Virtual environment not found in '.\%VENV_DIR%'.
    echo Please run setup-dev.bat first to create it.
    pause
    exit /b 1
)
call %VENV_DIR%\Scripts\activate.bat
echo.
 
echo [2/4] Checking Docker status...

REM Check if Docker is running by trying a quiet command.
docker info > nul 2> nul
IF %ERRORLEVEL% EQU 0 (
    echo Docker is already running.
    goto :dockerReady
)

echo Docker is not running. Attempting to start Docker Desktop...
REM The path to Docker Desktop might vary. This is the default location.
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

REM Wait for the Docker daemon to initialize, with a timeout.
set /a "retries=0"
:waitForDocker
set /a "retries+=1"
if %retries% gtr 12 (
    echo.
    echo ERROR: Docker Desktop did not start within 60 seconds.
    echo Please start it manually and run this script again.
    pause
    exit /b 1
)

echo Waiting for Docker daemon... (attempt %retries%/12)
timeout /t 5 /nobreak > nul
docker info > nul 2> nul
IF %ERRORLEVEL% NEQ 0 (
    goto :waitForDocker
)

echo Docker started successfully.
echo.

:dockerReady
echo [3/4] Ensuring Docker services are running...
docker-compose up -d

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: docker-compose failed to start services.
    pause
    exit /b 1
)
echo Docker services are ready.
echo.

echo [4/4] Starting API and Frontend servers in new windows...
echo.

REM Start the backend API server in a new window.
start "Podcast Pro Plus API" cmd /k "call %VENV_DIR%\Scripts\activate.bat && cd podcast-pro-plus && uvicorn api.main:app --reload --env-file .env.local"

REM Start the frontend development server in a new window.
start "Podcast Pro Plus Frontend" cmd /k "cd frontend && npm run dev"

echo =================================================================
echo  All systems go! Your servers are starting in new windows.
echo =================================================================
echo.
echo You can close this window.
endlocal