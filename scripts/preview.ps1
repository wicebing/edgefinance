$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .venv/Scripts/python.exe -m edgefinance serve
