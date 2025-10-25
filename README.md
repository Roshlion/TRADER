# TRADER

**Quantitative trading research platform**

Building data-driven trading strategies using high-performance analytics and machine learning.

---

## Overview

TRADER is a research and development platform for quantitative trading strategies. It processes market data at scale using modern data engineering tools and applies statistical and machine learning techniques to identify trading opportunities.

**Research Focus:**
- High-frequency pattern recognition
- Statistical arbitrage strategies
- Machine learning-based predictions
- Risk-adjusted portfolio optimization

**Technical Capabilities:**
- Minute-level market data processing
- Columnar analytics (Parquet/DuckDB)
- Cloud-native architecture
- Backtesting infrastructure

---

## Tech Stack

- **Python 3.11+** - Core development
- **Polars** - High-performance DataFrames (Rust-based)
- **DuckDB** - In-process SQL analytics engine
- **PyArrow/Parquet** - Columnar storage format
- **AWS S3** - Cloud data lake
- **rclone** - Data transfer & sync

---

## Quick Start

```powershell
# Initialize Python environment
.\scripts\windows\init.ps1

# Configure (non-secret settings only)
copy .env.example .env
# Edit .env with your configuration

# Run sample data pull
.\scripts\windows\sample_pull.ps1
```

---

## Project Structure

```
TRADER/
├── src/trader/         # Core trading logic & utilities
├── scripts/
│   ├── windows/        # PowerShell automation
│   └── python/         # Data processing pipelines
├── sql/                # Analytics queries
├── notebooks/          # Research & experiments
└── tests/              # Test suite
```

---

## Development

**Requirements:**
- Python 3.11+
- PowerShell 5.1+ (Windows)
- AWS CLI configured
- rclone installed

**Setup:**
```powershell
# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import polars, duckdb, pyarrow; print('All dependencies installed')"
```

---

## Data Pipeline

**Sources:**
- Market data: Polygon.io Flat Files API
- Storage: AWS S3 (encrypted, versioned)
- Format: CSV.gz (raw), Parquet (curated)

**Processing:**
- Server-side sync (Polygon → S3 via rclone)
- Parquet conversion for analytics
- Partitioned by date for query optimization

---

## License

To be determined

---

## Disclaimer

This project is for educational and research purposes. Trading involves substantial risk of loss. Past performance does not guarantee future results.
