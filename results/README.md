# TRADER Optimization Results

This directory contains results from TRADER optimization runs.

## Directory Structure

Each run is stored in its own directory with the format: `{run_type}_{timestamp}`

Example: `test_20251110_180825/`

### Artifacts

- `artifacts/portfolios/*.json` - Portfolio weight configurations and metadata
  - `latest_weights.json` - Most recent portfolio weights
  - `{timestamp}_weights.json` - Timestamped snapshot

### Reports

- `reports/portfolio/metrics_table.csv` - Performance metrics summary
  - Sharpe Ratio, Sortino Ratio, Max Drawdown
  - Total Return, CAGR, Win Rate
  - Per-strategy and portfolio-level metrics

## Available Runs

### Test Run - Nov 10, 2025 (SUCCESS)
**Directory:** `test_20251110_180825/`
- **Duration:** Oct 1-3, 2025 (3 days)
- **Strategies:** 2 (mean reversion strategies)
- **Tickers:** AAPL
- **Runtime:** 45 seconds
- **Status:** ✅ Success
- **Results:**
  - Sharpe Ratio: 0.185
  - Portfolio validated successfully
  - Artifacts uploaded to S3

### Run #2 - Nov 10, 2025 (FAILED)
**Directory:** Not available (run failed)
- **Duration:** Oct 2024 - Oct 2025 (attempted full year)
- **Strategies:** 13 strategies
- **Tickers:** 5 (AAPL, MSFT, GOOGL, AMZN, TSLA)
- **Runtime:** 42 minutes before failure
- **Status:** ❌ Failed
- **Failure Reason:** Missing September 2025 data in S3
  - Walk-forward validation attempted to access 2025-09-26 to 2025-09-30
  - Dataset only contains Oct 2024 - Oct 2025
- **Instance:** i-0709a0f087f9476fd (t3.large)
- **No results saved**

### Phase 5 - Oct 28, 2024 (COMPLETE)
**Directory:** Not stored in this repo
- **Duration:** Oct 2025 (1 month)
- **Strategies:** 13 strategies
- **Status:** ✅ Complete
- **Winner:** VWAPReversion
  - Return: +6.66%
  - Sharpe Ratio: 1.85
  - Max Drawdown: -8.2%
- **Results:** See [VALIDATION_RESULTS.md](../VALIDATION_RESULTS.md)

## Usage

To view results for a specific run:

```bash
# View portfolio weights
cat results/test_20251110_180825/artifacts/portfolios/latest_weights.json

# View performance metrics
cat results/test_20251110_180825/reports/portfolio/metrics_table.csv
```

## Notes

- All runs include transaction costs (slippage + commission)
- Walk-forward validation uses 10-day train / 5-day test windows
- Cost-aware selection includes 1.0 bps rebalancing cost
- Regime detection adjusts weights by 25% based on market conditions
