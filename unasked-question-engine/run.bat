@echo off
REM Windows launcher: double-click or run from a terminal.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 run.py %* & goto :end)
where python >nul 2>nul && (python run.py %* & goto :end)
echo Python was not found. Install Python 3.11 or newer from python.org and tick "Add python.exe to PATH".
:end
pause
