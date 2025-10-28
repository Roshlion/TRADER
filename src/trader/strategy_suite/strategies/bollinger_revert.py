"""
Bollinger Bands Mean Reversion strategy.

Trades mean reversion from Bollinger Band extremes.
"""

from typing import List, Dict, Any
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class BollRevert(BaseStrategy):
    """
    Bollinger Bands Reversion strategy.

    Enters long when price touches lower Bollinger Band and starts to reverse,
    enters short when price touches upper Bollinger Band and starts to reverse.

    Parameters:
        len: Bollinger Band period (default: 20)
        stdev: Standard deviation multiplier (default: 2.0)
        exit_mid: Exit at middle band (SMA) vs wait for opposite band (default: True)
        rsi_filter: Optional RSI filter (default: None, or tuple like (30, 70))
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "len": 20,
            "stdev": 2.0,
            "exit_mid": True,
            "rsi_filter": None,  # e.g., (30, 70) for oversold/overbought
        }
        if params:
            default_params.update(params)
        super().__init__("BollRevert", default_params)

    def _calculate_bollinger(self, data: pl.DataFrame, length: int, std_mult: float) -> pl.DataFrame:
        """Calculate Bollinger Bands."""
        data = data.with_columns([
            pl.col("close").rolling_mean(length).alias("bb_mid"),
            pl.col("close").rolling_std(length).alias("bb_std"),
        ]).with_columns([
            (pl.col("bb_mid") + std_mult * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_mid") - std_mult * pl.col("bb_std")).alias("bb_lower"),
        ])
        return data

    def _calculate_rsi(self, data: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """Calculate RSI."""
        data = data.with_columns([
            (pl.col("close") - pl.col("close").shift(1)).alias("price_change")
        ]).with_columns([
            pl.when(pl.col("price_change") > 0).then(pl.col("price_change")).otherwise(0).alias("gain"),
            pl.when(pl.col("price_change") < 0).then(-pl.col("price_change")).otherwise(0).alias("loss"),
        ]).with_columns([
            pl.col("gain").rolling_mean(period).alias("avg_gain"),
            pl.col("loss").rolling_mean(period).alias("avg_loss"),
        ]).with_columns([
            (100 - 100 / (1 + pl.col("avg_gain") / (pl.col("avg_loss") + 1e-10))).alias("rsi")
        ])
        return data

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate Bollinger reversion signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        length = self.params["len"]
        std_mult = self.params["stdev"]
        exit_mid = self.params["exit_mid"]
        rsi_filter = self.params["rsi_filter"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate Bollinger Bands
            ticker_data = self._calculate_bollinger(ticker_data, length, std_mult)

            # Calculate RSI if filter enabled
            if rsi_filter:
                ticker_data = self._calculate_rsi(ticker_data)
                rsi_low, rsi_high = rsi_filter

            # Detect band touches
            ticker_data = ticker_data.with_columns([
                (pl.col("low") <= pl.col("bb_lower")).alias("touch_lower"),
                (pl.col("high") >= pl.col("bb_upper")).alias("touch_upper"),
                (pl.col("close") > pl.col("bb_mid")).alias("above_mid"),
                (pl.col("close") < pl.col("bb_mid")).alias("below_mid"),
            ])

            # Track position
            position = None

            for row in ticker_data.iter_rows(named=True):
                # Skip if missing data
                if not row["bb_mid"] or not row["bb_std"]:
                    continue

                # Exit conditions
                if position == "long":
                    if exit_mid and row["above_mid"]:
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Price crossed above middle band"
                        ))
                        position = None
                    elif not exit_mid and row["touch_upper"]:
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Price reached upper band"
                        ))
                        position = None

                elif position == "short":
                    if exit_mid and row["below_mid"]:
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Price crossed below middle band"
                        ))
                        position = None
                    elif not exit_mid and row["touch_lower"]:
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Price reached lower band"
                        ))
                        position = None

                # Entry conditions
                if position is None:
                    # Long signal: touch lower band
                    if row["touch_lower"]:
                        # Check RSI filter if enabled
                        if rsi_filter and (not row.get("rsi") or row["rsi"] > rsi_low):
                            continue

                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.BUY,
                            size=1.0,
                            price=row["close"],
                            confidence=0.75,
                            reason=f"Touched lower Bollinger Band ({row['bb_lower']:.2f})",
                            indicators={
                                "bb_upper": row["bb_upper"],
                                "bb_mid": row["bb_mid"],
                                "bb_lower": row["bb_lower"],
                                "bb_width": (row["bb_upper"] - row["bb_lower"]) / row["bb_mid"] if row["bb_mid"] else None,
                                "rsi": row.get("rsi")
                            }
                        ))
                        position = "long"

                    # Short signal: touch upper band
                    elif row["touch_upper"]:
                        # Check RSI filter if enabled
                        if rsi_filter and (not row.get("rsi") or row["rsi"] < rsi_high):
                            continue

                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SHORT,
                            size=1.0,
                            price=row["close"],
                            confidence=0.75,
                            reason=f"Touched upper Bollinger Band ({row['bb_upper']:.2f})",
                            indicators={
                                "bb_upper": row["bb_upper"],
                                "bb_mid": row["bb_mid"],
                                "bb_lower": row["bb_lower"],
                                "bb_width": (row["bb_upper"] - row["bb_lower"]) / row["bb_mid"] if row["bb_mid"] else None,
                                "rsi": row.get("rsi")
                            }
                        ))
                        position = "short"

        return signals
