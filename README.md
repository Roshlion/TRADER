# TRADER

**Quantitative trading research platform with multi-strategy portfolio optimization**

Building data-driven trading strategies using high-performance analytics, machine learning, and sophisticated portfolio optimization techniques.

---

## Overview

TRADER is an advanced research and development platform for quantitative trading strategies. It processes market data at scale using modern data engineering tools and applies statistical, machine learning, and portfolio optimization techniques to identify profitable trading opportunities.

**Key Features:**
- **14 Production-Ready Intraday Strategies** - Momentum, mean-reversion, pairs trading, and ML-based
- **Full Year of Historical Data** - Oct 2024 - Oct 2025 (~400M minute bars)
- **Automated Parameter Optimization** - Grid search, random search, and genetic algorithms
- **Portfolio Optimization** - Static (Markowitz, Risk Parity) and dynamic allocation
- **ML-Based Strategy Selection** - Adaptive weighting using gradient boosting
- **High-Performance Backtesting** - Minute-level data with realistic transaction costs
- **Cloud-Native Architecture** - AWS S3 data lake with DuckDB analytics

---

## Tech Stack

- **Python 3.11+** - Core development
- **Polars** - High-performance DataFrames (Rust-based)
- **DuckDB** - In-process SQL analytics engine
- **PyArrow/Parquet** - Columnar storage format
- **scikit-learn** - Machine learning for strategy selection
- **scipy** - Portfolio optimization (Markowitz, Risk Parity)
- **AWS S3** - Cloud data lake
- **rclone** - Data transfer & sync

---

## Quick Start

### Installation

```powershell
# Initialize Python environment
.\scripts\windows\init.ps1

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import polars, duckdb, scipy, sklearn; print('All dependencies installed')"
```

### Configuration

```powershell
# Configure AWS credentials and settings
copy .env.example .env
# Edit .env with your configuration
```

### Run Your First Backtest

```powershell
# Test a single strategy (with transaction costs)
cd src
../.venv/Scripts/python -m trader.strategy_suite.backtest \
  --strategy mean_reversion.VWAPReversion \
  --tickers AAPL,MSFT \
  --start 2025-10-01 --end 2025-10-31 \
  --capital 100000 \
  --slippage 0.0005 --commission 0.001
```

---

## Trading Strategies

TRADER includes 14 battle-tested intraday strategies (8 from Phase 4, 5 from Phase 3, 1 ML from Phase 5):

### Momentum Strategies

**Opening Range Breakout (ORB)**
- Trades breakouts of the first N minutes range
- Parameters: `range_minutes`, `confirm_bars`, `atr_mult_stop`
- Best for: Trending markets, high-volatility opens

**ATR Channel Breakout**
- Enters on price exceeding prior close ± k×ATR
- Parameters: `atr_len`, `k`, `vol_filter`
- Best for: Trend-following, breakout confirmation

**Kalman Trend Filter**
- Smooths price with Kalman filter, trades crossovers
- Parameters: `q`, `r`, `hold_trail_atr`
- Best for: Noise reduction, clean trend signals

### Mean Reversion Strategies

**VWAP Bands Reversion**
- Mean-reverts when price stretches beyond VWAP ± dev×std
- Parameters: `dev`, `confirm_red_green`, `hold_max_minutes`
- Best for: Range-bound markets, overextensions

**Bollinger Bands Reversion**
- Trades reversals from Bollinger Band extremes
- Parameters: `len`, `stdev`, `exit_mid`
- Best for: Volatility-based mean reversion

### Statistical Arbitrage

**Kalman Pairs Trading**
- Mean-reverts spread between cointegrated pairs
- Uses Kalman filter for dynamic hedge ratio
- Parameters: `pair`, `z_entry`, `z_exit`, `half_life`
- Best for: Correlated equities, relative value

**Cross-Sectional Momentum (CSM)**
- Ranks tickers by performance, longs top/shorts bottom
- Market-neutral basket approach
- Parameters: `lookback`, `rebalance_minutes`, `basket_n`
- Best for: Universe trading, sector rotation

### Time-Based

**Intraday Seasonality**
- Trades during statistically favorable time windows
- Parameters: `slots`, `direction`, `filter_vol_pct`
- Best for: Open/close effects, time-of-day patterns

---

## Parameter Optimization

### Grid Search

Systematically test all parameter combinations in parallel:

