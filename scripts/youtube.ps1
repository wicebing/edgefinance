param([switch]$PlanOnly)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$arguments = @("-m", "edgefinance", "youtube")
if ($PlanOnly) { $arguments += "--plan-only" }
& .venv/Scripts/python.exe @arguments
exit $LASTEXITCODE
