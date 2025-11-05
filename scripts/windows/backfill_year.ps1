# Backfill a full year of data using existing pipeline
# Downloads from Polygon → AWS S3, then converts to Parquet
param(
    [Parameter(Mandatory=$true)]
    [string]$StartMonth,  # Format: YYYY/MM (e.g., 2024/10)

    [Parameter(Mandatory=$true)]
    [string]$EndMonth,    # Format: YYYY/MM (e.g., 2025/10)

    [bool]$DryRun = $true,  # Safe default: preview only

    [int]$MaxTransferGB = 50,  # Increased for year-long backfill

    [string]$BwLimit = "20M",

    [int]$Concurrency = 6  # Parquet conversion parallelism
)
$ErrorActionPreference = "Stop"

# Parse start and end dates
function Parse-YearMonth {
    param([string]$ym)
    $parts = $ym.Split("/")
    return @{
        Year = [int]$parts[0]
        Month = [int]$parts[1]
    }
}

$start = Parse-YearMonth $StartMonth
$end = Parse-YearMonth $EndMonth

# Generate month list
$months = @()
$current = $start.Clone()

while (($current.Year -lt $end.Year) -or
       ($current.Year -eq $end.Year -and $current.Month -le $end.Month)) {

    $monthStr = "$($current.Year)/$($current.Month.ToString('00'))"
    $months += @{
        String = $monthStr
        Year = $current.Year
        Month = $current.Month
    }

    # Increment month
    $current.Month++
    if ($current.Month -gt 12) {
        $current.Month = 1
        $current.Year++
    }
}

Write-Host "`n=== Backfill Configuration ===" -ForegroundColor Cyan
Write-Host "Date Range:  $StartMonth to $EndMonth"
Write-Host "Total Months: $($months.Count)"
Write-Host "Mode:        $(if ($DryRun) { 'DRY RUN' } else { 'LIVE'})"
Write-Host "Max Transfer: $MaxTransferGB GB total"
Write-Host "==============================`n" -ForegroundColor Cyan

$successful = @()
$failed = @()

foreach ($m in $months) {
    $monthStr = $m.String
    Write-Host "`n" -NoNewline
    Write-Host ("="*80) -ForegroundColor Green
    Write-Host "Processing: $monthStr" -ForegroundColor Green
    Write-Host ("="*80) -ForegroundColor Green

    # STEP 1: Download from Polygon to S3 (raw area)
    Write-Host "`n[1/2] Downloading $monthStr from Polygon..." -ForegroundColor Yellow

    try {
        & "$PSScriptRoot\bulk_sync.ps1" `
            -Month $monthStr `
            -DryRun:$DryRun `
            -MaxTransferGB $MaxTransferGB `
            -BwLimit $BwLimit

        Write-Host "[1/2] Download complete for $monthStr" -ForegroundColor Green

    } catch {
        Write-Host "[1/2] Download FAILED for $monthStr" -ForegroundColor Red
        Write-Host "Error: $_" -ForegroundColor Red
        $failed += $monthStr
        continue  # Skip conversion if download failed
    }

    # STEP 2: Convert to Parquet (skip in dry-run mode)
    if (-not $DryRun) {
        Write-Host "`n[2/2] Converting $monthStr to Parquet..." -ForegroundColor Yellow

        # Load environment for bucket name
        . "$PSScriptRoot\load_env.ps1"

        # Activate venv
        if (Test-Path ".\.venv\Scripts\Activate.ps1") {
            . .\.venv\Scripts\Activate.ps1
        } else {
            Write-Warning "Virtual environment not found. Run .\scripts\windows\init.ps1"
            $failed += $monthStr
            continue
        }

        try {
            python .\scripts\python\csv_to_parquet.py `
                --input-bucket $env:S3_BUCKET `
                --input-prefix "us_stocks_sip/minute_aggs_v1/$monthStr" `
                --output-bucket $env:S3_BUCKET `
                --output-prefix "curated/minute_bars" `
                --year $m.Year `
                --month $m.Month `
                --concurrency $Concurrency

            if ($LASTEXITCODE -eq 0) {
                Write-Host "[2/2] Conversion complete for $monthStr" -ForegroundColor Green
                $successful += $monthStr
            } else {
                Write-Host "[2/2] Conversion FAILED for $monthStr (exit code $LASTEXITCODE)" -ForegroundColor Red
                $failed += $monthStr
            }

        } catch {
            Write-Host "[2/2] Conversion FAILED for $monthStr" -ForegroundColor Red
            Write-Host "Error: $_" -ForegroundColor Red
            $failed += $monthStr
        }

    } else {
        Write-Host "[2/2] Skipping conversion (dry-run mode)" -ForegroundColor Yellow
        $successful += $monthStr
    }
}

# Final summary
Write-Host "`n" -NoNewline
Write-Host ("="*80) -ForegroundColor Cyan
Write-Host "BACKFILL SUMMARY" -ForegroundColor Cyan
Write-Host ("="*80) -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "`nMode: DRY RUN (no files copied or converted)" -ForegroundColor Yellow
} else {
    Write-Host "`nMode: LIVE" -ForegroundColor Green
}

Write-Host "`nSuccessful: $($successful.Count) months"
foreach ($m in $successful) {
    Write-Host "  $([char]0x2713) $m" -ForegroundColor Green
}

if ($failed.Count -gt 0) {
    Write-Host "`nFailed: $($failed.Count) months"
    foreach ($m in $failed) {
        Write-Host "  $([char]0x2717) $m" -ForegroundColor Red
    }
}

Write-Host "`n" -NoNewline
Write-Host ("="*80) -ForegroundColor Cyan
Write-Host "Data Locations:" -ForegroundColor Cyan
Write-Host "  Raw:     s3://$($env:S3_BUCKET)/us_stocks_sip/minute_aggs_v1/" -ForegroundColor Gray
Write-Host "  Curated: s3://$($env:S3_BUCKET)/curated/minute_bars/" -ForegroundColor Gray
Write-Host ("="*80) -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "`nTo execute real download + conversion, run:" -ForegroundColor Yellow
    Write-Host "  .\scripts\windows\backfill_year.ps1 -StartMonth '$StartMonth' -EndMonth '$EndMonth' -DryRun:`$false`n" -ForegroundColor Yellow
}

# Exit with error if any failed
if ($failed.Count -gt 0) {
    exit 1
}
