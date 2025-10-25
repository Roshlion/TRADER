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
