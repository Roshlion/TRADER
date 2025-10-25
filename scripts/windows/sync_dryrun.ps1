# DRY RUN ONLY: preview a server-side streamed sync Polygon -> your S3 (no local disk)
# Requires: rclone remotes 'polygon' and 'aws' configured, S3 bucket exists
$ErrorActionPreference = "Stop"
. .\.venv\Scripts\Activate.ps1
. .\scripts\windows\load_env.ps1 2>$null

if (-not $env:S3_BUCKET) { Write-Error "Set S3_BUCKET in .env"; }
$prefix = if ($env:DATA_PREFIX) { $env:DATA_PREFIX } else { "us_stocks_sip/minute_aggs_v1" }

# Limit: one month, dry-run, bandwidth caps, and transfer ceiling for cost control
$src  = "polygon:flatfiles/$prefix/2025/10/"
$dest = "aws:$($env:S3_BUCKET)/$prefix/2025/10/"
rclone sync $src $dest `
  --dry-run --progress --fast-list `
  --create-empty-src-dirs `
  --s3-no-check-bucket `
  --transfers=4 --checkers=8 `
  --bwlimit=10M `
  --max-transfer=2G `
  --size-only

Write-Host "[DRY RUN] Completed. Nothing copied."
