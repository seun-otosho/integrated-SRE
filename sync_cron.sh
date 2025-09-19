#!/bin/bash

# =============================================================================
# SRE Dashboard - Cron-Friendly Sync Script
# =============================================================================
# Designed for automated execution via cron with minimal output
# Logs everything to files and only outputs on errors
# =============================================================================

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="/home/asher/pyenv"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/cron_sync_$(date +%Y%m%d_%H%M%S).log"
ERROR_LOG="$LOG_DIR/cron_errors.log"

# Create logs directory
mkdir -p "$LOG_DIR"

# Redirect all output to log file
exec 1>> "$LOG_FILE"
exec 2>> "$LOG_FILE"

echo "======================================"
echo "Cron Sync Started: $(date)"
echo "======================================"

# Activate virtual environment
cd "$SCRIPT_DIR"
source "$VENV_PATH/bin/activate"

# Run sync operations with error handling
ERRORS=0

# Sentry sync
echo "$(date): Starting Sentry sync..."
if ! python manage.py sync_sentry; then
    echo "ERROR: Sentry sync failed" >> "$ERROR_LOG"
    ((ERRORS++))
fi

# JIRA sync  
echo "$(date): Starting JIRA sync..."
if ! python manage.py sync_jira; then
    echo "ERROR: JIRA sync failed" >> "$ERROR_LOG"
    ((ERRORS++))
fi

# SonarCloud sync
echo "$(date): Starting SonarCloud sync..."
if ! python manage.py sync_sonarcloud; then
    echo "ERROR: SonarCloud sync failed" >> "$ERROR_LOG"
    ((ERRORS++))
fi

# Dashboard refresh
echo "$(date): Refreshing dashboards..."
if ! python manage.py refresh_dashboards --force; then
    echo "ERROR: Dashboard refresh failed" >> "$ERROR_LOG"
    ((ERRORS++))
fi

# Cleanup old logs (keep last 7 days)
find "$LOG_DIR" -name "cron_sync_*.log" -mtime +7 -delete

echo "======================================"
echo "Cron Sync Completed: $(date)"
echo "Errors: $ERRORS"
echo "======================================"

# Exit with error code if any operations failed
exit $ERRORS