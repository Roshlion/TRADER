"""
Acceptance criteria checker for optimizer results.

Validates that optimization results meet minimum thresholds:
- Sharpe >= 1.0
- Max Drawdown <= 5%
- Sortino >= 1.2
"""

import argparse
import json
import sys
from pathlib import Path


class AcceptanceChecker:
    """Check if results meet acceptance criteria."""

    # Acceptance thresholds
    MIN_SHARPE = 1.0
    MAX_DRAWDOWN = 5.0  # Percentage
    MIN_SORTINO = 1.2

    def __init__(self, results_file: str):
        """
        Initialize checker with results file.

        Args:
            results_file: Path to JSON results file (weights.json or wfv results)
        """
        self.results_file = results_file
        self.results = self._load_results()

    def _load_results(self) -> dict:
        """Load results from JSON file."""
        with open(self.results_file, 'r') as f:
            data = json.load(f)
        return data

    def _extract_metrics(self) -> dict:
        """Extract relevant metrics from results."""
        # Handle different result formats
        if 'metrics' in self.results:
            # Standard weights.json format
            metrics = self.results['metrics']
        elif 'summary' in self.results and 'pooled_oos_metrics' in self.results['summary']:
            # Walk-forward validation format (use OOS metrics)
            metrics = self.results['summary']['pooled_oos_metrics']
        else:
            raise ValueError("Unknown results format")

        return metrics

    def check(self) -> bool:
        """
        Check if results meet acceptance criteria.

        Returns:
            True if all criteria met, False otherwise
        """
        metrics = self._extract_metrics()

        print("="*60)
        print("Acceptance Criteria Check")
        print("="*60)

        # Extract metrics (handle different naming conventions)
        sharpe = metrics.get('sharpe', metrics.get('pooled_oos_sharpe', 0))
        sortino = metrics.get('sortino', metrics.get('pooled_oos_sortino', 0))
        max_dd = abs(metrics.get('max_dd', metrics.get('pooled_oos_max_dd', 100)))

        # Check each criterion
        checks = []

        # Sharpe
        sharpe_pass = sharpe >= self.MIN_SHARPE
        status = "[PASS]" if sharpe_pass else "[FAIL]"
        print(f"Sharpe Ratio:  {sharpe:>8.3f}  (>= {self.MIN_SHARPE:.1f})  {status}")
        checks.append(sharpe_pass)

        # Sortino
        sortino_pass = sortino >= self.MIN_SORTINO
        status = "[PASS]" if sortino_pass else "[FAIL]"
        print(f"Sortino Ratio: {sortino:>8.3f}  (>= {self.MIN_SORTINO:.1f})  {status}")
        checks.append(sortino_pass)

        # Max Drawdown
        max_dd_pass = max_dd <= self.MAX_DRAWDOWN
        status = "[PASS]" if max_dd_pass else "[FAIL]"
        print(f"Max Drawdown:  {max_dd:>8.2f}% (<= {self.MAX_DRAWDOWN:.1f}%)  {status}")
        checks.append(max_dd_pass)

        print("="*60)

        # Overall result
        all_pass = all(checks)
        if all_pass:
            print("RESULT: [PASS] ALL CRITERIA MET")
        else:
            print("RESULT: [FAIL] CRITERIA NOT MET")

        print("="*60)

        return all_pass


def main():
    parser = argparse.ArgumentParser(
        description="Check if optimizer results meet acceptance criteria"
    )

    parser.add_argument(
        "results_file",
        help="Path to results JSON file (e.g., artifacts/portfolios/latest_weights.json)"
    )

    parser.add_argument(
        "--min-sharpe",
        type=float,
        default=1.0,
        help="Minimum Sharpe ratio (default: 1.0)"
    )

    parser.add_argument(
        "--max-dd",
        type=float,
        default=5.0,
        help="Maximum drawdown in percent (default: 5.0)"
    )

    parser.add_argument(
        "--min-sortino",
        type=float,
        default=1.2,
        help="Minimum Sortino ratio (default: 1.2)"
    )

    args = parser.parse_args()

    # Check if file exists
    if not Path(args.results_file).exists():
        print(f"Error: Results file not found: {args.results_file}")
        return 1

    # Create checker and run
    checker = AcceptanceChecker(args.results_file)

    # Update thresholds if provided
    checker.MIN_SHARPE = args.min_sharpe
    checker.MAX_DRAWDOWN = args.max_dd
    checker.MIN_SORTINO = args.min_sortino

    # Run check
    passed = checker.check()

    # Return exit code
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
