"""
Parameter sweep orchestrator using grid/random search with parallel execution.
"""

import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Type, Optional
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools
from dataclasses import asdict

from ..strategies.base import BaseStrategy
from ..backtest import run_backtest
from ..metrics import PerformanceMetrics


def _run_single_backtest(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a single backtest (worker function for parallel execution).

    Args:
        args: Dictionary with strategy_class, params, tickers, dates, capital

    Returns:
        Dictionary with results
    """
    try:
        # Unpack args
        strategy_cls = args["strategy_class"]
        params = args["params"]
        tickers = args["tickers"]
        start_date = args["start_date"]
        end_date = args["end_date"]
        initial_capital = args["initial_capital"]

        # Instantiate strategy with params
        strategy = strategy_cls(params=params)

        # Run backtest
        results = run_backtest(
            strategy=strategy,
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital
        )

        # Extract metrics
        metrics = results["metrics"]

        if metrics is None:
            return {
                "strategy": strategy.name,
                "params": json.dumps(params),
                "sharpe": 0.0,
                "sortino": 0.0,
                "pnl": 0.0,
                "return_pct": 0.0,
                "max_dd": 0.0,
                "trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "calmar": 0.0,
                "success": False,
                "error": "No signals generated"
            }

        return {
            "strategy": strategy.name,
            "params": json.dumps(params),
            "sharpe": metrics.sharpe_ratio,
            "sortino": metrics.sortino_ratio,
            "pnl": metrics.total_pnl,
            "return_pct": metrics.total_return_pct,
            "max_dd": metrics.max_drawdown_pct,
            "trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "profit_factor": metrics.profit_factor,
            "calmar": metrics.calmar_ratio,
            "success": True,
            "error": None
        }

    except Exception as e:
        return {
            "strategy": args["strategy_class"].__name__,
            "params": json.dumps(args["params"]),
            "sharpe": 0.0,
            "sortino": 0.0,
            "pnl": 0.0,
            "return_pct": 0.0,
            "max_dd": 0.0,
            "trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "calmar": 0.0,
            "success": False,
            "error": str(e)
        }


class SweepRunner:
    """
    Parameter sweep runner with parallel execution.

    Runs grid or random search over strategy parameters and collects metrics.
    """

    def __init__(
        self,
        strategy_cls: Type[BaseStrategy],
        param_grid: Dict[str, List[Any]],
        tickers: List[str],
        start_date: str,
        end_date: str,
        capital: float = 100000.0,
        out_csv: Optional[str] = None,
        n_jobs: int = 4,
        random: bool = False,
        n_samples: int = 100,
        seed: int = 42
    ):
        """
        Initialize sweep runner.

        Args:
            strategy_cls: Strategy class (not instance)
            param_grid: Dictionary mapping param name to list of values
            tickers: List of ticker symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            capital: Initial capital
            out_csv: Output CSV path (if None, auto-generated)
            n_jobs: Number of parallel workers
            random: Use random search instead of grid search
            n_samples: Number of random samples (if random=True)
            seed: Random seed for reproducibility
        """
        self.strategy_cls = strategy_cls
        self.param_grid = param_grid
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.capital = capital
        self.n_jobs = n_jobs
        self.random = random
        self.n_samples = n_samples
        self.seed = seed

        # Auto-generate output path if not provided
        if out_csv is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            strategy_name = strategy_cls.__name__
            out_csv = f"artifacts/sweeps/{strategy_name}_{timestamp}.csv"

        self.out_csv = out_csv
        self.results_df = None

    def _generate_param_combinations(self) -> List[Dict[str, Any]]:
        """
        Generate parameter combinations for sweep.

        Returns:
            List of parameter dictionaries
        """
        if self.random:
            # Random search
            np.random.seed(self.seed)
            param_combinations = []

            for _ in range(self.n_samples):
                params = {}
                for key, values in self.param_grid.items():
                    params[key] = np.random.choice(values)
                param_combinations.append(params)

        else:
            # Grid search - all combinations
            param_names = list(self.param_grid.keys())
            param_values = [self.param_grid[name] for name in param_names]

            param_combinations = []
            for values in itertools.product(*param_values):
                params = dict(zip(param_names, values))
                param_combinations.append(params)

        return param_combinations

    def run(self) -> pd.DataFrame:
        """
        Run parameter sweep.

        Returns:
            DataFrame with results
        """
        print(f"\n{'=' * 60}")
        print(f"PARAMETER SWEEP: {self.strategy_cls.__name__}")
        print(f"{'=' * 60}")
        print(f"Tickers: {', '.join(self.tickers)}")
        print(f"Date range: {self.start_date} to {self.end_date}")
        print(f"Initial capital: ${self.capital:,.2f}")
        print(f"Search type: {'Random' if self.random else 'Grid'}")
        print(f"Parallel workers: {self.n_jobs}")

        # Generate parameter combinations
        param_combinations = self._generate_param_combinations()
        print(f"Parameter combinations: {len(param_combinations)}")
        print(f"{'=' * 60}\n")

        # Prepare jobs
        jobs = []
        for params in param_combinations:
            job = {
                "strategy_class": self.strategy_cls,
                "params": params,
                "tickers": self.tickers,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "initial_capital": self.capital
            }
            jobs.append(job)

        # Run backtests in parallel
        results = []
        completed = 0

        print(f"Running {len(jobs)} backtests...")

        with ProcessPoolExecutor(max_workers=self.n_jobs) as executor:
            # Submit all jobs
            future_to_job = {executor.submit(_run_single_backtest, job): job for job in jobs}

            # Process as they complete
            for future in as_completed(future_to_job):
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1

                    # Progress update
                    if completed % max(1, len(jobs) // 20) == 0:
                        pct = (completed / len(jobs)) * 100
                        print(f"  Progress: {completed}/{len(jobs)} ({pct:.1f}%)")

                except Exception as e:
                    print(f"  Error in backtest: {e}")
                    completed += 1

        print(f"\nCompleted all {len(results)} backtests")

        # Convert to DataFrame
        self.results_df = pd.DataFrame(results)

        # Sort by objective (Sharpe ratio by default)
        self.results_df = self.results_df.sort_values("sharpe", ascending=False)

        # Save to CSV
        Path(self.out_csv).parent.mkdir(parents=True, exist_ok=True)
        self.results_df.to_csv(self.out_csv, index=False)
        print(f"\nResults saved to: {self.out_csv}")

        # Also copy to reports directory
        reports_dir = Path("reports/sweeps")
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / Path(self.out_csv).name
        self.results_df.to_csv(report_path, index=False)
        print(f"Copy saved to: {report_path}")

        # Print summary
        self._print_summary()

        return self.results_df

    def _print_summary(self):
        """Print summary of sweep results."""
        if self.results_df is None or len(self.results_df) == 0:
            print("\nNo results to summarize")
            return

        print(f"\n{'=' * 60}")
        print("SWEEP SUMMARY")
        print(f"{'=' * 60}")

        # Filter successful runs
        successful = self.results_df[self.results_df["success"] == True]
        failed = len(self.results_df) - len(successful)

        print(f"Total runs: {len(self.results_df)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {failed}")

        if len(successful) > 0:
            print(f"\nTop 5 by Sharpe Ratio:")
            print("-" * 60)

            top_5 = successful.head(5)
            for idx, row in top_5.iterrows():
                print(f"\n  Rank {idx + 1}:")
                print(f"    Params: {row['params']}")
                print(f"    Sharpe: {row['sharpe']:.3f}")
                print(f"    Return: {row['return_pct']:.2f}%")
                print(f"    Max DD: {row['max_dd']:.2f}%")
                print(f"    Trades: {row['trades']}")
                print(f"    Win Rate: {row['win_rate']:.2f}%")

            print(f"\n{'=' * 60}")
            print("STATISTICS")
            print(f"{'=' * 60}")
            print(f"Sharpe - Mean: {successful['sharpe'].mean():.3f}, Std: {successful['sharpe'].std():.3f}")
            print(f"Sharpe - Min: {successful['sharpe'].min():.3f}, Max: {successful['sharpe'].max():.3f}")
            print(f"Return % - Mean: {successful['return_pct'].mean():.2f}%, Std: {successful['return_pct'].std():.2f}%")
            print(f"Max DD % - Mean: {successful['max_dd'].mean():.2f}%, Worst: {successful['max_dd'].min():.2f}%")
            print(f"{'=' * 60}\n")

    def get_best_params(self, objective: str = "sharpe") -> Dict[str, Any]:
        """
        Get the best parameter set based on objective.

        Args:
            objective: Metric to optimize (sharpe, sortino, pnl, return_pct, etc.)

        Returns:
            Dictionary of best parameters
        """
        if self.results_df is None or len(self.results_df) == 0:
            raise ValueError("No results available. Run sweep first.")

        successful = self.results_df[self.results_df["success"] == True]

        if len(successful) == 0:
            raise ValueError("No successful backtests")

        best_row = successful.sort_values(objective, ascending=False).iloc[0]
        best_params = json.loads(best_row["params"])

        return best_params
