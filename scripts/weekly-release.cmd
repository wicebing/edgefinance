@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" -m edgefinance weekly %*
if errorlevel 1 exit /b %ERRORLEVEL%
".venv\Scripts\python.exe" -m edgefinance podcast
if errorlevel 1 exit /b %ERRORLEVEL%
".venv\Scripts\python.exe" -m edgefinance youtube
exit /b %ERRORLEVEL%
