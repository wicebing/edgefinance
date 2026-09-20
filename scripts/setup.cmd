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
set "TTS_VENDOR=%~dp0..\..\tts\vendor_coqui311"
set "TTS_PYTHON=%EDGEFINANCE_PODCAST_PYTHON%"
if not defined TTS_PYTHON set "TTS_PYTHON=%USERPROFILE%\anaconda3\python.exe"
if exist "%TTS_VENDOR%" if exist "%TTS_PYTHON%" (
  "%TTS_PYTHON%" -c "import sys; sys.path.insert(0, r'%TTS_VENDOR%'); import pypinyin" 2>nul
  if errorlevel 1 (
    "%TTS_PYTHON%" -m pip install --target "%TTS_VENDOR%" "pypinyin>=0.55,<0.56"
    if errorlevel 1 exit /b %ERRORLEVEL%
  )
)
".venv\Scripts\python.exe" -m edgefinance doctor
exit /b %ERRORLEVEL%
