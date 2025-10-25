Gotcha—you’re on Windows. Here’s a single, condensed **Claude prompt** that will set up the repo and a safe Windows-native pipeline (PowerShell + rclone + Python with Polars/PyArrow/DuckDB). It keeps strict guardrails (no secrets in git, small-sample only, dry-runs by default), and you can paste this directly into Claude in VS Code.

---

# ✅ CLAUDE OPS PROMPT — TRADER (Windows / PowerShell Safe Mode)

**Role:** You are my local repo/devops assistant running in VS Code on **Windows** with shell access.
**Goal (Phase 1 only):** Scaffold the repo, create safe configuration, set up **rclone** remotes for Polygon & AWS, add Python data utilities (Polars/PyArrow/DuckDB), and validate with **one small sample**. Do **not** bulk-ingest yet.

## Guardrails (must follow)

1. **No secrets in git.** Never write keys into tracked files. Use ephemeral **PowerShell environment variables** and `.env` (gitignored) for non-secret config only.
2. **Small-sample only.** Pull **one** CSV (or a tiny handful) for validation; **bulk sync must remain dry-run**.
3. **Idempotent.** If a file/folder exists, don’t overwrite unless content differs; if bucket exists, skip creation.
4. **Confirm before any command** that creates/modifies cloud resources or transfers data.
5. **Redact secrets** in logs and outputs.
6. **Rollback hints** for each create/change (files to delete, commands to revert).

## Variables (ask me once; then proceed)

* `AWS_REGION` (e.g., `us-east-1`)
* `S3_BUCKET` (e.g., `polygon-trader-data-<unique>`)
* `POLYGON_ACCESS_KEY`
* `POLYGON_SECRET_KEY`
* `DATA_PREFIX` = `us_stocks_sip/minute_aggs_v1` (default unless I change it)

> Use `POLYGON_ENDPOINT=https://files.polygon.io` and `POLYGON_BUCKET=flatfiles` (fixed).

---

## PLAN (execute step-by-step; pause for confirmation at each step)

### Step 0 — Repo scaffold (Windows-native paths)

Create folders & baseline files in the current repo (TRADER):

**Folders**

```
src/trader
scripts/windows
scripts/python
sql
notebooks
config
tests
data
.github/workflows
```

**Files (with exact contents)**

#### `.gitignore`

```
# Python
__pycache__/
*.pyc
.venv/
.env
.env.*
.ipynb_checkpoints/

# Data & temp
data/
!data/.gitkeep
tmp/
.cache/

# OS/Editor
.DS_Store
.vscode/
```

#### `README.md`

```md
# TRADER (Windows-safe setup)

Local code + cloud data. Polygon Flat Files -> S3; compute later on EC2/SageMaker.
This repo is Windows-native (PowerShell + rclone) with strict safe-mode defaults.

## Quickstart (Windows)
1) `.\scripts\windows\init.ps1` (creates venv, installs deps)
2) `copy .env.example .env` and fill non-secret values
3) Export Polygon secrets in current PowerShell session (DO NOT COMMIT):
   `$env:POLYGON_ACCESS_KEY="..." ; $env:POLYGON_SECRET_KEY="..."`
4) Validate single-file pull: `.\scripts\windows\sample_pull.ps1`
5) Dry-run list/sync with rclone: `.\scripts\windows\sync_dryrun.ps1`
```

#### `requirements.txt`

```
boto3
pandas
polars
pyarrow
duckdb
python-dotenv
```

#### `.env.example`

```
# Non-secret config ONLY (copy to .env and edit). DO NOT put keys here.
AWS_REGION=us-east-1
S3_BUCKET=polygon-trader-data-CHANGE-ME
POLYGON_FILES_ENDPOINT=https://files.polygon.io
POLYGON_BUCKET=flatfiles
DATA_PREFIX=us_stocks_sip/minute_aggs_v1
# secrets must be exported in PowerShell session, not stored:
# $env:POLYGON_ACCESS_KEY="..."
# $env:POLYGON_SECRET_KEY="..."
```

