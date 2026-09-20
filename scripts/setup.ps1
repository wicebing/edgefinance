$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv/Scripts/python.exe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& .venv/Scripts/python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .venv/Scripts/python.exe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ttsVendor = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "tts\vendor_coqui311"
$ttsPython = if ($env:EDGEFINANCE_PODCAST_PYTHON) { $env:EDGEFINANCE_PODCAST_PYTHON } else { Join-Path $env:USERPROFILE "anaconda3\python.exe" }
if ((Test-Path $ttsVendor) -and (Test-Path $ttsPython)) {
    & $ttsPython -c "import sys; sys.path.insert(0, r'$ttsVendor'); import pypinyin"
    if ($LASTEXITCODE -ne 0) {
        & $ttsPython -m pip install --target $ttsVendor "pypinyin>=0.55,<0.56"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
& .venv/Scripts/python.exe -m edgefinance doctor
