@echo off
REM Launch EC2 Spot Instance for TRADER Optimizer
REM Usage: launch_spot.bat

echo ============================================================
echo Launching EC2 Spot Instance (c6i.2xlarge)
echo ============================================================
echo.

REM Configuration
set INSTANCE_TYPE=c6i.2xlarge
set AMI_ID=ami-0c7217cdde317cfec
set KEY_NAME=trader-optimizer
set SECURITY_GROUP=sg-0616e1ad92cffbda8
set MAX_PRICE=0.20
set REGION=us-east-1

echo Instance Type: %INSTANCE_TYPE%
echo Region: %REGION%
echo Max Spot Price: $%MAX_PRICE%/hour
echo.

REM Create user data script (bootstrap)
echo Creating bootstrap script...
echo #!/bin/bash > user_data_temp.sh
echo set -euxo pipefail >> user_data_temp.sh
echo exec ^> ^>(tee /var/log/user-data.log^|logger -t user-data -s 2^>^/dev/console^) 2^>^&1 >> user_data_temp.sh
echo apt-get update ^&^& apt-get upgrade -y >> user_data_temp.sh
echo apt-get install -y git python3-pip python3-venv htop tmux >> user_data_temp.sh
echo echo "Bootstrap complete at $(date)" >> user_data_temp.sh

REM Launch spot instance
echo Launching spot instance...
aws ec2 run-instances ^
  --region %REGION% ^
  --instance-type %INSTANCE_TYPE% ^
  --image-id %AMI_ID% ^
  --key-name %KEY_NAME% ^
  --security-group-ids %SECURITY_GROUP% ^
  --instance-market-options "MarketType=spot,SpotOptions={MaxPrice=%MAX_PRICE%,SpotInstanceType=one-time}" ^
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}" ^
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=trader-optimizer},{Key=Project,Value=TRADER}]" ^
  --user-data file://user_data_temp.sh ^
  --output json > ec2_launch_output.json

if errorlevel 1 (
    echo ERROR: Failed to launch instance
    del user_data_temp.sh
    exit /b 1
)

echo.
echo Instance launched successfully!

REM Extract instance ID
for /f "tokens=2 delims=:" %%a in ('findstr "InstanceId" ec2_launch_output.json') do set INSTANCE_ID=%%a
set INSTANCE_ID=%INSTANCE_ID:"=%
set INSTANCE_ID=%INSTANCE_ID:,=%
set INSTANCE_ID=%INSTANCE_ID: =%

echo Instance ID: %INSTANCE_ID%
echo.

echo Waiting for instance to be running...
aws ec2 wait instance-running --region %REGION% --instance-ids %INSTANCE_ID%

echo.
echo Getting public IP address...
aws ec2 describe-instances ^
  --region %REGION% ^
  --instance-ids %INSTANCE_ID% ^
  --query "Reservations[0].Instances[0].PublicIpAddress" ^
  --output text > instance_ip.txt

set /p INSTANCE_IP=<instance_ip.txt

echo.
echo ============================================================
echo Instance Ready!
echo ============================================================
echo Instance ID: %INSTANCE_ID%
echo Public IP:   %INSTANCE_IP%
echo.
echo SSH Command:
echo   ssh -i trader-optimizer.pem ubuntu@%INSTANCE_IP%
echo.
echo Next steps:
echo   1. Wait 1-2 minutes for bootstrap to complete
echo   2. SSH into the instance
echo   3. Run: bash /path/to/setup_instance.sh
echo ============================================================

REM Save connection info
echo INSTANCE_ID=%INSTANCE_ID% > ec2_connection_info.txt
echo INSTANCE_IP=%INSTANCE_IP% >> ec2_connection_info.txt
echo SSH_COMMAND=ssh -i trader-optimizer.pem ubuntu@%INSTANCE_IP% >> ec2_connection_info.txt
echo LAUNCH_TIME=%date% %time% >> ec2_connection_info.txt

REM Cleanup
del user_data_temp.sh

echo.
echo Connection info saved to: ec2_connection_info.txt
