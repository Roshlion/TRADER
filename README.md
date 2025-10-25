# TRADER

**AI-powered algorithmic trading platform**

Building intelligent trading strategies using machine learning and quantitative analysis to identify market opportunities.

---

## Overview

TRADER analyzes market data using AI to discover patterns, predict price movements, and develop profitable trading strategies. The platform processes high-frequency market data and applies machine learning models to identify opportunities in real-time.

**Current Focus:**
- Pattern recognition in minute-level stock data
- Strategy backtesting and optimization
- Risk management and position sizing
- Multi-timeframe analysis

**Future Roadmap:**
- Real-time trade execution
- Portfolio optimization algorithms
- Sentiment analysis integration
- Multi-asset strategy expansion

---

## Tech Stack

- **Python 3.11+** - Core development
- **Polars** - High-performance data processing
- **DuckDB** - Fast SQL analytics
- **PyArrow** - Columnar storage

---

## Quick Start

```powershell
# Initialize environment
.\scripts\windows\init.ps1

# Configure settings
copy .env.example .env
```

---

## Project Structure

```
TRADER/
├── src/trader/       # Core trading logic
├── scripts/          # Automation & utilities
├── sql/              # Analytics queries
├── notebooks/        # Research & experiments
└── tests/            # Test suite
```

---

## Data Sources

- **Market Data:** polygon.io
- **Local Testing Source:** S3
