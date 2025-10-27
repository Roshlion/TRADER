"""
Backtest orchestrator for running trading strategies on historical data.

Loads data from S3 Parquet via DuckDB, generates signals, simulates trades,
calculates metrics, and produces reports.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import sys
from pathlib import Path
import polars as pl
import duckdb

from .simulator import Simulator, SimulatorConfig
from .metrics import calculate_metrics, print_metrics_summary, PerformanceMetrics
from .strategies.base import BaseStrategy
from .strategies.momentum import BreakoutMomentumStrategy, VolumeSpikeStrategy
from .strategies.mean_reversion import VWAPReversionStrategy, BollingerBandStrategy
from .strategies.stat_arb import PairsTradingStrategy
from .strategies.ml import MLClassifierStrategy


@dataclass
class BacktestConfig:
    """
    Configuration for a backtest run.

    Attributes:
        strategy: Strategy instance to test
        tickers: List of ticker symbols
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        s3_bucket: S3 bucket name
        s3_prefix: S3 key prefix for parquet files
        simulator_config: Configuration for trade simulator
    """
    strategy: BaseStrategy
    tickers: List[str]
    start_date: str
    end_date: str
    s3_bucket: str = "polygon-trader-data-roshen"
    s3_prefix: str = "curated/minute_bars"
    simulator_config: Optional[SimulatorConfig] = None


class Backtester:
    """
    Main backtesting engine.

    Orchestrates data loading, signal generation, trade simulation,
    and metric calculation.
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize backtester.

        Args:
            config: Backtest configuration
        """
        self.config = config
        self.simulator = Simulator(config.simulator_config or SimulatorConfig())
        self.conn = None

    def _init_duckdb(self):
        """Initialize DuckDB connection with S3 support."""
        if self.conn is None:
            import os
            import boto3

            self.conn = duckdb.connect()
            # Install and load httpfs for S3 access
            self.conn.execute("INSTALL httpfs;")
            self.conn.execute("LOAD httpfs;")

            # Get AWS credentials using boto3 (reads from env vars or ~/.aws/credentials)
            try:
                session = boto3.Session()
                credentials = session.get_credentials()

                if credentials:
                    # Set DuckDB S3 configuration
                    self.conn.execute(f"SET s3_region='{session.region_name or 'us-east-1'}';")
                    self.conn.execute(f"SET s3_access_key_id='{credentials.access_key}';")
                    self.conn.execute(f"SET s3_secret_access_key='{credentials.secret_key}';")

                    # Handle session token if present (for temporary credentials)
                    if credentials.token:
                        self.conn.execute(f"SET s3_session_token='{credentials.token}';")

                    print(f"DuckDB initialized with S3 support (region: {session.region_name or 'us-east-1'})")
                else:
                    raise ValueError("No AWS credentials found. Run 'aws configure' or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

            except Exception as e:
                raise RuntimeError(f"Failed to initialize S3 credentials for DuckDB: {e}")

    def load_data(self) -> pl.DataFrame:
        """
        Load market data from S3 Parquet via DuckDB.

        Returns:
            Polars DataFrame with OHLCV data
        """
        self._init_duckdb()

        # Parse dates
        start = datetime.strptime(self.config.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(self.config.end_date, "%Y-%m-%d").date()

        # Generate list of dates
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            # Increment day
            from datetime import timedelta
            current += timedelta(days=1)

        print(f"Loading data for {len(self.config.tickers)} tickers from {start} to {end}...")

        all_data = []

        for date_obj in dates:
            date_str = date_obj.strftime("%Y-%m-%d")
            year = date_obj.year
            month = date_obj.month

            # Parquet files are in partitioned structure: year=YYYY/month=MM/day=YYYY-MM-DD/part-0000.parquet
            s3_path = f"s3://{self.config.s3_bucket}/{self.config.s3_prefix}/year={year}/month={month}/day={date_str}/*.parquet"

            # Build ticker filter
            ticker_list = ", ".join([f"'{t}'" for t in self.config.tickers])

            query = f"""
            SELECT
                window_start as timestamp,
                ticker,
                open,
                high,
                low,
                close,
                volume
            FROM read_parquet('{s3_path}')
            WHERE ticker IN ({ticker_list})
            ORDER BY window_start
            """

            try:
                # Execute query and get as Polars DataFrame
                result = self.conn.execute(query).pl()

                if len(result) > 0:
                    all_data.append(result)
                    print(f"  Loaded {len(result)} rows for {date_str}")
                else:
                    print(f"  No data for {date_str}")

            except Exception as e:
                print(f"  Warning: Could not load data for {date_str}: {e}")
                continue

        if not all_data:
            raise ValueError("No data loaded from S3")

        # Combine all data
        combined = pl.concat(all_data)
        print(f"Total rows loaded: {len(combined)}")

        return combined

    def run(self) -> Dict[str, Any]:
        """
        Run the full backtest.

        Returns:
            Dictionary with results including metrics, trades, and equity curve
        """
        print("\n" + "=" * 60)
        print(f"BACKTEST: {self.config.strategy.name}")
        print("=" * 60)
        print(f"Strategy params: {self.config.strategy.params}")
        print(f"Tickers: {', '.join(self.config.tickers)}")
        print(f"Date range: {self.config.start_date} to {self.config.end_date}")
        print("=" * 60 + "\n")

        # Load data
        data = self.load_data()

        # Generate signals
        print("\nGenerating signals...")
        signals = self.config.strategy.generate_signals(data)
        print(f"Generated {len(signals)} signals")

        if len(signals) == 0:
            print("Warning: No signals generated. Check strategy parameters.")
            return {
                "strategy": self.config.strategy.name,
                "params": self.config.strategy.params,
                "metrics": None,
                "trades": [],
                "equity_curve": [],
                "num_signals": 0,
            }

        # Print first few signals
        print("\nFirst 5 signals:")
        for sig in signals[:5]:
            print(f"  {sig}")

        # Run simulation
        print("\nRunning simulation...")
        trades, equity_curve = self.simulator.run(signals, data)
        print(f"Completed {len(trades)} trades")

        # Calculate metrics
        print("\nCalculating metrics...")
        metrics = calculate_metrics(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=self.simulator.config.initial_capital
        )

        # Print metrics summary
        print_metrics_summary(metrics)

        return {
            "strategy": self.config.strategy.name,
            "params": self.config.strategy.params,
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
            "num_signals": len(signals),
        }

    def close(self):
        """Close DuckDB connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


