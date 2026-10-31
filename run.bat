@echo off
title PlayStation Accessories - Open Source Edition
echo =========================================================
echo    Avvio PlayStation Accessories (Open Source Edition)
echo =========================================================
echo.

python "%~dp0app\main.py"

if errorlevel 1 (
    echo.
    echo Si e verificato un errore durante l'avvio.
    pause
)
