@echo off
setlocal
cd /d "%~dp0..\.."
"runtime\python\python.exe" -B -X utf8 scripts\build_installer.py %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo Installer build failed.
pause
exit /b %BUILD_RESULT%
