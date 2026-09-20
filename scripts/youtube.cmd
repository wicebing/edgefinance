@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" -m edgefinance youtube %*
exit /b %ERRORLEVEL%
