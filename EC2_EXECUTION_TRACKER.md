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
- [x] Spot request submitted (sir-hnhzbj2h)
- [x] Instance launched (i-0d29dbfff95608560)
- [x] Setup complete (clone repo + AWS creds + dependencies)
- [x] Small test passed (2 strategies, 1 week, Sharpe=0.225)
- [x] Full run started (PID 6368, tmux session "optimizer", log: logs/ec2_full_20251110_074825.log)
- [ ] Run completed (ETA: ~12:00-13:00 UTC)
- [ ] Results uploaded to S3
- [ ] Instance terminated
- [ ] Results validated

**Real-time Updates:**
- 09:21:00 UTC: Spot request submitted (sir-epcz9vcj)
- 09:21:05 UTC: Waiting for spot instance to be assigned...
- 09:25:00 UTC: Launch script fixes completed (TagSpecifications, IAM, jq)
- 09:31:00 UTC: First spot request failed (price $0.15 < minimum $0.1697)
- 09:31:30 UTC: Cancelled sir-epcz9vcj, increased price to $0.20
- 09:45:00 UTC: Relaunched with sir-hnhzbj2h - SUCCESS
- 09:45:45 UTC: Instance i-0d29dbfff95608560 running at 3.239.18.187
- 09:50:00 UTC: Setup complete (Python 3.10, dependencies installed, S3 access confirmed)
- 09:55:00 UTC: Small test PASSED (2 strategies, Sharpe=0.225, artifacts generated)
- 09:56:00 UTC: Ready for full annual optimization
- 10:47:00 UTC: Fixed run_remote_full.sh directory path issue (TRADER vs Trader)
- 10:48:00 UTC: **FULL RUN STARTED** - PID 6368, tmux "optimizer", Run ID 20251110_074825
- 10:48:30 UTC: Confirmed process running (CPU 35%, Memory 1.8GB)
- Expected completion: ~12:00-13:00 UTC (4-5 hours from start)

---

## Cost Tracking

| Run # | Instance Type | Runtime (hrs) | Spot Price | Total Cost | Date |
|-------|---------------|---------------|------------|------------|------|
| -     | -             | -             | -          | -          | -    |

**Total EC2 Costs:** $0.00

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
