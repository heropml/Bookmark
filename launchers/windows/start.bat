@echo off
cd /d "%~dp0..\.."

set "PY="
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Launcher\py.exe" set "PY=%LocalAppData%\Programs\Python\Launcher\py.exe"
if not defined PY (
  where python >nul 2>&1 && for /f "delims=" %%I in ('where python') do if not defined PY set "PY=%%I"
)

if not defined PY (
  echo Python not found.
  echo Install Python 3, or add python.exe to PATH.
  pause
  exit /b 1
)

"%PY%" -X utf8 "%~dp0..\..\scripts\manage.py"
if errorlevel 1 (
  echo start failed
  pause
)
