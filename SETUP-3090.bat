@echo off
REM One-click: pull cloud-agent work from GitHub + install vLLM on dual 3090.
REM Double-click this file on your Windows GPU PC (needs Git, Docker Desktop, WSL2).

setlocal
cd /d "%~dp0"

echo.
echo === Sand Casting v2 / vLLM setup for dual RTX 3090 ===
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git not installed. Get it from https://git-scm.com/download/win
  pause
  exit /b 1
)

echo Pulling latest from GitHub...
git fetch origin
git checkout cursor/vllm-abliterated-3090-853d
if errorlevel 1 (
  echo Checkout failed. Trying fresh clone instructions:
  echo   git clone https://github.com/tmophoto/sand_casting_v2.git
  echo   cd sand_casting_v2
  echo   git checkout cursor/vllm-abliterated-3090-853d
  pause
  exit /b 1
)
git pull origin cursor/vllm-abliterated-3090-853d

echo.
echo Starting vLLM install (Docker + model download — first run takes a while)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\vllm-3090\install-and-launch-tailscale.ps1"

echo.
echo Done. API should be at http://localhost:8080/v1
pause
