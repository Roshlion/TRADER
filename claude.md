Here’s a single, copy-paste **Claude prompt** that does the bare-minimum, **100% local** setup to pull a tiny slice of Polygon **Flat Files** (minute data), convert to Parquet, and sanity-check rows—no cloud services, just your laptop.

---

**CLAUDE PROMPT (paste everything below):**

You are writing a minimal local-only setup to use Polygon.io **Flat Files** (minute aggregates) on my laptop. Do NOT use any cloud resources. Produce a single, self-contained answer with:

1. A **bash script** I can run line-by-line that:

   * Installs prerequisites (macOS or Linux): `brew` fallback to curl where needed.
   * Installs **rclone**, **python3**, **pip**, and creates a venv `./.venv`.
   * Installs Python deps: `polars pyarrow duckdb`.
   * Configures **rclone** for Polygon Flat Files using env vars (NO hardcoded keys).
   * Downloads a **tiny sample** of minute aggregates (e.g., 1 trading day) into `./raw/`.
   * Keeps everything local under a folder `./polygon_local_demo/`.

2. A **.env template** (dotenv) with placeholders to avoid hardcoding secrets:

   ```
   POLYGON_S3_KEY=REPLACE_ME
   POLYGON_S3_SECRET=REPLACE_ME
   POLYGON_ENDPOINT=https://files.polygon.io
   ```

   Instruct me to `cp .env.example .env` and fill in values.

3. An **rclone** one-time config command that reads keys from env (no interactive prompts), alias name = `polygon`.

   * Endpoint: `https://files.polygon.io`
   * Bucket to browse: `flatfiles`
   * Example path to minute aggregates (adjust if needed): `flatfiles/us_stocks_sip/minute_agg_v1/2024/04/`
   * Provide commands to list and to copy **one** small date file to `./raw/2024-04-01.csv.gz`
   * Make the date easily changeable with a bash variable `DAY=2024-04-01`.

4. A **Python script** `etl_csvgz_to_parquet.py` that:

   * Reads `./raw/*.csv.gz` (Polygon minute aggregates like the AAPL sample CSV format).
   * Uses **Polars** to load gzipped CSV with schema:

     * `ticker:str, volume:i64, open:f64, close:f64, high:f64, low:f64, window_start:i64, transactions:i64`
   * Converts `window_start` (ns since epoch) → `ts` (datetime, ns).
   * Normalizes `ticker` to uppercase, sorts by `ticker, ts`, drops dupes on (`ticker, ts`).
   * Writes partitioned **Parquet** to `./lake_parquet/us_stocks/minute_agg/year=YYYY/month=MM/day=DD/ticker=TICK/part-0.parquet`
     (derive YYYY/MM/DD from filename or from a `--date` CLI arg).
   * Prints a **5-row head** and a small summary (min/max ts, distinct tickers).

5. A **quick sanity query** using **DuckDB** (pure local) that:

   * SELECTs a few rows from the new Parquet path, filters `ticker='AAPL'` if present, and prints top 10.

6. Keep it small and robust:

   * Assume macOS or Ubuntu.
   * Add `set -euo pipefail` in the bash script.
   * Use `python -m venv .venv && source .venv/bin/activate`.
   * Handle missing tools gracefully with helpful echo messages.
   * No external network calls besides Polygon Flat Files via rclone.

7. Final section: **How to run** (4 steps max):

   * Create `.env`
   * Run bash setup
   * Pull one day file
   * Run ETL + DuckDB sanity check

Use these exact directories:

* Project root: `polygon_local_demo/`
* Raw gzip CSVs: `polygon_local_demo/raw/`
* Parquet lake: `polygon_local_demo/lake_parquet/`

Important:

* Do NOT print real credentials.
* Assume the sample minute CSV matches Polygon’s structure shown here:
  `ticker,volume,open,close,high,low,window_start,transactions`
* If the sample file contains multiple tickers, the script should still work.

Return ONE cohesive answer containing:

* `.env.example`
* `setup_local.sh` (bash)
* `etl_csvgz_to_parquet.py`
* `duckdb_check.sql`
* A short “How to run” list.

No extra commentary—just the files and commands.
