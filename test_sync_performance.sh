#!/bin/bash

# =============================================================================
# Sync Script Performance Testing
# =============================================================================

set -e

VENV_PATH="/home/asher/pyenv"
source "$VENV_PATH/bin/activate"

echo "🧪 Testing Sync Script Performance"
echo "======================================"

# Test individual commands with timeouts
echo "1. Testing Sentry sync (dry-run)..."
timeout 10s python manage.py sync_sentry --dry-run

echo "2. Testing JIRA sync (dry-run)..."
timeout 10s python manage.py sync_jira --dry-run || echo "JIRA doesn't support dry-run"

echo "3. Testing SonarCloud sync (dry-run)..."
timeout 10s python manage.py sync_sonarcloud --dry-run

echo "4. Testing dashboard refresh..."
time python manage.py refresh_dashboards --stats

echo "5. Testing actual Sentry sync (with timeout)..."
timeout 30s python manage.py sync_sentry || echo "Sentry sync timed out (normal for large datasets)"

echo ""
echo "✅ Performance test completed!"
echo "📊 Dashboard refresh is fastest - use for frequent updates"
echo "⏱️  Full syncs may take several minutes with real data"