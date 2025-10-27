# Intraday Trading Strategy Suite (Phase 3)

A modular backtesting framework for intraday US equity trading strategies using Polygon minute-bar data stored as Parquet on S3.

## Architecture Overview

```
Market Data (S3 Parquet via DuckDB)
    ↓
Strategy Signals (rules/ML models)
    ↓
Trade Simulation (execution, slippage, capital)
    ↓
Metrics & Analysis (PnL, Sharpe, Drawdown, etc.)
    ↓
Reports & Visualizations (equity curves, heatmaps, logs)
```

## Module Structure

```
strategy_suite/
├── __init__.py
├── backtest.py          # Main orchestrator for running backtests
├── simulator.py         # Trade execution simulation (fills, slippage, P&L)
├── metrics.py           # Performance metrics calculation
├── visualization.py     # Plotting and reporting utilities
├── example.py           # Example usage scripts
├── README.md           # This file
└── strategies/         # Individual strategy implementations
    ├── __init__.py
    ├── base.py              # Base classes and utilities
    ├── momentum.py          # Momentum strategies (breakouts, volume spikes)
    ├── mean_reversion.py    # Mean reversion (VWAP, Bollinger Bands)
    ├── stat_arb.py          # Statistical arbitrage (pairs trading)
    └── ml.py                # ML-based strategies (classifiers)
```

## Available Strategies

### 1. Momentum Strategies (`momentum.py`)

#### BreakoutMomentumStrategy
Enters long when price breaks above recent high with volume confirmation.

**Parameters:**
- `lookback_bars` (int): Number of bars for high/low range (default: 30)
- `volume_threshold` (float): Minimum relative volume multiple (default: 2.0)
- `holding_period` (int): Bars to hold position (default: 60)

**Example:**
```python
from strategies.momentum import BreakoutMomentumStrategy

strategy = BreakoutMomentumStrategy(params={
    "lookback_bars": 30,
    "volume_threshold": 2.0,
    "holding_period": 60
})
```

#### VolumeSpikeStrategy
Trades on unusual volume spikes with directional price movement.

**Parameters:**
- `rvol_threshold` (float): Minimum relative volume for spike (default: 3.0)
- `price_change_pct` (float): Minimum price change % (default: 0.5)
- `holding_period` (int): Bars to hold position (default: 30)

### 2. Mean Reversion Strategies (`mean_reversion.py`)

#### VWAPReversionStrategy
Trades when price deviates significantly from VWAP, expecting reversion.

**Parameters:**
- `std_dev_threshold` (float): Number of std devs from VWAP (default: 2.0)
- `holding_period` (int): Maximum bars to hold (default: 30)
- `min_volume` (int): Minimum volume filter (default: 10000)

#### BollingerBandStrategy
Trades at Bollinger Band extremes, expecting bounce back to middle.

**Parameters:**
- `bb_window` (int): Bollinger Band window (default: 20)
- `bb_std` (float): Number of std devs for bands (default: 2.0)
- `holding_period` (int): Maximum bars to hold (default: 30)
- `entry_threshold` (float): How far beyond band to trigger (default: 0.0)

### 3. Statistical Arbitrage (`stat_arb.py`)

#### PairsTradingStrategy
Trades the spread between two correlated stocks.

**Parameters:**
- `ticker_pair` (tuple): Two ticker symbols, e.g., ("AAPL", "MSFT")
- `lookback_window` (int): Window for spread statistics (default: 60)
- `entry_z_score` (float): Z-score threshold for entry (default: 2.0)
- `exit_z_score` (float): Z-score threshold for exit (default: 0.5)
- `hedge_ratio_method` (str): 'fixed' or 'rolling' (default: 'rolling')

**Example:**
```python
from strategies.stat_arb import PairsTradingStrategy

strategy = PairsTradingStrategy(params={
    "ticker_pair": ("AAPL", "MSFT"),
    "entry_z_score": 2.5,
    "exit_z_score": 0.5
})
```

### 4. Machine Learning Strategies (`ml.py`)

#### MLClassifierStrategy
Uses a pre-trained classifier to predict price direction.

