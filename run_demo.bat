@echo off
rem Double-click for a simulated election night (no live sources needed).
cd /d "%~dp0"
where py >nul 2>nul && (py -3 run_local.py --demo --reset) || (python run_local.py --demo --reset)
pause
