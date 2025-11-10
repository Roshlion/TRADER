#!/bin/bash
# Small test run on EC2 to validate environment
# Tests 2 strategies on AAPL/MSFT for 1 week
# Expected runtime: ~5 minutes

set -euo pipefail

echo "============================================================"
echo "EC2 Small Validation Test"
echo "============================================================"
echo "Started at: $(date)"
echo "Instance: $(ec2-metadata --instance-id 2>/dev/null | cut -d' ' -f2 || echo 'unknown')"
echo "Instance Type: $(ec2-metadata --instance-type 2>/dev/null | cut -d' ' -f2 || echo 'unknown')"
echo ""

# Change to repo directory
cd ~/Trader || cd /home/ubuntu/Trader || { echo "ERROR: Trader directory not found"; exit 1; }

# Activate virtual environment
source .venv/bin/activate || source ~/.venv/trader/bin/activate || { echo "ERROR: Virtual environment not found"; exit 1; }

# Create logs directory
mkdir -p logs reports/ec2

# Log file
LOG_FILE="logs/ec2_small_$(date +%Y%m%d_%H%M%S).log"

echo "Logging to: $LOG_FILE"
echo ""

# Run optimization
echo "Running small test (2 strategies, 1 week)..."
echo "  Strategies: VWAPReversion, ORB"
echo "  Tickers: AAPL, MSFT"
echo "  Period: 2025-10-01 to 2025-10-07"
echo ""

python -m scripts.python.optimize_portfolio \
  --strategies mean_reversion.VWAPReversion,opening_range.ORB \
  --tickers AAPL,MSFT \
  --start 2025-10-01 --end 2025-10-07 \
  --mode static --objective sharpe \
  --cost-aware on --rebalance-cost-bps 1.0 \
  --regime on --regime-weight 0.25 \
  --slippage 0.0005 --commission 0.001 \
  --max-weight 0.5 --long-only \
  2>&1 | tee "$LOG_FILE"

EXIT_CODE=$?

echo ""
echo "============================================================"
echo "Small Test Complete"
echo "============================================================"
echo "Finished at: $(date)"
echo "Exit code: $EXIT_CODE"
echo "Log: $LOG_FILE"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "[PASS] Test completed successfully"
    echo ""
    echo "Results saved to:"
    ls -lh artifacts/portfolios/latest_weights.json 2>/dev/null || echo "  (weights file not found)"
    ls -lh reports/portfolio/*.png 2>/dev/null | head -3 || echo "  (charts not found)"
    echo ""
    echo "Next step: Run full optimization with:"
    echo "  bash ~/Trader/scripts/aws/run_remote_full.sh"
else
    echo "[FAIL] Test failed with exit code $EXIT_CODE"
    echo "Check log for details: $LOG_FILE"
fi

echo "============================================================"

exit $EXIT_CODE
