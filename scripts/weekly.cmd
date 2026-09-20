@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" -m edgefinance weekly %*
exit /b %ERRORLEVEL%
