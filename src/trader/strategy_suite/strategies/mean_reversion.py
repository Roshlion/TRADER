"""
Mean reversion trading strategies.

Strategies that exploit short-term price overextensions, betting that
price will revert to its mean (VWAP, moving average, Bollinger Bands, etc.).
"""

from typing import List, Dict, Any
from datetime import datetime
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data, calculate_vwap, calculate_bollinger_bands
)


class VWAPReversionStrategy(BaseStrategy):
    """
    VWAP mean reversion strategy.

    Trades when price deviates significantly from VWAP, expecting reversion.
    Long when price is below VWAP - threshold, short when above VWAP + threshold.

    Parameters:
        std_dev_threshold: Number of standard deviations from VWAP (default: 2.0)
        holding_period: Maximum bars to hold position (default: 30)
        min_volume: Minimum volume filter (default: 10000)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "std_dev_threshold": 2.0,
            "holding_period": 30,
            "min_volume": 10000,
        }
        if params:
            default_params.update(params)
        super().__init__("VWAPReversion", default_params)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate VWAP reversion signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        std_threshold = self.params["std_dev_threshold"]
        holding_period = self.params["holding_period"]
        min_vol = self.params["min_volume"]

        signals = []

        # Group by ticker and date (VWAP resets daily)
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Filter by minimum volume
            ticker_data = ticker_data.filter(pl.col("volume") >= min_vol)

            if len(ticker_data) == 0:
                continue

            # Calculate VWAP
            ticker_data = calculate_vwap(ticker_data)

            # Calculate standard deviation of (price - VWAP)
            ticker_data = ticker_data.with_columns([
                (pl.col("close") - pl.col("vwap")).alias("vwap_deviation"),
            ])

            # Rolling std of deviation (for dynamic threshold)
            ticker_data = ticker_data.with_columns([
                pl.col("vwap_deviation").rolling_std(20).alias("deviation_std"),
            ])

            # Calculate z-score
            ticker_data = ticker_data.with_columns([
                (pl.col("vwap_deviation") / pl.col("deviation_std")).alias("vwap_zscore"),
            ])

            # Detect reversion signals
            ticker_data = ticker_data.with_columns([
                # Long signal: price significantly below VWAP
                (pl.col("vwap_zscore") < -std_threshold).alias("oversold"),
                # Short signal: price significantly above VWAP
                (pl.col("vwap_zscore") > std_threshold).alias("overbought"),
                # Exit signal: price crossed back to VWAP
                (pl.col("vwap_zscore").abs() < 0.5).alias("at_vwap"),
            ])

            # Track position
            position = None
            position_entry_idx = None

            for i, row in enumerate(ticker_data.iter_rows(named=True)):
                if row["oversold"] and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Reversion to VWAP"
                        ))

                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=min(abs(row["vwap_zscore"]) / std_threshold, 1.0) if row["vwap_zscore"] else None,
                        reason=f"Oversold: {row['vwap_zscore']:.2f} std devs below VWAP",
                        indicators={
                            "vwap": row["vwap"],
                            "vwap_zscore": row["vwap_zscore"],
                            "deviation": row["vwap_deviation"],
                        }
                    ))
                    position = "long"
                    position_entry_idx = i

                elif row["overbought"] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Reversion to VWAP"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=min(abs(row["vwap_zscore"]) / std_threshold, 1.0) if row["vwap_zscore"] else None,
                        reason=f"Overbought: {row['vwap_zscore']:.2f} std devs above VWAP",
                        indicators={
                            "vwap": row["vwap"],
                            "vwap_zscore": row["vwap_zscore"],
                            "deviation": row["vwap_deviation"],
                        }
                    ))
                    position = "short"
                    position_entry_idx = i

                elif position:
                    # Check for mean reversion or holding period exit
                    if row["at_vwap"] or (position_entry_idx and i - position_entry_idx >= holding_period):
                        exit_reason = "Reverted to VWAP" if row["at_vwap"] else f"Holding period ({holding_period} bars)"

                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=exit_reason
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=exit_reason
                            ))
                        position = None
                        position_entry_idx = None

        return signals


class BollingerBandStrategy(BaseStrategy):
    """
    Bollinger Band mean reversion strategy.

    Trades when price touches or crosses Bollinger Bands, expecting bounce back.
    Long at lower band, short at upper band.

    Parameters:
        bb_window: Bollinger Band window (default: 20)
        bb_std: Number of standard deviations for bands (default: 2.0)
        holding_period: Maximum bars to hold (default: 30)
        entry_threshold: How far beyond band to trigger (default: 0.0 = touch)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "bb_window": 20,
            "bb_std": 2.0,
            "holding_period": 30,
            "entry_threshold": 0.0,
        }
        if params:
            default_params.update(params)
        super().__init__("BollingerBandStrategy", default_params)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate Bollinger Band reversion signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        bb_window = self.params["bb_window"]
        bb_std = self.params["bb_std"]
        holding_period = self.params["holding_period"]
        entry_threshold = self.params["entry_threshold"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Calculate Bollinger Bands
            ticker_data = calculate_bollinger_bands(ticker_data, window=bb_window, num_std=bb_std)

            # Calculate band width for volatility filter
            ticker_data = ticker_data.with_columns([
                ((pl.col("bb_upper") - pl.col("bb_lower")) / pl.col("bb_middle") * 100).alias("bb_width_pct"),
            ])

            # Detect signals
            ticker_data = ticker_data.with_columns([
                # Lower band touch/breach (oversold)
                (pl.col("close") <= pl.col("bb_lower") * (1 - entry_threshold)).alias("at_lower_band"),
                # Upper band touch/breach (overbought)
                (pl.col("close") >= pl.col("bb_upper") * (1 + entry_threshold)).alias("at_upper_band"),
                # Back inside bands (reversion)
                (
                    (pl.col("close") > pl.col("bb_lower")) &
                    (pl.col("close") < pl.col("bb_upper"))
                ).alias("inside_bands"),
            ])

            # Track position
            position = None
            position_entry_idx = None

            for i, row in enumerate(ticker_data.iter_rows(named=True)):
                # Skip if Bollinger Bands not yet calculated
                if row["bb_lower"] is None or row["bb_upper"] is None:
                    continue

                if row["at_lower_band"] and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Bounce from lower band"
                        ))

                    # Enter long
                    distance_from_band = (row["bb_lower"] - row["close"]) / row["bb_middle"] * 100
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=min(abs(distance_from_band) / 5.0, 1.0),  # Normalize to ~5% as max
                        reason=f"At lower Bollinger Band ({row['bb_lower']:.2f})",
                        indicators={
                            "bb_lower": row["bb_lower"],
                            "bb_middle": row["bb_middle"],
                            "bb_upper": row["bb_upper"],
                            "bb_width_pct": row["bb_width_pct"],
                        }
                    ))
                    position = "long"
                    position_entry_idx = i

                elif row["at_upper_band"] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Bounce from upper band"
                        ))

                    # Enter short
                    distance_from_band = (row["close"] - row["bb_upper"]) / row["bb_middle"] * 100
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=min(abs(distance_from_band) / 5.0, 1.0),
                        reason=f"At upper Bollinger Band ({row['bb_upper']:.2f})",
                        indicators={
                            "bb_lower": row["bb_lower"],
                            "bb_middle": row["bb_middle"],
                            "bb_upper": row["bb_upper"],
                            "bb_width_pct": row["bb_width_pct"],
                        }
                    ))
                    position = "short"
                    position_entry_idx = i

                elif position:
                    # Check for reversion to middle or holding period
                    at_middle = abs(row["close"] - row["bb_middle"]) / row["bb_middle"] < 0.01  # Within 1% of middle
                    holding_expired = position_entry_idx and i - position_entry_idx >= holding_period

                    if at_middle or holding_expired:
                        exit_reason = "Reverted to BB middle" if at_middle else f"Holding period ({holding_period} bars)"

                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=exit_reason
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=exit_reason
                            ))
                        position = None
                        position_entry_idx = None

        return signals