**Parameters:**
- `model`: Pre-trained model with `predict_proba` method
- `feature_columns` (list): List of feature column names
- `confidence_threshold` (float): Minimum prediction confidence (default: 0.7)
- `holding_period` (int): Bars to hold position (default: 10)

## Quick Start

### 1. Basic Usage

```python
from backtest import run_backtest
from strategies.momentum import BreakoutMomentumStrategy

# Define strategy
strategy = BreakoutMomentumStrategy(params={
    "lookback_bars": 30,
    "volume_threshold": 2.0
})

# Run backtest
results = run_backtest(
    strategy=strategy,
    tickers=["AAPL"],
    start_date="2025-10-01",
    end_date="2025-10-05",
    initial_capital=100000.0
)

# Results contain:
# - metrics: PerformanceMetrics object
# - trades: List of Trade objects
# - equity_curve: List of (timestamp, value) tuples
```

### 2. Command Line Interface

```powershell
# Run a backtest from command line
python -m trader.strategy_suite.backtest `
    --strategy momentum.BreakoutMomentum `
    --tickers AAPL `
    --start 2025-10-01 `
    --end 2025-10-05 `
    --capital 100000

# With custom parameters
python -m trader.strategy_suite.backtest `
    --strategy mean_reversion.VWAPReversion `
    --tickers "AAPL,MSFT,GOOGL" `
    --start 2025-10-01 `
    --end 2025-10-31 `
    --capital 100000 `
    --params '{"std_dev_threshold": 2.5, "holding_period": 45}'
```

### 3. Generate Visualizations

```python
from visualization import create_full_report, plot_equity_curve
from pathlib import Path

# Generate complete report with all plots
create_full_report(
    results=results,
    output_dir=Path("reports"),
    strategy_name="BreakoutMomentum_AAPL"
)

# Or plot individual charts
plot_equity_curve(
    equity_curve=results["equity_curve"],
    title="My Strategy Equity Curve",
    save_path=Path("equity_curve.png")
)
```

## Performance Metrics

The suite calculates comprehensive performance metrics:

### Return Metrics
- **Total Return (%)**: Net profit/loss as percentage of initial capital
- **Total P&L ($)**: Absolute profit/loss in dollars
- **CAGR (%)**: Compound Annual Growth Rate (annualized)

### Risk Metrics
- **Sharpe Ratio**: Risk-adjusted return (higher is better)
- **Sortino Ratio**: Downside risk-adjusted return
- **Max Drawdown (%)**: Largest peak-to-trough decline
- **Max DD Duration**: Longest drawdown period in days
- **Calmar Ratio**: CAGR / Max Drawdown
- **Daily Volatility (%)**: Standard deviation of returns

### Trade Statistics
- **Win Rate (%)**: Percentage of profitable trades
- **Profit Factor**: Gross profit / Gross loss
- **Avg Win/Loss ($)**: Average profit/loss per winning/losing trade
- **Win/Loss Ratio**: Avg Win / Avg Loss
- **Total Trades**: Number of completed trades

### Other
- **Avg Trade Duration**: Average time in position
- **Exposure (%)**: Average capital deployed

## Simulator Configuration

Customize trade execution and risk management:

```python
from simulator import SimulatorConfig

config = SimulatorConfig(
    initial_capital=100000.0,
    slippage_rate=0.0005,           # 0.05% slippage per trade
    commission_per_share=0.0,       # Commission (e.g., 0.0 for zero-commission)
    position_size=0.1,              # 10% of capital per position
    max_positions=10,               # Maximum concurrent positions
    stop_loss_pct=0.01,             # 1% stop loss
    take_profit_pct=0.02,           # 2% take profit
    execution_delay_bars=1,         # Execution delay (1 = next bar)
    allow_shorts=True               # Allow short selling
)

# Use in backtest
results = run_backtest(
    strategy=strategy,
    tickers=["AAPL"],
    start_date="2025-10-01",
    end_date="2025-10-05",
    **config.__dict__  # Pass config parameters
)
```

## Creating Custom Strategies

Extend `BaseStrategy` to create your own:

```python
from strategies.base import BaseStrategy, Signal, SignalAction
import polars as pl