def run_backtest(
    strategy: BaseStrategy,
    tickers: List[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to run a backtest.

    Args:
        strategy: Strategy instance
        tickers: List of ticker symbols
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        initial_capital: Starting capital
        **kwargs: Additional simulator config parameters

    Returns:
        Dictionary with backtest results
    """
    sim_config = SimulatorConfig(initial_capital=initial_capital, **kwargs)

    config = BacktestConfig(
        strategy=strategy,
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        simulator_config=sim_config
    )

    backtester = Backtester(config)
    try:
        results = backtester.run()
        return results
    finally:
        backtester.close()


def main():
    """Command-line interface for running backtests."""
    parser = argparse.ArgumentParser(
        description="Backtest trading strategies on historical data"
    )
    parser.add_argument(
        "--strategy",
        required=True,
        choices=[
            "momentum.BreakoutMomentum",
            "momentum.VolumeSpike",
            "mean_reversion.VWAPReversion",
            "mean_reversion.BollingerBand",
            "stat_arb.PairsTrading",
            "ml.MLClassifier",
        ],
        help="Strategy to backtest"
    )
    parser.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated list of tickers (e.g., 'AAPL,MSFT')"
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
    parser.add_argument(
        "--params",
        help="Strategy parameters as JSON string (e.g., '{\"lookback_bars\": 30}')"
    )

    args = parser.parse_args()

    # Parse tickers
    tickers = [t.strip() for t in args.tickers.split(",")]

    # Parse strategy params
    params = {}
    if args.params:
        import json
        params = json.loads(args.params)

    # Create strategy instance
    strategy_map = {
        "momentum.BreakoutMomentum": BreakoutMomentumStrategy,
        "momentum.VolumeSpike": VolumeSpikeStrategy,
        "mean_reversion.VWAPReversion": VWAPReversionStrategy,
        "mean_reversion.BollingerBand": BollingerBandStrategy,
        "stat_arb.PairsTrading": PairsTradingStrategy,
        "ml.MLClassifier": MLClassifierStrategy,
    }

    strategy_class = strategy_map[args.strategy]
    strategy = strategy_class(params=params)

    # Run backtest
    results = run_backtest(
        strategy=strategy,
        tickers=tickers,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital
    )

    print("\nBacktest completed successfully!")
    return results


if __name__ == "__main__":
    main()
