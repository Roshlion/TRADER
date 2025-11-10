"""
Intraday Trading Strategy Suite (Phase 3)

A modular backtesting framework for intraday US equity trading strategies.
Uses DuckDB to query Polygon minute-bar data stored as Parquet on S3.

Architecture:
    Market Data (S3 Parquet via DuckDB)
    → Strategy Signals (rules/ML models)
    → Trade Simulation (execution, slippage, capital)
    → Metrics & Analysis (PnL, Sharpe, Drawdown, etc.)
    → Reports & Visualizations (equity curves, heatmaps, logs)
"""

__version__ = "0.1.0"
