"""
Trade execution simulator with realistic modeling of slippage, latency,
capital constraints, and risk management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import polars as pl
import numpy as np
from .strategies.base import Signal, SignalAction


@dataclass
class Position:
    """
    Represents an open position.

    Attributes:
        ticker: Stock ticker
        shares: Number of shares (positive for long, negative for short)
        entry_price: Average entry price
        entry_time: Time position was opened
        stop_loss: Optional stop-loss price
        take_profit: Optional take-profit price
    """
    ticker: str
    shares: float
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @property
    def is_long(self) -> bool:
        return self.shares > 0

    @property
    def is_short(self) -> bool:
        return self.shares < 0

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.is_long:
            return self.shares * (current_price - self.entry_price)
        else:
            return -self.shares * (self.entry_price - current_price)

    def value(self, current_price: float) -> float:
        """Calculate position value (market value)."""
        return abs(self.shares) * current_price


@dataclass
class Trade:
    """
    Represents a completed trade.

    Attributes:
        ticker: Stock ticker
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        shares: Number of shares traded
        pnl: Realized profit/loss
        return_pct: Return percentage
        side: 'long' or 'short'
        entry_reason: Why trade was entered
        exit_reason: Why trade was exited
    """
    ticker: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    return_pct: float
    side: str
    entry_reason: Optional[str] = None
    exit_reason: Optional[str] = None


@dataclass
class SimulatorConfig:
    """
    Configuration for the trade simulator.

    Attributes:
        initial_capital: Starting capital in dollars
        slippage_rate: Slippage as fraction of price (e.g., 0.0005 = 0.05%)
        commission_per_share: Commission per share (e.g., 0.0 for zero-commission)
        position_size: Default position size as fraction of capital (e.g., 0.1 = 10%)
        max_positions: Maximum number of concurrent positions
        stop_loss_pct: Default stop-loss percentage (e.g., 0.01 = 1%)
        take_profit_pct: Default take-profit percentage (e.g., 0.02 = 2%)
        execution_delay_bars: Number of bars delay for execution (default 1)
        allow_shorts: Whether to allow short selling
    """
    initial_capital: float = 100000.0
    slippage_rate: float = 0.0005
    commission_per_share: float = 0.0
    position_size: float = 0.1
    max_positions: int = 10
    stop_loss_pct: Optional[float] = 0.01
    take_profit_pct: Optional[float] = 0.02
    execution_delay_bars: int = 1
    allow_shorts: bool = True


class Simulator:
    """
    Simulates trade execution on historical data.

    Takes signals and market data, simulates realistic execution with slippage,
    tracks positions, applies risk management, and produces trade logs and
    equity curve.
    """

    def __init__(self, config: SimulatorConfig = None):
        """
        Initialize simulator.

        Args:
            config: Simulator configuration
        """
        self.config = config or SimulatorConfig()
        self.reset()

    def reset(self):
        """Reset simulator state."""
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.current_time: Optional[datetime] = None

    def run(
        self,
        signals: List[Signal],
        market_data: pl.DataFrame
    ) -> Tuple[List[Trade], List[Tuple[datetime, float]]]:
        """
        Run simulation on signals and market data.

        Args:
            signals: List of trading signals in chronological order
            market_data: DataFrame with columns: timestamp, ticker, open, high, low, close, volume

        Returns:
            Tuple of (trades, equity_curve)
            - trades: List of completed Trade objects
            - equity_curve: List of (timestamp, portfolio_value) tuples
        """
        self.reset()

        # Sort signals by timestamp
        signals_sorted = sorted(signals, key=lambda s: s.timestamp)

        # Create price lookup for efficient access
        # Group by ticker for easier lookup
        ticker_data = {}
        for ticker in market_data["ticker"].unique():
            ticker_df = market_data.filter(pl.col("ticker") == ticker).sort("timestamp")
            ticker_data[ticker] = ticker_df

        signal_idx = 0
        all_timestamps = sorted(market_data["timestamp"].unique())

        for timestamp in all_timestamps:
            self.current_time = timestamp

            # Check for stop-loss and take-profit on open positions
            self._check_risk_management(timestamp, ticker_data)

            # Process signals at this timestamp
            while signal_idx < len(signals_sorted) and signals_sorted[signal_idx].timestamp <= timestamp:
                signal = signals_sorted[signal_idx]
                self._process_signal(signal, ticker_data)
                signal_idx += 1

            # Mark-to-market and record equity
            portfolio_value = self._calculate_portfolio_value(timestamp, ticker_data)
            self.equity_curve.append((timestamp, portfolio_value))

        # Close all remaining positions at end
        self._close_all_positions(all_timestamps[-1], ticker_data, "end_of_period")

        return self.trades, self.equity_curve

    def _process_signal(self, signal: Signal, ticker_data: Dict[str, pl.DataFrame]):
        """Process a single signal."""
        ticker = signal.ticker

        # Get execution price (next bar open, with slippage and latency)
        execution_price = self._get_execution_price(signal, ticker_data)
        if execution_price is None:
            return  # Cannot execute (no data available)

        if signal.action == SignalAction.BUY:
            self._execute_buy(signal, execution_price)
        elif signal.action == SignalAction.SELL:
            self._execute_sell(signal, execution_price)
        elif signal.action == SignalAction.SHORT:
            if self.config.allow_shorts:
                self._execute_short(signal, execution_price)
        elif signal.action == SignalAction.COVER:
            self._execute_cover(signal, execution_price)

    def _get_execution_price(
        self,
        signal: Signal,
        ticker_data: Dict[str, pl.DataFrame]
    ) -> Optional[float]:
        """
        Get execution price with latency and slippage.

        Execution happens at the next bar's open (after delay), with slippage applied.
        """
        ticker = signal.ticker
        if ticker not in ticker_data:
            return None

        df = ticker_data[ticker]

        # Find the bar at signal time
        signal_bars = df.filter(pl.col("timestamp") >= signal.timestamp)
        if len(signal_bars) < self.config.execution_delay_bars + 1:
            return None  # Not enough data for execution

        # Execute at the next bar's open (with delay)
        execution_bar = signal_bars[self.config.execution_delay_bars]
        base_price = execution_bar["open"][0]

        # Apply slippage (assuming market order)
        if signal.action in [SignalAction.BUY, SignalAction.COVER]:
            # Buy: slippage increases price
            execution_price = base_price * (1 + self.config.slippage_rate)
        else:
            # Sell/Short: slippage decreases price
            execution_price = base_price * (1 - self.config.slippage_rate)

        return float(execution_price)

    def _execute_buy(self, signal: Signal, execution_price: float):
        """Execute a buy order (open long position or close short)."""
        ticker = signal.ticker

        # If short position exists, close it first
        if ticker in self.positions and self.positions[ticker].is_short:
            self._close_position(ticker, execution_price, "covered_by_buy")
            return

        # Check if we can open a new position
        if len(self.positions) >= self.config.max_positions:
            return  # Max positions reached

        # Calculate position size
        position_value = self.cash * self.config.position_size
        shares = position_value / execution_price
        cost = shares * execution_price + shares * self.config.commission_per_share

        if cost > self.cash:
            shares = self.cash / (execution_price + self.config.commission_per_share)
            cost = shares * execution_price + shares * self.config.commission_per_share

        if shares <= 0:
            return  # Not enough cash

        # Open position
        self.cash -= cost

        # Calculate stop-loss and take-profit
        stop_loss = None
        take_profit = None
        if self.config.stop_loss_pct:
            stop_loss = execution_price * (1 - self.config.stop_loss_pct)
        if self.config.take_profit_pct:
            take_profit = execution_price * (1 + self.config.take_profit_pct)

        self.positions[ticker] = Position(
            ticker=ticker,
            shares=shares,
            entry_price=execution_price,
            entry_time=self.current_time,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def _execute_sell(self, signal: Signal, execution_price: float):
        """Execute a sell order (close long position)."""
        ticker = signal.ticker
        if ticker in self.positions and self.positions[ticker].is_long:
            self._close_position(ticker, execution_price, signal.reason or "signal")

    def _execute_short(self, signal: Signal, execution_price: float):
        """Execute a short order."""
        ticker = signal.ticker

        # If long position exists, close it first
        if ticker in self.positions and self.positions[ticker].is_long:
            self._close_position(ticker, execution_price, "sold_before_short")
            return

        # Check if we can open a new position
        if len(self.positions) >= self.config.max_positions:
            return

        # Calculate position size (negative shares for short)
        position_value = self.cash * self.config.position_size
        shares = -(position_value / execution_price)  # Negative for short

        # For shorts, we receive cash
        proceeds = abs(shares) * execution_price - abs(shares) * self.config.commission_per_share
        self.cash += proceeds

        # Calculate stop-loss and take-profit for short
        stop_loss = None
        take_profit = None
        if self.config.stop_loss_pct:
            stop_loss = execution_price * (1 + self.config.stop_loss_pct)  # Above entry for shorts
        if self.config.take_profit_pct:
            take_profit = execution_price * (1 - self.config.take_profit_pct)  # Below entry for shorts

        self.positions[ticker] = Position(
            ticker=ticker,
            shares=shares,
            entry_price=execution_price,
            entry_time=self.current_time,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def _execute_cover(self, signal: Signal, execution_price: float):
        """Execute a cover order (close short position)."""
        ticker = signal.ticker
        if ticker in self.positions and self.positions[ticker].is_short:
            self._close_position(ticker, execution_price, signal.reason or "signal")

    def _close_position(self, ticker: str, exit_price: float, reason: str):
        """Close a position and record the trade."""
        if ticker not in self.positions:
            return

        position = self.positions[ticker]
        shares = abs(position.shares)

        # Calculate P&L
        pnl = position.unrealized_pnl(exit_price)

        # Apply commission
        commission = shares * self.config.commission_per_share
        pnl -= commission

        # For longs, we receive cash; for shorts, we pay cash
        if position.is_long:
            proceeds = shares * exit_price - commission
            self.cash += proceeds
        else:
            cost = shares * exit_price + commission
            self.cash -= cost

        # Calculate return percentage
        return_pct = pnl / (shares * position.entry_price) * 100

        # Record trade
        trade = Trade(
            ticker=ticker,
            entry_time=position.entry_time,
            exit_time=self.current_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            shares=shares,
            pnl=pnl,
            return_pct=return_pct,
            side="long" if position.is_long else "short",
            exit_reason=reason
        )
        self.trades.append(trade)

        # Remove position
        del self.positions[ticker]

    def _check_risk_management(self, timestamp: datetime, ticker_data: Dict[str, pl.DataFrame]):
        """Check stop-loss and take-profit for all positions."""
        to_close = []

        for ticker, position in self.positions.items():
            if ticker not in ticker_data:
                continue

            # Get current bar
            df = ticker_data[ticker]
            current_bars = df.filter(pl.col("timestamp") == timestamp)
            if len(current_bars) == 0:
                continue

            bar = current_bars[0]
            low = float(bar["low"][0])
            high = float(bar["high"][0])

            # Check stop-loss
            if position.stop_loss is not None:
                if position.is_long and low <= position.stop_loss:
                    to_close.append((ticker, position.stop_loss, "stop_loss"))
                elif position.is_short and high >= position.stop_loss:
                    to_close.append((ticker, position.stop_loss, "stop_loss"))

            # Check take-profit
            if position.take_profit is not None:
                if position.is_long and high >= position.take_profit:
                    to_close.append((ticker, position.take_profit, "take_profit"))
                elif position.is_short and low <= position.take_profit:
                    to_close.append((ticker, position.take_profit, "take_profit"))

        # Close positions that hit stops/targets
        for ticker, price, reason in to_close:
            self._close_position(ticker, price, reason)

    def _close_all_positions(
        self,
        timestamp: datetime,
        ticker_data: Dict[str, pl.DataFrame],
        reason: str
    ):
        """Close all open positions."""
        tickers = list(self.positions.keys())
        for ticker in tickers:
            if ticker not in ticker_data:
                continue

            df = ticker_data[ticker]
            last_bars = df.filter(pl.col("timestamp") == timestamp)
            if len(last_bars) > 0:
                close_price = float(last_bars[0]["close"][0])
                self._close_position(ticker, close_price, reason)

    def _calculate_portfolio_value(
        self,
        timestamp: datetime,
        ticker_data: Dict[str, pl.DataFrame]
    ) -> float:
        """Calculate total portfolio value (cash + positions)."""
        total_value = self.cash

        for ticker, position in self.positions.items():
            if ticker not in ticker_data:
                continue

            df = ticker_data[ticker]
            current_bars = df.filter(pl.col("timestamp") == timestamp)
            if len(current_bars) > 0:
                current_price = float(current_bars[0]["close"][0])
                total_value += position.unrealized_pnl(current_price)

        return total_value

    def get_summary(self) -> Dict[str, any]:
        """Get summary statistics of the simulation."""
        if not self.equity_curve:
            return {}

        initial_equity = self.config.initial_capital
        final_equity = self.equity_curve[-1][1]
        total_return = (final_equity - initial_equity) / initial_equity * 100

        return {
            "initial_capital": initial_equity,
            "final_equity": final_equity,
            "total_return_pct": total_return,
            "total_pnl": final_equity - initial_equity,
            "num_trades": len(self.trades),
            "num_winners": sum(1 for t in self.trades if t.pnl > 0),
            "num_losers": sum(1 for t in self.trades if t.pnl < 0),
        }
