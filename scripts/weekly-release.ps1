param(
    [int]$MaxJobs = 60,
    [ValidateSet("auto", "cpu", "cuda")][string]$Device = "auto"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .venv/Scripts/python.exe -m edgefinance weekly --max-jobs $MaxJobs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .venv/Scripts/python.exe -m edgefinance podcast --device $Device
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .venv/Scripts/python.exe -m edgefinance youtube
exit $LASTEXITCODE
