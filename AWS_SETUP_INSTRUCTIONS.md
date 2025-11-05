# AWS EC2 Setup Instructions

Your IAM user `ai-backtester` (arn:aws:iam::190164554141:user/ai-backtester) needs EC2 permissions to launch instances.

## Option 1: Grant EC2 Permissions (Recommended)

**Do this in AWS Console:**

1. Go to **IAM Console** → **Users** → `ai-backtester`
2. Click **Add permissions** → **Attach policies directly**
3. Search and attach: **AmazonEC2FullAccess**
4. Click **Add permissions**

### Minimal Permissions (if you want least privilege)

Instead of FullAccess, create a custom policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:RequestSpotInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeSpotInstanceRequests",
        "ec2:DescribeKeyPairs",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeImages",
        "ec2:CreateTags",
        "ec2:TerminateInstances",
        "ec2:StopInstances",
        "ec2:StartInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

## Option 2: Use AWS Console to Launch (No IAM Changes)

If you can't modify IAM, launch manually:

### Step-by-Step Console Launch

1. **Go to EC2 Console** → **Instances** → **Launch Instance**

2. **Name**: `trader-optimizer`

3. **AMI**:
   - Click "Browse more AMIs"
   - Search: `Ubuntu Server 22.04 LTS`
   - Select: **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type**
   - Architecture: **64-bit (x86)**

4. **Instance Type**:
   - Select `c6i.2xlarge`

5. **Key Pair**:
   - If you don't have one: Click "Create new key pair"
     - Name: `trader-optimizer`
     - Type: RSA
     - Format: `.pem` (for SSH)
     - Download and save it!
   - If you have one: Select it

6. **Network Settings**:
   - Click "Edit"
   - Auto-assign public IP: **Enable**
   - Firewall (security groups):
     - Create new security group OR select existing
     - Name: `trader-optimizer-sg`
     - Add rule: Type=SSH, Source=My IP (or 0.0.0.0/0 if you need access from anywhere)

7. **Configure Storage**:
   - Size: **30 GB**
   - Type: **gp3**

8. **Advanced Details** (scroll down):
   - **Purchasing option**: ✅ **Request Spot Instances**
   - **Maximum price**: `0.15` (current ~$0.10-0.12)
   - **IAM instance profile**: Select one with S3 read access (if available)
   - **User data** (paste this):

   ```bash
   #!/bin/bash
   # Basic setup
   apt-get update
   apt-get install -y git python3-pip
   ```

9. **Click "Launch instance"**

10. **Wait 2-3 minutes**, then find your instance public IP in EC2 console

## After Launch (Both Options)

Once instance is running, you'll need to:

1. **Get the public IP** from EC2 console
2. **SSH in**: `ssh -i trader-optimizer.pem ubuntu@<PUBLIC_IP>`
3. **Clone repository**: Will need git credentials
4. **Run setup script**: `bash ~/Trader/scripts/aws/setup_instance.sh`

---

## Which Option Do You Prefer?

**Option 1 (CLI)**: Faster, repeatable, can automate
**Option 2 (Console)**: No IAM changes, good for one-time use

Let me know which you choose and I'll guide you through!
