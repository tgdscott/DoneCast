@echo off
setlocal
REM Always run from the folder where this script lives
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"
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
 
REM [2/4] Optional Docker step — skip if not present or unavailable
IF NOT EXIST docker-compose.yml goto no_docker
echo [2/4] Docker compose file detected. Checking Docker...

REM Check if docker is available
where docker > nul 2> nul
IF %ERRORLEVEL% NEQ 0 (
    echo   'docker' command not found. Skipping Docker steps.
    goto afterDocker
)

REM Try a quiet docker info
docker info > nul 2> nul
IF %ERRORLEVEL% NEQ 0 (
    echo   Docker not running. Attempting to start Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    set retries=0
:pollDocker
    set /A retries+=1
    IF %retries% GTR 12 (
        echo   Timed out waiting for Docker. Continuing without Docker.
        goto afterDocker
    )
    echo   Waiting for Docker daemon... attempt %retries% of 12
    timeout /t 5 /nobreak > nul
    docker info > nul 2> nul
    IF ERRORLEVEL 1 goto pollDocker
    echo   Docker started successfully.
)

REM Check docker-compose availability
where docker-compose > nul 2> nul
IF %ERRORLEVEL% NEQ 0 (
    echo   'docker-compose' not found. Skipping Docker services.
    goto afterDocker
)

echo [3/4] Bringing up Docker services with docker-compose...
docker-compose up -d
IF %ERRORLEVEL% NEQ 0 (
    echo   docker-compose returned an error. Skipping Docker and continuing.
) ELSE (
    echo   Docker services are ready.
)
echo.
goto afterDocker

:no_docker
echo [2/4] No docker-compose.yml found. Skipping Docker steps.

:afterDocker

echo [4/4] Starting API and Frontend servers in new windows...
echo.

REM Start the backend API server in a new window.
start "Podcast Pro Plus API" cmd /k "call %VENV_DIR%\Scripts\activate.bat && cd backend && uvicorn api.main:app --reload --env-file .env.local"

REM Start the frontend development server in a new window.
start "Podcast Pro Plus Frontend" cmd /k "cd frontend && npm run dev"

echo =================================================================
echo  All systems go! Your servers are starting in new windows.
echo =================================================================
echo.
echo You can close this window.
popd
endlocal