# EC2 Run #3 - Full Annual Optimization

**Status:** ✅ RUNNING
**Instance:** i-0709a0f087f9476fd (t3.large)
**Started:** 03:41:41 UTC, Nov 11, 2025
**Run ID:** full_20251111_034141
**Process:** PID 10009, background SSH session 4e06bc

---

## Configuration

- **13 strategies:** All available (VWAPReversion, ORB, ATRBreakout, VWAPBands, BollRevert, Seasonality, CSM, KalPairs, KFTrend, BreakoutMomentum, VolumeSpike, BollingerBand, MLClassifier)
- **5 tickers:** AAPL, MSFT, GOOGL, AMZN, TSLA
- **Period:** Oct 1, 2024 - Oct 31, 2025 (13 months, ~268 trading days)
- **Walk-Forward Validation:** 10 day train / 5 day test windows
- **Cost-Aware:** 1.0 bps turnover penalty
- **Regime Detection:** 25% weight adjustment
- **Transaction Costs:** 0.05% slippage + $0.001/share commission
- **Max Weight:** 40% per strategy
- **Long Only:** Yes

---

## Estimated Metrics

- **Runtime:** 8-12 hours (t3.large)
- **Cost:** ~$0.67 - $1.00
- **Results:** s3://polygon-trader-data-roshen/trader-results/full_20251111_034141/
- **Log:** ~/TRADER/logs/ec2_full_20251111_034141.log

---

## Errors Encountered & Fixes Applied

### Bug #1: S3 Path Month Formatting ⚠️
**Error:**
```
IO Error: No files found that match the pattern "s3://.../month=9/day=2025-09-26/*.parquet"
```

**Cause:** Code generated `month=9` but S3 uses zero-padded `month=09`

**Fix:** Updated `backtest.py` lines 132 and 354:
```python
month = f"{date_obj.month:02d}"  # Zero-pad month (09 instead of 9)
```

**Files Modified:** `src/trader/strategy_suite/backtest.py`

---

### Bug #2: Timezone-Aware DateTime Slicing ⚠️
**Error:**
```
TypeError: Cannot compare tz-naive and tz-aware datetime-like objects
```

**Cause:** Walk-forward validation created timezone-naive dates but DataFrame index was timezone-aware

**Fix:** Updated `walk_forward.py` lines 87-89:
```python
# Make timezone-aware to match returns_df index
if self.returns_df.index.tz is not None:
    dates = dates.tz_localize(self.returns_df.index.tz)
```

**Files Modified:** `src/trader/strategy_suite/optimizer/walk_forward.py`

---

### Bug #3: Incorrect End Date ⚠️
**Error:** Script used `--end 2025-10-01` instead of full dataset through Oct 31

**Fix:** Updated `run_remote_full.sh` to use `--end 2025-10-31`

**Files Modified:** `scripts/aws/run_remote_full.sh`

---

### Bug #4: Missing Scripts on EC2 📁
**Error:**
```
No module named scripts.python.optimize_portfolio
```

**Cause:** Scripts directory was never uploaded to EC2 during initial setup

**Fix:** Uploaded entire scripts directory:
```bash
scp -r C:/Users/Roshl/Trader/scripts/ ubuntu@13.220.151.92:~/TRADER/
```

---

### Bug #5: Missing src/ Package on EC2 📁
**Error:**
```
ModuleNotFoundError: No module named 'trader.strategy_suite.backtest'
```

**Cause:** src/trader package was not uploaded to EC2

**Fix:**
1. Uploaded src directory: `scp -r C:/Users/Roshl/Trader/src/ ubuntu@13.220.151.92:~/TRADER/`
2. Set PYTHONPATH in run script: `export PYTHONPATH=/home/ubuntu/TRADER/src:$PYTHONPATH`

---

## Lessons Learned for Future EC2 Runs

### Pre-Flight Checklist ✅
1. **Verify S3 data range** - Check first and last dates exist
2. **Test scripts locally** - Run small validation test first
3. **Upload complete codebase** - Verify all directories (src/, scripts/, configs/)
4. **Set PYTHONPATH** - Ensure Python can find trader package
5. **Use zero-padded months** - S3 partitioning uses `month=09` not `month=9`
6. **Handle timezones** - Ensure datetime objects match DataFrame index timezone
7. **Run validation test on EC2** - 3-5 days, 1-2 tickers, verify S3 upload works
8. **Launch via background SSH** - Use local background SSH session to keep process alive

### EC2 Setup Automation (For Next Time)
```bash
# 1. Launch instance
bash scripts/aws/launch_ec2.sh

# 2. SSH and setup
ssh -i trader-optimizer.pem ubuntu@<IP>

# 3. Upload entire codebase
scp -r C:/Users/Roshl/Trader/src/ ubuntu@<IP>:~/TRADER/
scp -r C:/Users/Roshl/Trader/scripts/ ubuntu@<IP>:~/TRADER/

# 4. Create run script with PYTHONPATH
export PYTHONPATH=/home/ubuntu/TRADER/src:$PYTHONPATH

# 5. Run validation test
bash ~/run_optimization_final.sh

# 6. If test passes, launch full run via background SSH
ssh -i trader-optimizer.pem ubuntu@<IP> 'bash ~/run_optimization_final.sh' &
```

### Common Pitfalls to Avoid
1. **Don't skip validation test** - Always run 3-5 day test first
2. **Don't assume code is uploaded** - Verify with `ls -la`
3. **Don't use nohup alone** - Process may still die; use background SSH session
4. **Don't forget PYTHONPATH** - Set in every run script
5. **Don't use tmux/screen** - Background SSH is simpler and more reliable

---

## Monitoring Commands

```bash
# Check if process is running
ssh -i trader-optimizer.pem ubuntu@13.220.151.92 'ps aux | grep python | grep optimize'

# View log in real-time
ssh -i trader-optimizer.pem ubuntu@13.220.151.92 'tail -f ~/TRADER/logs/ec2_full_20251111_034141.log'

# Check CPU/memory usage
ssh -i trader-optimizer.pem ubuntu@13.220.151.92 'top -b -n 1 | head -20'

# Check progress (look for "Fold X/Y")
ssh -i trader-optimizer.pem ubuntu@13.220.151.92 'grep -i "fold" ~/TRADER/logs/ec2_full_20251111_034141.log | tail -5'
```

---

## Expected Results

When complete, the run will produce:
- **Portfolio Weights:** `artifacts/portfolios/latest_weights.json`
- **Walk-Forward Results:** `artifacts/wfv/` (per-fold metrics)
- **Performance Metrics:** `reports/portfolio/metrics_table.csv`
- **Charts:** `reports/portfolio/*.png` (equity curve, correlation matrix)
- **S3 Upload:** All results automatically synced to S3

---

## Post-Run Actions

1. **Download results:**
   ```bash
   aws s3 sync s3://polygon-trader-data-roshen/trader-results/full_20251111_034141/ ./results_run3/
   ```

2. **Commit to GitHub:**
   ```bash
   cd C:/Users/Roshl/Trader
   git add results/
   git commit -m "feat: add Run #3 optimization results"
   git push
   ```

3. **Terminate instance:**
   ```bash
   aws ec2 terminate-instances --region us-east-1 --instance-ids i-0709a0f087f9476fd
   ```

4. **Update website** with final results and metrics
