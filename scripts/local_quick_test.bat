@echo off
REM Local quick test for optimizer validation
REM Tests 3 strategies on AAPL/MSFT for 1 week with all enhancements enabled

echo ============================================================
echo Local Quick Test - Optimizer Validation
echo ============================================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Run optimization with all features enabled
python -m scripts.python.optimize_portfolio ^
  --strategies mean_reversion.VWAPReversion,opening_range.ORB,stat_arb.PairsTrading ^
  --tickers AAPL,MSFT ^
  --start 2025-10-01 --end 2025-10-07 ^
  --mode static --objective sharpe ^
  --walkforward on --wf-train-days 3 --wf-test-days 2 ^
  --cost-aware on --rebalance-cost-bps 1.0 ^
  --regime on --regime-weight 0.25 ^
  --slippage 0.0005 --commission 0.001 ^
  --max-weight 0.5 --long-only

echo.
echo ============================================================
echo Quick Test Complete
echo ============================================================
