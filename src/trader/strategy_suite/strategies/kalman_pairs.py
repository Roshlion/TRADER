"""
Kalman Pairs (Cointegration) strategy.

Trades mean reversion of spread between two cointegrated tickers using Kalman filter for hedge ratio.
"""

from typing import List, Dict, Any, Tuple
import polars as pl
import numpy as np
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class KalPairs(BaseStrategy):
    """
    Kalman Pairs strategy.

    Uses Kalman filter to estimate dynamic hedge ratio between two tickers,
    trades mean reversion of the spread when it exceeds entry threshold.

    Parameters:
        pair: Tuple of two ticker symbols (default: ('AAPL', 'MSFT'))
        z_entry: Z-score entry threshold (default: 2.0)
        z_exit: Z-score exit threshold (default: 0.5)
        half_life: Half-life for mean reversion in minutes (default: 60)
        use_kalman: Use Kalman filter vs rolling OLS (default: True)
        delta: Kalman filter transition variance (default: 1e-4)
        vega: Kalman filter observation variance (default: 1e-3)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "pair": ('AAPL', 'MSFT'),
            "z_entry": 2.0,
            "z_exit": 0.5,
            "half_life": 60,
            "use_kalman": True,
            "delta": 1e-4,  # Process noise
            "vega": 1e-3,   # Observation noise
        }
        if params:
            default_params.update(params)
        super().__init__("KalPairs", default_params)

    def _kalman_filter_hedge_ratio(self, y: np.ndarray, x: np.ndarray,
                                   delta: float, vega: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Estimate hedge ratio using Kalman filter.

        Args:
            y: Dependent variable (price series)
            x: Independent variable (price series)
            delta: Transition (process) covariance
            vega: Observation covariance

        Returns:
            (hedge_ratios, intercepts) for each time step
        """
        n = len(y)
        hedge_ratios = np.zeros(n)
        intercepts = np.zeros(n)

        # Initialize state
        # State: [beta, alpha] where y = alpha + beta * x
        state = np.zeros(2)
        P = np.eye(2)  # State covariance

        R = vega  # Observation covariance
        Q = delta * np.eye(2)  # Process covariance

        for t in range(n):
            if t == 0:
                # Initialize with simple ratio
                if x[t] != 0:
                    state[0] = y[t] / x[t]
                    state[1] = 0
            else:
                # Prediction step
                # State prediction: same as previous
                # P = P + Q
                P = P + Q

            # Observation
            H = np.array([x[t], 1.0])  # Observation matrix: y = beta*x + alpha

            # Innovation
            y_pred = H @ state
            innovation = y[t] - y_pred

            # Innovation covariance
            S = H @ P @ H.T + R

            # Kalman gain
            if S > 0:
                K = P @ H.T / S

                # Update state
                state = state + K * innovation

                # Update covariance
                P = (np.eye(2) - np.outer(K, H)) @ P

            hedge_ratios[t] = state[0]
            intercepts[t] = state[1]

        return hedge_ratios, intercepts

    def _rolling_ols_hedge_ratio(self, y: np.ndarray, x: np.ndarray,
                                 window: int = 60) -> Tuple[np.ndarray, np.ndarray]:
        """
        Estimate hedge ratio using rolling OLS.

        Returns:
            (hedge_ratios, intercepts) for each time step
        """
        n = len(y)
        hedge_ratios = np.full(n, np.nan)
        intercepts = np.full(n, np.nan)

        for t in range(window, n):
            y_window = y[t-window:t]
            x_window = x[t-window:t]

            # OLS: y = alpha + beta * x
            X = np.column_stack([x_window, np.ones(window)])
            try:
                params = np.linalg.lstsq(X, y_window, rcond=None)[0]
                hedge_ratios[t] = params[0]
                intercepts[t] = params[1]
            except:
                pass

        return hedge_ratios, intercepts

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate Kalman pairs signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        ticker1, ticker2 = self.params["pair"]
        z_entry = self.params["z_entry"]
        z_exit = self.params["z_exit"]
        half_life = self.params["half_life"]
        use_kalman = self.params["use_kalman"]
        delta = self.params["delta"]
        vega = self.params["vega"]

        # Extract data for both tickers
        data1 = data.filter(pl.col("ticker") == ticker1).sort("timestamp")
        data2 = data.filter(pl.col("ticker") == ticker2).sort("timestamp")

        if len(data1) == 0 or len(data2) == 0:
            return []

        # Align timestamps (inner join)
        merged = data1.join(data2, on="timestamp", suffix="_pair")

        if len(merged) < half_life:
            return []

        # Extract prices
        y = merged["close"].to_numpy()
        x = merged["close_pair"].to_numpy()
        timestamps = merged["timestamp"].to_list()

        # Calculate hedge ratio
        if use_kalman:
            hedge_ratios, intercepts = self._kalman_filter_hedge_ratio(y, x, delta, vega)
        else:
            hedge_ratios, intercepts = self._rolling_ols_hedge_ratio(y, x, half_life)

        # Calculate spread
        spread = y - hedge_ratios * x - intercepts

        # Calculate rolling mean and std of spread for z-score
        spread_series = pl.Series("spread", spread)
        rolling_mean = spread_series.rolling_mean(half_life).to_numpy()
        rolling_std = spread_series.rolling_std(half_life).to_numpy()

        # Calculate z-score
        z_scores = np.where(rolling_std > 0, (spread - rolling_mean) / rolling_std, 0)

        signals = []
        position = None  # 'long_spread' or 'short_spread'

        for i in range(half_life, len(merged)):
            timestamp = timestamps[i]
            z = z_scores[i]
            hedge_ratio = hedge_ratios[i]

            if np.isnan(z) or np.isnan(hedge_ratio):
                continue

            # Exit conditions
            if position == "long_spread" and abs(z) < z_exit:
                # Close long spread (sell ticker1, buy ticker2)
                signals.append(Signal(
                    timestamp=timestamp,
                    ticker=ticker1,
                    action=SignalAction.SELL,
                    size=1.0,
                    price=y[i],
                    reason=f"Spread z-score reverted to {z:.2f}"
                ))
                signals.append(Signal(
                    timestamp=timestamp,
                    ticker=ticker2,
                    action=SignalAction.COVER,
                    size=hedge_ratio,
                    price=x[i],
                    reason=f"Spread z-score reverted to {z:.2f}"
                ))
                position = None

            elif position == "short_spread" and abs(z) < z_exit:
                # Close short spread (buy ticker1, sell ticker2)
                signals.append(Signal(
                    timestamp=timestamp,
                    ticker=ticker1,
                    action=SignalAction.COVER,
                    size=1.0,
                    price=y[i],
                    reason=f"Spread z-score reverted to {z:.2f}"
                ))
                signals.append(Signal(
                    timestamp=timestamp,
                    ticker=ticker2,
                    action=SignalAction.SELL,
                    size=hedge_ratio,
                    price=x[i],
                    reason=f"Spread z-score reverted to {z:.2f}"
                ))
                position = None

            # Entry conditions
            if position is None:
                if z < -z_entry:
                    # Long spread: buy ticker1, short ticker2
                    signals.append(Signal(
                        timestamp=timestamp,
                        ticker=ticker1,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=y[i],
                        confidence=min(abs(z) / z_entry, 1.0),
                        reason=f"Spread z-score {z:.2f} < -{z_entry}",
                        indicators={
                            "z_score": z,
                            "hedge_ratio": hedge_ratio,
                            "spread": spread[i],
                            "pair": f"{ticker1}/{ticker2}"
                        }
                    ))
                    signals.append(Signal(
                        timestamp=timestamp,
                        ticker=ticker2,
                        action=SignalAction.SHORT,
                        size=hedge_ratio,
                        price=x[i],
                        confidence=min(abs(z) / z_entry, 1.0),
                        reason=f"Spread z-score {z:.2f} < -{z_entry}",
                        indicators={
                            "z_score": z,
                            "hedge_ratio": hedge_ratio,
                            "spread": spread[i],
                            "pair": f"{ticker1}/{ticker2}"
                        }
                    ))
                    position = "long_spread"

                elif z > z_entry:
                    # Short spread: short ticker1, buy ticker2
                    signals.append(Signal(
                        timestamp=timestamp,
                        ticker=ticker1,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=y[i],
                        confidence=min(abs(z) / z_entry, 1.0),
                        reason=f"Spread z-score {z:.2f} > {z_entry}",
                        indicators={
                            "z_score": z,
                            "hedge_ratio": hedge_ratio,
                            "spread": spread[i],
                            "pair": f"{ticker1}/{ticker2}"
                        }
                    ))
                    signals.append(Signal(
                        timestamp=timestamp,
                        ticker=ticker2,
                        action=SignalAction.BUY,
                        size=hedge_ratio,
                        price=x[i],
                        confidence=min(abs(z) / z_entry, 1.0),
                        reason=f"Spread z-score {z:.2f} > {z_entry}",
                        indicators={
                            "z_score": z,
                            "hedge_ratio": hedge_ratio,
                            "spread": spread[i],
                            "pair": f"{ticker1}/{ticker2}"
                        }
                    ))
                    position = "short_spread"

        return signals
