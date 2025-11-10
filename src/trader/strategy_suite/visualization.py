"""
Visualization utilities for strategy backtests.

Generate equity curves, performance heatmaps, and trade distribution plots.
"""

from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from .simulator import Trade
from .metrics import PerformanceMetrics


def plot_equity_curve(
    equity_curve: List[Tuple[datetime, float]],
    title: str = "Equity Curve",
    save_path: Optional[Path] = None,
    show: bool = True
):
    """
    Plot portfolio equity over time.

    Args:
        equity_curve: List of (timestamp, portfolio_value) tuples
        title: Plot title
        save_path: Path to save figure (optional)
        show: Whether to display the plot
    """
    if not equity_curve:
        print("No equity curve data to plot")
        return

    timestamps = [t for t, _ in equity_curve]
    values = [v for _, v in equity_curve]

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(timestamps, values, linewidth=2, color='#2E86AB')
    ax.fill_between(timestamps, values, alpha=0.3, color='#2E86AB')

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Portfolio Value ($)', fontsize=12)
    ax.grid(True, alpha=0.3)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45, ha='right')

    # Add horizontal line at initial value
    initial_value = values[0]
    ax.axhline(y=initial_value, color='gray', linestyle='--', alpha=0.5, label='Initial Capital')

    ax.legend()
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Equity curve saved to {save_path}")

    if show:
        plt.show()
    else:
        plt.close()


def plot_drawdown(
    equity_curve: List[Tuple[datetime, float]],
    title: str = "Drawdown",
    save_path: Optional[Path] = None,
    show: bool = True
):
    """
    Plot drawdown over time.

    Args:
        equity_curve: List of (timestamp, portfolio_value) tuples
        title: Plot title
        save_path: Path to save figure
        show: Whether to display the plot
    """
    if not equity_curve:
        print("No equity curve data to plot")
        return

    timestamps = [t for t, _ in equity_curve]
    values = np.array([v for _, v in equity_curve])

    # Calculate drawdown
    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / running_max * 100

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.fill_between(timestamps, drawdown, 0, where=drawdown < 0,
                     color='red', alpha=0.3, label='Drawdown')
    ax.plot(timestamps, drawdown, color='darkred', linewidth=1)

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Drawdown (%)', fontsize=12)
    ax.grid(True, alpha=0.3)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45, ha='right')

    ax.legend()
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Drawdown plot saved to {save_path}")

    if show:
        plt.show()
    else:
        plt.close()


