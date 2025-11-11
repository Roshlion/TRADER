"""
Walk-Forward Validation for portfolio optimization.

Implements rolling window validation:
1. Optimize on training window A
2. Test on hold-out window B
3. Roll forward and repeat
4. Aggregate in-sample and out-of-sample metrics
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json

from .weights import StaticOptimizer


class WalkForwardValidator:
    """
    Walk-forward validation for strategy portfolios.

    Splits data into rolling train/test windows and evaluates
    portfolio performance on out-of-sample data.
    """

    def __init__(
        self,
        returns_df: pd.DataFrame,
        train_days: int = 10,
        test_days: int = 5,
        overlap_days: int = 0
    ):
        """
        Initialize walk-forward validator.

        Args:
            returns_df: DataFrame with strategy returns (columns = strategies, index = timestamp)
            train_days: Training window size in trading days
            test_days: Test window size in trading days
            overlap_days: Overlap between consecutive training windows (default: 0)
        """
        self.returns_df = returns_df.copy()
        self.train_days = train_days
        self.test_days = test_days
        self.overlap_days = overlap_days

        # Convert returns index to datetime if not already
        if not isinstance(self.returns_df.index, pd.DatetimeIndex):
            self.returns_df.index = pd.to_datetime(self.returns_df.index)

    def _get_trading_days(self, start_date: pd.Timestamp, days: int) -> pd.Timestamp:
        """
        Get end date N trading days after start_date.

        Args:
            start_date: Start date
            days: Number of trading days

        Returns:
            End date (N trading days later)
        """
        # Filter to dates >= start_date
        future_dates = self.returns_df.index[self.returns_df.index >= start_date]

        if len(future_dates) < days:
            # Not enough data
            return None

        return future_dates[days - 1]

    def _create_folds(self) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
        """
        Create train/test fold boundaries.

        Returns:
            List of (train_start, train_end, test_start, test_end) tuples
        """
        folds = []

        # Get unique CALENDAR dates (not timestamps)
        dates = pd.Series(self.returns_df.index.date).unique()
        dates = pd.to_datetime(dates)

        # Make timezone-aware to match returns_df index
        if self.returns_df.index.tz is not None:
            dates = dates.tz_localize(self.returns_df.index.tz)

        dates = sorted(dates)

        current_idx = 0
        while current_idx < len(dates):
            # Train period
            train_start_date = dates[current_idx]
            train_end_idx = current_idx + self.train_days - 1
            if train_end_idx >= len(dates):
                break
            train_end_date = dates[train_end_idx]

            # Test period
            test_start_idx = train_end_idx + 1
            if test_start_idx >= len(dates):
                break
            test_start_date = dates[test_start_idx]

            test_end_idx = test_start_idx + self.test_days - 1
            if test_end_idx >= len(dates):
                break
            test_end_date = dates[test_end_idx]

            folds.append((train_start_date, train_end_date, test_start_date, test_end_date))

            # Move to next fold (with overlap adjustment)
            step = self.train_days + self.test_days - self.overlap_days
            current_idx += step

        return folds

    def run(
        self,
        objective: str = 'sharpe',
        max_weight: Optional[float] = None,
        long_only: bool = True
    ) -> Dict:
        """
        Run walk-forward validation.

        Args:
            objective: Optimization objective ('sharpe', 'sortino', 'return', etc.)
            max_weight: Maximum weight per strategy
            long_only: Only positive weights

        Returns:
            Dictionary with:
                - 'folds': List of per-fold results
                - 'summary': Aggregated metrics (IS, OOS, pooled)
                - 'weights_history': List of optimal weights per fold
        """
        folds = self._create_folds()

        if len(folds) == 0:
            raise ValueError("Insufficient data for walk-forward validation")

        print(f"\nWalk-Forward Validation: {len(folds)} folds")
        print(f"  Train: {self.train_days} days, Test: {self.test_days} days, Overlap: {self.overlap_days} days")
        print(f"  Objective: {objective}")

        fold_results = []
        weights_history = []

        # Collect all IS and OOS returns for pooled metrics
        all_is_returns = []
        all_oos_returns = []

        for fold_idx, (train_start, train_end, test_start, test_end) in enumerate(folds):
            print(f"\nFold {fold_idx + 1}/{len(folds)}")
            print(f"  Train: {train_start.date()} to {train_end.date()}")
            print(f"  Test:  {test_start.date()} to {test_end.date()}")

            # Split data
            train_data = self.returns_df.loc[train_start:train_end]
            test_data = self.returns_df.loc[test_start:test_end]

            # Optimize on training data
            optimizer = StaticOptimizer(train_data)

            if objective == 'equal':
                weights, _, train_metrics = optimizer.equal()
            elif objective == 'risk_parity':
                weights, _, train_metrics = optimizer.risk_parity()
            elif objective == 'sharpe':
                weights, _, train_metrics = optimizer.mean_variance(
                    objective='sharpe',
                    max_weight=max_weight,
                    long_only=long_only
                )
            elif objective == 'return':
                weights, _, train_metrics = optimizer.mean_variance(
                    objective='return',
                    max_weight=max_weight,
                    long_only=long_only
                )
            else:
                raise ValueError(f"Unknown objective: {objective}")

            # Apply weights to test data (out-of-sample)
            weights_array = np.array([weights.get(col, 0.0) for col in test_data.columns])
            test_portfolio_returns = (test_data * weights_array).sum(axis=1)

            # Calculate test metrics
            test_metrics = self._calculate_metrics(test_portfolio_returns, prefix='oos_')

            # Store fold results
            fold_result = {
                'fold': fold_idx + 1,
                'train_start': str(train_start.date()),
                'train_end': str(train_end.date()),
                'test_start': str(test_start.date()),
                'test_end': str(test_end.date()),
                'weights': weights,
                'is_metrics': train_metrics,
                'oos_metrics': test_metrics
            }

            fold_results.append(fold_result)
            weights_history.append(weights)

            # Collect returns for pooled metrics
            train_portfolio_returns = (train_data * np.array([weights.get(col, 0.0) for col in train_data.columns])).sum(axis=1)
            all_is_returns.append(train_portfolio_returns)
            all_oos_returns.append(test_portfolio_returns)

            # Print fold summary
            print(f"    IS Sharpe:  {train_metrics.get('sharpe', 0):.3f}")
            print(f"    OOS Sharpe: {test_metrics.get('oos_sharpe', 0):.3f}")

        # Aggregate pooled metrics
        pooled_is_returns = pd.concat(all_is_returns)
        pooled_oos_returns = pd.concat(all_oos_returns)

        pooled_is_metrics = self._calculate_metrics(pooled_is_returns, prefix='pooled_is_')
        pooled_oos_metrics = self._calculate_metrics(pooled_oos_returns, prefix='pooled_oos_')

        # Calculate average metrics across folds
        avg_is_metrics = self._average_fold_metrics(fold_results, 'is_metrics')
        avg_oos_metrics = self._average_fold_metrics(fold_results, 'oos_metrics')

        summary = {
            'n_folds': len(folds),
            'avg_is_metrics': avg_is_metrics,
            'avg_oos_metrics': avg_oos_metrics,
            'pooled_is_metrics': pooled_is_metrics,
            'pooled_oos_metrics': pooled_oos_metrics
        }

        print("\n" + "="*60)
        print("Walk-Forward Summary")
        print("="*60)
        print(f"Average IS Sharpe:  {avg_is_metrics.get('sharpe', 0):.3f}")
        print(f"Average OOS Sharpe: {avg_oos_metrics.get('oos_sharpe', 0):.3f}")
        print(f"Pooled OOS Sharpe:  {pooled_oos_metrics.get('pooled_oos_sharpe', 0):.3f}")
        print("="*60)

        return {
            'folds': fold_results,
            'summary': summary,
            'weights_history': weights_history
        }

    def _calculate_metrics(self, returns: pd.Series, prefix: str = '') -> Dict[str, float]:
        """
        Calculate performance metrics for a returns series.

        Args:
            returns: Returns series
            prefix: Prefix for metric keys

        Returns:
            Dictionary of metrics
        """
        from ..metrics import sharpe, sortino, max_drawdown, hit_rate

        if len(returns) == 0:
            return {}

        # Calculate equity curve
        equity = (1 + returns).cumprod()

        metrics = {
            f'{prefix}total_return': ((equity.iloc[-1] - 1) * 100) if len(equity) > 0 else 0,
            f'{prefix}sharpe': sharpe(returns.values, rf=0.0, annualize=True, periods_per_year=252),
            f'{prefix}sortino': sortino(returns.values, rf=0.0, annualize=True, periods_per_year=252),
            f'{prefix}max_dd': max_drawdown(equity.values) * 100,
            f'{prefix}hit_rate': hit_rate(returns.values),
            f'{prefix}mean_return': returns.mean() * 252 * 100,  # Annualized %
            f'{prefix}volatility': returns.std() * np.sqrt(252) * 100  # Annualized %
        }

        return metrics

    def _average_fold_metrics(self, fold_results: List[Dict], metrics_key: str) -> Dict[str, float]:
        """
        Calculate average metrics across folds.

        Args:
            fold_results: List of fold result dictionaries
            metrics_key: Key for metrics dict in each fold ('is_metrics' or 'oos_metrics')

        Returns:
            Dictionary of averaged metrics
        """
        if not fold_results:
            return {}

        # Get all metric keys from first fold
        metric_keys = fold_results[0][metrics_key].keys()

        avg_metrics = {}
        for key in metric_keys:
            values = [fold[metrics_key].get(key, 0) for fold in fold_results]
            avg_metrics[key] = np.mean(values)

        return avg_metrics

    def save_results(self, results: Dict, output_dir: str = "artifacts/wfv") -> str:
        """
        Save walk-forward validation results to JSON.

        Args:
            results: Results dictionary from run()
            output_dir: Output directory

        Returns:
            Path to saved file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_path / f"wfv_{timestamp}.json"

        # Convert results to JSON-serializable format
        serializable_results = {
            'timestamp': timestamp,
            'config': {
                'train_days': self.train_days,
                'test_days': self.test_days,
                'overlap_days': self.overlap_days
            },
            'summary': results['summary'],
            'folds': results['folds']
        }

        with open(output_file, 'w') as f:
            json.dump(serializable_results, f, indent=2, default=str)

        print(f"\nSaved WFV results: {output_file}")

        return str(output_file)
