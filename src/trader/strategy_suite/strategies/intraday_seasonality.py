"""
Intraday Seasonality / Time-of-Day Edge strategy.

Trades based on statistically favorable time windows (open/close effects, etc.).
"""

from typing import List, Dict, Any, Tuple
from datetime import time
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class Seasonality(BaseStrategy):
    """
    Intraday Seasonality strategy.

    Trades only during specific time windows that have historically shown
    directional edge (e.g., opening momentum, closing drift).

    Parameters:
        slots: List of time window tuples (start, end) (default: [('09:35','10:15'), ('15:10','15:55')])
        direction: Trade direction per slot ('long', 'short', 'both', 'auto') (default: 'auto')
        filter_vol_pct: Minimum volume percentile to trade (default: 50)
        momentum_lookback: Bars to look back for momentum signal (default: 5)
        hold_until_slot_end: Hold position until end of time slot (default: True)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "slots": [('09:35', '10:15'), ('15:10', '15:55')],  # Opening and closing windows
            "direction": 'auto',  # Can be 'long', 'short', 'both', or 'auto'
            "filter_vol_pct": 50,
            "momentum_lookback": 5,
            "hold_until_slot_end": True,
        }
        if params:
            default_params.update(params)
        super().__init__("Seasonality", default_params)

    def _is_in_slot(self, trade_time: time, slots: List[Tuple[str, str]]) -> Tuple[bool, int]:
        """Check if time is within any trading slot. Returns (in_slot, slot_index)."""
        for idx, (start, end) in enumerate(slots):
            start_time = time.fromisoformat(start)
            end_time = time.fromisoformat(end)
            if start_time <= trade_time <= end_time:
                return True, idx
        return False, -1

    def _get_slot_end_time(self, slot_idx: int, slots: List[Tuple[str, str]]) -> time:
        """Get the end time of a slot."""
        if 0 <= slot_idx < len(slots):
            return time.fromisoformat(slots[slot_idx][1])
        return None

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate seasonality signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        slots = self.params["slots"]
        direction = self.params["direction"]
        vol_pct_filter = self.params["filter_vol_pct"]
        momentum_lookback = self.params["momentum_lookback"]
        hold_until_end = self.params["hold_until_slot_end"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Extract time
            ticker_data = ticker_data.with_columns([
                pl.col("timestamp").dt.time().alias("time"),
            ])

            # Calculate volume percentile
            ticker_data = ticker_data.with_columns([
                pl.col("volume").rank(method="average").alias("vol_rank")
            ]).with_columns([
                (pl.col("vol_rank") / pl.col("vol_rank").count() * 100).alias("vol_pct")
            ])

            # Calculate momentum (return over lookback period)
            ticker_data = ticker_data.with_columns([
                ((pl.col("close") - pl.col("close").shift(momentum_lookback)) /
                 pl.col("close").shift(momentum_lookback) * 100).alias("momentum_pct")
            ])

            # Track position
            position = None
            position_slot = None
            slot_end_time = None

            for row in ticker_data.iter_rows(named=True):
                trade_time = row["time"]
                in_slot, slot_idx = self._is_in_slot(trade_time, slots)

                # Check volume filter
                if row["vol_pct"] < vol_pct_filter:
                    continue

                # Exit at slot end if holding
                if position and hold_until_end and slot_end_time:
                    if trade_time >= slot_end_time:
                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=f"Time slot ended at {slot_end_time}"
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=f"Time slot ended at {slot_end_time}"
                            ))
                        position = None
                        position_slot = None
                        slot_end_time = None

                # Only trade in designated slots
                if not in_slot:
                    continue

                # Skip if already in position for this slot
                if position and position_slot == slot_idx:
                    continue

                # Determine trade direction
                trade_dir = direction
                if direction == 'auto':
                    # Use momentum to determine direction
                    if row["momentum_pct"] and row["momentum_pct"] > 0:
                        trade_dir = 'long'
                    elif row["momentum_pct"] and row["momentum_pct"] < 0:
                        trade_dir = 'short'
                    else:
                        continue

                # Generate signals
                if trade_dir in ['long', 'both'] and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="Slot direction changed"
                        ))

                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=0.65,
                        reason=f"Seasonality: long in slot {slot_idx} ({slots[slot_idx][0]}-{slots[slot_idx][1]})",
                        indicators={
                            "slot_idx": slot_idx,
                            "slot_time": f"{slots[slot_idx][0]}-{slots[slot_idx][1]}",
                            "momentum_pct": row["momentum_pct"],
                            "vol_pct": row["vol_pct"]
                        }
                    ))
                    position = "long"
                    position_slot = slot_idx
                    slot_end_time = self._get_slot_end_time(slot_idx, slots)

                elif trade_dir in ['short', 'both'] and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="Slot direction changed"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=0.65,
                        reason=f"Seasonality: short in slot {slot_idx} ({slots[slot_idx][0]}-{slots[slot_idx][1]})",
                        indicators={
                            "slot_idx": slot_idx,
                            "slot_time": f"{slots[slot_idx][0]}-{slots[slot_idx][1]}",
                            "momentum_pct": row["momentum_pct"],
                            "vol_pct": row["vol_pct"]
                        }
                    ))
                    position = "short"
                    position_slot = slot_idx
                    slot_end_time = self._get_slot_end_time(slot_idx, slots)

        return signals
