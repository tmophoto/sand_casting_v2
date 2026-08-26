@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  Sand Casting Simulator - GPU Build (PyVista + RTX 3090)
echo ============================================================
echo.
echo  This build includes PyVista/VTK for GPU-accelerated OpenGL.
echo  Output size: ~400-700 MB (VTK DLLs are large).
echo.
echo  CuPy (CUDA array acceleration) is NOT bundled here because
echo  it must match your exact CUDA version. After building, run:
echo    pip install cupy-cuda12x
echo  on the target machine and the app will use it automatically.
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.10+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo Found: %%v

:: ── Install dependencies ─────────────────────────────────────────────────────
echo.
echo [1/4] Installing base dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 ( echo ERROR: requirements.txt failed. & pause & exit /b 1 )

echo [2/4] Installing PyVista + pyvistaqt...
pip install pyvista pyvistaqt --quiet
if errorlevel 1 (
    echo ERROR: Could not install pyvista/pyvistaqt.
    echo Make sure you have an internet connection and pip is up to date:
    echo   pip install --upgrade pip
    pause & exit /b 1
)

pip install pyinstaller --quiet
if errorlevel 1 ( echo ERROR: Could not install PyInstaller. & pause & exit /b 1 )
echo       Done.

:: ── Clean previous GPU build ─────────────────────────────────────────────────
echo.
echo [3/4] Cleaning previous GPU build output...
if exist "dist\SandCastingSim_GPU"  rmdir /s /q "dist\SandCastingSim_GPU"
if exist "build\SandCastingSim_GPU" rmdir /s /q "build\SandCastingSim_GPU"
echo       Done.

:: ── Build ────────────────────────────────────────────────────────────────────
echo.
echo [4/4] Building GPU executable (may take 3-8 minutes, VTK is large)...
echo       Please wait...
echo.
pyinstaller SandCastingSim_GPU.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: Build failed. Common fixes:
    echo   - pip install pyvista pyvistaqt --upgrade
    echo   - pip install pyinstaller --upgrade
    echo   - Check that pyvista imports cleanly: python -c "import pyvista"
    pause & exit /b 1
)

:: ── Success ───────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  GPU Build complete!
echo.
echo  Executable : dist\SandCastingSim_GPU\SandCastingSim.exe
echo  To share   : zip the entire dist\SandCastingSim_GPU\ folder
echo.
echo  For CuPy CUDA array acceleration on the target machine:
echo    pip install cupy-cuda12x   (adjust version to match CUDA)
echo  The app detects CuPy automatically at startup.
echo ============================================================
echo.

set /p launch="Launch GPU app now to test? (y/n): "
if /i "!launch!"=="y" (
    start "" "dist\SandCastingSim_GPU\SandCastingSim.exe"
)

pause
