@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 exit /b %ERRORLEVEL%
)
".venv\Scripts\python.exe" -m pip install -r requirements.lock
if errorlevel 1 exit /b %ERRORLEVEL%
".venv\Scripts\python.exe" -m pip install --no-deps -e .
if errorlevel 1 exit /b %ERRORLEVEL%
".venv\Scripts\python.exe" -m edgefinance doctor
exit /b %ERRORLEVEL%
