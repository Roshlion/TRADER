"""
Performance metrics calculation for trading strategies.

Computes risk-adjusted returns, drawdowns, win rates, and other
key performance indicators.
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import numpy as np
from datetime import datetime
from .simulator import Trade


@dataclass
class PerformanceMetrics:
    """
    Complete performance metrics for a trading strategy.

    Attributes:
        total_return_pct: Total return as percentage
        total_pnl: Total profit/loss in dollars
        cagr: Compound Annual Growth Rate (annualized)
        sharpe_ratio: Risk-adjusted return (Sharpe ratio)
        sortino_ratio: Downside risk-adjusted return
        max_drawdown_pct: Maximum drawdown as percentage
        max_drawdown_duration_days: Longest drawdown period in days
        calmar_ratio: CAGR / Max Drawdown
        win_rate: Percentage of winning trades
        profit_factor: Gross profit / Gross loss
        avg_win: Average winning trade P&L
        avg_loss: Average losing trade P&L
        avg_win_loss_ratio: Average win / Average loss
        total_trades: Number of completed trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        largest_win: Largest winning trade P&L
        largest_loss: Largest losing trade P&L
        avg_trade_duration_mins: Average trade duration in minutes
        exposure_pct: Average capital exposure percentage
        daily_volatility: Daily return volatility
        initial_capital: Starting capital
        final_equity: Ending equity
    """
    total_return_pct: float
    total_pnl: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_win_loss_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    largest_win: float
    largest_loss: float
    avg_trade_duration_mins: float
    exposure_pct: float
    daily_volatility: float
    initial_capital: float
    final_equity: float

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary."""
        return {
            "Total Return (%)": f"{self.total_return_pct:.2f}",
            "Total P&L ($)": f"{self.total_pnl:,.2f}",
            "CAGR (%)": f"{self.cagr:.2f}",
            "Sharpe Ratio": f"{self.sharpe_ratio:.3f}",
            "Sortino Ratio": f"{self.sortino_ratio:.3f}",
            "Max Drawdown (%)": f"{self.max_drawdown_pct:.2f}",
            "Max DD Duration (days)": f"{self.max_drawdown_duration_days:.1f}",
            "Calmar Ratio": f"{self.calmar_ratio:.3f}",
            "Win Rate (%)": f"{self.win_rate:.2f}",
            "Profit Factor": f"{self.profit_factor:.3f}",
            "Avg Win ($)": f"{self.avg_win:,.2f}",
            "Avg Loss ($)": f"{self.avg_loss:,.2f}",
            "Avg Win/Loss Ratio": f"{self.avg_win_loss_ratio:.3f}",
            "Total Trades": self.total_trades,
            "Winning Trades": self.winning_trades,
            "Losing Trades": self.losing_trades,
            "Largest Win ($)": f"{self.largest_win:,.2f}",
            "Largest Loss ($)": f"{self.largest_loss:,.2f}",
            "Avg Trade Duration (mins)": f"{self.avg_trade_duration_mins:.1f}",
            "Exposure (%)": f"{self.exposure_pct:.2f}",
            "Daily Volatility (%)": f"{self.daily_volatility:.2f}",
            "Initial Capital ($)": f"{self.initial_capital:,.2f}",
            "Final Equity ($)": f"{self.final_equity:,.2f}",
        }


