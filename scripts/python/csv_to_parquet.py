"""
Convert Polygon CSV.gz minute bars to Parquet with partitioning.

Usage:
    python scripts/python/csv_to_parquet.py \
        --input-bucket polygon-trader-data-roshen \
        --input-prefix us_stocks_sip/minute_aggs_v1/2025/10 \
        --output-bucket polygon-trader-data-roshen \
        --output-prefix curated/minute_bars \
        --year 2025 --month 10 \
        --concurrency 4
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
import tempfile

import boto3
import polars as pl
from dotenv import load_dotenv

load_dotenv()


def get_s3_client():
    """Get AWS S3 client with environment credentials."""
    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))


def list_csv_files(s3_client, bucket: str, prefix: str) -> list[str]:
    """List all CSV.gz files under the given S3 prefix."""
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".csv.gz"):
                keys.append(key)
    return sorted(keys)


def extract_date_from_key(key: str) -> Optional[str]:
    """
    Extract YYYY-MM-DD from key like us_stocks_sip/minute_aggs_v1/2025/10/2025-10-01.csv.gz
    """
    filename = key.split("/")[-1]  # "2025-10-01.csv.gz"
    date_part = filename.replace(".csv.gz", "")  # "2025-10-01"
    if len(date_part) == 10 and date_part.count("-") == 2:
        return date_part
    return None


def convert_one_file(
    s3_client,
    input_bucket: str,
    input_key: str,
    output_bucket: str,
    output_prefix: str,
    year: int,
    month: int,
) -> tuple[str, int]:
    """
    Convert one CSV.gz file to Parquet.

    Returns: (output_key, file_size_bytes)
    """
    date = extract_date_from_key(input_key)
    if not date:
        raise ValueError(f"Cannot extract date from key: {input_key}")

    # Download to temp file
    with tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        s3_client.download_file(input_bucket, input_key, tmp_path)

        # Read CSV with Polars
        df = pl.read_csv(
            tmp_path,
            has_header=True,
            infer_schema_length=10000,
        )

        # Cast to specified schema
        # window_start is already Int64 (Unix timestamp in nanoseconds)
        df = df.select([
            pl.col("ticker").cast(pl.Utf8).alias("ticker"),
            pl.col("volume").cast(pl.Int64).alias("volume"),
            pl.col("open").cast(pl.Float64).alias("open"),
            pl.col("close").cast(pl.Float64).alias("close"),
            pl.col("high").cast(pl.Float64).alias("high"),
            pl.col("low").cast(pl.Float64).alias("low"),
            pl.from_epoch(pl.col("window_start"), time_unit="ns").dt.replace_time_zone("UTC").alias("window_start"),
            pl.col("transactions").cast(pl.Int64).alias("transactions"),
        ])

        # Write to temp parquet
        parquet_tmp = tmp_path.replace(".csv.gz", ".parquet")
        df.write_parquet(
            parquet_tmp,
            compression="zstd",
            use_pyarrow=True,
        )

        # Upload to S3 with partitioning structure
        output_key = f"{output_prefix}/year={year}/month={month:02d}/day={date}/part-0000.parquet"
        s3_client.upload_file(parquet_tmp, output_bucket, output_key)

        # Get file size
        file_size = os.path.getsize(parquet_tmp)

        # Cleanup
        os.unlink(tmp_path)
        os.unlink(parquet_tmp)

        return (output_key, file_size)

    except Exception as e:
        # Cleanup on error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        parquet_tmp = tmp_path.replace(".csv.gz", ".parquet")
        if os.path.exists(parquet_tmp):
            os.unlink(parquet_tmp)
        raise RuntimeError(f"Failed to convert {input_key}: {e}") from e


def main():
    parser = argparse.ArgumentParser(description="Convert CSV.gz to Parquet with partitioning")
    parser.add_argument("--input-bucket", required=True, help="Input S3 bucket")
    parser.add_argument("--input-prefix", required=True, help="Input S3 prefix")
    parser.add_argument("--output-bucket", required=True, help="Output S3 bucket")
    parser.add_argument("--output-prefix", required=True, help="Output S3 prefix")
    parser.add_argument("--year", type=int, required=True, help="Year for partitioning")
    parser.add_argument("--month", type=int, required=True, help="Month for partitioning")
    parser.add_argument("--concurrency", type=int, default=4, help="Number of concurrent workers")
    args = parser.parse_args()

    s3_client = get_s3_client()

    # List input files
    print(f"Listing CSV.gz files in s3://{args.input_bucket}/{args.input_prefix}...")
    csv_files = list_csv_files(s3_client, args.input_bucket, args.input_prefix)
    print(f"Found {len(csv_files)} CSV.gz files")

    if not csv_files:
        print("No CSV.gz files found. Exiting.")
        return

    # Convert with concurrency
    print(f"\nConverting with concurrency={args.concurrency}...")
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(
                convert_one_file,
                s3_client,
                args.input_bucket,
                key,
                args.output_bucket,
                args.output_prefix,
                args.year,
                args.month,
            ): key
            for key in csv_files
        }

        for i, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                output_key, file_size = future.result()
                results.append((output_key, file_size))
                print(f"[{i}/{len(csv_files)}] ✓ {key} → {output_key} ({file_size:,} bytes)")
            except Exception as e:
                print(f"[{i}/{len(csv_files)}] ✗ {key} - ERROR: {e}", file=sys.stderr)

    # Print summary
    print("\n" + "="*80)
    print("CONVERSION COMPLETE")
    print("="*80)
    print(f"Total Parquet files: {len(results)}")
    total_bytes = sum(size for _, size in results)
    print(f"Total bytes: {total_bytes:,} ({total_bytes / 1024**2:.2f} MB)")
    print(f"Output location: s3://{args.output_bucket}/{args.output_prefix}/year={args.year}/month={args.month:02d}/")
    print("="*80)


if __name__ == "__main__":
    main()
