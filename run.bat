@echo off
title PlayStation Accessories - Open Source Edition V3.0
echo =========================================================
echo    Avvio PlayStation Accessories (Open Source Edition)
echo =========================================================
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0app\main.py" %*
) else (
    python "%~dp0app\main.py" %*
)

if errorlevel 1 (
    echo.
    echo Si e verificato un errore durante l'avvio.
    pause
)
