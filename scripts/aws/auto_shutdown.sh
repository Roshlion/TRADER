#!/bin/bash
# Auto-shutdown script for EC2 instances
# Monitors CPU usage and shuts down when idle to save costs

# Configuration
IDLE_THRESHOLD=5           # CPU usage percentage threshold
CHECK_INTERVAL=300         # Check every 5 minutes (300 seconds)
IDLE_DURATION=1800         # Shutdown after 30 minutes idle (1800 seconds)
LOG_FILE="/var/log/auto-shutdown.log"

# Track idle time
idle_time=0

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

get_cpu_usage() {
    # Get CPU idle percentage and calculate usage
    cpu_idle=$(top -bn2 -d 1 | grep "Cpu(s)" | tail -1 | awk '{print $8}' | cut -d'%' -f1)
    cpu_usage=$(awk "BEGIN {print 100 - $cpu_idle}")
    echo "$cpu_usage"
}

log_message "=== Auto-shutdown monitor started ==="
log_message "Config: Threshold=${IDLE_THRESHOLD}%, Check interval=${CHECK_INTERVAL}s, Idle duration=${IDLE_DURATION}s"

while true; do
    cpu_usage=$(get_cpu_usage)

    # Check if CPU usage is below threshold
    if (( $(awk "BEGIN {print ($cpu_usage < $IDLE_THRESHOLD)}") )); then
        idle_time=$((idle_time + CHECK_INTERVAL))
        log_message "CPU usage: ${cpu_usage}% (below threshold) - Idle time: ${idle_time}s / ${IDLE_DURATION}s"

        # Check if idle duration exceeded
        if [ $idle_time -ge $IDLE_DURATION ]; then
            log_message "IDLE THRESHOLD EXCEEDED - Initiating shutdown"
            log_message "Instance will shutdown in 60 seconds. Cancel with: sudo shutdown -c"

            # Send notification to any logged-in users
            wall "Auto-shutdown: Instance idle for ${IDLE_DURATION}s. Shutting down in 60 seconds. Cancel with: sudo shutdown -c"

            # Schedule shutdown in 60 seconds
            sudo shutdown -h +1 "Auto-shutdown due to idle CPU"

            # Exit the monitoring script
            exit 0
        fi
    else
        # Reset idle time if CPU usage is above threshold
        if [ $idle_time -gt 0 ]; then
            log_message "CPU usage: ${cpu_usage}% (active) - Resetting idle timer"
        fi
        idle_time=0
    fi

    # Wait before next check
    sleep $CHECK_INTERVAL
done
