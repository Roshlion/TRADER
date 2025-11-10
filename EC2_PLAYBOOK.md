# EC2 Playbook - Complete Step-by-Step Guide

**Purpose:** Exact commands to reproduce EC2 optimization runs from scratch.
**Last Updated:** 2025-11-10
**Author:** Claude (documented from successful Run #1)

---

## Prerequisites

**Required Files:**
- `trader-optimizer.pem` - EC2 SSH key pair (in project root)
- AWS credentials configured locally (`aws configure`)

**AWS Resources:**
- Key Pair: `trader-optimizer`
- Security Group: `sg-0616e1ad92cffbda8` (trader-optimizer-sg, allows SSH)
- Region: us-east-1

---

## Part 1: Launch EC2 Instance

### Step 1.1: Launch Spot Instance

```bash
cd C:\Users\Roshl\Trader
bash scripts/aws/launch_ec2.sh
```

**Expected Output:**
```
=== TRADER EC2 Spot Instance Launcher ===
Launching EC2 Spot Instance...
  Instance Type: c6i.2xlarge
  Region: us-east-1
  Spot Max Price: $0.20/hour

Spot request submitted successfully!
Spot Request ID: sir-XXXXXXXX

Instance launched: i-XXXXXXXXXXXXXXXXX
Public IP: X.X.X.X
Cost: ~$0.10-0.12/hour (Spot)
```

**Save the Instance ID and IP address!**

### Step 1.2: Fix SSH Key Permissions (Windows)

```bash
icacls trader-optimizer.pem /inheritance:r /grant:r "Roshl:R"
```

### Step 1.3: Test SSH Connection

Wait 30 seconds for instance to initialize, then:

```bash
ssh -i trader-optimizer.pem -o StrictHostKeyChecking=no ubuntu@<PUBLIC_IP> "echo 'Connected!' && uptime"
```

**Expected:** Connection successful, uptime shows instance just started.

---

## Part 2: Setup Environment on EC2

### Step 2.1: Install System Packages

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  sudo apt-get update -qq &&
  sudo apt-get install -y -qq git python3-venv python3-pip awscli curl htop unzip
"
```

**Time:** ~2-3 minutes

### Step 2.2: Clone Repository

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~ &&
  git clone -b setup/scaffold https://github.com/Roshlion/TRADER.git &&
  echo 'Repo cloned successfully'
"
```

**Note:** Directory will be `~/TRADER` (uppercase)

### Step 2.3: Create Virtual Environment

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~/TRADER &&
  python3 -m venv .venv &&
  echo 'Virtual environment created'
"
```

### Step 2.4: Install Python Dependencies

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~/TRADER &&
  source .venv/bin/activate &&
  pip install --upgrade pip &&
  pip install -r requirements.txt
"
```

**Time:** ~5-8 minutes (installing scipy, sklearn, polars, etc.)

### Step 2.5: Configure AWS Credentials

**Option A: Use local credentials (recommended)**

```bash
# Get local credentials
aws configure get aws_access_key_id
aws configure get aws_secret_access_key
aws configure get region

# Configure on EC2
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
mkdir -p ~/.aws
cat > ~/.aws/credentials <<EOF
[default]
aws_access_key_id = <YOUR_ACCESS_KEY>
aws_secret_access_key = <YOUR_SECRET_KEY>
EOF

cat > ~/.aws/config <<EOF
[default]
region = us-east-1
output = json
EOF

chmod 600 ~/.aws/credentials ~/.aws/config
echo 'AWS credentials configured'
"
```

**Option B: Run interactively**

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP>
cd ~/TRADER
aws configure
# Enter credentials when prompted
```

### Step 2.6: Verify S3 Access

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  aws s3 ls s3://polygon-trader-data-roshen/curated/minute_bars/ | head -5
"
```

**Expected:** List of year=2024/, year=2025/ folders

---

## Part 3: Run Small Validation Test

### Step 3.1: Execute Small Test

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~/TRADER &&
  source .venv/bin/activate &&
  mkdir -p logs reports/ec2 artifacts/portfolios &&
  python -m scripts.python.optimize_portfolio \
    --strategies mean_reversion.VWAPReversion,opening_range.ORB \
    --tickers AAPL,MSFT \
    --start 2025-10-01 --end 2025-10-07 \
    --mode static --objective sharpe \
    --cost-aware on --rebalance-cost-bps 1.0 \
    --regime on --regime-weight 0.25 \
    --slippage 0.0005 --commission 0.001 \
    --max-weight 0.5 --long-only
"
```

**Time:** ~4-5 minutes
**Expected:**
- Process completes successfully
- Reports: `Sharpe Ratio`, `Total Return`, `Max Drawdown`
- Files created in `artifacts/portfolios/` and `reports/portfolio/`

### Step 3.2: Verify Test Results

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~/TRADER &&
  ls -lh artifacts/portfolios/latest_weights.json &&
  ls -lh reports/portfolio/*.png
"
```

**Expected:** JSON file + 3 PNG charts

---

## Part 4: Launch Full Annual Optimization

### Step 4.1: Start in Tmux (detachable session)

```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~/TRADER &&
  source .venv/bin/activate &&
  tmux new-session -d -s optimizer 'bash scripts/aws/run_remote_full.sh; exec bash' &&
  sleep 3 &&
  tmux send-keys -t optimizer '' Enter &&
  echo 'Run started in tmux session optimizer'
"
```

**Time to complete:** 4-5 hours
**Cost:** ~$0.50-0.60

### Step 4.2: Monitor Progress

**Check process is running:**
```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  ps aux | grep 'python.*optimize_portfolio' | grep -v grep
"
```

**Expected:** Shows Python process with CPU ~30-50%, Memory ~10-15%

**View tmux session:**
```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP>
tmux attach -t optimizer
# Detach with: Ctrl+B then D
```

**Tail logs:**
```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  tail -f ~/TRADER/logs/ec2_full_*.log
"
```

---

## Part 5: Close Laptop & Return Later

**✅ YOU CAN SAFELY:**
- Close your laptop
- Shut down your computer
- Come back tomorrow

**The process will keep running on EC2!**

**Auto-shutdown protection:**
- The auto-shutdown script monitors CPU usage
- If CPU < 10% for 30 minutes → instance shuts down
- During optimization, CPU is 30-50% → **will NOT shut down**
- After completion, auto-shutdown kicks in after 30 minutes idle

---

## Part 6: Check Results When You Return

### Step 6.1: Reconnect and Check Status

```bash
# SSH back into instance
ssh -i trader-optimizer.pem ubuntu@3.239.18.187

# Check if process is still running
ps aux | grep optimize_portfolio

# Attach to tmux to see live output
tmux attach -t optimizer
```

**If run completed, you'll see:**
- "Optimization complete!"
- "Results saved to: artifacts/portfolios/..."
- "S3 upload successful"

### Step 6.2: View Results on EC2

```bash
cd ~/TRADER

# View portfolio weights
cat artifacts/portfolios/latest_weights.json | head -50

# View final metrics
tail -100 logs/ec2_full_20251110_074825.log

# List generated files
ls -lh artifacts/portfolios/
ls -lh reports/portfolio/
```

### Step 6.3: Download Results to Local Machine

**From your Windows machine:**

```bash
# Download from S3 (recommended)
aws s3 sync s3://polygon-trader-data-roshen/trader-results/20251110_074825/ ./results_20251110/

# Or download directly via SCP (alternative)
scp -i trader-optimizer.pem -r ubuntu@3.239.18.187:~/TRADER/artifacts/portfolios ./local_results/
scp -i trader-optimizer.pem -r ubuntu@3.239.18.187:~/TRADER/reports/portfolio ./local_results/
```

### Step 6.4: Verify S3 Upload

```bash
aws s3 ls s3://polygon-trader-data-roshen/trader-results/20251110_074825/ --recursive
```

**Expected:** Artifacts, reports, and logs all uploaded

---

## Part 7: Terminate Instance (IMPORTANT!)

**⚠️ Always terminate after downloading results to stop billing!**

```bash
# Terminate instance
aws ec2 terminate-instances --region us-east-1 --instance-ids i-0d29dbfff95608560

# Verify termination
aws ec2 describe-instances \
  --instance-ids i-0d29dbfff95608560 \
  --query 'Reservations[0].Instances[0].State.Name' \
  --output text
```

**Expected:** `shutting-down` or `terminated`

---

## Common Issues & Troubleshooting

### Issue: "Permission denied (publickey)"

**Fix:**
```bash
icacls trader-optimizer.pem /inheritance:r /grant:r "Roshl:R"
```

### Issue: "ModuleNotFoundError: No module named 'seaborn'"

**Fix:**
```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP> "
  cd ~/TRADER &&
  source .venv/bin/activate &&
  pip install seaborn
"
```

### Issue: Directory not found (~/Trader vs ~/TRADER)

**Fix:** The script now checks both, but if you see this error:
```bash
cd ~/TRADER  # Use uppercase
```

### Issue: S3 access denied

**Fix:** Reconfigure AWS credentials:
```bash
ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP>
aws configure
# Re-enter credentials
```

### Issue: Process not running in tmux

**Fix:** Check if it errored out:
```bash
tmux attach -t optimizer
# Scroll up to see errors
```

Common causes:
- Missing dependencies (install via pip)
- S3 credentials expired (reconfigure)
- Out of memory (use larger instance type)

---

## Quick Reference: Essential Commands

### Launch & Setup (one-time)
```bash
# 1. Launch instance
bash scripts/aws/launch_ec2.sh

# 2. Setup environment
ssh -i trader-optimizer.pem ubuntu@<IP>
cd ~/TRADER
source .venv/bin/activate

# 3. Configure AWS
aws configure
```

### Run Optimization
```bash
# Small test (5 min)
python -m scripts.python.optimize_portfolio \
  --strategies mean_reversion.VWAPReversion,opening_range.ORB \
  --tickers AAPL,MSFT --start 2025-10-01 --end 2025-10-07 \
  --mode static --objective sharpe

# Full run (4-5 hours, in tmux)
tmux new-session -s optimizer
bash scripts/aws/run_remote_full.sh
# Ctrl+B then D to detach
```

### Monitor
```bash
# Check process
ps aux | grep optimize_portfolio

# View tmux
tmux attach -t optimizer

# Tail logs
tail -f ~/TRADER/logs/ec2_full_*.log
```

### Cleanup
```bash
# Download results
aws s3 sync s3://polygon-trader-data-roshen/trader-results/<RUN_ID>/ ./results/

# Terminate
aws ec2 terminate-instances --instance-ids <INSTANCE_ID>
```

---

## Cost Breakdown

| Task | Duration | Cost |
|------|----------|------|
| Setup & small test | 20-30 min | $0.02-0.05 |
| Full annual run | 4-5 hours | $0.40-0.60 |
| **Total per run** | **~5 hours** | **~$0.60** |

**100 tickers (future):** 60-90 hours, ~$7-11

---

## Data Availability

**Verified:** 11,172 unique tickers available in S3 (Oct 2024)
**Daily volume:** ~1.5M minute bars per day
**Format:** Parquet with Hive partitioning (year/month/day)
**Location:** `s3://polygon-trader-data-roshen/curated/minute_bars/`

---

## Next Time: Scaling to 100+ Tickers

**Recommended approach:**
1. Start with 20 tickers first (test scaling)
2. Use c6i.8xlarge (32 vCPU) for 100 ticker runs
3. Consider batch processing (5 runs × 20 tickers)
4. Enable checkpointing for multi-day runs

---

_End of Playbook_
