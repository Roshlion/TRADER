# EC2 Quick Start Guide - Automated Setup

**Purpose:** Launch EC2 instance and run full optimization in <5 minutes

**Last Updated:** 2025-11-10

---

## Prerequisites

- AWS CLI configured locally (`aws configure`)
- SSH key: `trader-optimizer.pem` in project root
- Security group: `sg-0616e1ad92cffbda8` (trader-optimizer-sg)

---

## Quick Launch (Copy-Paste Commands)

### 1. Launch Instance (On-Demand - Always Available)

```bash
# Launch t3.large (recommended for reliability)
aws ec2 run-instances \
  --region us-east-1 \
  --image-id ami-0c7217cdde317cfec \
  --instance-type t3.large \
  --key-name trader-optimizer \
  --security-group-ids sg-0616e1ad92cffbda8 \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=trader-full-run},{Key=Purpose,Value=optimization}]' \
  --query 'Instances[0].[InstanceId,PrivateIpAddress]' \
  --output text
```

**Save the Instance ID and wait 30 seconds for boot**

### 2. Get Public IP

```bash
INSTANCE_ID="i-xxxxxxxxx"  # Replace with your instance ID
aws ec2 describe-instances --region us-east-1 --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
```

### 3. Upload Code & Setup (3 minutes)

```bash
# Wait for SSH to be ready (run until successful)
ssh -i trader-optimizer.pem -o StrictHostKeyChecking=no ubuntu@<PUBLIC_IP> "echo 'SSH ready'"

# Upload code
scp -i trader-optimizer.pem -r src scripts requirements.txt .env ubuntu@<PUBLIC_IP>:~/

# Install dependencies & configure
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> << 'SETUP'
set -e
# Install system packages
sudo apt-get update -qq
sudo apt-get install -y python3.10 python3.10-venv python3-pip git unzip

# Install AWS CLI
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# Create Python venv
python3.10 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q boto3 polars pyarrow duckdb scikit-learn matplotlib seaborn pyyaml

# Configure AWS (using .env file)
source .env
aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
aws configure set region us-east-1

# Create directories
mkdir -p logs artifacts/portfolios reports/portfolio

echo "✓ Setup complete"
SETUP
```

### 4. Run Small Test (Optional but Recommended)

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> << 'TEST'
source ~/.venv/bin/activate
python -m scripts.python.optimize_portfolio \
  --strategies mean_reversion.VWAPReversion,opening_range.ORB \
  --tickers AAPL \
  --start 2025-10-01 --end 2025-10-03 \
  --mode static --objective sharpe \
  --slippage 0.0005 --commission 0.001 \
  --max-weight 0.5 --long-only
TEST
```

**Expected:** Completes in ~45 seconds, shows Sharpe > 0

### 5. Launch Full Optimization (8-12 hours)

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> << 'FULL_RUN'
source ~/.venv/bin/activate
RUN_ID=$(date +%Y%m%d_%H%M%S)

# Launch in tmux (survives disconnects)
tmux new-session -d -s optimizer "source ~/.venv/bin/activate && bash -c '
set -e
LOG_FILE=logs/ec2_full_${RUN_ID}.log

python -m scripts.python.optimize_portfolio \
  --strategies mean_reversion.VWAPReversion,opening_range.ORB,volatility_breakout.ATRBreakout,vwap_bands.VWAPBands,bollinger_revert.BollRevert,intraday_seasonality.Seasonality,cross_sectional_momo.CSM,kalman_pairs.KalPairs,kf_trend.KFTrend,momentum.BreakoutMomentum,momentum.VolumeSpike,mean_reversion.BollingerBand,machine_learning.MLClassifier \
  --tickers AAPL,MSFT,GOOGL,AMZN,TSLA \
  --start 2024-10-01 --end 2025-10-01 \
  --mode static --objective sharpe \
  --walkforward on --wf-train-days 10 --wf-test-days 5 \
  --cost-aware on --rebalance-cost-bps 1.0 \
  --regime on --regime-weight 0.25 \
  --slippage 0.0005 --commission 0.001 \
  --max-weight 0.4 --long-only \
  2>&1 | tee \$LOG_FILE

EXIT_CODE=\${PIPESTATUS[0]}

if [ \$EXIT_CODE -eq 0 ]; then
  echo \"✓ Uploading to S3...\"
  aws s3 sync artifacts/ s3://polygon-trader-data-roshen/trader-results/full_${RUN_ID}/artifacts/ --region us-east-1
  aws s3 sync reports/ s3://polygon-trader-data-roshen/trader-results/full_${RUN_ID}/reports/ --region us-east-1
  aws s3 cp \$LOG_FILE s3://polygon-trader-data-roshen/trader-results/full_${RUN_ID}/logs/ --region us-east-1
  echo \"✓ Results: s3://polygon-trader-data-roshen/trader-results/full_${RUN_ID}/\"
else
  echo \"✗ Failed: \$EXIT_CODE\"
  aws s3 cp \$LOG_FILE s3://polygon-trader-data-roshen/trader-results/errors/full_${RUN_ID}_error.log --region us-east-1
fi
' || sleep infinity"

echo "✓ Full optimization started in tmux session 'optimizer'"
echo "Run ID: $RUN_ID"
echo "Monitor: ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> 'tmux attach -t optimizer'"
FULL_RUN
```

