"""
CLI for multi-strategy portfolio optimization.

Runs multiple strategies, combines their returns, and optimizes portfolio weights
using various methods (static, dynamic, meta).
"""

import argparse
import json
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from trader.strategy_suite.backtest import run_backtest
from trader.strategy_suite.optimizer.weights import StaticOptimizer
from trader.strategy_suite.optimizer.dynamic import DynamicAllocator
from trader.strategy_suite.visualization import (
    plot_equity_curve,
    plot_drawdown,
    plot_multi_equity,
    plot_corr_heatmap,
    plot_weight_trajectory
)
from trader.strategy_suite.metrics import (
    sharpe,
    sortino,
    max_drawdown,
    calmar,
    calculate_metrics
)

# Import all strategies
from trader.strategy_suite.strategies.opening_range import ORB
from trader.strategy_suite.strategies.volatility_breakout import ATRBreakout
from trader.strategy_suite.strategies.vwap_bands import VWAPBands
from trader.strategy_suite.strategies.bollinger_revert import BollRevert
from trader.strategy_suite.strategies.intraday_seasonality import Seasonality
from trader.strategy_suite.strategies.cross_sectional_momo import CSM
from trader.strategy_suite.strategies.kalman_pairs import KalPairs
from trader.strategy_suite.strategies.kf_trend import KFTrend
from trader.strategy_suite.strategies.momentum import BreakoutMomentumStrategy, VolumeSpikeStrategy
from trader.strategy_suite.strategies.mean_reversion import VWAPReversionStrategy, BollingerBandStrategy
from trader.strategy_suite.strategies.stat_arb import PairsTradingStrategy


# Strategy registry
STRATEGIES = {
    # New strategies
    "opening_range.ORB": ORB,
    "volatility_breakout.ATRBreakout": ATRBreakout,
    "vwap_bands.VWAPBands": VWAPBands,
    "bollinger_revert.BollRevert": BollRevert,
    "intraday_seasonality.Seasonality": Seasonality,
    "cross_sectional_momo.CSM": CSM,
    "kalman_pairs.KalPairs": KalPairs,
    "kf_trend.KFTrend": KFTrend,

    # Existing strategies
    "momentum.BreakoutMomentum": BreakoutMomentumStrategy,
    "momentum.VolumeSpike": VolumeSpikeStrategy,
    "mean_reversion.VWAPReversion": VWAPReversionStrategy,
    "mean_reversion.BollingerBand": BollingerBandStrategy,
    "stat_arb.PairsTrading": PairsTradingStrategy,
}


def load_config(config_file: str) -> dict:
    """Load optimizer config from YAML file."""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config


