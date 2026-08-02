@echo off
cd /d "%~dp0"
title Tube Label Printer - Setup

echo ============================================
echo  Tube Label Printer - one-time setup
echo ============================================
echo.

py -3 --version >nul 2>&1
if errorlevel 1 goto nopython

echo Installing the two libraries the app needs...
echo.
py -3 -m pip install --upgrade --quiet pip
py -3 -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto pipfailed

echo.
echo Creating a Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Tube Label Printer.lnk');" ^
  "$s.TargetPath=(Get-Command pythonw.exe).Source; $s.Arguments='\"%CD%\run.pyw\"';" ^
  "$s.WorkingDirectory='%CD%'; $s.Description='Print Eppendorf tube labels'; $s.Save()"

echo.
echo Done. Now run "2 - Check Setup.bat" to confirm the printer is seen.
echo.
pause
exit /b 0

:nopython
echo.
echo  Python is not installed on this PC.
echo.
echo  Install Python 3.10 or newer from https://www.python.org/downloads/
echo  IMPORTANT: tick "Add Python to PATH" on the first screen of the installer.
echo.
echo  Then run this file again.
echo.
pause
exit /b 1

:pipfailed
echo.
echo  Could not install the libraries. If this PC is behind a proxy, ask IT
echo  for the proxy address and run:
echo.
echo     py -3 -m pip install --proxy http://PROXY:PORT -r requirements.txt
echo.
pause
exit /b 1