def calculate_metrics(
    equity_curve: List[Tuple[datetime, float]],
    trades: List[Trade],
    initial_capital: float,
    risk_free_rate: float = 0.0
) -> PerformanceMetrics:
    """
    Calculate comprehensive performance metrics.

    Args:
        equity_curve: List of (timestamp, portfolio_value) tuples
        trades: List of completed Trade objects
        initial_capital: Starting capital
        risk_free_rate: Annual risk-free rate (default 0.0)

    Returns:
        PerformanceMetrics object with all calculated metrics
    """
    if not equity_curve or not trades:
        # Return zeros if no data
        return PerformanceMetrics(
            total_return_pct=0, total_pnl=0, cagr=0, sharpe_ratio=0,
            sortino_ratio=0, max_drawdown_pct=0, max_drawdown_duration_days=0,
            calmar_ratio=0, win_rate=0, profit_factor=0, avg_win=0, avg_loss=0,
            avg_win_loss_ratio=0, total_trades=0, winning_trades=0, losing_trades=0,
            largest_win=0, largest_loss=0, avg_trade_duration_mins=0,
            exposure_pct=0, daily_volatility=0, initial_capital=initial_capital,
            final_equity=initial_capital
        )

    # Extract equity values and timestamps
    timestamps = np.array([t for t, _ in equity_curve])
    equity_values = np.array([v for _, v in equity_curve])
    final_equity = equity_values[-1]

    # Total return and P&L
    total_pnl = final_equity - initial_capital
    total_return_pct = (total_pnl / initial_capital) * 100

    # Calculate returns
    returns = np.diff(equity_values) / equity_values[:-1]

    # Time-based metrics
    start_date = timestamps[0]
    end_date = timestamps[-1]
    days = (end_date - start_date).total_seconds() / (24 * 3600)
    years = days / 365.25

    # CAGR
    if years > 0:
        cagr = (np.power(final_equity / initial_capital, 1 / years) - 1) * 100
    else:
        cagr = 0

    # Volatility (annualized)
    if len(returns) > 1:
        # Assume intraday data, annualize appropriately
        # For minute data over trading days, use sqrt(252 * 390 trading minutes)
        periods_per_year = 252 * 390  # Trading days * minutes per day
        daily_volatility = np.std(returns) * np.sqrt(periods_per_year) * 100
    else:
        daily_volatility = 0

    # Sharpe Ratio (annualized)
    if daily_volatility > 0 and len(returns) > 0:
        mean_return = np.mean(returns)
        sharpe_ratio = (mean_return * periods_per_year - risk_free_rate) / (np.std(returns) * np.sqrt(periods_per_year))
    else:
        sharpe_ratio = 0

    # Sortino Ratio (downside deviation)
    downside_returns = returns[returns < 0]
    if len(downside_returns) > 1:
        downside_std = np.std(downside_returns) * np.sqrt(periods_per_year)
        if downside_std > 0:
            sortino_ratio = (np.mean(returns) * periods_per_year - risk_free_rate) / downside_std
        else:
            sortino_ratio = 0
    else:
        sortino_ratio = 0

    # Max Drawdown
    max_dd_pct, max_dd_duration = calculate_max_drawdown(equity_curve)

    # Calmar Ratio
    if max_dd_pct != 0:
        calmar_ratio = cagr / abs(max_dd_pct)
    else:
        calmar_ratio = 0

    # Trade statistics
    winning_trades = [t for t in trades if t.pnl > 0]
    losing_trades = [t for t in trades if t.pnl < 0]
    total_trades = len(trades)
    num_winners = len(winning_trades)
    num_losers = len(losing_trades)

    # Win rate
    win_rate = (num_winners / total_trades * 100) if total_trades > 0 else 0

    # Profit factor
    gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0
    gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

    # Average win/loss
    avg_win = (gross_profit / num_winners) if num_winners > 0 else 0
    avg_loss = (gross_loss / num_losers) if num_losers > 0 else 0
    avg_win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0

    # Largest win/loss
    largest_win = max((t.pnl for t in trades), default=0)
    largest_loss = min((t.pnl for t in trades), default=0)

    # Average trade duration
    if trades:
        durations = [(t.exit_time - t.entry_time).total_seconds() / 60 for t in trades]
        avg_trade_duration_mins = np.mean(durations)
    else:
        avg_trade_duration_mins = 0

    # Exposure (simplified - could be more sophisticated)
    # Rough estimate: assume full position size when trades are open
    if trades:
        total_trade_time = sum((t.exit_time - t.entry_time).total_seconds() for t in trades)
        total_time = (end_date - start_date).total_seconds()
        exposure_pct = (total_trade_time / total_time * 100) if total_time > 0 else 0
    else:
        exposure_pct = 0

    return PerformanceMetrics(
        total_return_pct=total_return_pct,
        total_pnl=total_pnl,
        cagr=cagr,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_duration_days=max_dd_duration,
        calmar_ratio=calmar_ratio,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_win_loss_ratio=avg_win_loss_ratio,
        total_trades=total_trades,
        winning_trades=num_winners,
        losing_trades=num_losers,
        largest_win=largest_win,
        largest_loss=largest_loss,
        avg_trade_duration_mins=avg_trade_duration_mins,
        exposure_pct=exposure_pct,
        daily_volatility=daily_volatility,
        initial_capital=initial_capital,
        final_equity=final_equity
    )