def run_strategy_backtest(
    strategy_name: str,
    strategy_cls: type,
    tickers: List[str],
    start: str,
    end: str,
    capital: float,
    **strategy_params
) -> pd.Series:
    """
    Run backtest for a single strategy and return its returns series.

    Returns:
        Series indexed by timestamp with period returns
    """
    print(f"  Running backtest for {strategy_name}...")

    try:
        # Initialize strategy with default params
        strategy = strategy_cls(params=strategy_params if strategy_params else {})

        # Run backtest using existing API
        results = run_backtest(
            strategy=strategy,
            tickers=tickers,
            start_date=start,
            end_date=end,
            initial_capital=capital
        )

        # Extract equity curve
        equity_curve = results.get('equity_curve', [])

        if len(equity_curve) == 0:
            print(f"    WARNING: No equity data for {strategy_name}")
            return pd.Series(dtype=float)

        # Convert equity curve (list of tuples) to returns series
        timestamps = [t for t, _ in equity_curve]
        values = [v for _, v in equity_curve]

        equity_series = pd.Series(values, index=timestamps)
        returns = equity_series.pct_change().fillna(0)
        returns.name = strategy_name

        final_equity = values[-1] if values else capital
        print(f"    Completed: {len(returns)} bars, final equity: ${final_equity:,.2f}")

        return returns

    except Exception as e:
        print(f"    ERROR running {strategy_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.Series(dtype=float)


def build_returns_matrix(
    strategies: List[str],
    tickers: List[str],
    start: str,
    end: str,
    capital: float
) -> pd.DataFrame:
    """
    Run backtests for all strategies and build returns matrix.

    Returns:
        DataFrame with columns = strategy names, index = timestamp, values = returns
    """
    print(f"\nRunning backtests for {len(strategies)} strategies...")

    returns_dict = {}

    for strat_name in strategies:
        if strat_name not in STRATEGIES:
            print(f"  WARNING: Unknown strategy '{strat_name}', skipping")
            continue

        strategy_cls = STRATEGIES[strat_name]

        # Use default params (could load from config later)
        strat_returns = run_strategy_backtest(
            strat_name,
            strategy_cls,
            tickers,
            start,
            end,
            capital
        )

        if len(strat_returns) > 0:
            returns_dict[strat_name] = strat_returns

    if not returns_dict:
        raise ValueError("No valid strategy returns generated")

    # Combine into DataFrame and align timestamps
    returns_df = pd.DataFrame(returns_dict)

    # Forward fill missing values (if strategies have different timestamps)
    returns_df = returns_df.fillna(0)

    print(f"\nReturns matrix: {returns_df.shape[0]} bars × {returns_df.shape[1]} strategies")
    return returns_df


def optimize_static(
    returns_df: pd.DataFrame,
    objective: str = "sharpe",
    constraints: dict = None
) -> tuple:
    """
    Run static optimization.

    Returns:
        (weights_dict, portfolio_returns, metrics)
    """
    print(f"\nOptimizing static portfolio (objective: {objective})...")

    optimizer = StaticOptimizer(returns_df)

    if objective == "equal":
        weights, port_returns, metrics = optimizer.equal()
    elif objective == "risk_parity":
        weights, port_returns, metrics = optimizer.risk_parity()
    elif objective == "sharpe":
        # Pass constraints if provided
        max_weight = constraints.get('max_weight', 1.0) if constraints else 1.0
        long_only = constraints.get('long_only', True) if constraints else True
        weights, port_returns, metrics = optimizer.mean_variance(
            objective='sharpe',
            max_weight=max_weight,
            long_only=long_only
        )
    else:
        raise ValueError(f"Unknown objective: {objective}")

    return weights, port_returns, metrics


def optimize_dynamic(
    returns_df: pd.DataFrame,
    mode: str = "rolling",
    window: int = 240,
    rebalance: int = 60
) -> tuple:
    """
    Run dynamic optimization.

    Returns:
        (weights_df, portfolio_returns, metrics)
    """
    print(f"\nOptimizing dynamic portfolio (mode: {mode}, window: {window}, rebalance: {rebalance})...")

    allocator = DynamicAllocator(returns_df)

    if mode == "rolling":
        port_returns, weights_df = allocator.rolling_perf(
            window=window,
            rebalance=rebalance,
            floor=0.0
        )
    elif mode == "regime":
        # For regime, we'd need to implement regime detection
        # For now, fall back to rolling
        print("  WARNING: Regime mode not fully implemented, using rolling instead")
        port_returns, weights_df = allocator.rolling_perf(
            window=window,
            rebalance=rebalance,
            floor=0.0
        )
    else:
        raise ValueError(f"Unknown dynamic mode: {mode}")

    # Calculate metrics
    from trader.strategy_suite.metrics import calculate_metrics
    metrics = calculate_metrics(port_returns)

    return weights_df, port_returns, metrics


def save_results(
    weights: Dict[str, float] or pd.DataFrame,
    portfolio_returns: pd.Series,
    metrics: Dict[str, float],
    strategy_returns: pd.DataFrame,
    mode: str,
    objective: str
) -> str:
    """
    Save optimization results to artifacts/ and reports/.

    Returns:
        Path to saved weights file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create output directories
    artifacts_dir = Path("artifacts/portfolios")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    reports_dir = Path("reports/portfolio")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Save weights
    weights_file = artifacts_dir / f"{timestamp}_weights.json"

    if isinstance(weights, dict):
        # Static weights
        weights_data = {
            "mode": mode,
            "objective": objective,
            "timestamp": timestamp,
            "weights": weights,
            "metrics": metrics
        }
    else:
        # Dynamic weights (DataFrame)
        weights_data = {
            "mode": mode,
            "objective": objective,
            "timestamp": timestamp,
            "weights": "dynamic",  # Indicate it's time-varying
            "metrics": metrics
        }
        # Save weights timeseries separately
        weights_ts_file = artifacts_dir / f"{timestamp}_weights_timeseries.csv"
        weights.to_csv(weights_ts_file)
        print(f"\nSaved weights timeseries: {weights_ts_file}")

    with open(weights_file, 'w') as f:
        json.dump(weights_data, f, indent=2, default=str)

    print(f"\nSaved weights: {weights_file}")

    # Save metrics table
    metrics_file = reports_dir / f"metrics_table.csv"
    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(metrics_file, index=False)
    print(f"Saved metrics: {metrics_file}")

    # Generate plots
    print("\nGenerating plots...")

    # 1. Equity curve
    equity = (1 + portfolio_returns).cumprod()
    equity_file = reports_dir / "equity_curve.png"

    # Convert Series to list of tuples for plot_equity_curve
    equity_tuples = [(ts, val) for ts, val in zip(equity.index, equity.values)]
    plot_equity_curve(equity_tuples, title=f"Portfolio Equity Curve ({mode} {objective})", save_path=equity_file, show=False)
    print(f"  Saved: {equity_file}")

    # 2. Multi-equity (portfolio vs components)
    multi_equity_file = reports_dir / "multi_equity.png"
    component_equities = {col: (1 + strategy_returns[col]).cumprod() for col in strategy_returns.columns}
    component_equities['Portfolio'] = equity
    plot_multi_equity(component_equities, output_file=str(multi_equity_file))
    print(f"  Saved: {multi_equity_file}")

    # 3. Correlation heatmap
    corr_file = reports_dir / "corr_heatmap.png"
    plot_corr_heatmap(strategy_returns, output_file=str(corr_file))
    print(f"  Saved: {corr_file}")

    # 4. Weights trajectory (if dynamic)
    if isinstance(weights, pd.DataFrame):
        weights_plot_file = reports_dir / "weights_timeseries.png"
        plot_weight_trajectory(weights, output_file=str(weights_plot_file))
        print(f"  Saved: {weights_plot_file}")

    # Also save latest_weights.json
    latest_file = artifacts_dir / "latest_weights.json"
    with open(latest_file, 'w') as f:
        json.dump(weights_data, f, indent=2, default=str)
    print(f"Saved latest: {latest_file}")

    return str(weights_file)


def print_metrics_table(metrics: Dict[str, float], title: str = "Portfolio Metrics"):
    """Print metrics in a formatted table."""
    print(f"\n{'='*60}")
    print(f"{title:^60}")
    print('='*60)

    for key, value in metrics.items():
        if isinstance(value, (int, float)):
            if 'sharpe' in key.lower() or 'sortino' in key.lower() or 'calmar' in key.lower():
                print(f"{key:.<30} {value:>10.3f}")
            elif 'drawdown' in key.lower() or 'return' in key.lower():
                print(f"{key:.<30} {value:>10.2%}")
            else:
                print(f"{key:.<30} {value:>10,.2f}")
        else:
            print(f"{key:.<30} {str(value):>10}")

    print('='*60)


def main():
    parser = argparse.ArgumentParser(
        description="Optimize multi-strategy portfolio"
    )

    # Strategy selection
    parser.add_argument(
        "--strategies",
        required=True,
        help="Comma-separated list of strategies (or 'all')"
    )

    # Data parameters
    parser.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated list of tickers"
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100000.0,
        help="Initial capital (default: 100000)"
    )

    # Optimization mode
    parser.add_argument(
        "--mode",
        choices=["static", "dynamic", "meta"],
        default="static",
        help="Optimization mode (default: static)"
    )
    parser.add_argument(
        "--objective",
        choices=["equal", "risk_parity", "sharpe", "sortino"],
        default="sharpe",
        help="Optimization objective for static mode (default: sharpe)"
    )

    # Dynamic mode options
    parser.add_argument(
        "--dyn",
        choices=["rolling", "regime"],
        default="rolling",
        help="Dynamic allocation method (default: rolling)"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=240,
        help="Rolling window size in bars (default: 240)"
    )
    parser.add_argument(
        "--rebalance",
        type=int,
        default=60,
        help="Rebalancing frequency in bars (default: 60)"
    )

    # Configuration file
    parser.add_argument(
        "--config",
        help="Path to YAML config file (overrides command-line args)"
    )

    args = parser.parse_args()

    # Load config if provided
    config = {}
    if args.config:
        config = load_config(args.config)

    # Parse strategies
    if args.strategies.lower() == "all":
        strategies = list(STRATEGIES.keys())
    else:
        strategies = [s.strip() for s in args.strategies.split(",")]

    # Parse tickers
    tickers = [t.strip() for t in args.tickers.split(",")]

    # Get constraints from config
    constraints = config.get('constraints', {})

    print("="*60)
    print("Multi-Strategy Portfolio Optimizer")
    print("="*60)
    print(f"Mode: {args.mode}")
    print(f"Objective: {args.objective}")
    print(f"Strategies: {len(strategies)}")
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Capital: ${args.capital:,.2f}")
    print("="*60)

    # Build returns matrix
    returns_df = build_returns_matrix(
        strategies,
        tickers,
        args.start,
        args.end,
        args.capital
    )

    # Run optimization
    if args.mode == "static":
        weights, portfolio_returns, metrics = optimize_static(
            returns_df,
            objective=args.objective,
            constraints=constraints
        )

        # Print results
        print("\nOptimal Weights:")
        for strat, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            print(f"  {strat:.<40} {weight:>10.2%}")

        print_metrics_table(metrics, "Static Portfolio Metrics")

    elif args.mode == "dynamic":
        weights_df, portfolio_returns, metrics = optimize_dynamic(
            returns_df,
            mode=args.dyn,
            window=args.window,
            rebalance=args.rebalance
        )

        # Print final weights
        print("\nFinal Weights (last rebalance):")
        final_weights = weights_df.iloc[-1]
        for strat, weight in sorted(final_weights.items(), key=lambda x: x[1], reverse=True):
            print(f"  {strat:.<40} {weight:>10.2%}")

        print_metrics_table(metrics, "Dynamic Portfolio Metrics")

        # Use final weights as dict for saving
        weights = weights_df

    else:
        raise NotImplementedError("Meta mode not yet implemented")

    # Save results
    weights_file = save_results(
        weights,
        portfolio_returns,
        metrics,
        returns_df,
        args.mode,
        args.objective
    )

    print(f"\n{'='*60}")
    print("Optimization complete!")
    print(f"Weights saved to: {weights_file}")
    print(f"Reports saved to: reports/portfolio/")
    print('='*60)


if __name__ == "__main__":
    main()