```powershell
python -m scripts.python.run_sweeps \
  --strategy opening_range.ORB \
  --tickers AAPL,MSFT \
  --start 2025-10-01 --end 2025-10-24 \
  --grid configs/sweeps/orb.yaml \
  --capital 100000 --jobs 6
```

**Parameter grid example** (`configs/sweeps/orb.yaml`):
```yaml
range_minutes: [15, 30, 60]
confirm_bars: [0, 1, 2]
atr_mult_stop: [0.5, 1.0, 1.5]
```

Results saved to: `artifacts/sweeps/*.csv` and `reports/sweeps/`

### Genetic Algorithm Optimization

Evolve optimal parameters using evolutionary algorithms:

```powershell
python -m scripts.python.run_sweeps \
  --strategy vwap_bands.VWAPBands \
  --tickers AAPL,MSFT \
  --start 2025-10-01 --end 2025-10-24 \
  --grid configs/sweeps/vwap.yaml \
  --ga --ga-population 50 --ga-generations 20 --ga-fitness sharpe
```

**Features:**
- Tournament selection for diversity
- Uniform crossover and Gaussian mutation
- Configurable population size and generations
- Multiple fitness objectives (Sharpe, Sortino, Calmar, Return)

### Random Search

For large parameter spaces, sample randomly:

```powershell
python -m scripts.python.run_sweeps \
  --strategy bollinger_revert.BollRevert \
  --tickers AAPL \
  --start 2025-10-01 --end 2025-10-24 \
  --grid configs/sweeps/bollinger.yaml \
  --random --n-samples 100 --jobs 8
```

---

## Portfolio Optimization

Combine multiple strategies for superior risk-adjusted returns.

### Static Allocation

**Equal Weight**
```python
from trader.strategy_suite.optimizer.weights import StaticOptimizer

optimizer = StaticOptimizer(returns_df)
weights, portfolio_returns, metrics = optimizer.equal()
```

**Risk Parity (Equal Risk Contribution)**
```python
weights, portfolio_returns, metrics = optimizer.risk_parity()
```

**Mean-Variance (Sharpe Maximization)**
```python
weights, portfolio_returns, metrics = optimizer.mean_variance(
    objective='sharpe',
    max_weight=0.4,  # Max 40% per strategy
    long_only=True
)
```

### Dynamic Allocation

**Rolling Performance Rebalancing**
```python
from trader.strategy_suite.optimizer.dynamic import DynamicAllocator

allocator = DynamicAllocator(strat_returns)
portfolio_returns, weights_ts = allocator.rolling_perf(
    window=240,      # 4 hour lookback
    rebalance=60,    # Rebalance hourly
    metric='sharpe'
)
```

**Regime-Based Switching**
```python
# Define regime detector (e.g., volatility threshold)
def volatility_regime(idx):
    realized_vol = calculate_vol(idx)
    return 'high' if realized_vol > threshold else 'low'

portfolio_returns, weights_ts = allocator.regime_switch(
    detector=volatility_regime,
    W_a={'ORB': 0.6, 'VWAPBands': 0.4},        # High vol weights
    W_b={'BollRevert': 0.5, 'Seasonality': 0.5} # Low vol weights
)
```

### ML-Based Meta-Selection

Use machine learning to predict best-performing strategies:

```python
from trader.strategy_suite.optimizer.meta import MetaSelector

selector = MetaSelector(strat_returns, mode='classifier', lookback=20)
selector.train()  # Walk-forward training

portfolio_returns, weights_ts = selector.backtest()
selector.save('artifacts/models/meta_selector.pkl')
```

**Features extracted:**
- Recent returns per strategy (last 5 periods)
- Rolling volatility
- Cumulative returns over lookback
- Cross-sectional ranks
- Time-of-day (sin/cos encoded)

---

## OptimalStrategy Wrapper

Trade a portfolio of strategies as a single strategy:

```python
from trader.strategy_suite.optimal.optimal import OptimalStrategy, create_portfolio_config

# Create portfolio config
weights = {
    'ORB': 0.3,
    'VWAPBands': 0.3,
    'BollRevert': 0.2,
    'CSM': 0.2
}

strategy_params = {
    'ORB': {'range_minutes': 30, 'confirm_bars': 1},
    'VWAPBands': {'dev': 1.5, 'hold_max_minutes': 60},
    'BollRevert': {'len': 20, 'stdev': 2.0},
    'CSM': {'lookback': 60, 'basket_n': 5}
}

create_portfolio_config(weights, strategy_params, 'artifacts/portfolios/best_weights.json')

# Backtest the portfolio
from trader.strategy_suite.backtest import run_backtest

optimal = OptimalStrategy()
results = run_backtest(
    strategy=optimal,
    tickers=['AAPL', 'MSFT', 'GOOGL', 'AMZN'],
    start_date='2025-10-01',
    end_date='2025-10-24',
    initial_capital=100000
)
```

