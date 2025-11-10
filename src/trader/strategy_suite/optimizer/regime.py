"""
Regime detection for portfolio optimization.

Detects market regimes (volatility and trend) to improve strategy selection.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple
from collections import defaultdict


class RegimeDetector:
    """
    Detect market regimes from price/returns data.

    Classifies market conditions along two dimensions:
    - Volatility: 'high' or 'low'
    - Trend: 'up', 'down', or 'flat'
    """

    def __init__(
        self,
        vol_window: int = 20,
        trend_window: int = 20,
        vol_threshold: float = 1.0,  # Multiple of median vol
        trend_threshold: float = 0.0005  # Min trend strength
    ):
        """
        Initialize regime detector.

        Args:
            vol_window: Window for volatility calculation (default: 20)
            trend_window: Window for trend calculation (default: 20)
            vol_threshold: Volatility threshold as multiple of median (default: 1.0)
            trend_threshold: Minimum trend strength to classify as trending (default: 0.0005)
        """
        self.vol_window = vol_window
        self.trend_window = trend_window
        self.vol_threshold = vol_threshold
        self.trend_threshold = trend_threshold

    def detect(self, returns: pd.Series) -> Dict[pd.Timestamp, Dict[str, str]]:
        """
        Detect regimes for a returns time series.

        Args:
            returns: Time series of returns

        Returns:
            Dictionary mapping timestamp to regime dict
            {'timestamp': {'vol': 'high'|'low', 'trend': 'up'|'down'|'flat'}}
        """
        if len(returns) < max(self.vol_window, self.trend_window):
            # Not enough data
            return {}

        # Calculate rolling volatility (std dev)
        rolling_vol = returns.rolling(window=self.vol_window).std()

        # Calculate rolling trend (linear regression slope)
        rolling_trend = self._calculate_rolling_trend(returns, self.trend_window)

        # Determine volatility regime
        median_vol = rolling_vol.median()
        vol_regime = pd.Series('low', index=returns.index)
        vol_regime[rolling_vol > median_vol * self.vol_threshold] = 'high'

        # Determine trend regime
        trend_regime = pd.Series('flat', index=returns.index)
        trend_regime[rolling_trend > self.trend_threshold] = 'up'
        trend_regime[rolling_trend < -self.trend_threshold] = 'down'

        # Combine into regime dictionary
        regimes = {}
        for ts in returns.index:
            if pd.notna(vol_regime[ts]) and pd.notna(trend_regime[ts]):
                regimes[ts] = {
                    'vol': vol_regime[ts],
                    'trend': trend_regime[ts]
                }

        return regimes

    def _calculate_rolling_trend(self, returns: pd.Series, window: int) -> pd.Series:
        """
        Calculate rolling trend using linear regression slope.

        Args:
            returns: Returns series
            window: Window size

        Returns:
            Series of trend slopes
        """
        # Convert to cumulative returns (price proxy)
        cum_returns = (1 + returns).cumprod()

        # Calculate rolling linear regression slope
        slopes = pd.Series(index=returns.index, dtype=float)

        for i in range(window, len(cum_returns) + 1):
            window_data = cum_returns.iloc[i-window:i]

            # Fit linear regression
            x = np.arange(len(window_data))
            y = window_data.values

            # Calculate slope using least squares
            x_mean = x.mean()
            y_mean = y.mean()

            numerator = np.sum((x - x_mean) * (y - y_mean))
            denominator = np.sum((x - x_mean) ** 2)

            if denominator > 0:
                slope = numerator / denominator
                # Normalize by current price level
                slopes.iloc[i-1] = slope / y_mean if y_mean != 0 else 0
            else:
                slopes.iloc[i-1] = 0

        return slopes

    def calculate_regime_scores(
        self,
        returns_df: pd.DataFrame,
        strategy_returns: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Calculate per-strategy regime fitness scores.

        Strategies that perform well in the current regime get higher scores.

        Args:
            returns_df: DataFrame of recent returns (for regime detection)
            strategy_returns: Historical returns for each strategy

        Returns:
            Dictionary mapping strategy name to regime score (0-1)
        """
        # Detect current regime using most recent data
        # Use first column as market proxy (or average across strategies)
        market_proxy = returns_df.mean(axis=1)

        regimes = self.detect(market_proxy)

        if len(regimes) == 0:
            # No regime detected, return equal scores
            return {col: 0.5 for col in strategy_returns.columns}

        # Get most recent regime
        latest_regime = regimes[max(regimes.keys())]

        # Calculate strategy performance in similar historical regimes
        strategy_scores = {}

        for strategy in strategy_returns.columns:
            score = self._calculate_strategy_regime_fit(
                strategy_returns[strategy],
                market_proxy,
                latest_regime
            )
            strategy_scores[strategy] = score

        return strategy_scores

    def _calculate_strategy_regime_fit(
        self,
        strategy_returns: pd.Series,
        market_proxy: pd.Series,
        target_regime: Dict[str, str]
    ) -> float:
        """
        Calculate how well a strategy fits a target regime.

        Args:
            strategy_returns: Strategy's historical returns
            market_proxy: Market returns for regime detection
            target_regime: Target regime {'vol': 'high'|'low', 'trend': 'up'|'down'|'flat'}

        Returns:
            Fitness score (0-1, higher is better)
        """
        # Detect historical regimes
        regimes = self.detect(market_proxy)

        if len(regimes) == 0:
            return 0.5  # Neutral score

        # Find periods matching target regime
        matching_periods = []
        for ts, regime in regimes.items():
            if (regime['vol'] == target_regime['vol'] and
                regime['trend'] == target_regime['trend']):
                matching_periods.append(ts)

        if len(matching_periods) == 0:
            return 0.5  # No matching historical periods

        # Calculate strategy performance in matching periods
        matching_returns = strategy_returns.loc[strategy_returns.index.isin(matching_periods)]

        if len(matching_returns) == 0:
            return 0.5

        # Calculate Sharpe ratio in matching regime
        mean_ret = matching_returns.mean()
        std_ret = matching_returns.std()

        if std_ret == 0:
            return 0.5

        regime_sharpe = mean_ret / std_ret

        # Convert Sharpe to 0-1 score (sigmoid-like)
        # Sharpe of 0 -> score 0.5, positive Sharpe -> higher score
        score = 1 / (1 + np.exp(-regime_sharpe))

        return score


def blend_with_regime_scores(
    base_weights: Dict[str, float],
    regime_scores: Dict[str, float],
    regime_weight: float = 0.25
) -> Dict[str, float]:
    """
    Blend base portfolio weights with regime fitness scores.

    Args:
        base_weights: Base optimization weights
        regime_scores: Regime fitness scores per strategy
        regime_weight: Weight for regime adjustment (0-1, default: 0.25)

    Returns:
        Blended weights dictionary
    """
    # Normalize regime scores to sum to 1
    total_score = sum(regime_scores.values())
    if total_score == 0:
        norm_scores = {k: 1/len(regime_scores) for k in regime_scores.keys()}
    else:
        norm_scores = {k: v/total_score for k, v in regime_scores.items()}

    # Blend base weights with regime scores
    blended_weights = {}
    for strategy in base_weights.keys():
        base_w = base_weights[strategy]
        regime_w = norm_scores.get(strategy, 0)

        # Weighted average
        blended_w = (1 - regime_weight) * base_w + regime_weight * regime_w

        blended_weights[strategy] = blended_w

    # Renormalize to sum to 1
    total_weight = sum(blended_weights.values())
    if total_weight > 0:
        blended_weights = {k: v/total_weight for k, v in blended_weights.items()}

    return blended_weights