#### `.github/workflows/ci.yml`

```yaml
name: ci
on:
  push: { branches: [ "**" ] }
  pull_request:
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python -m pip install -U pip
      - run: pip install -r requirements.txt
      - run: python -c "print('lint placeholder')"
```

#### `sql/minute_to_daily.sql`

```sql
-- Example DuckDB SQL to aggregate minute bars -> daily OHLCV
-- Assumes a table 'minute_bars' with schema:
-- (ticker TEXT, volume BIGINT, open DOUBLE, close DOUBLE, high DOUBLE, low DOUBLE, window_start TIMESTAMP)

WITH per_min AS (
  SELECT
    ticker,
    CAST(window_start AS DATE) AS d,
    open,
    close,
    high,
    low,
    volume
  FROM minute_bars
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY ticker, d ORDER BY window_start ASC) AS rn_open,
    ROW_NUMBER() OVER (PARTITION BY ticker, d ORDER BY window_start DESC) AS rn_close
  FROM per_min
)
SELECT
  ticker,
  d AS trading_day,
  FIRST(open) FILTER (WHERE rn_open = 1) AS open,
  MAX(high) AS high,
  MIN(low) AS low,
  FIRST(close) FILTER (WHERE rn_close = 1) AS close,
  SUM(volume) AS volume
FROM ranked
GROUP BY ticker, d
ORDER BY ticker, d;
```

#### `src/trader/io.py`

```python
from __future__ import annotations
import os
from typing import Iterable, Optional
import boto3
from botocore.config import Config
import polars as pl

POLYGON_ENDPOINT = os.getenv("POLYGON_FILES_ENDPOINT", "https://files.polygon.io")
POLYGON_BUCKET = os.getenv("POLYGON_BUCKET", "flatfiles")

def polygon_s3_client(access_key: str, secret_key: str):
    return boto3.client(
        "s3",
        endpoint_url=POLYGON_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )

def list_polygon_keys(prefix: str, access_key: str, secret_key: str, max_items: int = 100) -> list[str]:
    s3 = polygon_s3_client(access_key, secret_key)
    paginator = s3.get_paginator("list_objects_v2")
    out = []
    for page in paginator.paginate(Bucket=POLYGON_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            out.append(obj["Key"])
            if len(out) >= max_items:
                return out
    return out

def download_polygon_object(key: str, local_path: str, access_key: str, secret_key: str) -> None:
    s3 = polygon_s3_client(access_key, secret_key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    s3.download_file(POLYGON_BUCKET, key, local_path)

def read_csv_gz_polars(local_path: str, columns: Optional[list[str]] = None) -> pl.DataFrame:
    return pl.read_csv(local_path, has_header=True, infer_schema_length=1000, columns=columns)
```

#### `scripts/python/sample_pull.py`

```python
import os, sys, pathlib
from dotenv import load_dotenv
from src.trader.io import list_polygon_keys, download_polygon_object, read_csv_gz_polars

load_dotenv()
ENDPOINT = os.getenv("POLYGON_FILES_ENDPOINT", "https://files.polygon.io")
BUCKET = os.getenv("POLYGON_BUCKET", "flatfiles")
PREFIX = os.getenv("DATA_PREFIX", "us_stocks_sip/minute_aggs_v1")

ACCESS = os.getenv("POLYGON_ACCESS_KEY")
SECRET = os.getenv("POLYGON_SECRET_KEY")
if not ACCESS or not SECRET:
    print("Export POLYGON_ACCESS_KEY and POLYGON_SECRET_KEY in PowerShell session.", file=sys.stderr)
    sys.exit(1)

# target a recent month to limit listing
prefix_month = f"{PREFIX}/2025/10/"
keys = list_polygon_keys(prefix_month, ACCESS, SECRET, max_items=50)
key = next((k for k in keys if k.endswith(".csv.gz")), None)
if not key:
    print("No .csv.gz found under:", prefix_month)
    sys.exit(0)

out_dir = pathlib.Path("data"); out_dir.mkdir(exist_ok=True)
out_path = out_dir / key.split("/")[-1]
download_polygon_object(key, str(out_path), ACCESS, SECRET)
print(f"Downloaded: s3://{BUCKET}/{key} -> {out_path}")

# Show first 5 rows safely with Polars
df = read_csv_gz_polars(str(out_path))
print(df.head(5))
```

