# EC2 Instance Connection Information

## Instance Details

**Instance ID**: `i-0c103dbc16871b96f`
**Public IP**: `3.82.45.243`
**Instance Type**: `c6i.2xlarge` (8 vCPU, 16 GB RAM)
**Spot Price**: ~$0.16/hour
**Region**: us-east-1
**Status**: Running ✅

---

## Connect to Your Instance

### Step 1: SSH into the Instance

```bash
ssh -i trader-optimizer.pem ubuntu@3.82.45.243
```

**Note**: The key file `trader-optimizer.pem` is in your Trader directory.

If you get a "permissions too open" error:
```bash
icacls trader-optimizer.pem /inheritance:r
icacls trader-optimizer.pem /grant:r "%USERNAME%:R"
```

### Step 2: Install Git and Clone Repository

Once connected, run:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install git
sudo apt-get install -y git

# Clone your repository (you'll need to authenticate)
git clone https://github.com/YOUR_USERNAME/Trader.git
# OR if using SSH:
# git clone git@github.com:YOUR_USERNAME/Trader.git

cd Trader
```

### Step 3: Run Setup Script

```bash
# Make scripts executable
chmod +x scripts/aws/*.sh

# Run setup (installs Python, dependencies, auto-shutdown)
bash scripts/aws/setup_instance.sh
```

This will:
- Install Python 3.12 and pip
- Create virtual environment
- Install all dependencies from requirements.txt
- Configure AWS CLI (you'll need to enter your credentials)
- Set up auto-shutdown monitor

### Step 4: Configure AWS Credentials

During setup, you'll be prompted for AWS credentials:

```
AWS Access Key ID: [Enter your access key]
AWS Secret Access Key: [Enter your secret key]
Default region name: us-east-1
Default output format: json
```

Use the same credentials from your local `.aws/credentials` file.

### Step 5: Test the Setup

```bash
# Activate virtual environment
source .venv/bin/activate

# Test S3 access
aws s3 ls s3://polygon-trader-data-roshen/curated/minute_bars/

# Run a quick backtest (should take ~2-3 minutes)
cd src
python -m trader.strategy_suite.backtest \
  --strategy mean_reversion.VWAPReversion \
  --tickers AAPL \
  --start 2025-10-20 --end 2025-10-24 \
  --capital 100000
```

---

## Running the Optimizer

### Full Multi-Strategy Optimization (October 2025 data)

```bash
cd ~/Trader
source .venv/bin/activate

python -m scripts.python.optimize_portfolio \
  --strategies opening_range.ORB,volatility_breakout.ATRBreakout,vwap_bands.VWAPBands,bollinger_revert.BollRevert,intraday_seasonality.Seasonality,cross_sectional_momo.CSM,kalman_pairs.KalPairs,kf_trend.KFTrend,momentum.BreakoutMomentum,momentum.VolumeSpike,mean_reversion.VWAPReversion,mean_reversion.BollingerBand,stat_arb.PairsTrading,machine_learning.MLClassifierStrategy \
  --tickers AAPL,MSFT,GOOGL,AMZN,TSLA \
  --start 2025-10-01 --end 2025-10-31 \
  --mode static --objective sharpe \
  --transaction_cost 0.001 --slippage 0.0005
```

**Estimated Runtime**: 2-4 hours (depending on number of strategies/tickers)

### Monitor Progress

Open a second SSH session and monitor:

```bash
# Watch CPU usage
htop

# Monitor auto-shutdown logs
sudo journalctl -u auto-shutdown -f
```

---

## Auto-Shutdown Details

**Auto-shutdown is ENABLED** - instance will automatically terminate when idle.

**Settings**:
- CPU threshold: 5% (shuts down if CPU < 5%)
- Idle duration: 30 minutes
- Check interval: Every 5 minutes

**How it works**:
1. When your optimizer finishes, CPU drops to ~1-2%
2. After 30 minutes of idle CPU, auto-shutdown triggers
3. Instance terminates automatically (stops billing)

**Cancel auto-shutdown** (if you need more time):
```bash
sudo shutdown -c
```

**Check auto-shutdown status**:
```bash
sudo systemctl status auto-shutdown
```

**View logs**:
```bash
sudo cat /var/log/auto-shutdown.log
```

---

## Estimated Costs

| Scenario | Runtime | Cost |
|----------|---------|------|
| Quick test (1-2 days, 2 tickers) | 30 min | ~$0.08 |
| Medium backtest (1 week, 5 tickers) | 2 hours | ~$0.32 |
| **Full optimization (1 month, all strategies)** | **4 hours** | **~$0.64** |
| Extended backtest (3 months) | 8 hours | ~$1.28 |

**Storage**: 30 GB EBS = ~$2.40/month (prorated if you terminate)

**Total expected cost for Phase 5 validation**: **< $1.00**

---

## Manual Shutdown

If you want to manually stop the instance before auto-shutdown triggers:

### From EC2 Instance (SSH):
```bash
sudo shutdown now
```

### From Your Local Machine:
```bash
# Stop (can restart later)
aws ec2 stop-instances --instance-ids i-0c103dbc16871b96f

# Terminate (permanently delete)
aws ec2 terminate-instances --instance-ids i-0c103dbc16871b96f
```

**IMPORTANT**: Spot instances cannot be stopped, only terminated. Once terminated, you'll need to launch a new instance.

---

## Troubleshooting

### Can't SSH: "Connection refused"
- Wait 30-60 seconds after launch for SSH daemon to start
- Verify security group allows SSH: `aws ec2 describe-security-groups --group-ids sg-0616e1ad92cffbda8`

### Can't access S3 data
- Verify AWS credentials: `aws s3 ls` (should list buckets)
- Check region matches: `aws configure get region` (should be us-east-1)

### Optimizer runs slowly
- Check CPU usage: `htop` (should be near 100% during optimization)
- Verify instance type: `ec2-metadata --instance-type` (should be c6i.2xlarge)

### Auto-shutdown triggered too early
- Increase idle duration in `/home/ubuntu/auto_shutdown.sh`
- Or disable it: `sudo systemctl stop auto-shutdown`

---

## Next Steps

1. **SSH in**: `ssh -i trader-optimizer.pem ubuntu@3.82.45.243`
2. **Clone repo and setup**: Follow steps above
3. **Run optimizer**: Use commands in "Running the Optimizer" section
4. **Monitor**: Check logs and CPU usage
5. **Let it finish**: Auto-shutdown will handle termination

**The instance is ready to use!** 🚀
