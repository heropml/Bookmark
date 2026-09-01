@echo off
set "PY=%~dp0..\..\runtime\python\python.exe"
cd /d "%~dp0..\.."
if not exist "%PY%" (
  echo Portable Python not found: runtime\python\python.exe
  pause
  exit /b 1
)
if "%~1"=="" (
  "%PY%" -X utf8 "%~dp0..\..\scripts\manage.py" --replace "%~dp0..\..\data\bookmarks.html"
) else (
  "%PY%" -X utf8 "%~dp0..\..\scripts\manage.py" --replace "%~1"
)
echo.
pause