#### `scripts/python/duckdb_example.py`

```python
import os, sys, gzip
import duckdb
import pandas as pd

# Read one csv.gz to pandas then register as DuckDB table
# (Polars -> Arrow would also work; keeping it simple for demo)
if len(sys.argv) < 2:
    print("Usage: python scripts/python/duckdb_example.py data\\<file>.csv.gz")
    sys.exit(1)

gz_path = sys.argv[1]
with gzip.open(gz_path, "rt") as f:
    df = pd.read_csv(f)

con = duckdb.connect()
con.register("minute_bars", df)
res = con.execute(open("sql/minute_to_daily.sql").read()).df()
print(res.head())
```

#### `scripts/windows/init.ps1`

```powershell
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
```

#### `scripts/windows/rclone-setup.ps1`

```powershell
# Sets up rclone remotes for Polygon (S3-compatible) and AWS (env-auth)
# REQUIREMENT: rclone installed & on PATH
$ErrorActionPreference = "Stop"

# Validate env secrets are present (session only)
if (-not $env:POLYGON_ACCESS_KEY -or -not $env:POLYGON_SECRET_KEY) {
  Write-Error "Set POLYGON_ACCESS_KEY and POLYGON_SECRET_KEY in this session before running."
}

# Create/overwrite remotes idempotently
rclone config delete polygon 2>$null
rclone config delete aws 2>$null

rclone config create polygon s3 env_auth=false `
  access_key_id="$env:POLYGON_ACCESS_KEY" `
  secret_access_key="$env:POLYGON_SECRET_KEY" `
  endpoint="https://files.polygon.io" `
  provider="Other" --non-interactive

rclone config create aws s3 env_auth=true provider=AWS --non-interactive

Write-Host "Remotes configured: polygon, aws"
Write-Host "Test list (limited):"
rclone ls polygon:flatfiles/us_stocks_sip/minute_aggs_v1/2025/10 --max-depth 1 --fast-list --cutoff-mode=soft | Select-Object -First 20
```

#### `scripts/windows/sample_pull.ps1`

```powershell
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
```

#### `scripts/windows/s3_bucket_setup.ps1`

```powershell
# Creates secure S3 bucket with encryption, versioning, lifecycle
param(
  [Parameter(Mandatory=$true)][string]$Bucket,
  [Parameter(Mandatory=$true)][string]$Region
)
$ErrorActionPreference = "Stop"

# Check existence
try {
  aws s3api head-bucket --bucket $Bucket 1>$null 2>$null
  Write-Host "Bucket exists: $Bucket (skipping create)"
} catch {
  Write-Host "Creating bucket: $Bucket in $Region"
  aws s3api create-bucket --bucket $Bucket --region $Region --create-bucket-configuration LocationConstraint=$Region
}

aws s3api put-bucket-encryption --bucket $Bucket --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-versioning --bucket $Bucket --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket $Bucket --lifecycle-configuration '{
  "Rules":[
    {"ID":"expire-mpu-7d","Status":"Enabled","AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}},
    {"ID":"glacier-90d","Status":"Enabled","Filter":{"Prefix":""},"Transitions":[{"Days":90,"StorageClass":"GLACIER"}]}
  ]
}'
Write-Host "S3 bucket hardened. To rollback: delete lifecycle + versioning, then remove bucket when empty."
```

