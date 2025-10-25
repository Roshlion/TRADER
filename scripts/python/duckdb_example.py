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