def plot_returns_distribution(
    trades: List[Trade],
    title: str = "Trade Returns Distribution",
    save_path: Optional[Path] = None,
    show: bool = True
):
    """
    Plot distribution of trade returns.

    Args:
        trades: List of Trade objects
        title: Plot title
        save_path: Path to save figure
        show: Whether to display the plot
    """
    if not trades:
        print("No trades to plot")
        return

    returns = [t.return_pct for t in trades]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Histogram
    ax1.hist(returns, bins=30, color='#2E86AB', alpha=0.7, edgecolor='black')
    ax1.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
    ax1.set_title('Returns Histogram', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Return (%)', fontsize=10)
    ax1.set_ylabel('Frequency', fontsize=10)
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Box plot
    ax2.boxplot(returns, vert=True, patch_artist=True,
                boxprops=dict(facecolor='#2E86AB', alpha=0.7))
    ax2.axhline(y=0, color='red', linestyle='--', linewidth=2)
    ax2.set_title('Returns Box Plot', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Return (%)', fontsize=10)
    ax2.grid(True, alpha=0.3, axis='y')

    fig.suptitle(title, fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Returns distribution saved to {save_path}")

    if show:
        plt.show()
    else:
        plt.close()


def plot_trade_pnl_timeline(
    trades: List[Trade],
    title: str = "Trade P&L Timeline",
    save_path: Optional[Path] = None,
    show: bool = True
):
    """
    Plot P&L of each trade over time.

    Args:
        trades: List of Trade objects
        title: Plot title
        save_path: Path to save figure
        show: Whether to display the plot
    """
    if not trades:
        print("No trades to plot")
        return

    exit_times = [t.exit_time for t in trades]
    pnls = [t.pnl for t in trades]
    colors = ['green' if p > 0 else 'red' for p in pnls]

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.bar(exit_times, pnls, color=colors, alpha=0.6, edgecolor='black', width=0.0003)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=1)

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Trade Exit Time', fontsize=12)
    ax.set_ylabel('P&L ($)', fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45, ha='right')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Trade P&L timeline saved to {save_path}")

    if show:
        plt.show()
    else:
        plt.close()


def create_performance_heatmap(
    trades: List[Trade],
    title: str = "Performance Heatmap (Ticker × Day)",
    save_path: Optional[Path] = None,
    show: bool = True
):
    """
    Create heatmap showing P&L by ticker and day.

    Args:
        trades: List of Trade objects
        title: Plot title
        save_path: Path to save figure
        show: Whether to display the plot
    """
    if not trades:
        print("No trades to plot")
        return

    # Aggregate P&L by ticker and date
    pnl_by_ticker_date = {}

    for trade in trades:
        ticker = trade.ticker
        date = trade.exit_time.date()

        if ticker not in pnl_by_ticker_date:
            pnl_by_ticker_date[ticker] = {}

        if date not in pnl_by_ticker_date[ticker]:
            pnl_by_ticker_date[ticker][date] = 0

        pnl_by_ticker_date[ticker][date] += trade.pnl

    # Get all unique tickers and dates
    tickers = sorted(pnl_by_ticker_date.keys())
    all_dates = sorted(set(
        date for ticker_data in pnl_by_ticker_date.values()
        for date in ticker_data.keys()
    ))

    # Create matrix
    matrix = np.zeros((len(tickers), len(all_dates)))

    for i, ticker in enumerate(tickers):
        for j, date in enumerate(all_dates):
            matrix[i, j] = pnl_by_ticker_date[ticker].get(date, 0)

    # Plot heatmap
    fig, ax = plt.subplots(figsize=(max(12, len(all_dates) * 0.5), max(6, len(tickers) * 0.3)))

    sns.heatmap(
        matrix,
        xticklabels=[d.strftime('%Y-%m-%d') for d in all_dates],
        yticklabels=tickers,
        cmap='RdYlGn',
        center=0,
        annot=True,
        fmt='.0f',
        cbar_kws={'label': 'P&L ($)'},
        ax=ax
    )

    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Ticker', fontsize=12)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Performance heatmap saved to {save_path}")

    if show:
        plt.show()
    else:
        plt.close()


def create_full_report(
    results: Dict[str, Any],
    output_dir: Path,
    strategy_name: str
):
    """
    Create a complete visual report for a backtest run.

    Generates multiple plots and saves them to the output directory.

    Args:
        results: Backtest results dictionary
        output_dir: Directory to save plots
        strategy_name: Name of strategy for file naming
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    equity_curve = results.get("equity_curve", [])
    trades = results.get("trades", [])

    # Equity curve
    plot_equity_curve(
        equity_curve,
        title=f"{strategy_name} - Equity Curve",
        save_path=output_dir / f"{strategy_name}_equity_curve.png",
        show=False
    )

    # Drawdown
    plot_drawdown(
        equity_curve,
        title=f"{strategy_name} - Drawdown",
        save_path=output_dir / f"{strategy_name}_drawdown.png",
        show=False
    )

    # Returns distribution
    if trades:
        plot_returns_distribution(
            trades,
            title=f"{strategy_name} - Returns Distribution",
            save_path=output_dir / f"{strategy_name}_returns_dist.png",
            show=False
        )

        # Trade P&L timeline
        plot_trade_pnl_timeline(
            trades,
            title=f"{strategy_name} - Trade P&L Timeline",
            save_path=output_dir / f"{strategy_name}_pnl_timeline.png",
            show=False
        )

        # Performance heatmap
        create_performance_heatmap(
            trades,
            title=f"{strategy_name} - Performance Heatmap",
            save_path=output_dir / f"{strategy_name}_heatmap.png",
            show=False
        )

    print(f"\nFull report generated in {output_dir}")


def save_metrics_to_csv(
    metrics: PerformanceMetrics,
    strategy_name: str,
    params: Dict[str, Any],
    output_path: Path
):
    """
    Save metrics to a CSV file.

    Args:
        metrics: PerformanceMetrics object
        strategy_name: Name of the strategy
        params: Strategy parameters
        output_path: Path to save CSV
    """
    import csv

    # Prepare row
    row = {
        "Strategy": strategy_name,
        "Parameters": str(params),
        **metrics.to_dict()
    }

    # Check if file exists
    file_exists = output_path.exists()

    with open(output_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    print(f"Metrics appended to {output_path}")


def plot_multi_equity(
    equity_curves: Dict[str, any],
    title: str = "Multi-Strategy Equity Curves",
    output_file: Optional[str] = None,
    show: bool = True
):
    """
    Plot multiple equity curves on the same chart.

    Args:
        equity_curves: Dictionary mapping strategy names to equity Series/lists
        title: Plot title
        output_file: Path to save figure (optional)
        show: Whether to display the plot
    """
    import pandas as pd

    fig, ax = plt.subplots(figsize=(14, 7))

    for name, equity in equity_curves.items():
        if isinstance(equity, pd.Series):
            ax.plot(equity.index, equity.values, label=name, linewidth=2, alpha=0.8)
        elif isinstance(equity, list) and len(equity) > 0 and isinstance(equity[0], tuple):
            # List of (timestamp, value) tuples
            timestamps = [t for t, _ in equity]
            values = [v for _, v in equity]
            ax.plot(timestamps, values, label=name, linewidth=2, alpha=0.8)
        else:
            # Assume it's a list of values
            ax.plot(equity, label=name, linewidth=2, alpha=0.8)

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Equity', fontsize=12)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Saved plot: {output_file}")

    if show:
        plt.show()
    else:
        plt.close()


def plot_corr_heatmap(
    returns_df: any,
    title: str = "Strategy Returns Correlation Heatmap",
    output_file: Optional[str] = None,
    show: bool = True
):
    """
    Plot correlation heatmap of strategy returns.

    Args:
        returns_df: DataFrame with strategy returns as columns
        title: Plot title
        output_file: Path to save figure (optional)
        show: Whether to display the plot
    """
    import pandas as pd

    if not isinstance(returns_df, pd.DataFrame):
        print("Warning: returns_df is not a DataFrame, skipping heatmap")
        return

    # Compute correlation matrix
    corr = returns_df.corr()

    fig, ax = plt.subplots(figsize=(10, 8))

    # Create heatmap
    im = ax.imshow(corr, cmap='RdYlGn', aspect='auto', vmin=-1, vmax=1)

    # Set ticks and labels
    ax.set_xticks(np.arange(len(corr.columns)))
    ax.set_yticks(np.arange(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=45, ha='right')
    ax.set_yticklabels(corr.index)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Correlation', rotation=270, labelpad=20)

    # Add correlation values as text
    for i in range(len(corr.index)):
        for j in range(len(corr.columns)):
            text = ax.text(j, i, f'{corr.iloc[i, j]:.2f}',
                          ha="center", va="center", color="black", fontsize=9)

    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Saved plot: {output_file}")

    if show:
        plt.show()
    else:
        plt.close()


def plot_weight_trajectory(
    weights_df: any,
    title: str = "Portfolio Weights Over Time",
    output_file: Optional[str] = None,
    show: bool = True
):
    """
    Plot time-varying portfolio weights as a stacked area chart.

    Args:
        weights_df: DataFrame with strategies as columns, timestamps as index, weights as values
        title: Plot title
        output_file: Path to save figure (optional)
        show: Whether to display the plot
    """
    import pandas as pd

    if not isinstance(weights_df, pd.DataFrame):
        print("Warning: weights_df is not a DataFrame, skipping weight trajectory")
        return

    fig, ax = plt.subplots(figsize=(14, 7))

    # Create stacked area plot
    ax.stackplot(weights_df.index, *[weights_df[col] for col in weights_df.columns],
                 labels=weights_df.columns, alpha=0.7)

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Weight', fontsize=12)
    ax.set_ylim([0, 1])
    ax.legend(loc='upper left', fontsize=10, bbox_to_anchor=(1.02, 1))
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Saved plot: {output_file}")

    if show:
        plt.show()
    else:
        plt.close()
