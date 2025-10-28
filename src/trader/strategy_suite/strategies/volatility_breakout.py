"""
Volatility Breakout (ATR Channel) strategy.

Trades breakouts beyond prior day close ± k*ATR.
"""

from typing import List, Dict, Any
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class ATRBreakout(BaseStrategy):
    """
    ATR Channel Breakout strategy.

    Enters long when price breaks above prior close + k*ATR,
    enters short when price breaks below prior close - k*ATR.

    Parameters:
        atr_len: ATR calculation period (default: 14)
        k: ATR multiplier for bands (default: 1.5)
        vol_filter: Only trade on high volume (default: True)
        trailing_atr_mult: Trailing stop ATR multiplier (default: 2.0)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "atr_len": 14,
            "k": 1.5,
            "vol_filter": True,
            "trailing_atr_mult": 2.0,
        }
        if params:
            default_params.update(params)
        super().__init__("ATRBreakout", default_params)

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
        """Generate ATR breakout signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        atr_len = self.params["atr_len"]
        k = self.params["k"]
        vol_filter = self.params["vol_filter"]
        trail_mult = self.params["trailing_atr_mult"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate ATR
            ticker_data = self._calculate_atr(ticker_data, atr_len)

            # Calculate ATR bands around prior close
            ticker_data = ticker_data.with_columns([
                pl.col("close").shift(1).alias("prior_close")
            ]).with_columns([
                (pl.col("prior_close") + k * pl.col("atr")).alias("upper_band"),
                (pl.col("prior_close") - k * pl.col("atr")).alias("lower_band"),
            ])

            # Volume filter
            if vol_filter:
                ticker_data = ticker_data.with_columns([
                    pl.col("volume").rolling_mean(20).alias("avg_volume")
                ]).with_columns([
                    (pl.col("volume") > pl.col("avg_volume")).alias("high_volume")
                ])
            else:
                ticker_data = ticker_data.with_columns([
                    pl.lit(True).alias("high_volume")
                ])

            # Detect breakouts
            ticker_data = ticker_data.with_columns([
                (pl.col("close") > pl.col("upper_band")).alias("breakout_up"),
                (pl.col("close") < pl.col("lower_band")).alias("breakout_down"),
            ])

            # Track position
            position = None
            entry_price = None
            trailing_stop = None

            for row in ticker_data.iter_rows(named=True):
                # Skip if missing data
                if not row["atr"] or not row["upper_band"]:
                    continue

                # Update trailing stop
                if position == "long" and entry_price and row["atr"]:
                    trailing_stop = max(trailing_stop or 0, row["close"] - trail_mult * row["atr"])

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
                    trailing_stop = min(trailing_stop or float('inf'), row["close"] + trail_mult * row["atr"])

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

                # Check for new signals
                if row["breakout_up"] and row["high_volume"] and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Opposite breakout"
                        ))

                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=0.75,
                        reason=f"ATR breakout above {row['upper_band']:.2f}",
                        indicators={
                            "upper_band": row["upper_band"],
                            "lower_band": row["lower_band"],
                            "atr": row["atr"],
                            "stop": row["close"] - trail_mult * row["atr"]
                        }
                    ))
                    position = "long"
                    entry_price = row["close"]
                    trailing_stop = row["close"] - trail_mult * row["atr"]

                elif row["breakout_down"] and row["high_volume"] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Opposite breakout"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=0.75,
                        reason=f"ATR breakdown below {row['lower_band']:.2f}",
                        indicators={
                            "upper_band": row["upper_band"],
                            "lower_band": row["lower_band"],
                            "atr": row["atr"],
                            "stop": row["close"] + trail_mult * row["atr"]
                        }
                    ))
                    position = "short"
                    entry_price = row["close"]
                    trailing_stop = row["close"] + trail_mult * row["atr"]

        return signals
