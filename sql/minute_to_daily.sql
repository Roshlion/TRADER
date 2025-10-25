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
