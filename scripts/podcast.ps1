param(
    [ValidateSet("auto", "cpu", "cuda")][string]$Device = "auto",
    [switch]$ScriptOnly,
    [switch]$ForceScript
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$arguments = @("-m", "edgefinance", "podcast", "--device", $Device)
if ($ScriptOnly) { $arguments += "--script-only" }
if ($ForceScript) { $arguments += "--force-script" }
& .venv/Scripts/python.exe @arguments
exit $LASTEXITCODE