**You can now close your laptop!** The run continues on EC2.

---

## Monitoring Progress

### Check if Still Running

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "ps aux | grep optimize_portfolio | grep -v grep"
```

**If output shows process:** Still running
**If empty:** Completed (or crashed)

### View Live Output

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP>
tmux attach -t optimizer
# Detach: Ctrl+B then D
```

### Check S3 for Results

```bash
# List all runs
aws s3 ls s3://polygon-trader-data-roshen/trader-results/

# Download specific run
aws s3 sync s3://polygon-trader-data-roshen/trader-results/full_YYYYMMDD_HHMMSS/ ./results/
```

---

## After Completion

### Download Results

```bash
RUN_ID="20251110_181411"  # Replace with your run ID
aws s3 sync s3://polygon-trader-data-roshen/trader-results/full_${RUN_ID}/ ./results_${RUN_ID}/
```

### Terminate Instance (STOP BILLING!)

```bash
aws ec2 terminate-instances --region us-east-1 --instance-ids $INSTANCE_ID
```

---

## Cost Estimates

| Instance Type | vCPU | RAM | Runtime | Cost/Hour | Total Cost |
|---------------|------|-----|---------|-----------|------------|
| t3.large      | 2    | 8GB | 10-12h  | $0.0832   | $0.83-1.00 |
| c6i.2xlarge   | 8    | 16GB| 4-6h    | $0.34     | $1.36-2.04 |
| c6i.2xlarge (spot) | 8 | 16GB | 4-6h | $0.10-0.12 | $0.40-0.72 |

**Recommendation:** Use t3.large for reliability (spot capacity often unavailable)

---

## Troubleshooting

### SSH Connection Refused
**Wait 60 seconds** after launch for instance to fully boot

### S3 Access Denied
Verify `.env` has correct AWS credentials:
```bash
aws configure get aws_access_key_id
aws configure get aws_secret_access_key
```

### Out of Memory
Reduce tickers or switch to larger instance (c6i.2xlarge)

### Optimization Fails
Check strategy imports:
```bash
python -c "from src.trader.strategy_suite.strategies.mean_reversion import VWAPReversion; print('OK')"
```

---

## What We Learned (2025-11-10)

**Issues from Previous Run:**
1. ❌ Spot instances can have no capacity (c6i.2xlarge unavailable)
2. ❌ Git clone requires auth for private repos
3. ❌ Auto-shutdown can terminate before S3 upload completes

**Solutions:**
1. ✅ Use on-demand instances for critical runs (t3.large recommended)
2. ✅ Use SCP to upload code directly (faster, no auth needed)
3. ✅ Run in tmux without auto-shutdown, terminate manually after results confirmed
4. ✅ Always run small test first to verify S3 upload works

**Key Insight:** The ~$0.20/hour premium for on-demand vs spot is worth it for peace of mind on long runs.

---

## Advanced: Spot Instance (if available)

```bash
# Only use if spot capacity is available and you're comfortable with interruptions
bash scripts/aws/launch_ec2.sh  # Existing script, may fail if no capacity
```

**Not recommended for production runs** due to:
- Capacity unavailability
- Potential interruptions mid-run
- No guaranteed completion

---

_Last validated: 2025-11-10 (Run ID: test_20251110_180825)_