class MyCustomStrategy(BaseStrategy):
    def __init__(self, params=None):
        default_params = {
            "my_param": 10,
        }
        if params:
            default_params.update(params)
        super().__init__("MyCustomStrategy", default_params)

    def generate_signals(self, data: pl.DataFrame) -> list[Signal]:
        signals = []

        # Your strategy logic here
        # Iterate through data and generate signals

        for row in data.iter_rows(named=True):
            # Example: Buy if close > some threshold
            if row["close"] > threshold:
                signals.append(Signal(
                    timestamp=row["timestamp"],
                    ticker=row["ticker"],
                    action=SignalAction.BUY,
                    size=1.0,
                    price=row["close"],
                    reason="Custom condition met"
                ))

        return signals
```

## Data Requirements

### S3 Data Format
- **Location**: `s3://polygon-trader-data-roshen/us_stocks_sip/minute_aggs_v1/`
- **Format**: Parquet files partitioned by date (YYYY-MM-DD.parquet)
- **Schema**:
  - `timestamp` (datetime)
  - `ticker` (string)
  - `open`, `high`, `low`, `close` (float)
  - `volume` (int)

### AWS Credentials
Set environment variables before running:
```powershell
$env:AWS_ACCESS_KEY_ID = "your-access-key"
$env:AWS_SECRET_ACCESS_KEY = "your-secret-key"
```

## Example Workflows

See `example.py` for complete examples:

1. **Single Strategy Backtest**: Test one strategy on one or more tickers
2. **Multiple Strategy Comparison**: Compare different strategies on same data
3. **Parameter Sweep**: Optimize strategy parameters systematically

Run examples:
```powershell
# Example 1: Single backtest
python src/trader/strategy_suite/example.py 1

# Example 2: Compare strategies
python src/trader/strategy_suite/example.py 2

# Example 3: Parameter optimization
python src/trader/strategy_suite/example.py 3
```

## Output Files

Backtests generate the following outputs:

### Reports Directory (`reports/`)
- `{strategy_name}_equity_curve.png`: Portfolio value over time
- `{strategy_name}_drawdown.png`: Drawdown chart
- `{strategy_name}_returns_dist.png`: Distribution of trade returns
- `{strategy_name}_pnl_timeline.png`: P&L per trade over time
- `{strategy_name}_heatmap.png`: Performance by ticker and day

### CSV Summary (`strategy_results.csv`)
Tabular summary of all runs with metrics for easy comparison in Excel/pandas.

## Best Practices

1. **Start Small**: Test on 1-2 tickers for 1-2 days first
2. **Validate Data**: Ensure S3 data is accessible before running large backtests
3. **Parameter Sensitivity**: Test multiple parameter combinations
4. **Out-of-Sample Testing**: Use different periods for validation
5. **Transaction Costs**: Always include realistic slippage and commissions
6. **Risk Management**: Use stop-losses to prevent runaway losses
7. **Multiple Strategies**: Diversify by running several uncorrelated strategies

## Troubleshooting

### "No data loaded from S3"
- Check AWS credentials are set
- Verify S3 bucket and path are correct
- Ensure dates have data available

### "No signals generated"
- Check strategy parameters (might be too restrictive)
- Verify data has required columns (OHLCV)
- Try relaxing entry conditions

### DuckDB errors
- Ensure DuckDB and httpfs extension are installed
- Check network connectivity to S3

### Performance Issues
- Reduce date range or number of tickers
- Use fewer strategy parameter combinations
- Process data in smaller chunks (day by day)

## Dependencies

Required packages:
- `polars` - Fast DataFrame operations
- `duckdb` - SQL analytics on Parquet
- `numpy` - Numerical computations
- `matplotlib` - Plotting
- `seaborn` - Heatmaps

Install:
```powershell
pip install polars duckdb numpy matplotlib seaborn
```

## Future Enhancements

Potential extensions for Phase 4+:
- Real-time data integration
- Live trading connector
- Portfolio optimization (multi-strategy)
- Advanced ML feature engineering
- Genetic algorithm for parameter optimization
- Walk-forward analysis
- Risk dashboards

---

For questions or issues, refer to the main project documentation or check the example scripts.
