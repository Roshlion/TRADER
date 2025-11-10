# EC2 Execution Tracker

**Purpose:** This document tracks EC2 optimizer runs managed by Claude.
**Last Updated:** 2025-11-05

---

## Current Status

**Active Runs:** 1 (Run #1 RUNNING - started 07:48 UTC)
**Completed Runs:** 0
**Failed Runs:** 0

---

## Script Status & Issues

### ✅ Working Scripts
- `scripts/aws/launch_ec2.sh` - **FIXED** - Updated with trader-optimizer credentials + TagSpecifications fix
- `scripts/aws/setup_instance.sh` - Ready (existing, has logging)
- `scripts/aws/run_remote_small.sh` - Ready (comprehensive logging)
- `scripts/aws/run_remote_full.sh` - Ready (extensive logging + S3 upload)
- `scripts/aws/auto_shutdown.sh` - Ready (existing)

### ❌ Broken Scripts
- `scripts/aws/launch_spot.bat` - **DO NOT USE** - Windows batch syntax issues, didn't execute properly

### 📝 Decision Log
**2025-11-05 09:15 UTC:**
- Attempted to use launch_spot.bat → Failed (batch script syntax problems)
- Discovered existing launch_ec2.sh → Fixed configuration
- Using launch_ec2.sh for all launches going forward
- All remote scripts (run_remote_*.sh) have proper logging built in

**2025-11-05 09:25 UTC:**
- Fixed TagSpecifications error in launch_ec2.sh
- Issue: TagSpecifications not allowed in LaunchSpecification for spot instances
- Solution: Moved to aws ec2 create-tags command after instance launch
- Reason: AWS API difference between request-spot-instances and run-instances

**2025-11-05 09:27 UTC:**
- Removed IamInstanceProfile from launch_ec2.sh
- Issue: IAM profile "EC2-S3-Access" doesn't exist, ai-backtester user lacks IAM permissions
- Solution: Removed profile, will configure AWS credentials manually on instance during setup
- Note: setup_instance.sh prompts for AWS credentials (already designed for this)

**2025-11-05 09:30 UTC:**
- Fixed jq dependency in launch_ec2.sh
- Issue: Script required jq (JSON parser) which isn't installed on Windows
- Solution: Replaced jq with AWS CLI's built-in --query and --output text
- Changes: Direct extraction of SpotInstanceRequestId in single command

**2025-11-05 09:31 UTC:**
- Spot request sir-epcz9vcj failed (price too low)
- Issue: $0.15 spot price < $0.1697 minimum required
- Solution: Increased SPOT_PRICE to $0.20 in launch_ec2.sh
- Cancelled failed request, relaunching

---

## Run History

### Template Entry
```
### Run #X - [RUNNING/COMPLETED/FAILED]
**Run ID:** YYYYMMDD_HHMMSS
**Started:** YYYY-MM-DD HH:MM:SS
**Instance ID:** i-xxxxxxxxx
**Instance Type:** c6i.2xlarge
**Public IP:** x.x.x.x

**Configuration:**
- Strategies: [list or "all"]
- Tickers: AAPL, MSFT, etc.
- Period: YYYY-MM-DD to YYYY-MM-DD
- Mode: static/dynamic/meta
- Features: WFV [ON/OFF], Cost-Aware [ON/OFF], Regime [ON/OFF]

**Progress:**
- [timestamp] Status update

**Results:**
- Exit Code: 0/1
- Runtime: X hours
- Cost: $X.XX
- S3 Location: s3://bucket/path/
- Key Metrics:
  - Sharpe: X.XX
  - Max DD: X.XX%
  - Total Return: X.XX%

**Notes:**
- Any issues or observations
```

---

## Active Run Template (for Claude to update during execution)

### Run #1 - [RUNNING]
**Run ID:** 20251105_092100
**Started:** 2025-11-05 09:21:00 UTC (relaunched at 09:45 UTC)
**Spot Request:** sir-hnhzbj2h (previous sir-epcz9vcj cancelled - price too low)
**Instance ID:** i-0d29dbfff95608560
**Public IP:** 3.239.18.187
**Instance Type:** c6i.2xlarge (8 vCPU, 16 GB RAM)

**Configuration:**
- Strategies: All 13 (VWAPReversion, ORB, ATRBreakout, VWAPBands, BollRevert, Seasonality, CSM, KalPairs, KFTrend, BreakoutMomentum, VolumeSpike, BollingerBand, MLClassifier)
- Tickers: AAPL, MSFT, GOOGL, AMZN, TSLA
- Period: 2024-10-01 to 2025-10-01 (1 year)
- Mode: static Sharpe optimization
- Features: WFV [ON], Cost-Aware [ON], Regime [ON]
- Transaction Costs: 0.05% slippage + $0.001/share commission

**Checklist:**
- [x] Instance launched (t3.large on-demand)
- [x] Setup complete via SCP upload (no git clone needed)
- [x] AWS CLI installed and S3 access verified
- [x] Small test passed (2 strategies, 3 days, AAPL only)
- [x] S3 upload verified (s3://polygon-trader-data-roshen/trader-results/test_20251110_180825/)
- [x] Full run started (PID 4543, tmux session "optimizer", log: logs/ec2_full_20251110_181411.log)
- [ ] Run completed (ETA: ~02:00-06:00 UTC Nov 11)
- [ ] Results uploaded to S3
- [ ] Instance terminated
- [ ] Results validated

**Real-time Updates:**
- 17:57:00 UTC: Attempted c6i.2xlarge spot - no capacity available
- 17:58:00 UTC: Cancelled spot request, switched to t3.large on-demand
- 18:01:00 UTC: Instance i-0709a0f087f9476fd launched successfully
- 18:02:00 UTC: SSH access confirmed
- 18:03:00 UTC: Code uploaded via SCP (src/, scripts/, requirements.txt)
- 18:05:00 UTC: Python venv created, dependencies installed
- 18:06:00 UTC: AWS CLI installed, credentials configured
- 18:07:00 UTC: S3 access verified (s3://polygon-trader-data-roshen/curated/)
- 18:08:00 UTC: Small test PASSED (2 strategies × AAPL × 3 days, Sharpe=0.185)
- 18:08:30 UTC: S3 upload verified (test_20251110_180825)
- 18:08:45 UTC: Results downloaded and validated locally
- 18:14:11 UTC: **FULL RUN STARTED** - PID 4543, tmux "optimizer", Run ID 20251110_181411
- 18:14:30 UTC: Confirmed process running (CPU 25%, Memory 803MB)
- Expected completion: ~02:00-06:00 UTC Nov 11 (8-12 hours from start)

---

## Cost Tracking

| Run # | Instance Type | Runtime (hrs) | Price/hr | Total Cost | Status | Date |
|-------|---------------|---------------|----------|------------|--------|------|
| 1     | c6i.2xlarge (spot) | ~5 | $0.11 | ~$0.55 | FAILED (results lost) | 2025-11-10 |
| 2     | t3.large (on-demand) | 8-12 (est) | $0.0832 | ~$0.83-1.00 | RUNNING | 2025-11-10 |

**Total EC2 Costs (to date):** ~$1.38-1.55

**Notes:**
- Run #1 wasted ~$0.55 due to premature termination
- Run #2 uses on-demand for reliability (~$0.30 premium worth it)

---

## S3 Results Archive

All completed runs are archived to:
```
s3://polygon-trader-data-roshen/trader-results/
  ├── YYYYMMDD_HHMMSS/
  │   ├── artifacts/
  │   ├── reports/
  │   └── logs/
```

**Download Command:**
```bash
aws s3 sync s3://polygon-trader-data-roshen/trader-results/YYYYMMDD_HHMMSS/ ./results/
```

---

##  Quick Reference Commands

### Launch Instance (from Windows)
```cmd
cd C:\Users\Roshl\Trader
scripts\aws\launch_spot.bat
```

### SSH to Instance
```bash
ssh -i trader-optimizer.pem ubuntu@<IP>
```

### On EC2: Setup
```bash
cd ~/Trader
bash scripts/aws/setup_instance.sh
```

### On EC2: Small Test
```bash
cd ~/Trader
source .venv/bin/activate
bash scripts/aws/run_remote_small.sh
```

### On EC2: Full Run (in tmux)
```bash
tmux new -s optimizer
cd ~/Trader
source .venv/bin/activate
bash scripts/aws/run_remote_full.sh
# Detach: Ctrl+B then D
```

### Monitor Progress (reconnect SSH)
```bash
ssh -i trader-optimizer.pem ubuntu@<IP>
tmux attach -t optimizer
# OR
tail -f ~/Trader/logs/ec2_full_*.log
```

### Download Results (from Windows)
```cmd
aws s3 sync s3://polygon-trader-data-roshen/trader-results/YYYYMMDD_HHMMSS/ results\
```

### Terminate Instance
```cmd
aws ec2 terminate-instances --region us-east-1 --instance-ids i-xxxxxxxxx
```

---

## Monitoring Checklist for Claude

When managing an EC2 run, Claude should:

1. **Pre-Launch:**
   - [ ] Verify AWS credentials are configured
   - [ ] Confirm S3 data is accessible
   - [ ] Check no other instances are running

2. **Launch:**
   - [ ] Execute launch script
   - [ ] Record instance ID and IP in this tracker
   - [ ] Save connection info

3. **Setup:**
   - [ ] SSH into instance
   - [ ] Run setup script
   - [ ] Verify S3 access works
   - [ ] Confirm auto-shutdown is active

4. **Test:**
   - [ ] Run small validation test
   - [ ] Check test results pass
   - [ ] Verify artifacts are generated

5. **Full Run:**
   - [ ] Start full optimization in tmux
   - [ ] Detach and disconnect
   - [ ] Record start time

6. **Monitoring:**
   - [ ] Periodic check-ins (every 1-2 hours)
   - [ ] Update status in this tracker
   - [ ] Monitor for errors

7. **Completion:**
   - [ ] Verify run completed successfully
   - [ ] Check S3 upload succeeded
   - [ ] Download key results
   - [ ] Terminate instance
   - [ ] Calculate and record cost

8. **Post-Run:**
   - [ ] Validate results locally
   - [ ] Update run history
   - [ ] Document any issues
   - [ ] Update total cost tracking

---

## Troubleshooting

### Instance won't launch
- Check spot price limits
- Verify security group exists
- Confirm key pair is valid

### Setup fails
- Check AWS credentials
- Verify S3 bucket access
- Ensure correct region

### Optimization fails
- Check data availability for date range
- Verify strategy imports
- Review error logs

### Auto-shutdown not working
- Check service status: `sudo systemctl status auto-shutdown`
- View logs: `sudo journalctl -u auto-shutdown -f`
- Restart: `sudo systemctl restart auto-shutdown`

---

## Notes for Claude

**Important Reminders:**
1. Always update this tracker during execution
2. Record all instance IDs and costs
3. Verify S3 uploads before terminating
4. Save error logs for failed runs
5. Update CLAUDE.md with run results

**Cost Control:**
- Spot instance target: < $0.20/hour
- Expected full run: 4-6 hours = $0.64-$1.20
- Always verify auto-shutdown is running
- Terminate manually if auto-shutdown fails

**Success Criteria:**
- Exit code 0
- Artifacts generated
- S3 upload successful
- Metrics look reasonable (Sharpe > 0, etc.)

---

_End of Tracker_
