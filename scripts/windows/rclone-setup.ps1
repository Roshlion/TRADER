# Sets up rclone remotes for Polygon (S3-compatible) and AWS (env-auth)
# REQUIREMENT: rclone installed & on PATH
$ErrorActionPreference = "Stop"

# Validate env secrets are present (session only)
if (-not $env:POLYGON_ACCESS_KEY -or -not $env:POLYGON_SECRET_KEY) {
  Write-Error "Set POLYGON_ACCESS_KEY and POLYGON_SECRET_KEY in this session before running."
}

# Create/overwrite remotes idempotently
rclone config delete polygon 2>&1 | Out-Null
rclone config delete aws 2>&1 | Out-Null

rclone config create polygon s3 env_auth=false `
  access_key_id="$env:POLYGON_ACCESS_KEY" `
  secret_access_key="$env:POLYGON_SECRET_KEY" `
  endpoint="https://files.polygon.io" `
  provider="Other" --non-interactive

rclone config create aws s3 env_auth=true provider=AWS --non-interactive

Write-Host "Remotes configured: polygon, aws"
Write-Host "Test list (limited):"
rclone ls polygon:flatfiles/us_stocks_sip/minute_aggs_v1/2025/10 --max-depth 1 --fast-list --cutoff-mode=soft | Select-Object -First 20
