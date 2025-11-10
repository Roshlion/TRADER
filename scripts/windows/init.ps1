# Creates venv & installs deps (Windows)
$ErrorActionPreference = "Stop"

if (!(Test-Path -Path ".venv")) {
  python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt

# Create data gitkeep
if (!(Test-Path -Path "data\.gitkeep")) {
  New-Item -ItemType File -Path "data\.gitkeep" | Out-Null
}

Write-Host "Venv ready. Remember to: copy .env.example .env and fill non-secret values."
Write-Host "Export Polygon secrets per-session:"
Write-Host '$env:POLYGON_ACCESS_KEY="..." ; $env:POLYGON_SECRET_KEY="..."'
