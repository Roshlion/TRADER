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
