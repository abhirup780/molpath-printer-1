@echo off
cd /d "%~dp0"
title Tube Label Printer - Setup Check

py -3 -m labelprint.doctor %*

echo.
echo ----------------------------------------------------------------
echo  To also send one real test feed to the printer, run:
echo     "2 - Check Setup.bat" --test-print
echo ----------------------------------------------------------------
echo.
pause