---

## Project Structure

```
TRADER/
├── src/trader/
│   └── strategy_suite/
│       ├── strategies/          # 8 trading strategies
│       │   ├── opening_range.py
│       │   ├── volatility_breakout.py
│       │   ├── vwap_bands.py
│       │   ├── bollinger_revert.py
│       │   ├── intraday_seasonality.py
│       │   ├── cross_sectional_momo.py
│       │   ├── kalman_pairs.py
│       │   └── kf_trend.py
│       ├── optimizer/           # Portfolio optimization
│       │   ├── weights.py       # Static: Equal, Risk Parity, MV
│       │   ├── dynamic.py       # Dynamic allocation
│       │   └── meta.py          # ML-based selection
│       ├── sweep/               # Parameter optimization
│       │   ├── grid.py          # Grid/random search
│       │   └── ga.py            # Genetic algorithms
│       ├── optimal/             # Multi-strategy wrapper
│       │   └── optimal.py
│       ├── backtest.py          # Orchestrator
│       ├── simulator.py         # Trade execution sim
│       ├── metrics.py           # Performance analytics
│       └── visualization.py     # Plotting utilities
├── scripts/
│   ├── windows/                 # PowerShell automation
│   └── python/
│       └── run_sweeps.py        # Parameter sweep CLI
├── configs/
│   ├── optimizer.yaml           # Portfolio config
│   └── sweeps/                  # Parameter grids
│       ├── orb.yaml
│       ├── vwap.yaml
│       └── bollinger.yaml
├── artifacts/
│   ├── sweeps/                  # Sweep results (CSV)
│   ├── portfolios/              # Portfolio configs (JSON)
│   └── models/                  # Trained ML models
└── reports/
    ├── sweeps/                  # Sweep analysis
    └── portfolio/               # Portfolio reports
```

---

## Data Pipeline

**Sources:**
- Market data: Polygon.io Flat Files API (minute OHLCV)
- Storage: AWS S3 (encrypted, versioned, partitioned)
- Format: CSV.gz (raw), Parquet (curated)

**Processing:**
- Server-side sync via rclone (Polygon → S3)
- Parquet conversion for columnar analytics
- Partitioned by date: `year=YYYY/month=MM/day=YYYY-MM-DD/*.parquet`
- Queried via DuckDB (no full download required)

**Data Access Pattern:**
```python
# DuckDB automatically queries only required partitions
query = f"""
SELECT * FROM read_parquet('s3://bucket/curated/minute_bars/year=2025/month=10/day=*/*)
WHERE ticker IN ('AAPL', 'MSFT')
ORDER BY window_start
"""
```

---

## Performance Metrics

The system calculates comprehensive performance analytics:

**Return Metrics:**
- Total return, CAGR, daily returns

**Risk Metrics:**
- Sharpe Ratio (risk-adjusted return)
- Sortino Ratio (downside risk-adjusted)
- Max Drawdown (peak-to-trough)
- Ulcer Index (downside volatility)
- Calmar Ratio (CAGR / Max DD)

**Trade Statistics:**
- Win rate, profit factor
- Average win/loss, win/loss ratio
- Trade count, exposure %

**Portfolio Metrics:**
- Correlation matrix
- Effective N (diversification)
- Time-varying weights (for dynamic allocation)

---

## Configuration

### Environment Variables

Create `.env` with:
```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret

# Data Configuration
S3_BUCKET=your-bucket-name
S3_PREFIX=curated/minute_bars

# Backtest Configuration
INITIAL_CAPITAL=100000
SLIPPAGE_BPS=1.0
COMMISSION_PER_SHARE=0.001
```

### Strategy Configuration

