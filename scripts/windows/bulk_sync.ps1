# Bulk sync Polygon -> S3 with server-side streaming (no local disk)
# Supports both dry-run and real sync modes
param(
  [bool]$DryRun = $true,  # Default to dry-run for safety
  [string]$Month = "2025/10",  # Target month to sync (format: YYYY/MM)
  [int]$MaxTransferGB = 10,  # Max transfer in GB (cost control)
  [string]$BwLimit = "20M"  # Bandwidth limit
)
$ErrorActionPreference = "Stop"

# Load environment variables
. "$PSScriptRoot\load_env.ps1"

if (-not $env:S3_BUCKET) {
  Write-Error "S3_BUCKET not set in .env"
}

$prefix = if ($env:DATA_PREFIX) { $env:DATA_PREFIX } else { "us_stocks_sip/minute_aggs_v1" }
$src = "polygon:flatfiles/$prefix/$Month/"
$dest = "aws:$($env:S3_BUCKET)/$prefix/$Month/"

Write-Host "=== Polygon -> S3 Sync Configuration ===" -ForegroundColor Cyan
Write-Host "Source:      $src"
Write-Host "Destination: $dest"
Write-Host "Mode:        $(if ($DryRun) { 'DRY RUN (no changes)' } else { 'REAL SYNC (will copy data)' })"
Write-Host "Max Transfer: $MaxTransferGB GB"
Write-Host "Bandwidth:   $BwLimit"
Write-Host "=========================================`n" -ForegroundColor Cyan

$rcloneArgs = @(
  "sync"
  $src
  $dest
  "--progress"
  "--fast-list"
  "--create-empty-src-dirs"
  "--s3-no-check-bucket"
  "--transfers=8"
  "--checkers=16"
  "--bwlimit=$BwLimit"
  "--max-transfer=$($MaxTransferGB)G"
  "--size-only"
)

if ($DryRun) {
  $rcloneArgs += "--dry-run"
  Write-Host "[DRY RUN] Preview of what would be copied:`n" -ForegroundColor Yellow
}

& rclone @rcloneArgs

if ($DryRun) {
  Write-Host "`n[DRY RUN] Complete. No data was copied." -ForegroundColor Yellow
  Write-Host "To perform real sync, run with -DryRun:`$false" -ForegroundColor Yellow
} else {
  Write-Host "`n[SYNC COMPLETE] Data copied to S3." -ForegroundColor Green
}
