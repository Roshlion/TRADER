#!/bin/bash
# EC2 Instance Setup Script for TRADER Optimizer
# Sets up Python environment, AWS CLI, and dependencies

set -e  # Exit on error

echo "=== TRADER EC2 Setup Starting ==="
echo "Timestamp: $(date)"

# Update system packages
echo "[1/8] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

# Install essential tools
echo "[2/8] Installing essential tools..."
sudo apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    git \
    curl \
    htop \
    awscli \
    unzip

# Configure AWS CLI (will prompt for credentials)
echo "[3/8] Configuring AWS CLI..."
if [ ! -f ~/.aws/credentials ]; then
    echo "AWS credentials not found. Please configure:"
    aws configure
else
    echo "AWS credentials already configured."
fi

# Clone repository (if not already present)
echo "[4/8] Setting up repository..."
REPO_DIR=~/Trader
if [ ! -d "$REPO_DIR" ]; then
    echo "Repository not found. Please provide git clone URL:"
    read -p "Git clone URL: " GIT_URL
    git clone "$GIT_URL" "$REPO_DIR"
    cd "$REPO_DIR"
else
    echo "Repository already exists at $REPO_DIR"
    cd "$REPO_DIR"
    git pull
fi

# Create virtual environment
echo "[5/8] Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv
fi

# Activate and install dependencies
echo "[6/8] Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "WARNING: requirements.txt not found. Install manually."
fi

# Set up auto-shutdown script
echo "[7/8] Setting up auto-shutdown monitor..."
SHUTDOWN_SCRIPT="/home/ubuntu/auto_shutdown.sh"
sudo cp scripts/aws/auto_shutdown.sh "$SHUTDOWN_SCRIPT"
sudo chmod +x "$SHUTDOWN_SCRIPT"

# Create systemd service for auto-shutdown
sudo tee /etc/systemd/system/auto-shutdown.service > /dev/null <<EOF
[Unit]
Description=Auto-shutdown monitor for idle EC2 instance
After=network.target

[Service]
Type=simple
User=ubuntu
ExecStart=$SHUTDOWN_SCRIPT
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable auto-shutdown.service
sudo systemctl start auto-shutdown.service

# Display status
echo "[8/8] Setup complete!"
echo ""
echo "=== Setup Summary ==="
echo "Python version: $(python3.12 --version)"
echo "Virtual environment: $REPO_DIR/.venv"
echo "Auto-shutdown: Enabled (monitors CPU every 5min, shuts down after 30min idle)"
echo "AWS region: $(aws configure get region)"
echo ""
echo "=== Next Steps ==="
echo "1. Activate environment: source .venv/bin/activate"
echo "2. Run optimizer: cd $REPO_DIR && python -m scripts.python.optimize_portfolio --help"
echo "3. Monitor auto-shutdown: sudo journalctl -u auto-shutdown -f"
echo "4. Cancel auto-shutdown (if needed): sudo shutdown -c"
echo ""
echo "=== Cost Monitoring ==="
echo "Instance type: $(ec2-metadata --instance-type | cut -d' ' -f2)"
echo "Hourly rate: ~\$0.10 (Spot) or \$0.34 (On-Demand)"
echo "Auto-shutdown will terminate after 30min idle to save costs."
echo ""
