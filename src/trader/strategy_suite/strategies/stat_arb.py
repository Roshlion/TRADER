"""
Statistical arbitrage strategies.

Strategies that trade spreads between correlated instruments,
focusing on pairs trading and cointegration-based approaches.
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime
import polars as pl
import numpy as np
from .base import BaseStrategy, Signal, SignalAction, validate_data


class PairsTradingStrategy(BaseStrategy):
    """
    Pairs trading strategy based on mean reversion of price spread.

    Trades the spread between two correlated stocks. When spread deviates
    from its mean, goes long the underperformer and short the outperformer,
    expecting convergence.

    Parameters:
        ticker_pair: Tuple of two ticker symbols, e.g., ("AAPL", "MSFT")
        lookback_window: Window for calculating spread statistics (default: 60)
        entry_z_score: Z-score threshold for entry (default: 2.0)
        exit_z_score: Z-score threshold for exit (default: 0.5)
        hedge_ratio_method: 'fixed' or 'rolling' (default: 'rolling')
        hedge_ratio: If method='fixed', use this ratio (default: 1.0)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "ticker_pair": None,  # Must be provided
            "lookback_window": 60,
            "entry_z_score": 2.0,
            "exit_z_score": 0.5,
            "hedge_ratio_method": "rolling",
            "hedge_ratio": 1.0,
        }
        if params:
            default_params.update(params)
        super().__init__("PairsTradingStrategy", default_params)

        if not self.params["ticker_pair"] or len(self.params["ticker_pair"]) != 2:
            raise ValueError("ticker_pair parameter must be a tuple of two ticker symbols")

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate pairs trading signals."""
        validate_data(data, ["timestamp", "ticker", "close"])

        ticker_a, ticker_b = self.params["ticker_pair"]
        lookback = self.params["lookback_window"]
        entry_z = self.params["entry_z_score"]
        exit_z = self.params["exit_z_score"]
        hedge_method = self.params["hedge_ratio_method"]
        fixed_hedge = self.params["hedge_ratio"]

        # Extract data for each ticker
        data_a = data.filter(pl.col("ticker") == ticker_a).sort("timestamp")
        data_b = data.filter(pl.col("ticker") == ticker_b).sort("timestamp")

        if len(data_a) == 0 or len(data_b) == 0:
            return []

        # Align timestamps (inner join)
        aligned = data_a.join(
            data_b,
            on="timestamp",
            suffix="_b"
        ).select([
            "timestamp",
            pl.col("close").alias("price_a"),
            pl.col("close_b").alias("price_b"),
        ])

        if len(aligned) < lookback:
            return []  # Not enough data

        # Calculate hedge ratio (beta)
        if hedge_method == "rolling":
            # Rolling linear regression to get beta
            hedge_ratios = []
            for i in range(len(aligned)):
                if i < lookback:
                    hedge_ratios.append(None)
                else:
                    window_data = aligned[i-lookback:i]
                    prices_a = window_data["price_a"].to_numpy()
                    prices_b = window_data["price_b"].to_numpy()

                    # Simple linear regression: price_a = beta * price_b + alpha
                    # Beta = Cov(A, B) / Var(B)
                    beta = np.cov(prices_a, prices_b)[0, 1] / np.var(prices_b)
                    hedge_ratios.append(beta)

            aligned = aligned.with_columns([
                pl.Series("hedge_ratio", hedge_ratios)
            ])
        else:
            # Fixed hedge ratio
            aligned = aligned.with_columns([
                pl.lit(fixed_hedge).alias("hedge_ratio")
            ])

        # Calculate spread: spread = price_a - beta * price_b
        aligned = aligned.with_columns([
            (pl.col("price_a") - pl.col("hedge_ratio") * pl.col("price_b")).alias("spread")
        ])

        # Calculate rolling mean and std of spread
        aligned = aligned.with_columns([
            pl.col("spread").rolling_mean(lookback).alias("spread_mean"),
            pl.col("spread").rolling_std(lookback).alias("spread_std"),
        ])

        # Calculate z-score of spread
        aligned = aligned.with_columns([
            ((pl.col("spread") - pl.col("spread_mean")) / pl.col("spread_std")).alias("spread_zscore")
        ])

        signals = []
        position = None  # 'long_spread' or 'short_spread' or None

        for row in aligned.iter_rows(named=True):
            if row["spread_zscore"] is None or np.isnan(row["spread_zscore"]):
                continue

            z = row["spread_zscore"]
            timestamp = row["timestamp"]
            price_a = row["price_a"]
            price_b = row["price_b"]
            hedge_ratio = row["hedge_ratio"]

            # Entry signals
            if z > entry_z and position != "short_spread":
                # Spread too high: short A, long B
                if position == "long_spread":
                    # Close existing long spread position
                    signals.extend(self._close_spread_position(
                        timestamp, ticker_a, ticker_b, price_a, price_b,
                        "long_spread", "Spread reversed"
                    ))

                # Open short spread position
                signals.extend(self._open_spread_position(
                    timestamp, ticker_a, ticker_b, price_a, price_b,
                    hedge_ratio, "short_spread",
                    f"Spread z-score {z:.2f} > {entry_z}"
                ))
                position = "short_spread"

            elif z < -entry_z and position != "long_spread":
                # Spread too low: long A, short B
                if position == "short_spread":
                    # Close existing short spread position
                    signals.extend(self._close_spread_position(
                        timestamp, ticker_a, ticker_b, price_a, price_b,
                        "short_spread", "Spread reversed"
                    ))

                # Open long spread position
                signals.extend(self._open_spread_position(
                    timestamp, ticker_a, ticker_b, price_a, price_b,
                    hedge_ratio, "long_spread",
                    f"Spread z-score {z:.2f} < -{entry_z}"
                ))
                position = "long_spread"

            # Exit signals (mean reversion)
            elif abs(z) < exit_z and position is not None:
                signals.extend(self._close_spread_position(
                    timestamp, ticker_a, ticker_b, price_a, price_b,
                    position, f"Spread converged (z={z:.2f})"
                ))
                position = None

        return signals

    def _open_spread_position(
        self,
        timestamp: datetime,
        ticker_a: str,
        ticker_b: str,
        price_a: float,
        price_b: float,
        hedge_ratio: float,
        position_type: str,
        reason: str
    ) -> List[Signal]:
        """Open a spread position (long/short both legs)."""
        signals = []

        if position_type == "long_spread":
            # Long spread: Long A, Short B
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_a,
                action=SignalAction.BUY,
                size=1.0,
                price=price_a,
                reason=f"Long spread: {reason}",
                indicators={"hedge_ratio": hedge_ratio, "spread_position": "long"}
            ))
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_b,
                action=SignalAction.SHORT,
                size=hedge_ratio,  # Hedge ratio determines B position size
                price=price_b,
                reason=f"Long spread: {reason}",
                indicators={"hedge_ratio": hedge_ratio, "spread_position": "long"}
            ))
        elif position_type == "short_spread":
            # Short spread: Short A, Long B
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_a,
                action=SignalAction.SHORT,
                size=1.0,
                price=price_a,
                reason=f"Short spread: {reason}",
                indicators={"hedge_ratio": hedge_ratio, "spread_position": "short"}
            ))
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_b,
                action=SignalAction.BUY,
                size=hedge_ratio,
                price=price_b,
                reason=f"Short spread: {reason}",
                indicators={"hedge_ratio": hedge_ratio, "spread_position": "short"}
            ))

        return signals

    def _close_spread_position(
        self,
        timestamp: datetime,
        ticker_a: str,
        ticker_b: str,
        price_a: float,
        price_b: float,
        position_type: str,
        reason: str
    ) -> List[Signal]:
        """Close a spread position (close both legs)."""
        signals = []

        if position_type == "long_spread":
            # Close long spread: Sell A, Cover B
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_a,
                action=SignalAction.SELL,
                size=1.0,
                price=price_a,
                reason=f"Close long spread: {reason}"
            ))
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_b,
                action=SignalAction.COVER,
                size=1.0,
                price=price_b,
                reason=f"Close long spread: {reason}"
            ))
        elif position_type == "short_spread":
            # Close short spread: Cover A, Sell B
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_a,
                action=SignalAction.COVER,
                size=1.0,
                price=price_a,
                reason=f"Close short spread: {reason}"
            ))
            signals.append(Signal(
                timestamp=timestamp,
                ticker=ticker_b,
                action=SignalAction.SELL,
                size=1.0,
                price=price_b,
                reason=f"Close short spread: {reason}"
            ))

        return signals
