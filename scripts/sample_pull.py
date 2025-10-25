import os, pathlib
import boto3
from botocore.config import Config

ENDPOINT = os.getenv("POLYGON_FILES_ENDPOINT", "https://files.polygon.io")
POLY_BUCKET = os.getenv("POLYGON_BUCKET", "flatfiles")
PREFIX = os.getenv("DATA_PREFIX", "us_stocks_sip/minute_aggs_v1")
LOCAL_DIR = pathlib.Path("data")

s3 = boto3.client("s3", endpoint_url=ENDPOINT, config=Config(signature_version="s3v4"))
resp = s3.list_objects_v2(Bucket=POLY_BUCKET, Prefix=f"{PREFIX}/2025/10/")
first = next(o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".csv.gz"))

LOCAL_DIR.mkdir(exist_ok=True)
local_path = LOCAL_DIR / first.split("/")[-1]
s3.download_file(POLY_BUCKET, first, str(local_path))
print(f"Downloaded: {first} -> {local_path}")
