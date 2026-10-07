@echo off
REM Dual 3090 + max context launcher (Windows). Run from this folder.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-max-context.ps1" %*
