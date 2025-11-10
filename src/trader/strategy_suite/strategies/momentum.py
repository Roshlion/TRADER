"""
Momentum-based trading strategies.

Strategies that aim to profit from trend continuation and rapid price moves,
including breakout strategies and volume spike strategies.
"""

from typing import List, Dict, Any
from datetime import datetime
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data, calculate_relative_volume
)


class BreakoutMomentumStrategy(BaseStrategy):
    """
    Breakout momentum strategy.

    Enters long when price breaks above recent high with volume confirmation.
    Exits on opposite signal or after holding period.

    Parameters:
        lookback_bars: Number of bars to look back for high/low (default: 30)
        volume_threshold: Minimum relative volume multiple (default: 2.0)
        holding_period: Bars to hold position before exit (default: 60)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "lookback_bars": 30,
            "volume_threshold": 2.0,
            "holding_period": 60,
        }
        if params:
            default_params.update(params)
        super().__init__("BreakoutMomentum", default_params)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate breakout momentum signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        lookback = self.params["lookback_bars"]
        vol_thresh = self.params["volume_threshold"]
        holding_period = self.params["holding_period"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate indicators
            ticker_data = calculate_relative_volume(ticker_data, window=10)

            # Calculate rolling high/low
            ticker_data = ticker_data.with_columns([
                pl.col("high").rolling_max(lookback).alias("recent_high"),
                pl.col("low").rolling_min(lookback).alias("recent_low"),
            ])

            # Detect breakouts
            ticker_data = ticker_data.with_columns([
                # Long breakout: close > recent high AND rvol > threshold
                (
                    (pl.col("close") > pl.col("recent_high").shift(1)) &
                    (pl.col("rvol") > vol_thresh)
                ).alias("long_breakout"),
                # Short breakout: close < recent low AND rvol > threshold
                (
                    (pl.col("close") < pl.col("recent_low").shift(1)) &
                    (pl.col("rvol") > vol_thresh)
                ).alias("short_breakout"),
            ])

            # Track positions to manage holding period
            position = None
            position_entry_idx = None

            for i, row in enumerate(ticker_data.iter_rows(named=True)):
                if row["long_breakout"] and position != "long":
                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,  # Will be sized by simulator
                        price=row["close"],
                        confidence=min(row["rvol"] / vol_thresh, 1.0) if row["rvol"] else None,
                        reason=f"Breakout above {row['recent_high']:.2f} with RVOL={row['rvol']:.2f}",
                        indicators={
                            "recent_high": row["recent_high"],
                            "rvol": row["rvol"],
                        }
                    ))
                    position = "long"
                    position_entry_idx = i

                elif row["short_breakout"] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Opposite breakout signal"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=min(row["rvol"] / vol_thresh, 1.0) if row["rvol"] else None,
                        reason=f"Breakdown below {row['recent_low']:.2f} with RVOL={row['rvol']:.2f}",
                        indicators={
                            "recent_low": row["recent_low"],
                            "rvol": row["rvol"],
                        }
                    ))
                    position = "short"
                    position_entry_idx = i

                elif position and position_entry_idx is not None:
                    # Check holding period exit
                    if i - position_entry_idx >= holding_period:
                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=f"Holding period ({holding_period} bars) reached"
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=f"Holding period ({holding_period} bars) reached"
                            ))
                        position = None
                        position_entry_idx = None

        return signals


class VolumeSpikeStrategy(BaseStrategy):
    """
    Volume spike momentum strategy.

    Enters when unusual volume spike occurs with price movement in same direction.
    Assumes volume precedes strong moves.

    Parameters:
        rvol_threshold: Minimum relative volume for spike (default: 3.0)
        price_change_pct: Minimum price change percentage (default: 0.5)
        holding_period: Bars to hold position (default: 30)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "rvol_threshold": 3.0,
            "price_change_pct": 0.5,
            "holding_period": 30,
        }
        if params:
            default_params.update(params)
        super().__init__("VolumeSpikeStrategy", default_params)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate volume spike signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        rvol_thresh = self.params["rvol_threshold"]
        price_change = self.params["price_change_pct"]
        holding_period = self.params["holding_period"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate indicators
            ticker_data = calculate_relative_volume(ticker_data, window=20)

            # Calculate price change percentage
            ticker_data = ticker_data.with_columns([
                ((pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1) * 100).alias("price_change_pct"),
            ])

            # Detect volume spikes with directional price movement
            ticker_data = ticker_data.with_columns([
                # Volume spike + upward price movement
                (
                    (pl.col("rvol") > rvol_thresh) &
                    (pl.col("price_change_pct") > price_change)
                ).alias("spike_up"),
                # Volume spike + downward price movement
                (
                    (pl.col("rvol") > rvol_thresh) &
                    (pl.col("price_change_pct") < -price_change)
                ).alias("spike_down"),
            ])

            # Track position
            position = None
            position_entry_idx = None

            for i, row in enumerate(ticker_data.iter_rows(named=True)):
                if row["spike_up"] and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Opposite volume spike"
                        ))

                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=min(row["rvol"] / rvol_thresh, 1.0) if row["rvol"] else None,
                        reason=f"Volume spike up: RVOL={row['rvol']:.2f}, Price +{row['price_change_pct']:.2f}%",
                        indicators={
                            "rvol": row["rvol"],
                            "price_change_pct": row["price_change_pct"],
                        }
                    ))
                    position = "long"
                    position_entry_idx = i

                elif row["spike_down"] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Opposite volume spike"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=min(row["rvol"] / rvol_thresh, 1.0) if row["rvol"] else None,
                        reason=f"Volume spike down: RVOL={row['rvol']:.2f}, Price {row['price_change_pct']:.2f}%",
                        indicators={
                            "rvol": row["rvol"],
                            "price_change_pct": row["price_change_pct"],
                        }
                    ))
                    position = "short"
                    position_entry_idx = i

                elif position and position_entry_idx is not None:
                    # Check holding period
                    if i - position_entry_idx >= holding_period:
                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=f"Holding period ({holding_period} bars) reached"
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=f"Holding period ({holding_period} bars) reached"
                            ))
                        position = None
                        position_entry_idx = None

        return signals
