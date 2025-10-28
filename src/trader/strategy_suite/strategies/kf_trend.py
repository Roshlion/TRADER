"""
Kalman Trend Filter strategy.

Smooths price with Kalman filter and trades trend crossovers.
"""

from typing import List, Dict, Any
import polars as pl
import numpy as np
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class KFTrend(BaseStrategy):
    """
    Kalman Filter Trend strategy.

    Uses Kalman filter to smooth price series and identify trend.
    Enters long when price crosses above filtered trend, short when below.

    Parameters:
        q: Process noise covariance (default: 0.001)
        r: Measurement noise covariance (default: 0.01)
        hold_trail_atr: Trailing stop as multiple of ATR (default: 1.5)
        atr_period: Period for ATR calculation (default: 14)
        min_trend_strength: Minimum trend slope to trade (default: 0.0)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "q": 0.001,  # Process noise
            "r": 0.01,   # Measurement noise
            "hold_trail_atr": 1.5,
            "atr_period": 14,
            "min_trend_strength": 0.0,
        }
        if params:
            default_params.update(params)
        super().__init__("KFTrend", default_params)

    def _kalman_filter(self, prices: np.ndarray, q: float, r: float) -> np.ndarray:
        """
        Apply Kalman filter to smooth price series.

        Args:
            prices: Price series
            q: Process noise covariance
            r: Measurement noise covariance

        Returns:
            Filtered prices
        """
        n = len(prices)
        filtered = np.zeros(n)

        # Initialize
        x = prices[0]  # Initial state estimate
        P = 1.0        # Initial estimate covariance

        for t in range(n):
            # Prediction
            x_pred = x
            P_pred = P + q

            # Update
            K = P_pred / (P_pred + r)  # Kalman gain
            x = x_pred + K * (prices[t] - x_pred)
            P = (1 - K) * P_pred

            filtered[t] = x

        return filtered

    def _calculate_atr(self, data: pl.DataFrame, period: int) -> pl.DataFrame:
        """Calculate Average True Range."""
        data = data.with_columns([
            pl.max_horizontal([
                pl.col("high") - pl.col("low"),
                (pl.col("high") - pl.col("close").shift(1)).abs(),
                (pl.col("low") - pl.col("close").shift(1)).abs()
            ]).alias("tr")
        ])

        data = data.with_columns([
            pl.col("tr").rolling_mean(period).alias("atr")
        ])

        return data

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate Kalman trend filter signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        q = self.params["q"]
        r = self.params["r"]
        trail_atr_mult = self.params["hold_trail_atr"]
        atr_period = self.params["atr_period"]
        min_trend = self.params["min_trend_strength"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate ATR for stops
            ticker_data = self._calculate_atr(ticker_data, atr_period)

            # Apply Kalman filter
            prices = ticker_data["close"].to_numpy()
            filtered_prices = self._kalman_filter(prices, q, r)

            # Add filtered prices to dataframe
            ticker_data = ticker_data.with_columns([
                pl.Series("kf_trend", filtered_prices)
            ])

            # Calculate trend slope (rate of change of filtered price)
            ticker_data = ticker_data.with_columns([
                (pl.col("kf_trend") - pl.col("kf_trend").shift(1)).alias("trend_slope")
            ])

            # Detect crossovers
            ticker_data = ticker_data.with_columns([
                (pl.col("close") > pl.col("kf_trend")).alias("above_trend"),
                (pl.col("close").shift(1) <= pl.col("kf_trend").shift(1)).alias("was_below_trend"),
                (pl.col("close") < pl.col("kf_trend")).alias("below_trend"),
                (pl.col("close").shift(1) >= pl.col("kf_trend").shift(1)).alias("was_above_trend"),
            ])

            # Detect crossover signals
            ticker_data = ticker_data.with_columns([
                (pl.col("above_trend") & pl.col("was_below_trend")).alias("cross_above"),
                (pl.col("below_trend") & pl.col("was_above_trend")).alias("cross_below"),
            ])

            # Track position
            position = None
            entry_price = None
            trailing_stop = None

            for row in ticker_data.iter_rows(named=True):
                # Skip if missing data
                if not row["kf_trend"] or not row["atr"]:
                    continue

                # Update trailing stop
                if position == "long" and entry_price and row["atr"]:
                    trailing_stop = max(trailing_stop or 0, row["close"] - trail_atr_mult * row["atr"])

                    # Check trailing stop
                    if row["close"] < trailing_stop:
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason=f"Trailing stop hit at {trailing_stop:.2f}"
                        ))
                        position = None
                        entry_price = None
                        trailing_stop = None
                        continue

                elif position == "short" and entry_price and row["atr"]:
                    trailing_stop = min(trailing_stop or float('inf'), row["close"] + trail_atr_mult * row["atr"])

                    # Check trailing stop
                    if row["close"] > trailing_stop:
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason=f"Trailing stop hit at {trailing_stop:.2f}"
                        ))
                        position = None
                        entry_price = None
                        trailing_stop = None
                        continue

                # Check trend strength
                if row["trend_slope"] and abs(row["trend_slope"]) < min_trend:
                    continue

                # Entry signals
                if row["cross_above"] and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Trend reversed"
                        ))

                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=0.75,
                        reason=f"Price crossed above Kalman trend ({row['kf_trend']:.2f})",
                        indicators={
                            "kf_trend": row["kf_trend"],
                            "trend_slope": row["trend_slope"],
                            "atr": row["atr"],
                            "stop": row["close"] - trail_atr_mult * row["atr"]
                        }
                    ))
                    position = "long"
                    entry_price = row["close"]
                    trailing_stop = row["close"] - trail_atr_mult * row["atr"]

                elif row["cross_below"] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Trend reversed"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=0.75,
                        reason=f"Price crossed below Kalman trend ({row['kf_trend']:.2f})",
                        indicators={
                            "kf_trend": row["kf_trend"],
                            "trend_slope": row["trend_slope"],
                            "atr": row["atr"],
                            "stop": row["close"] + trail_atr_mult * row["atr"]
                        }
                    ))
                    position = "short"
                    entry_price = row["close"]
                    trailing_stop = row["close"] + trail_atr_mult * row["atr"]

        return signals
