"""
CLI for running parameter sweeps on trading strategies.
"""

import argparse
import yaml
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from trader.strategy_suite.sweep.grid import SweepRunner
from trader.strategy_suite.sweep.ga import GAOptimizer, GAConfig

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


def load_param_grid(grid_file: str) -> dict:
    """Load parameter grid from YAML file."""
    with open(grid_file, 'r') as f:
        grid = yaml.safe_load(f)
    return grid


def main():
    parser = argparse.ArgumentParser(
        description="Run parameter sweeps on trading strategies"
    )

    # Required arguments
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy to sweep (e.g., opening_range.ORB)"
    )
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

    # Parameter grid
    parser.add_argument(
        "--grid",
        help="Path to YAML file with parameter grid"
    )

    # Optional arguments
    parser.add_argument(
        "--capital",
        type=float,
        default=100000.0,
        help="Initial capital (default: 100000)"
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)"
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="Use random search instead of grid search"
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=100,
        help="Number of random samples (if --random) (default: 100)"
    )
    parser.add_argument(
        "--out",
        help="Output CSV path (auto-generated if not provided)"
    )

    # Genetic algorithm options
    parser.add_argument(
        "--ga",
        action="store_true",
        help="Use genetic algorithm instead of grid/random search"
    )
    parser.add_argument(
        "--ga-population",
        type=int,
        default=50,
        help="GA population size (default: 50)"
    )
    parser.add_argument(
        "--ga-generations",
        type=int,
        default=20,
        help="GA number of generations (default: 20)"
    )
    parser.add_argument(
        "--ga-fitness",
        default="sharpe",
        choices=["sharpe", "sortino", "calmar", "return"],
        help="GA fitness metric (default: sharpe)"
    )

    args = parser.parse_args()

    # Parse tickers
    tickers = [t.strip() for t in args.tickers.split(",")]

    # Get strategy class
    if args.strategy not in STRATEGIES:
        print(f"Error: Unknown strategy '{args.strategy}'")
        print(f"Available strategies:")
        for name in STRATEGIES.keys():
            print(f"  - {name}")
        sys.exit(1)

    strategy_cls = STRATEGIES[args.strategy]

    # Load parameter grid if provided
    if args.grid:
        param_grid = load_param_grid(args.grid)
    else:
        # Use default parameter grid (empty - will use strategy defaults)
        print("Warning: No parameter grid provided. Using strategy defaults.")
        param_grid = {}

    # Run sweep
    if args.ga:
        # Genetic algorithm
        print("Using Genetic Algorithm optimizer")

        # Convert grid to ranges for GA
        # GA expects: param_name -> (min, max) for continuous or list of choices
        param_ranges = {}
        for param_name, values in param_grid.items():
            if isinstance(values, list) and len(values) > 0:
                # Check if values are numeric and can form a range
                if all(isinstance(v, (int, float)) for v in values):
                    # Use min/max as range
                    param_ranges[param_name] = (min(values), max(values))
                else:
                    # Use as discrete choices
                    param_ranges[param_name] = values
            else:
                print(f"Warning: Skipping parameter '{param_name}' - invalid format")

        if not param_ranges:
            print("Error: No valid parameter ranges for GA")
            sys.exit(1)

        ga_config = GAConfig(
            population_size=args.ga_population,
            generations=args.ga_generations,
            seed=42
        )

        optimizer = GAOptimizer(
            strategy_cls=strategy_cls,
            param_ranges=param_ranges,
            tickers=tickers,
            start_date=args.start,
            end_date=args.end,
            capital=args.capital,
            fitness_metric=args.ga_fitness,
            config=ga_config,
            out_json=args.out
        )

        result = optimizer.run()

        print("\nBest Parameters Found:")
        print(result["best_params"])
        print(f"\nBest {args.ga_fitness}: {result['best_fitness']:.3f}")

    else:
        # Grid or random search
        if not param_grid:
            print("Error: Parameter grid required for grid/random search")
            print("Provide --grid argument pointing to a YAML file")
            sys.exit(1)

        runner = SweepRunner(
            strategy_cls=strategy_cls,
            param_grid=param_grid,
            tickers=tickers,
            start_date=args.start,
            end_date=args.end,
            capital=args.capital,
            out_csv=args.out,
            n_jobs=args.jobs,
            random=args.random,
            n_samples=args.n_samples
        )

        results_df = runner.run()

        # Print best parameters
        best_params = runner.get_best_params(objective="sharpe")
        print("\nBest Parameters (by Sharpe):")
        print(best_params)


if __name__ == "__main__":
    main()
