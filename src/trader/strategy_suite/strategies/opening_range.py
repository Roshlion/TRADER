"""
Opening Range Breakout (ORB) strategy.

Trades breakouts of the first N minutes of the trading day.
"""

from typing import List, Dict, Any
from datetime import time
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class ORB(BaseStrategy):
    """
    Opening Range Breakout strategy.

    Enters long when price breaks above the high of the first N minutes,
    enters short when price breaks below the low of the first N minutes.

    Parameters:
        range_minutes: Number of minutes for opening range (default: 30)
        confirm_bars: Bars to confirm breakout (default: 0)
        atr_mult_stop: ATR multiplier for stop loss (default: 1.0)
        time_filter: Tuple of (start_time, end_time) for trading window (default: ('09:45','15:30'))
        vol_pct_filter: Minimum volume percentile (default: 60)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "range_minutes": 30,
            "confirm_bars": 0,
            "atr_mult_stop": 1.0,
            "time_filter": ('09:45', '15:30'),
            "vol_pct_filter": 60,
        }
        if params:
            default_params.update(params)
        super().__init__("ORB", default_params)

    def _calculate_atr(self, data: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """Calculate Average True Range."""
        data = data.with_columns([
            # True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
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
        """Generate ORB signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        range_minutes = self.params["range_minutes"]
        confirm_bars = self.params["confirm_bars"]
        atr_mult = self.params["atr_mult_stop"]
        time_start, time_end = self.params["time_filter"]
        vol_pct = self.params["vol_pct_filter"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate ATR for stops
            ticker_data = self._calculate_atr(ticker_data)

            # Extract date and time
            ticker_data = ticker_data.with_columns([
                pl.col("timestamp").dt.date().alias("date"),
                pl.col("timestamp").dt.time().alias("time"),
            ])

            # Calculate volume percentile
            ticker_data = ticker_data.with_columns([
                pl.col("volume").rank(method="average").alias("vol_rank")
            ]).with_columns([
                (pl.col("vol_rank") / pl.col("vol_rank").count() * 100).alias("vol_pct")
            ])

            # For each trading day
            for date in ticker_data["date"].unique():
                day_data = ticker_data.filter(pl.col("date") == date).sort("timestamp")

                if len(day_data) < range_minutes:
                    continue

                # Get opening range
                opening_range = day_data.head(range_minutes)
                or_high = opening_range["high"].max()
                or_low = opening_range["low"].min()

                # Track position and confirmation
                position = None
                confirm_count = 0
                confirm_target = None

                # Start looking for breakouts after opening range
                for row in day_data.slice(range_minutes).iter_rows(named=True):
                    trade_time = row["time"]

                    # Check time filter
                    if not (time.fromisoformat(time_start) <= trade_time <= time.fromisoformat(time_end)):
                        continue

                    # Check volume filter
                    if row["vol_pct"] < vol_pct:
                        continue

                    # Confirmation logic
                    if confirm_target:
                        if confirm_target == "long" and row["close"] > or_high:
                            confirm_count += 1
                        elif confirm_target == "short" and row["close"] < or_low:
                            confirm_count += 1
                        else:
                            confirm_count = 0
                            confirm_target = None

                        if confirm_count >= confirm_bars:
                            # Execute signal
                            if confirm_target == "long" and position != "long":
                                if position == "short":
                                    signals.append(Signal(
                                        timestamp=row["timestamp"],
                                        ticker=ticker,
                                        action=SignalAction.COVER,
                                        size=1.0,
                                        price=row["close"],
                                        reason="ORB reversal"
                                    ))

                                signals.append(Signal(
                                    timestamp=row["timestamp"],
                                    ticker=ticker,
                                    action=SignalAction.BUY,
                                    size=1.0,
                                    price=row["close"],
                                    confidence=0.8,
                                    reason=f"ORB break above {or_high:.2f}",
                                    indicators={
                                        "or_high": or_high,
                                        "or_low": or_low,
                                        "atr": row["atr"],
                                        "stop": row["close"] - atr_mult * row["atr"] if row["atr"] else None
                                    }
                                ))
                                position = "long"

                            elif confirm_target == "short" and position != "short":
                                if position == "long":
                                    signals.append(Signal(
                                        timestamp=row["timestamp"],
                                        ticker=ticker,
                                        action=SignalAction.SELL,
                                        size=1.0,
                                        price=row["close"],
                                        reason="ORB reversal"
                                    ))

                                signals.append(Signal(
                                    timestamp=row["timestamp"],
                                    ticker=ticker,
                                    action=SignalAction.SHORT,
                                    size=1.0,
                                    price=row["close"],
                                    confidence=0.8,
                                    reason=f"ORB break below {or_low:.2f}",
                                    indicators={
                                        "or_high": or_high,
                                        "or_low": or_low,
                                        "atr": row["atr"],
                                        "stop": row["close"] + atr_mult * row["atr"] if row["atr"] else None
                                    }
                                ))
                                position = "short"

                            confirm_count = 0
                            confirm_target = None

                    # Detect initial breakout
                    if not confirm_target:
                        if row["close"] > or_high and position != "long":
                            if confirm_bars == 0:
                                # No confirmation needed
                                if position == "short":
                                    signals.append(Signal(
                                        timestamp=row["timestamp"],
                                        ticker=ticker,
                                        action=SignalAction.COVER,
                                        size=1.0,
                                        price=row["close"],
                                        reason="ORB reversal"
                                    ))

                                signals.append(Signal(
                                    timestamp=row["timestamp"],
                                    ticker=ticker,
                                    action=SignalAction.BUY,
                                    size=1.0,
                                    price=row["close"],
                                    confidence=0.8,
                                    reason=f"ORB break above {or_high:.2f}",
                                    indicators={
                                        "or_high": or_high,
                                        "or_low": or_low,
                                        "atr": row["atr"],
                                        "stop": row["close"] - atr_mult * row["atr"] if row["atr"] else None
                                    }
                                ))
                                position = "long"
                            else:
                                confirm_target = "long"
                                confirm_count = 1

                        elif row["close"] < or_low and position != "short":
                            if confirm_bars == 0:
                                # No confirmation needed
                                if position == "long":
                                    signals.append(Signal(
                                        timestamp=row["timestamp"],
                                        ticker=ticker,
                                        action=SignalAction.SELL,
                                        size=1.0,
                                        price=row["close"],
                                        reason="ORB reversal"
                                    ))

                                signals.append(Signal(
                                    timestamp=row["timestamp"],
                                    ticker=ticker,
                                    action=SignalAction.SHORT,
                                    size=1.0,
                                    price=row["close"],
                                    confidence=0.8,
                                    reason=f"ORB break below {or_low:.2f}",
                                    indicators={
                                        "or_high": or_high,
                                        "or_low": or_low,
                                        "atr": row["atr"],
                                        "stop": row["close"] + atr_mult * row["atr"] if row["atr"] else None
                                    }
                                ))
                                position = "short"
                            else:
                                confirm_target = "short"
                                confirm_count = 1

        return signals
