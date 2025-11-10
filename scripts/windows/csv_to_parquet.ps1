# Convert October 2025 CSV.gz to Parquet with partitioning
$ErrorActionPreference = "Stop"

# Load environment
. .\scripts\windows\load_env.ps1

# Activate venv
if (!(Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Error "Run .\scripts\windows\init.ps1 first."
}
. .\.venv\Scripts\Activate.ps1

# Run conversion
python .\scripts\python\csv_to_parquet.py `
    --input-bucket polygon-trader-data-roshen `
    --input-prefix us_stocks_sip/minute_aggs_v1/2025/10 `
    --output-bucket polygon-trader-data-roshen `
    --output-prefix curated/minute_bars `
    --year 2025 `
    --month 10 `
    --concurrency 4
