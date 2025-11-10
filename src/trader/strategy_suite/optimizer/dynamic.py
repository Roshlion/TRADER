"""
Dynamic portfolio allocation (regime-based, rolling performance).
"""

import numpy as np
import pandas as pd
from typing import Dict, Callable, Tuple, Optional


class DynamicAllocator:
    """
    Dynamic portfolio allocator.

    Adjusts weights over time based on regimes or rolling performance.
    """

    def __init__(self, strat_returns: pd.DataFrame):
        """
        Initialize dynamic allocator.

        Args:
            strat_returns: DataFrame with columns = strategy names, rows = timestamps
        """
        self.strat_returns = strat_returns
        self.strategy_names = list(strat_returns.columns)
        self.n_strategies = len(self.strategy_names)

    def regime_switch(
        self,
        detector: Callable[[int], str],
        W_a: Dict[str, float],
        W_b: Dict[str, float]
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Regime-based switching between two weight sets.

        Args:
            detector: Function that takes timestamp index and returns regime ('a' or 'b')
            W_a: Weights for regime A
            W_b: Weights for regime B

        Returns:
            Tuple of (portfolio_returns, weights_timeseries)
        """
        portfolio_returns = []
        weights_list = []

        for idx in range(len(self.strat_returns)):
            regime = detector(idx)

            if regime == 'a':
                weights = np.array([W_a.get(s, 0) for s in self.strategy_names])
            else:
                weights = np.array([W_b.get(s, 0) for s in self.strategy_names])

            # Portfolio return for this period
            strat_ret = self.strat_returns.iloc[idx].values
            port_ret = np.dot(weights, strat_ret)

            portfolio_returns.append(port_ret)
            weights_list.append(weights)

        portfolio_returns = pd.Series(
            portfolio_returns,
            index=self.strat_returns.index
        )

        weights_df = pd.DataFrame(
            weights_list,
            index=self.strat_returns.index,
            columns=self.strategy_names
        )

        return portfolio_returns, weights_df

    def rolling_perf(
        self,
        window: int = 240,
        rebalance: int = 60,
        floor: float = 0.0,
        metric: str = 'sharpe'
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Rolling performance-based allocation.

        Reweights strategies based on their rolling performance.

        Args:
            window: Lookback window for performance calculation (in periods)
            rebalance: How often to rebalance (in periods)
            floor: Minimum weight (strategies with negative perf get floor weight)
            metric: Performance metric ('sharpe', 'return', 'sortino')

        Returns:
            Tuple of (portfolio_returns, weights_timeseries)
        """
        portfolio_returns = []
        weights_list = []
        current_weights = np.ones(self.n_strategies) / self.n_strategies

        for idx in range(len(self.strat_returns)):
            # Rebalance check
            if idx >= window and idx % rebalance == 0:
                # Calculate rolling performance for each strategy
                lookback_returns = self.strat_returns.iloc[idx-window:idx]

                perfs = []
                for col in self.strategy_names:
                    col_returns = lookback_returns[col].values

                    if metric == 'sharpe':
                        # Rolling Sharpe
                        if np.std(col_returns) > 0:
                            perf = np.mean(col_returns) / np.std(col_returns)
                        else:
                            perf = 0.0
                    elif metric == 'return':
                        # Cumulative return
                        perf = np.prod(1 + col_returns) - 1
                    elif metric == 'sortino':
                        # Rolling Sortino
                        downside = col_returns[col_returns < 0]
                        if len(downside) > 0 and np.std(downside) > 0:
                            perf = np.mean(col_returns) / np.std(downside)
                        else:
                            perf = np.mean(col_returns)
                    else:
                        perf = 0.0

                    perfs.append(max(perf, 0))  # Floor at 0

                # Normalize to weights
                total_perf = sum(perfs)
                if total_perf > 0:
                    new_weights = np.array([p / total_perf for p in perfs])
                else:
                    new_weights = np.ones(self.n_strategies) / self.n_strategies

                # Apply floor
                new_weights = np.maximum(new_weights, floor)

                # Renormalize
                new_weights = new_weights / np.sum(new_weights)

                current_weights = new_weights

            # Calculate return with current weights
            strat_ret = self.strat_returns.iloc[idx].values
            port_ret = np.dot(current_weights, strat_ret)

            portfolio_returns.append(port_ret)
            weights_list.append(current_weights.copy())

        portfolio_returns = pd.Series(
            portfolio_returns,
            index=self.strat_returns.index
        )

        weights_df = pd.DataFrame(
            weights_list,
            index=self.strat_returns.index,
            columns=self.strategy_names
        )

        return portfolio_returns, weights_df

    def time_of_day_tilt(
        self,
        base_weights: Dict[str, float],
        time_tilts: Dict[str, Dict[str, float]]
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Time-of-day tilted allocation.

        Args:
            base_weights: Base weights for all strategies
            time_tilts: Dictionary mapping time ranges to strategy multipliers
                Example: {'09:30-10:30': {'strategy1': 1.5, 'strategy2': 0.5}}

        Returns:
            Tuple of (portfolio_returns, weights_timeseries)
        """
        portfolio_returns = []
        weights_list = []

        for idx in range(len(self.strat_returns)):
            timestamp = self.strat_returns.index[idx]

            # Check which time range we're in
            time_str = timestamp.strftime("%H:%M")
            weights = np.array([base_weights.get(s, 0) for s in self.strategy_names])

            # Apply time tilts
            for time_range, tilts in time_tilts.items():
                start, end = time_range.split("-")
                if start <= time_str <= end:
                    for strat_name, mult in tilts.items():
                        if strat_name in self.strategy_names:
                            strat_idx = self.strategy_names.index(strat_name)
                            weights[strat_idx] *= mult

            # Renormalize
            if np.sum(weights) > 0:
                weights = weights / np.sum(weights)

            # Calculate return
            strat_ret = self.strat_returns.iloc[idx].values
            port_ret = np.dot(weights, strat_ret)

            portfolio_returns.append(port_ret)
            weights_list.append(weights)

        portfolio_returns = pd.Series(
            portfolio_returns,
            index=self.strat_returns.index
        )

        weights_df = pd.DataFrame(
            weights_list,
            index=self.strat_returns.index,
            columns=self.strategy_names
        )

        return portfolio_returns, weights_df