#### `scripts/windows/sync_dryrun.ps1`

```powershell
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
```

#### `scripts/windows/load_env.ps1`

```powershell
# Loads .env (non-secret) into $env: for current session
if (Test-Path ".env") {
  Get-Content ".env" | ForEach-Object {
    if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
    $parts = $_ -split "=", 2
    if ($parts.Length -eq 2) {
      $name = $parts[0].Trim()
      $value = $parts[1].Trim()
      [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
  Write-Host "Loaded .env into session."
} else {
  Write-Host "No .env found; skip."
}
```

---

### Step 1 — Commit safe files (no secrets, no data)

1. Stage and commit:

```powershell
git add .
git reset .env data/*.csv.gz 2>$null
git commit -m "windows scaffold: rclone + polars + duckdb; safe-mode scripts and SQL"
git push -u origin HEAD
```

**Rollback:** `git reset --hard HEAD~1` (if needed).

---

### Step 2 — Local environment

```powershell
# venv + deps
.\scripts\windows\init.ps1

# create non-secret env
copy .env.example .env
# (edit .env: set AWS_REGION, S3_BUCKET, etc.)

# export Polygon keys for this session (DO NOT COMMIT)
$env:POLYGON_ACCESS_KEY="<paste>"
$env:POLYGON_SECRET_KEY="<paste>"
```

---

### Step 3 — rclone remotes (safe)

```powershell
.\scripts\windows\rclone-setup.ps1
```

**Verify listing:** It prints up to ~20 keys.
**Rollback:** `rclone config delete polygon ; rclone config delete aws`.

---

### Step 4 — S3 bucket hardening (idempotent)

```powershell
.\scripts\windows\s3_bucket_setup.ps1 -Bucket "<your-bucket>" -Region "<your-region>"
```

**Rollback:** remove lifecycle/versioning, then delete bucket when empty.

---

### Step 5 — Tiny sample pull (Polygon → local)

```powershell
.\scripts\windows\sample_pull.ps1
```

You should see one `*.csv.gz` in `data\` and the first 5 rows printed from Polars.
**Rollback:** `Remove-Item data\*.csv.gz`.

---

### Step 6 — Dry-run preview of cloud sync (Polygon → your S3)

```powershell
.\scripts\windows\load_env.ps1
.\scripts\windows\sync_dryrun.ps1
```

No data copied (dry-run). Shows exactly what **would** sync.
**Rollback:** none (no writes).

---

### Optional — DuckDB daily aggregation demo

```powershell
# Point to the sample you just pulled
.\.venv\Scripts\python.exe .\scripts\python\duckdb_example.py .\data\<your-sample-file>.csv.gz
```

---

## Success Criteria

* Repo scaffolded with Windows-safe scripts and SQL.
* No secrets committed; `.env` only has non-secret config.
* rclone remotes (`polygon`, `aws`) configured; listing works.
* S3 bucket exists with encryption, versioning, lifecycle.
* One sample minute-agg CSV pulled locally; can preview in Polars.
* Dry-run sync preview shows candidate keys without copying.

## Notes for Later (don’t execute yet)

* For **bulk** sync: replace `--dry-run` with real run and add filters, e.g.:

  ```
  rclone sync polygon:flatfiles/%DATA_PREFIX%/2025 aws:%S3_BUCKET%/%DATA_PREFIX%/2025 `
    --include "*/10/*" --transfers=8 --checkers=16 --bwlimit=20M --max-transfer=20G
  ```
* For **compute**, we’ll add an EC2 bootstrap that: installs Python, rclone, clones this repo, loads `.env` from SSM, and runs batch jobs against **your S3**, not local.

---

**Ask me now for the five variables** (`AWS_REGION`, `S3_BUCKET`, `POLYGON_ACCESS_KEY`, `POLYGON_SECRET_KEY`, `DATA_PREFIX` if different) and then execute each step with confirmation prompts.
