@echo off
rem Double-click to run the tracker locally with live sources.
rem For a simulated night use: run_local.bat --demo
cd /d "%~dp0"
where py >nul 2>nul && (py -3 run_local.py %*) || (python run_local.py %*)
pause