def calculate_max_drawdown(
    equity_curve: List[Tuple[datetime, float]]
) -> Tuple[float, float]:
    """
    Calculate maximum drawdown and its duration.

    Args:
        equity_curve: List of (timestamp, portfolio_value) tuples

    Returns:
        Tuple of (max_drawdown_pct, max_drawdown_duration_days)
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0

    equity_values = np.array([v for _, v in equity_curve])
    timestamps = np.array([t for t, _ in equity_curve])

    # Calculate running maximum
    running_max = np.maximum.accumulate(equity_values)

    # Calculate drawdown at each point
    drawdowns = (equity_values - running_max) / running_max * 100

    # Maximum drawdown
    max_dd_pct = np.min(drawdowns)

    # Calculate drawdown duration
    max_dd_duration_days = 0.0
    current_dd_start = None

    for i, dd in enumerate(drawdowns):
        if dd < 0:
            if current_dd_start is None:
                current_dd_start = timestamps[i]
        else:
            if current_dd_start is not None:
                duration = (timestamps[i] - current_dd_start).total_seconds() / (24 * 3600)
                max_dd_duration_days = max(max_dd_duration_days, duration)
                current_dd_start = None

    # Check if we're still in a drawdown at the end
    if current_dd_start is not None:
        duration = (timestamps[-1] - current_dd_start).total_seconds() / (24 * 3600)
        max_dd_duration_days = max(max_dd_duration_days, duration)

    return max_dd_pct, max_dd_duration_days


def calculate_returns_series(equity_curve: List[Tuple[datetime, float]]) -> np.ndarray:
    """
    Calculate period-over-period returns from equity curve.

    Args:
        equity_curve: List of (timestamp, portfolio_value) tuples

    Returns:
        NumPy array of returns
    """
    equity_values = np.array([v for _, v in equity_curve])
    returns = np.diff(equity_values) / equity_values[:-1]
    return returns


def print_metrics_summary(metrics: PerformanceMetrics):
    """
    Print a formatted summary of performance metrics.

    Args:
        metrics: PerformanceMetrics object
    """
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"\nReturns:")
    print(f"  Total Return:        {metrics.total_return_pct:>10.2f}%")
    print(f"  Total P&L:          ${metrics.total_pnl:>10,.2f}")
    print(f"  CAGR:                {metrics.cagr:>10.2f}%")
    print(f"\nRisk Metrics:")
    print(f"  Sharpe Ratio:        {metrics.sharpe_ratio:>10.3f}")
    print(f"  Sortino Ratio:       {metrics.sortino_ratio:>10.3f}")
    print(f"  Max Drawdown:        {metrics.max_drawdown_pct:>10.2f}%")
    print(f"  Max DD Duration:     {metrics.max_drawdown_duration_days:>10.1f} days")
    print(f"  Calmar Ratio:        {metrics.calmar_ratio:>10.3f}")
    print(f"  Daily Volatility:    {metrics.daily_volatility:>10.2f}%")
    print(f"\nTrade Statistics:")
    print(f"  Total Trades:        {metrics.total_trades:>10}")
    print(f"  Winning Trades:      {metrics.winning_trades:>10} ({metrics.win_rate:.1f}%)")
    print(f"  Losing Trades:       {metrics.losing_trades:>10}")
    print(f"  Profit Factor:       {metrics.profit_factor:>10.3f}")
    print(f"  Avg Win:            ${metrics.avg_win:>10,.2f}")
    print(f"  Avg Loss:           ${metrics.avg_loss:>10,.2f}")
    print(f"  Win/Loss Ratio:      {metrics.avg_win_loss_ratio:>10.3f}")
    print(f"  Largest Win:        ${metrics.largest_win:>10,.2f}")
    print(f"  Largest Loss:       ${metrics.largest_loss:>10,.2f}")
    print(f"\nOther:")
    print(f"  Avg Trade Duration:  {metrics.avg_trade_duration_mins:>10.1f} mins")
    print(f"  Exposure:            {metrics.exposure_pct:>10.2f}%")
    print(f"  Initial Capital:    ${metrics.initial_capital:>10,.2f}")
    print(f"  Final Equity:       ${metrics.final_equity:>10,.2f}")
    print("=" * 60 + "\n")
