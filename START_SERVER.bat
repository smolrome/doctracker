@echo off
title DepEd Leyte Division - Document Tracker Server
color 0A
echo.
echo  =====================================================
echo   DepEd Leyte Division - Document Tracker
echo   Starting server...
echo  =====================================================
echo.

cd /d "%~dp0"

REM Try to activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python app.py

echo.
echo  Server stopped. Press any key to exit.
pause >nul
