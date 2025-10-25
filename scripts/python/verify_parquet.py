"""
Verify Parquet files with DuckDB - scan S3 and show sample minute rows.
"""

import os
import duckdb
import boto3
from dotenv import load_dotenv

load_dotenv()

# Get AWS credentials from boto3 session (uses AWS CLI config)
session = boto3.Session()
credentials = session.get_credentials()
if not credentials:
    raise RuntimeError("No AWS credentials found. Run 'aws configure' or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")

region = os.getenv("AWS_REGION", "us-east-1")
bucket = os.getenv("S3_BUCKET", "polygon-trader-data-roshen")

# S3 path to curated parquet files
s3_path = f"s3://{bucket}/curated/minute_bars/year=2025/month=10/*/*.parquet"

print(f"Scanning: {s3_path}")
print("=" * 80)

# Create DuckDB connection with S3 extension
con = duckdb.connect()
con.execute(f"SET s3_region='{region}'")
con.execute("SET s3_use_ssl=true")
con.execute(f"SET s3_access_key_id='{credentials.access_key}'")
con.execute(f"SET s3_secret_access_key='{credentials.secret_key}'")
if credentials.token:
    con.execute(f"SET s3_session_token='{credentials.token}'")

# Install and load httpfs for S3 access
con.execute("INSTALL httpfs")
con.execute("LOAD httpfs")

# Query: Get 10 sample minute rows, show schema and data
query = f"""
SELECT
    ticker,
    volume,
    open,
    close,
    high,
    low,
    window_start,
    transactions
FROM read_parquet('{s3_path}')
LIMIT 10
"""

result = con.execute(query).df()

print("\nSample of 10 Minute Rows:")
print("=" * 80)
print(result.to_string(index=False))

# Get count and date range
count_query = f"""
SELECT
    COUNT(*) as total_rows,
    MIN(window_start) as earliest_timestamp,
    MAX(window_start) as latest_timestamp,
    COUNT(DISTINCT DATE_TRUNC('day', window_start)) as distinct_days
FROM read_parquet('{s3_path}')
"""

stats = con.execute(count_query).df()
print("\n" + "=" * 80)
print("Statistics:")
print("=" * 80)
print(stats.to_string(index=False))

# Verify minute granularity - show distinct minute count for one ticker on one day
granularity_query = f"""
SELECT
    ticker,
    DATE(window_start) as trading_day,
    COUNT(*) as minute_bars,
    MIN(window_start) as first_bar,
    MAX(window_start) as last_bar
FROM read_parquet('{s3_path}')
WHERE ticker = (SELECT ticker FROM read_parquet('{s3_path}') LIMIT 1)
  AND DATE(window_start) = (SELECT MIN(DATE(window_start)) FROM read_parquet('{s3_path}'))
GROUP BY ticker, DATE(window_start)
"""

granularity = con.execute(granularity_query).df()
print("\n" + "=" * 80)
print("Minute Granularity Check (one ticker, one day):")
print("=" * 80)
print(granularity.to_string(index=False))

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
