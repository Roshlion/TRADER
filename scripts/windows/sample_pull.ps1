# Runs a *tiny* sample pull via Python (Polygon -> local data/)
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
  Write-Error "Run .\scripts\windows\init.ps1 first."
}
. .\.venv\Scripts\Activate.ps1

if (-not $env:POLYGON_ACCESS_KEY -or -not $env:POLYGON_SECRET_KEY) {
  Write-Error "Export POLYGON_ACCESS_KEY and POLYGON_SECRET_KEY in this session before running."
}

python .\scripts\python\sample_pull.py
