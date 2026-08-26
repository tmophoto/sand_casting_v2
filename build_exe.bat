@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  Sand Casting Simulator - Windows Build
echo ============================================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.10+ from https://python.org and make sure
    echo "Add Python to PATH" is checked during setup.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo Found: %%v

:: ── Install / upgrade runtime dependencies ───────────────────────────────────
echo.
echo [1/3] Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install requirements.txt dependencies.
    pause & exit /b 1
)

pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Could not install PyInstaller.
    pause & exit /b 1
)
echo       Done.

:: ── Clean previous build ─────────────────────────────────────────────────────
echo.
echo [2/3] Cleaning previous build output...
if exist "dist\SandCastingSim"  rmdir /s /q "dist\SandCastingSim"
if exist "build\SandCastingSim" rmdir /s /q "build\SandCastingSim"
echo       Done.

:: ── Run PyInstaller with the spec file ───────────────────────────────────────
echo.
echo [3/3] Building executable (this usually takes 1-3 minutes)...
echo       Please wait...
echo.
pyinstaller SandCastingSim.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See messages above for details.
    echo.
    echo Common fixes:
    echo   - Run:  pip install pyinstaller --upgrade
    echo   - If a module is missing, add it to hiddenimports in SandCastingSim.spec
    pause & exit /b 1
)

:: ── Success ───────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Build complete!
echo.
echo  Executable : dist\SandCastingSim\SandCastingSim.exe
echo  To share   : zip the entire dist\SandCastingSim\ folder
echo               (the .exe needs the DLLs next to it)
echo ============================================================
echo.

:: Offer to launch immediately for a quick smoke-test
set /p launch="Launch app now to test? (y/n): "
if /i "!launch!"=="y" (
    start "" "dist\SandCastingSim\SandCastingSim.exe"
)

pause
