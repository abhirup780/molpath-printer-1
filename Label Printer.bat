@echo off
cd /d "%~dp0"

rem pyw.exe is the windowed Python launcher shipped with python.org installs.
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3 "run.pyw"
    exit /b 0
)

where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe "run.pyw"
    exit /b 0
)

echo Python was not found. Run "1 - Setup.bat" first.
pause
exit /b 1
