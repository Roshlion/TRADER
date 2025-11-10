"""
Turnover and cost-aware optimization utilities.

Calculates portfolio turnover and adjusts metrics for rebalancing costs.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple


def calculate_turnover(
    returns_df: pd.DataFrame,
    weights: np.ndarray,
    window: int = 60
) -> float:
    """
    Calculate average portfolio turnover rate.

    Turnover is measured as the average absolute weight change per rebalance period.

    Args:
        returns_df: DataFrame of strategy returns
        weights: Target weights for each strategy
        window: Rebalancing window in periods (default: 60 = ~1 day for minute data)

    Returns:
        Average turnover rate (as decimal, e.g., 0.5 = 50% turnover)
    """
    if len(returns_df) < window * 2:
        # Not enough data for meaningful turnover calculation
        return 0.0

    # Simulate portfolio evolution with drift and periodic rebalancing
    n_strategies = len(weights)
    n_periods = len(returns_df)

    # Start with target weights
    current_weights = weights.copy()

    turnover_events = []

    for i in range(0, n_periods, window):
        if i + window > n_periods:
            break

        # Get returns for this window
        window_returns = returns_df.iloc[i:i+window]

        # Calculate weights at end of period (after drift)
        # Each strategy compounds at its return rate
        strategy_growth = (1 + window_returns).prod(axis=0).values
        drifted_weights = current_weights * strategy_growth

        # Normalize to sum to 1
        drifted_weights = drifted_weights / drifted_weights.sum()

        # Calculate turnover: sum of absolute weight changes
        weight_changes = np.abs(weights - drifted_weights)
        turnover = weight_changes.sum()

        turnover_events.append(turnover)

        # Reset to target weights (rebalance)
        current_weights = weights.copy()

    # Return average turnover per rebalance
    if len(turnover_events) == 0:
        return 0.0

    return np.mean(turnover_events)


def calculate_cost_adjusted_sharpe(
    returns_df: pd.DataFrame,
    weights: np.ndarray,
    rebalance_cost_bps: float = 1.0,
    turnover_window: int = 60
) -> Tuple[float, float, float]:
    """
    Calculate cost-adjusted Sharpe ratio.

    Args:
        returns_df: DataFrame of strategy returns
        weights: Target weights for each strategy
        rebalance_cost_bps: Rebalancing cost in basis points per % turnover (default: 1.0)
        turnover_window: Rebalancing frequency in periods (default: 60)

    Returns:
        Tuple of (raw_sharpe, turnover_pct, cost_adjusted_sharpe)
    """
    # Calculate portfolio returns
    portfolio_returns = (returns_df * weights).sum(axis=1)

    # Calculate raw Sharpe
    if len(portfolio_returns) == 0 or portfolio_returns.std() == 0:
        return 0.0, 0.0, 0.0

    raw_sharpe = (portfolio_returns.mean() / portfolio_returns.std()) * np.sqrt(252 * 390)  # Annualized

    # Calculate turnover
    turnover = calculate_turnover(returns_df, weights, window=turnover_window)
    turnover_pct = turnover * 100  # As percentage

    # Calculate cost penalty
    # Cost per rebalance = turnover * rebalance_cost_bps
    # Expressed as Sharpe penalty
    n_rebalances = len(returns_df) / turnover_window
    annual_turnover = turnover * (252 * 390 / turnover_window)  # Annualized turnover

    # Convert cost from bps to Sharpe penalty
    # Cost in bps per % turnover -> total annual cost
    annual_cost_bps = annual_turnover * 100 * rebalance_cost_bps
    annual_cost_fraction = annual_cost_bps / 10000  # Convert bps to fraction

    # Approximate Sharpe penalty as cost / volatility
    portfolio_vol = portfolio_returns.std() * np.sqrt(252 * 390)
    sharpe_penalty = annual_cost_fraction / portfolio_vol if portfolio_vol > 0 else 0

    # Adjusted Sharpe
    cost_adjusted_sharpe = raw_sharpe - sharpe_penalty

    return raw_sharpe, turnover_pct, cost_adjusted_sharpe


def add_turnover_metrics(
    returns_df: pd.DataFrame,
    weights: Dict[str, float],
    metrics: Dict[str, float],
    rebalance_cost_bps: float = 1.0,
    turnover_window: int = 60
) -> Dict[str, float]:
    """
    Add turnover and cost-adjusted metrics to existing metrics dict.

    Args:
        returns_df: DataFrame of strategy returns
        weights: Dictionary of strategy weights
        metrics: Existing metrics dictionary
        rebalance_cost_bps: Rebalancing cost in bps per % turnover
        turnover_window: Rebalancing frequency in periods

    Returns:
        Updated metrics dictionary with turnover info
    """
    # Convert weights dict to array
    weights_array = np.array([weights.get(col, 0.0) for col in returns_df.columns])

    # Calculate cost-adjusted metrics
    raw_sharpe, turnover_pct, adj_sharpe = calculate_cost_adjusted_sharpe(
        returns_df,
        weights_array,
        rebalance_cost_bps,
        turnover_window
    )

    # Add to metrics
    metrics['turnover_pct'] = turnover_pct
    metrics['raw_sharpe'] = raw_sharpe
    metrics['cost_adjusted_sharpe'] = adj_sharpe
    metrics['sharpe_penalty'] = raw_sharpe - adj_sharpe

    return metrics