Edit `configs/optimizer.yaml`:
```yaml
objective: sharpe          # sharpe|sortino|calmar|return
mode: static               # static|dynamic|meta
strategies:
  - opening_range.ORB
  - vwap_bands.VWAPBands
  - bollinger_revert.BollRevert
  - cross_sectional_momo.CSM

constraints:
  long_only: true
  max_weight: 0.4          # Max 40% per strategy

slippage_bps: 1.0
fees_bps: 0.2
```

---

## Development

### Requirements
- Python 3.11+
- PowerShell 5.1+ (Windows)
- AWS CLI configured
- rclone installed (for data pipeline)

### Setup

```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
python -c "import sys; sys.path.insert(0, 'src'); from trader.strategy_suite.strategies.opening_range import ORB; print('OK')"
```

### Adding New Strategies

1. **Create strategy file** in `src/trader/strategy_suite/strategies/`
2. **Inherit from `BaseStrategy`** and implement `generate_signals()`
3. **Add to registry** in `scripts/python/run_sweeps.py` and `optimal/optimal.py`
4. **Create parameter grid** in `configs/sweeps/`
5. **Run sweep** to optimize parameters
6. **Add to portfolio** via optimizer

**Template:**
```python
from .base import BaseStrategy, Signal, SignalAction

class MyStrategy(BaseStrategy):
    def __init__(self, params: Dict[str, Any] = None):
        default_params = {'param1': 10, 'param2': 0.5}
        if params:
            default_params.update(params)
        super().__init__("MyStrategy", default_params)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        # Your strategy logic here
        signals = []
        # ...
        return signals
```

---

## Deployment (EC2)

The system is designed for cloud deployment:

1. **Launch EC2 instance** (t3.medium or c5.large)
2. **Install dependencies**: Python, AWS CLI, rclone
3. **Clone repository** and install packages
4. **Configure IAM role** for S3 access (no credentials in code)
5. **Run backtests/sweeps** using instance cores
6. **Store artifacts** back to S3 for durability

**Recommended setup:**
- Instance: c5.2xlarge (8 vCPUs) for parallel sweeps
- Storage: 100GB EBS (SSD)
- Region: Same as S3 bucket (minimize data transfer)
- Auto-shutdown after job completion (cost savings)

---

## Best Practices

### Strategy Development
1. **Start simple** - Test single strategies before portfolios
2. **Out-of-sample validation** - Always use holdout data
3. **Walk-forward testing** - Retrain/reoptimize periodically
4. **Transaction costs** - Include realistic slippage and fees

### Portfolio Construction
1. **Diversify** - Combine uncorrelated strategies
2. **Risk management** - Use max weight constraints
3. **Regime awareness** - Consider dynamic allocation
4. **Rebalance frequency** - Balance turnover vs adaptation

### Optimization
1. **Avoid overfitting** - Keep parameter grids reasonable
2. **Use cross-validation** - Walk-forward or time-series splits
3. **Multiple objectives** - Consider Sharpe AND drawdown
4. **Robustness checks** - Test on multiple time periods

---

## Troubleshooting

**Import errors:**
```powershell
pip install scipy scikit-learn pyyaml statsmodels
```

**AWS credentials:**
```powershell
aws configure
# Or set environment variables in .env
```

**DuckDB S3 access:**
- Ensure AWS credentials are properly configured
- Check S3 bucket permissions
- Verify S3 path structure matches expected format

**No signals generated:**
- Check strategy parameters (may be too restrictive)
- Verify data quality and date range
- Review strategy logic for edge cases

---

## Performance

**Typical Runtime (c5.2xlarge, 8 cores):**
- Single strategy backtest (1 month, 2 tickers): ~30 seconds
- Parameter sweep (100 combinations, parallel): ~15 minutes
- GA optimization (50 population, 20 generations): ~45 minutes
- Portfolio optimization (5 strategies, 1 month): ~5 minutes

**Memory Usage:**
- Single strategy: ~500 MB
- Parameter sweep: ~2 GB (parallel processes)
- Portfolio optimization: ~1 GB

---

## License

To be determined

---

## Disclaimer

This project is for educational and research purposes only. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always conduct thorough testing and risk management before deploying any trading strategy with real capital.

**No Investment Advice:** The strategies and code provided do not constitute financial or investment advice. Users are solely responsible for their trading decisions.

---

## Support

For issues, questions, or contributions:
- **Documentation**: See `DOCUMENTATION.md` for complete technical details
- **Issues**: Create an issue in the repository
- **Configuration**: Check `configs/` for examples

---

**Built with ❤️ for algorithmic trading research**
