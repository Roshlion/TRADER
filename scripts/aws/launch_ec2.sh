#!/bin/bash
# EC2 Spot Instance Launch Script for TRADER Optimizer
# Launches a c6i.2xlarge Spot instance with auto-shutdown

# IMPORTANT: This script requires EC2 permissions
# Current IAM user (ai-backtester) does NOT have EC2 permissions
# See DOCUMENTATION.md for:
#   - Option 1: AWS Console launch (no IAM changes needed)
#   - Option 2: Grant EC2 permissions to ai-backtester user

# Configuration
INSTANCE_TYPE="c6i.2xlarge"
AMI_ID="ami-0c7217cdde317cfec"  # Ubuntu 22.04 LTS in us-east-1 (update if needed)
KEY_NAME="trader-optimizer"   # EC2 key pair
SECURITY_GROUP="sg-0616e1ad92cffbda8"  # trader-optimizer-sg (allows SSH)
REGION="us-east-1"
SPOT_PRICE="0.20"  # Max price willing to pay (current ~$0.17)
VOLUME_SIZE=30  # GB for root volume

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== TRADER EC2 Spot Instance Launcher ==="
echo ""

# Check for required variables
if [ "$KEY_NAME" == "YOUR_KEY_PAIR_NAME" ] || [ "$SECURITY_GROUP" == "YOUR_SECURITY_GROUP" ]; then
    echo -e "${RED}ERROR: Configuration required!${NC}"
    echo "Please edit this script and set:"
    echo "  - KEY_NAME: Your EC2 key pair name"
    echo "  - SECURITY_GROUP: Security group ID (must allow SSH on port 22)"
    echo ""
    echo "To create a key pair:"
    echo "  aws ec2 create-key-pair --key-name trader-optimizer --query 'KeyMaterial' --output text > trader-optimizer.pem"
    echo "  chmod 400 trader-optimizer.pem"
    echo ""
    exit 1
fi

# User data script (runs on first boot)
USER_DATA=$(cat <<'EOF'
#!/bin/bash
# Auto-run setup on first boot
cd /home/ubuntu
mkdir -p /var/log
touch /var/log/auto-shutdown.log
chown ubuntu:ubuntu /var/log/auto-shutdown.log

# Clone repository (user will need to configure AWS credentials)
# This will be done manually after SSH login
EOF
)

echo "Launching EC2 Spot Instance..."
echo "  Instance Type: $INSTANCE_TYPE"
echo "  Region: $REGION"
echo "  Spot Max Price: \$$SPOT_PRICE/hour (current ~\$0.10-0.12)"
echo "  AMI: $AMI_ID (Ubuntu 22.04 LTS)"
echo ""

# Launch spot instance and extract request ID directly
REQUEST_ID=$(aws ec2 request-spot-instances \
    --region "$REGION" \
    --spot-price "$SPOT_PRICE" \
    --instance-count 1 \
    --type "one-time" \
    --launch-specification "{
        \"ImageId\": \"$AMI_ID\",
        \"InstanceType\": \"$INSTANCE_TYPE\",
        \"KeyName\": \"$KEY_NAME\",
        \"SecurityGroupIds\": [\"$SECURITY_GROUP\"],
        \"UserData\": \"$(echo "$USER_DATA" | base64 -w 0)\",
        \"BlockDeviceMappings\": [{
            \"DeviceName\": \"/dev/sda1\",
            \"Ebs\": {
                \"VolumeSize\": $VOLUME_SIZE,
                \"VolumeType\": \"gp3\",
                \"DeleteOnTermination\": true
            }
        }]
    }" \
    --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
    --output text 2>&1)

if [ $? -eq 0 ] && [ -n "$REQUEST_ID" ] && [ "$REQUEST_ID" != "None" ]; then
    echo -e "${GREEN}Spot request submitted successfully!${NC}"

    # Request ID already extracted
    echo "Spot Request ID: $REQUEST_ID"
    echo ""
    echo "Waiting for instance to be assigned..."

    # Wait for spot request to be fulfilled
    aws ec2 wait spot-instance-request-fulfilled --region "$REGION" --spot-instance-request-ids "$REQUEST_ID"

    # Get instance ID
    INSTANCE_ID=$(aws ec2 describe-spot-instance-requests \
        --region "$REGION" \
        --spot-instance-request-ids "$REQUEST_ID" \
        --query 'SpotInstanceRequests[0].InstanceId' \
        --output text)

    echo -e "${GREEN}Instance launched: $INSTANCE_ID${NC}"

    # Wait for instance to be running
    echo "Waiting for instance to be running..."
    aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

    # Get public IP
    PUBLIC_IP=$(aws ec2 describe-instances \
        --region "$REGION" \
        --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text)

    # Tag the instance (tags cannot be in LaunchSpecification for spot instances)
    echo "Tagging instance..."
    aws ec2 create-tags \
        --region "$REGION" \
        --resources "$INSTANCE_ID" \
        --tags \
            Key=Name,Value=trader-optimizer \
            Key=Project,Value=TRADER \
            Key=AutoShutdown,Value=enabled

    echo ""
    echo -e "${GREEN}=== Instance Ready! ===${NC}"
    echo "Instance ID: $INSTANCE_ID"
    echo "Public IP: $PUBLIC_IP"
    echo "Instance Type: $INSTANCE_TYPE"
    echo "Cost: ~\$0.10-0.12/hour (Spot)"
    echo ""
    echo -e "${YELLOW}=== Next Steps ===${NC}"
    echo "1. Wait 30 seconds for instance initialization"
    echo "2. SSH into instance:"
    echo "   ssh -i $KEY_NAME.pem ubuntu@$PUBLIC_IP"
    echo ""
    echo "3. Run setup script:"
    echo "   bash ~/Trader/scripts/aws/setup_instance.sh"
    echo ""
    echo "4. Run optimizer (example):"
    echo "   cd ~/Trader"
    echo "   source .venv/bin/activate"
    echo "   python -m scripts.python.optimize_portfolio --strategies mean_reversion.VWAPReversion --tickers AAPL,MSFT --start 2025-10-01 --end 2025-10-31"
    echo ""
    echo "5. Monitor auto-shutdown:"
    echo "   sudo journalctl -u auto-shutdown -f"
    echo ""
    echo -e "${YELLOW}Instance will auto-shutdown after 30min idle to save costs${NC}"
    echo ""
else
    echo -e "${RED}Failed to launch instance!${NC}"
    echo "Error: Could not obtain spot request ID"
    echo "Request ID value: '$REQUEST_ID'"
    echo "This may indicate an AWS API error or permission issue."
    exit 1
fi
