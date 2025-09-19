#!/bin/bash

# =============================================================================
# SRE Dashboard - Quick Sync Script
# =============================================================================
# A simplified version for quick daily syncs with minimal logging
# =============================================================================

set -e

# Configuration
VENV_PATH="/home/asher/pyenv"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Quick SRE Dashboard Sync${NC}"
echo "Started at: $(date)"

# Activate virtual environment
echo -e "${YELLOW}🐍 Activating Python environment...${NC}"
source "$VENV_PATH/bin/activate"

# Quick sync operations
echo -e "${YELLOW}🔥 Syncing Sentry...${NC}"
python manage.py sync_sentry > /dev/null 2>&1

echo -e "${YELLOW}🎫 Syncing JIRA...${NC}"
python manage.py sync_jira > /dev/null 2>&1

echo -e "${YELLOW}✅ Syncing SonarCloud...${NC}"
python manage.py sync_sonarcloud > /dev/null 2>&1

echo -e "${YELLOW}📊 Refreshing dashboards...${NC}"
python manage.py refresh_dashboards --force > /dev/null 2>&1

echo -e "${GREEN}✅ Quick sync completed!${NC}"
echo "Finished at: $(date)"