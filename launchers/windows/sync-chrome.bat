@echo off
cd /d "%~dp0..\.."
python -X utf8 "%~dp0..\..\scripts\manage.py" --sync-chrome --build
echo.
pause
