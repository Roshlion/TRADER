"""
Example script demonstrating how to use the Strategy Suite.

This script shows how to:
1. Run a single strategy backtest
2. Compare multiple strategies
3. Generate visualizations and reports
"""

from pathlib import Path
from .backtest import run_backtest
from .strategies.momentum import BreakoutMomentumStrategy, VolumeSpikeStrategy
from .strategies.mean_reversion import VWAPReversionStrategy, BollingerBandStrategy
from .visualization import create_full_report, save_metrics_to_csv


def example_single_backtest():
    """
    Example: Run a single strategy backtest.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Single Strategy Backtest")
    print("=" * 60)

    # Define strategy
    strategy = BreakoutMomentumStrategy(params={
        "lookback_bars": 30,
        "volume_threshold": 2.0,
        "holding_period": 60
    })

    # Run backtest
    results = run_backtest(
        strategy=strategy,
        tickers=["AAPL"],  # Single ticker for quick test
        start_date="2025-10-01",
        end_date="2025-10-02",  # Just 2 days for testing
        initial_capital=100000.0,
        position_size=0.2,  # 20% per position
        max_positions=3,
        stop_loss_pct=0.01,  # 1% stop loss
        take_profit_pct=0.02,  # 2% take profit
    )

    # Generate report
    output_dir = Path("reports")
    create_full_report(
        results=results,
        output_dir=output_dir,
        strategy_name="BreakoutMomentum_AAPL"
    )

    # Save metrics to CSV
    if results["metrics"]:
        save_metrics_to_csv(
            metrics=results["metrics"],
            strategy_name=results["strategy"],
            params=results["params"],
            output_path=output_dir / "strategy_results.csv"
        )

    return results


def example_multiple_strategies():
    """
    Example: Compare multiple strategies on the same data.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Multiple Strategy Comparison")
    print("=" * 60)

    # Define strategies to test
    strategies = [
        BreakoutMomentumStrategy(params={"lookback_bars": 30, "volume_threshold": 2.0}),
        VolumeSpikeStrategy(params={"rvol_threshold": 3.0, "price_change_pct": 0.5}),
        VWAPReversionStrategy(params={"std_dev_threshold": 2.0, "holding_period": 30}),
        BollingerBandStrategy(params={"bb_window": 20, "bb_std": 2.0}),
    ]

    # Common parameters
    tickers = ["AAPL", "MSFT"]
    start_date = "2025-10-01"
    end_date = "2025-10-02"

    results_all = []
    output_dir = Path("reports/comparison")

    for strategy in strategies:
        print(f"\n\nTesting {strategy.name}...")

        try:
            results = run_backtest(
                strategy=strategy,
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                initial_capital=100000.0,
            )

            results_all.append(results)

            # Generate individual report
            create_full_report(
                results=results,
                output_dir=output_dir,
                strategy_name=f"{strategy.name}_{'-'.join(tickers)}"
            )

            # Save metrics
            if results["metrics"]:
                save_metrics_to_csv(
                    metrics=results["metrics"],
                    strategy_name=results["strategy"],
                    params=results["params"],
                    output_path=output_dir / "comparison_results.csv"
                )

        except Exception as e:
            print(f"Error testing {strategy.name}: {e}")
            continue

    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)

    for res in results_all:
        if res["metrics"]:
            m = res["metrics"]
            print(f"\n{res['strategy']}:")
            print(f"  Total Return: {m.total_return_pct:.2f}%")
            print(f"  Sharpe Ratio: {m.sharpe_ratio:.3f}")
            print(f"  Max Drawdown: {m.max_drawdown_pct:.2f}%")
            print(f"  Win Rate: {m.win_rate:.2f}%")
            print(f"  Trades: {m.total_trades}")

    return results_all


def example_parameter_sweep():
    """
    Example: Test different parameter combinations for a single strategy.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Parameter Sweep")
    print("=" * 60)

    # Parameter grid
    lookback_values = [20, 30, 40]
    volume_thresholds = [1.5, 2.0, 2.5]

    output_dir = Path("reports/parameter_sweep")
    results_all = []

    for lookback in lookback_values:
        for vol_thresh in volume_thresholds:
            print(f"\nTesting lookback={lookback}, volume_threshold={vol_thresh}")

            strategy = BreakoutMomentumStrategy(params={
                "lookback_bars": lookback,
                "volume_threshold": vol_thresh,
                "holding_period": 60
            })

            try:
                results = run_backtest(
                    strategy=strategy,
                    tickers=["AAPL"],
                    start_date="2025-10-01",
                    end_date="2025-10-03",
                    initial_capital=100000.0,
                )

                results_all.append(results)

                # Save metrics
                if results["metrics"]:
                    save_metrics_to_csv(
                        metrics=results["metrics"],
                        strategy_name=results["strategy"],
                        params=results["params"],
                        output_path=output_dir / "parameter_sweep_results.csv"
                    )

            except Exception as e:
                print(f"Error: {e}")
                continue

    # Find best parameters
    print("\n" + "=" * 60)
    print("BEST PARAMETERS (by Sharpe Ratio)")
    print("=" * 60)

    valid_results = [r for r in results_all if r["metrics"] and r["metrics"].sharpe_ratio > 0]

    if valid_results:
        best = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
        print(f"\nBest configuration:")
        print(f"  Parameters: {best['params']}")
        print(f"  Sharpe Ratio: {best['metrics'].sharpe_ratio:.3f}")
        print(f"  Total Return: {best['metrics'].total_return_pct:.2f}%")
        print(f"  Max Drawdown: {best['metrics'].max_drawdown_pct:.2f}%")
    else:
        print("No valid results with positive Sharpe ratio")

    return results_all


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        example = sys.argv[1]
    else:
        example = "1"

    if example == "1":
        example_single_backtest()
    elif example == "2":
        example_multiple_strategies()
    elif example == "3":
        example_parameter_sweep()
    else:
        print("Usage: python example.py [1|2|3]")
        print("  1: Single strategy backtest")
        print("  2: Multiple strategy comparison")
        print("  3: Parameter sweep")
