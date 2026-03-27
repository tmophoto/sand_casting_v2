@echo off
echo Building executable with PyInstaller...
pyinstaller --onefile --windowed --name "SandCastingSim" ^
    --icon=NONE ^
    --add-data "README.md;." ^
    casting_sim.py
