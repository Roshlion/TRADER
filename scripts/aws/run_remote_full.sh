#!/bin/bash
# Full annual optimization run on EC2
# All 14 strategies × full year (Oct 2024 - Oct 2025) × 5 tickers
# Expected runtime: 4-6 hours on c6i.2xlarge
# Expected cost: ~$0.64 - $0.96

set -euo pipefail

echo "============================================================"
echo "EC2 FULL ANNUAL OPTIMIZATION"
echo "============================================================"
echo "Started at: $(date)"
echo "Instance: $(ec2-metadata --instance-id 2>/dev/null | cut -d' ' -f2 || echo 'unknown')"
echo "Instance Type: $(ec2-metadata --instance-type 2>/dev/null | cut -d' ' -f2 || echo 'unknown')"
echo ""
echo "WARNING: This is a LONG-RUNNING job (4-6 hours)"
echo "  - All 14 strategies"
echo "  - Full year of data (Oct 2024 - Oct 2025)"
echo "  - 5 tickers: AAPL, MSFT, GOOGL, AMZN, TSLA"
echo "  - Features: Walk-forward, Cost-aware, Regime detection"
echo ""
echo "Estimated cost: \$0.64 - \$0.96"
echo "Auto-shutdown: Will terminate 30min after completion"
echo ""
read -p "Press ENTER to continue or Ctrl+C to cancel..."
echo ""

# Change to repo directory
cd ~/TRADER || cd /home/ubuntu/TRADER || cd ~/Trader || cd /home/ubuntu/Trader || { echo "ERROR: Trader directory not found"; exit 1; }

# Activate virtual environment
source .venv/bin/activate || source ~/.venv/trader/bin/activate || { echo "ERROR: Virtual environment not found"; exit 1; }

# Create logs directory
mkdir -p logs reports/ec2

# Log file
LOG_FILE="logs/ec2_full_$(date +%Y%m%d_%H%M%S).log"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Logging to: $LOG_FILE"
echo "Run ID: $TIMESTAMP"
echo ""

# Save run metadata
cat > logs/run_metadata_${TIMESTAMP}.json <<EOF
{
  "run_id": "$TIMESTAMP",
  "start_time": "$(date -Iseconds)",
  "instance_id": "$(ec2-metadata --instance-id 2>/dev/null | cut -d' ' -f2 || echo 'unknown')",
  "instance_type": "$(ec2-metadata --instance-type 2>/dev/null | cut -d' ' -f2 || echo 'unknown')",
  "strategies": "all",
  "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
  "period": "2024-10-01 to 2025-10-31",
  "features": {
    "walk_forward": true,
    "cost_aware": true,
    "regime_detection": true
  }
}
EOF

echo "============================================================"
echo "Configuration:"
echo "  Strategies: All (14 total)"
echo "  Tickers: AAPL, MSFT, GOOGL, AMZN, TSLA"
echo "  Period: Oct 2024 - Oct 2025 (1 year)"
echo "  Mode: Static Sharpe optimization"
echo "  Walk-Forward: ON (10 day train, 5 day test)"
echo "  Cost-Aware: ON (1.0 bps per % turnover)"
echo "  Regime: ON (25% weight adjustment)"
echo "  Transaction Costs: 0.05% slippage + $0.001/share commission"
echo "============================================================"
echo ""

# Run optimization
echo "Starting optimization..."
echo "Monitor progress with: tail -f $LOG_FILE"
echo ""

python -m scripts.python.optimize_portfolio \
  --strategies mean_reversion.VWAPReversion,opening_range.ORB,volatility_breakout.ATRBreakout,vwap_bands.VWAPBands,bollinger_revert.BollRevert,intraday_seasonality.Seasonality,cross_sectional_momo.CSM,kalman_pairs.KalPairs,kf_trend.KFTrend,momentum.BreakoutMomentum,momentum.VolumeSpike,mean_reversion.BollingerBand,machine_learning.MLClassifier \
  --tickers AAPL,MSFT,GOOGL,AMZN,TSLA \
  --start 2024-10-01 --end 2025-10-31 \
  --mode static --objective sharpe \
  --walkforward on --wf-train-days 10 --wf-test-days 5 \
  --cost-aware on --rebalance-cost-bps 1.0 \
  --regime on --regime-weight 0.25 \
  --slippage 0.0005 --commission 0.001 \
  --max-weight 0.4 --long-only \
  2>&1 | tee "$LOG_FILE"

EXIT_CODE=$?

# Update metadata with completion info
END_TIME=$(date -Iseconds)
cat >> logs/run_metadata_${TIMESTAMP}.json <<EOF_UPDATE

{
  "end_time": "$END_TIME",
  "exit_code": $EXIT_CODE,
  "log_file": "$LOG_FILE"
}
EOF_UPDATE

echo ""
echo "============================================================"
echo "Full Optimization Complete"
echo "============================================================"
echo "Finished at: $(date)"
echo "Exit code: $EXIT_CODE"
echo "Run ID: $TIMESTAMP"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "[PASS] Optimization completed successfully"
    echo ""
    echo "Results:"
    echo "  Weights: artifacts/portfolios/latest_weights.json"
    echo "  WFV Results: artifacts/wfv/"
    echo "  Charts: reports/portfolio/"
    echo "  Log: $LOG_FILE"
    echo ""

    # Show final metrics if available
    if [ -f "artifacts/portfolios/latest_weights.json" ]; then
        echo "Final Portfolio Metrics:"
        python3 -c "import json; d=json.load(open('artifacts/portfolios/latest_weights.json')); print(json.dumps(d.get('metrics',{}), indent=2))" 2>/dev/null || echo "(metrics not found)"
    fi

    echo ""
    echo "Uploading results to S3..."

    # Upload artifacts to S3
    aws s3 sync artifacts/ s3://polygon-trader-data-roshen/trader-results/${TIMESTAMP}/artifacts/ --region us-east-1 || echo "S3 upload failed (continuing)"
    aws s3 sync reports/ s3://polygon-trader-data-roshen/trader-results/${TIMESTAMP}/reports/ --region us-east-1 || echo "S3 upload failed (continuing)"
    aws s3 cp "$LOG_FILE" s3://polygon-trader-data-roshen/trader-results/${TIMESTAMP}/logs/ --region us-east-1 || echo "Log upload failed (continuing)"

    echo ""
    echo "S3 Results Location:"
    echo "  s3://polygon-trader-data-roshen/trader-results/${TIMESTAMP}/"
    echo ""
    echo "Download results with:"
    echo "  aws s3 sync s3://polygon-trader-data-roshen/trader-results/${TIMESTAMP}/ ./results_${TIMESTAMP}/"

else
    echo "[FAIL] Optimization failed with exit code $EXIT_CODE"
    echo ""
    echo "Check log for details: $LOG_FILE"
    echo ""
    echo "Uploading error log to S3..."
    aws s3 cp "$LOG_FILE" s3://polygon-trader-data-roshen/trader-results/errors/${TIMESTAMP}_error.log --region us-east-1 || echo "Log upload failed"
fi

echo ""
echo "============================================================"
echo "Auto-shutdown will occur in 30 minutes if CPU is idle"
echo "To prevent shutdown: sudo systemctl stop auto-shutdown"
echo "To shutdown now: sudo shutdown -h now"
echo "============================================================"

exit $EXIT_CODE
