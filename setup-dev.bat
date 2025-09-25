@echo off
setlocal
set VENV_DIR=.venv

echo.
echo =======================================
echo  One-Time Project Setup
echo =======================================
echo.
echo This script will create a Python virtual environment, install all
echo dependencies, and set up your local database.
echo You should only need to run this once.
echo.

echo [1/5] Creating Python virtual environment...
IF NOT EXIST %VENV_DIR%\Scripts\activate.bat (
    echo Creating new venv in '.\%VENV_DIR%'...
    rem Use py launcher to be explicit about version, falling back to generic python
    py -3.12 -m venv %VENV_DIR% > nul 2> nul
    IF %ERRORLEVEL% NEQ 0 (
        echo Trying with 'python' command...
        python -m venv %VENV_DIR%
    )
    IF %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to create virtual environment.
        echo Please ensure Python is installed and in your PATH.
        pause
        exit /b 1
    )
) ELSE (
    echo Virtual environment already exists.
)
echo.

echo [2/5] Activating environment and installing dependencies...
call %VENV_DIR%\Scripts\activate.bat
echo Upgrading pip...
python.exe -m pip install --upgrade pip > nul
echo Installing requirements...
pip install -r backend\requirements.txt
pip install "psycopg[binary]" bcrypt "pydantic>=2.0" "pydantic-settings"
echo Dependencies installed.
echo.

echo [3/5] Starting Docker services (PostgreSQL)...
docker-compose up -d
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Docker failed to start. Is Docker Desktop running?
    pause
    exit /b 1
)
echo Docker services started.
echo.

echo [4/5] Creating database schema...
cd backend
python create_db.py
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Database creation script failed.
    pause
    exit /b 1
)
echo Database schema is current.
echo.

echo [5/5] Seeding database with initial data...
python seed_db.py
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Database seeding script failed.
    pause
    exit /b 1
)
echo Database is seeded.
echo.
cd ..

echo.
echo =================================================================
echo  Setup Complete!
echo =================================================================
echo.
echo Now you can run 'start-dev.bat' to start your servers.
echo.
pause
endlocal