param([int]$MaxJobs = 60)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .venv/Scripts/python.exe -m edgefinance weekly --max-jobs $MaxJobs
exit $LASTEXITCODE
