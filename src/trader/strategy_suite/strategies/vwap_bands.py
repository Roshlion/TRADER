"""
VWAP Bands Mean Reversion strategy.

Trades mean reversion to VWAP when price stretches beyond bands.
"""

from typing import List, Dict, Any
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class VWAPBands(BaseStrategy):
    """
    VWAP Bands Reversion strategy.

    Enters long when price falls below VWAP - dev*std and starts to revert,
    enters short when price rises above VWAP + dev*std and starts to revert.

    Parameters:
        dev: Standard deviation multiplier for bands (default: 1.5)
        confirm_red_green: Require confirming candle color (default: True)
        hold_max_minutes: Maximum holding period in minutes (default: 60)
        reset_daily: Reset VWAP daily vs intraday cumulative (default: True)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "dev": 1.5,
            "confirm_red_green": True,
            "hold_max_minutes": 60,
            "reset_daily": True,
        }
        if params:
            default_params.update(params)
        super().__init__("VWAPBands", default_params)

    def _calculate_vwap_bands(self, data: pl.DataFrame, dev: float, reset_daily: bool) -> pl.DataFrame:
        """Calculate VWAP and bands."""
        if reset_daily:
            # Calculate VWAP per day
            data = data.with_columns([
                pl.col("timestamp").dt.date().alias("date")
            ])

            # Calculate cumulative values within each day
            data = data.with_columns([
                (pl.col("close") * pl.col("volume")).cum_sum().over("date").alias("cum_pv"),
                pl.col("volume").cum_sum().over("date").alias("cum_v")
            ]).with_columns([
                (pl.col("cum_pv") / pl.col("cum_v")).alias("vwap")
            ])

            # Calculate standard deviation from VWAP
            data = data.with_columns([
                ((pl.col("close") - pl.col("vwap")).pow(2) * pl.col("volume")).cum_sum().over("date").alias("cum_sq_diff")
            ]).with_columns([
                (pl.col("cum_sq_diff") / pl.col("cum_v")).sqrt().alias("vwap_std")
            ])
        else:
            # Cumulative VWAP across all data
            data = data.with_columns([
                (pl.col("close") * pl.col("volume")).cum_sum().alias("cum_pv"),
                pl.col("volume").cum_sum().alias("cum_v")
            ]).with_columns([
                (pl.col("cum_pv") / pl.col("cum_v")).alias("vwap")
            ])

            # Calculate standard deviation from VWAP
            data = data.with_columns([
                ((pl.col("close") - pl.col("vwap")).pow(2) * pl.col("volume")).cum_sum().alias("cum_sq_diff")
            ]).with_columns([
                (pl.col("cum_sq_diff") / pl.col("cum_v")).sqrt().alias("vwap_std")
            ])

        # Calculate bands
        data = data.with_columns([
            (pl.col("vwap") + dev * pl.col("vwap_std")).alias("upper_band"),
            (pl.col("vwap") - dev * pl.col("vwap_std")).alias("lower_band"),
        ])

        return data

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate VWAP bands reversion signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        dev = self.params["dev"]
        confirm = self.params["confirm_red_green"]
        hold_max = self.params["hold_max_minutes"]
        reset_daily = self.params["reset_daily"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate VWAP and bands
            ticker_data = self._calculate_vwap_bands(ticker_data, dev, reset_daily)

            # Detect candle color if confirmation needed
            if confirm:
                ticker_data = ticker_data.with_columns([
                    (pl.col("close") > pl.col("open")).alias("green_candle"),
                    (pl.col("close") < pl.col("open")).alias("red_candle"),
                ])

            # Detect conditions
            ticker_data = ticker_data.with_columns([
                (pl.col("close") < pl.col("lower_band")).alias("below_lower"),
                (pl.col("close") > pl.col("upper_band")).alias("above_upper"),
                (pl.col("close") > pl.col("vwap")).alias("above_vwap"),
                (pl.col("close") < pl.col("vwap")).alias("below_vwap"),
            ])

            # Track position
            position = None
            entry_idx = None

            rows = list(ticker_data.iter_rows(named=True))

            for i, row in enumerate(rows):
                # Skip if missing data
                if not row["vwap"] or not row["vwap_std"]:
                    continue

                # Check holding period
                if position and entry_idx is not None:
                    if i - entry_idx >= hold_max:
                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=f"Max holding period ({hold_max} bars) reached"
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=f"Max holding period ({hold_max} bars) reached"
                            ))
                        position = None
                        entry_idx = None
                        continue

                # Mean reversion to VWAP - exit conditions
                if position == "long" and row["above_vwap"]:
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SELL,
                        size=1.0,
                        price=row["close"],
                        reason="Price reverted above VWAP"
                    ))
                    position = None
                    entry_idx = None

                elif position == "short" and row["below_vwap"]:
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.COVER,
                        size=1.0,
                        price=row["close"],
                        reason="Price reverted below VWAP"
                    ))
                    position = None
                    entry_idx = None

                # Entry conditions
                if position is None:
                    # Long signal: below lower band + starts reversing up
                    if row["below_lower"]:
                        if not confirm or (i < len(rows) - 1 and rows[i]["green_candle"]):
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.BUY,
                                size=1.0,
                                price=row["close"],
                                confidence=0.7,
                                reason=f"Below VWAP band ({row['lower_band']:.2f}), reverting",
                                indicators={
                                    "vwap": row["vwap"],
                                    "upper_band": row["upper_band"],
                                    "lower_band": row["lower_band"],
                                    "deviation": (row["close"] - row["vwap"]) / row["vwap_std"] if row["vwap_std"] else None
                                }
                            ))
                            position = "long"
                            entry_idx = i

                    # Short signal: above upper band + starts reversing down
                    elif row["above_upper"]:
                        if not confirm or (i < len(rows) - 1 and rows[i]["red_candle"]):
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SHORT,
                                size=1.0,
                                price=row["close"],
                                confidence=0.7,
                                reason=f"Above VWAP band ({row['upper_band']:.2f}), reverting",
                                indicators={
                                    "vwap": row["vwap"],
                                    "upper_band": row["upper_band"],
                                    "lower_band": row["lower_band"],
                                    "deviation": (row["close"] - row["vwap"]) / row["vwap_std"] if row["vwap_std"] else None
                                }
                            ))
                            position = "short"
                            entry_idx = i

        return signals
