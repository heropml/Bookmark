@echo off
cd /d "%~dp0..\.."
if "%~1"=="" (
  python -X utf8 "%~dp0..\..\scripts\manage.py" --replace
) else (
  python -X utf8 "%~dp0..\..\scripts\manage.py" --replace "%~1"
)
echo.
pause
