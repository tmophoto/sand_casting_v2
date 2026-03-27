@echo off
cd /d "%~dp0"

echo Checking dependencies...
pip show PyQt6 >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: pip install failed. Make sure Python is in your PATH.
        pause
        exit /b 1
    )
)

echo Launching Sand Casting Simulator...
python casting_sim.py
if errorlevel 1 (
    echo.
    echo ERROR: App crashed. See above for details.
    pause
)
