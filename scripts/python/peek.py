import polars as pl
df = pl.read_csv("data/2025-10-02.csv.gz")
print(df.head(5))
print("rows:", df.height)
print("cols:", df.columns)
