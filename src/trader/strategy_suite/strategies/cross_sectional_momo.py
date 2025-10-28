"""
Cross-Sectional Momentum (CSM) strategy.

Ranks tickers by recent performance and trades long top performers, short bottom performers.
"""

from typing import List, Dict, Any
import polars as pl
from .base import (
    BaseStrategy, Signal, SignalAction,
    validate_data
)


class CSM(BaseStrategy):
    """
    Cross-Sectional Momentum strategy.

    Ranks tickers by their recent performance (returns over lookback period),
    enters long positions in top decile, short positions in bottom decile.
    Market-neutral basket approach.

    Parameters:
        lookback: Minutes to look back for performance calculation (default: 60)
        rebalance_minutes: How often to rebalance the portfolio (default: 30)
        basket_n: Number of tickers in each basket (long/short) (default: 5)
        min_tickers: Minimum number of tickers required (default: 10)
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "lookback": 60,
            "rebalance_minutes": 30,
            "basket_n": 5,
            "min_tickers": 10,
        }
        if params:
            default_params.update(params)
        super().__init__("CSM", default_params)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate cross-sectional momentum signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        lookback = self.params["lookback"]
        rebalance_freq = self.params["rebalance_minutes"]
        basket_n = self.params["basket_n"]
        min_tickers = self.params["min_tickers"]

        # Get unique timestamps
        timestamps = sorted(data["timestamp"].unique())

        if len(timestamps) < lookback:
            return []

        signals = []
        current_longs = set()
        current_shorts = set()
        last_rebalance_idx = 0

        # Iterate through timestamps
        for idx, timestamp in enumerate(timestamps):
            # Only rebalance at specified frequency
            if idx - last_rebalance_idx < rebalance_freq:
                continue

            # Get current data point
            current_data = data.filter(pl.col("timestamp") == timestamp)

            # Get lookback data
            lookback_start_idx = max(0, idx - lookback)
            if lookback_start_idx >= len(timestamps):
                continue

            lookback_start_time = timestamps[lookback_start_idx]
            lookback_data = data.filter(
                (pl.col("timestamp") >= lookback_start_time) &
                (pl.col("timestamp") <= timestamp)
            )

            # Calculate returns for each ticker over lookback period
            ticker_returns = []

            for ticker in current_data["ticker"].unique():
                ticker_lookback = lookback_data.filter(pl.col("ticker") == ticker).sort("timestamp")

                if len(ticker_lookback) < 2:
                    continue

                first_close = ticker_lookback["close"].head(1)[0]
                last_close = ticker_lookback["close"].tail(1)[0]

                if first_close and first_close > 0:
                    return_pct = (last_close - first_close) / first_close * 100
                    ticker_returns.append({
                        "ticker": ticker,
                        "return": return_pct,
                        "close": last_close
                    })

            # Need minimum number of tickers
            if len(ticker_returns) < min_tickers:
                continue

            # Sort by returns
            ticker_returns.sort(key=lambda x: x["return"], reverse=True)

            # Select top and bottom baskets
            n_per_basket = min(basket_n, len(ticker_returns) // 2)
            top_tickers = {item["ticker"] for item in ticker_returns[:n_per_basket]}
            bottom_tickers = {item["ticker"] for item in ticker_returns[-n_per_basket:]}

            # Close positions no longer in baskets
            for ticker in current_longs - top_tickers:
                ticker_data = current_data.filter(pl.col("ticker") == ticker)
                if len(ticker_data) > 0:
                    row = ticker_data.row(0, named=True)
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SELL,
                        size=1.0,
                        price=row["close"],
                        reason="Dropped from top basket"
                    ))

            for ticker in current_shorts - bottom_tickers:
                ticker_data = current_data.filter(pl.col("ticker") == ticker)
                if len(ticker_data) > 0:
                    row = ticker_data.row(0, named=True)
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.COVER,
                        size=1.0,
                        price=row["close"],
                        reason="Dropped from bottom basket"
                    ))

            # Open new long positions
            for ticker in top_tickers - current_longs:
                ticker_data = current_data.filter(pl.col("ticker") == ticker)
                if len(ticker_data) > 0:
                    row = ticker_data.row(0, named=True)
                    ticker_return = next((item["return"] for item in ticker_returns if item["ticker"] == ticker), None)

                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0 / n_per_basket,  # Equal weight within basket
                        price=row["close"],
                        confidence=0.7,
                        reason=f"Top momentum basket (return: {ticker_return:.2f}%)",
                        indicators={
                            "lookback_return": ticker_return,
                            "basket_position": list(top_tickers).index(ticker) + 1,
                            "basket_size": n_per_basket
                        }
                    ))

            # Open new short positions
            for ticker in bottom_tickers - current_shorts:
                ticker_data = current_data.filter(pl.col("ticker") == ticker)
                if len(ticker_data) > 0:
                    row = ticker_data.row(0, named=True)
                    ticker_return = next((item["return"] for item in ticker_returns if item["ticker"] == ticker), None)

                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0 / n_per_basket,  # Equal weight within basket
                        price=row["close"],
                        confidence=0.7,
                        reason=f"Bottom momentum basket (return: {ticker_return:.2f}%)",
                        indicators={
                            "lookback_return": ticker_return,
                            "basket_position": list(bottom_tickers).index(ticker) + 1,
                            "basket_size": n_per_basket
                        }
                    ))

            # Update current positions
            current_longs = top_tickers
            current_shorts = bottom_tickers
            last_rebalance_idx = idx

        return signals
