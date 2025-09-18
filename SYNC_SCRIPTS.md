# 🚀 SRE Dashboard Sync Scripts

This directory contains comprehensive sync scripts for the SRE Dashboard system. These scripts activate the Python virtual environment and run all necessary data synchronization commands.

## 📁 Available Scripts

### 1. `sync_all_systems.sh` - Complete Sync with Full Logging
**Use Case**: Manual execution, debugging, full system sync with detailed output

**Features:**
- ✅ Comprehensive logging with timestamps
- ✅ Colored output for easy reading
- ✅ Error handling and rollback
- ✅ Duration tracking
- ✅ Flexible command-line options
- ✅ Detailed statistics reporting

**Usage:**
```bash
# Full sync of all systems
./sync_all_systems.sh

# Skip specific systems
./sync_all_systems.sh --skip-sentry --skip-jira

# Refresh only dashboards (fastest)
./sync_all_systems.sh --only-dashboards

# Show help
./sync_all_systems.sh --help
```

**Options:**
- `--skip-sentry` - Skip Sentry data sync
- `--skip-jira` - Skip JIRA data sync  
- `--skip-sonarcloud` - Skip SonarCloud data sync
- `--skip-dashboards` - Skip dashboard cache refresh
- `--only-dashboards` - Only refresh dashboards (skip data sync)

### 2. `quick_sync.sh` - Fast Daily Sync
**Use Case**: Quick daily updates, minimal output

**Features:**
- ⚡ Fast execution with minimal logging
- ⚡ Silent operation (output suppressed)
- ⚡ Essential syncs only
- ⚡ Perfect for manual daily runs

**Usage:**
```bash
./quick_sync.sh
```

### 3. `sync_cron.sh` - Automated Cron Sync
**Use Case**: Scheduled execution via cron, production automation

**Features:**
- 🤖 Designed for cron execution
- 🤖 Logs to files with timestamps
- 🤖 Error logging to separate file
- 🤖 Automatic log cleanup (7-day retention)
- 🤖 Exit codes for monitoring

**Usage:**
```bash
# Manual execution
./sync_cron.sh

# Add to crontab for hourly sync
0 * * * * /path/to/sync_cron.sh

# Add to crontab for daily sync at 2 AM
0 2 * * * /path/to/sync_cron.sh
```

## 🔧 Configuration

### Virtual Environment Path
All scripts use the virtual environment located at:
```bash
VENV_PATH="/home/asher/pyenv"
```

**To change the path**, edit this variable in each script file.

### Log Directory
Logs are stored in:
```bash
LOG_DIR="./logs"
```

**Log files:**
- `sync_YYYYMMDD_HHMMSS.log` - Full sync logs
- `cron_sync_YYYYMMDD_HHMMSS.log` - Cron sync logs  
- `cron_errors.log` - Cron error accumulation

## 📊 What Gets Synced

### 1. Sentry Integration
```bash
python manage.py sync_sentry --organizations
python manage.py sync_sentry --issues
python manage.py sentry_auto_link_jira
python manage.py sentry_fuzzy_match_jira
```

### 2. JIRA Integration
```bash
python manage.py sync_jira
```

### 3. SonarCloud Integration
```bash
python manage.py sync_sonarcloud --organizations
python manage.py sync_sonarcloud --metrics
```

### 4. Dashboard Cache Refresh
```bash
python manage.py refresh_dashboards --dashboard executive --force
python manage.py refresh_dashboards --dashboard product --force
python manage.py refresh_dashboards --dashboard environment --force
python manage.py refresh_dashboards --cleanup
```

## ⏱️ Recommended Schedule

### Development Environment
```bash
# Quick sync every 2 hours during work hours
0 9,11,13,15,17 * * 1-5 /path/to/quick_sync.sh

# Full sync daily at 7 AM
0 7 * * * /path/to/sync_all_systems.sh --only-dashboards
```

### Production Environment
```bash
# Cron sync every hour
0 * * * * /path/to/sync_cron.sh

# Full sync daily at 2 AM
0 2 * * * /path/to/sync_all_systems.sh
```

## 🔍 Monitoring & Troubleshooting

### Check Last Sync Status
```bash
# Check recent logs
tail -f logs/sync_*.log

# Check for errors
cat logs/cron_errors.log

# Check dashboard statistics
./sync_all_systems.sh --only-dashboards
```

### Common Issues

**1. Virtual Environment Not Found**
```bash
# Update VENV_PATH in scripts
VENV_PATH="/your/correct/path"
```

**2. Django Database Connection**
```bash
# Check Django settings
python manage.py check
```

**3. API Authentication Issues**
```bash
# Check API keys in Django admin
# Verify network connectivity to external services
```

**4. Permission Issues**
```bash
# Make scripts executable
chmod +x *.sh

# Check log directory permissions
mkdir -p logs
chmod 755 logs
```

## 📈 Performance Guidelines

### Sync Duration Expectations
- **Quick Sync**: 30-60 seconds
- **Dashboard Only**: 5-10 seconds
- **Full Sync**: 2-5 minutes

### Resource Usage
- **CPU**: Moderate during sync operations
- **Memory**: ~200MB peak usage
- **Network**: API calls to Sentry, JIRA, SonarCloud

### Optimization Tips
1. Use `--only-dashboards` for frequent refreshes
2. Schedule full syncs during low-traffic periods
3. Monitor log file sizes and clean up regularly
4. Use `quick_sync.sh` for manual daily operations

## 🎯 Script Selection Guide

| Use Case | Script | Frequency | Output |
|----------|--------|-----------|---------|
| Manual debugging | `sync_all_systems.sh` | As needed | Full colored output |
| Daily manual sync | `quick_sync.sh` | Daily | Minimal output |
| Automated production | `sync_cron.sh` | Hourly | File logging only |
| Dashboard refresh only | `sync_all_systems.sh --only-dashboards` | Multiple times/day | Status output |

## 🔐 Security Notes

- Scripts activate virtual environment automatically
- No hardcoded credentials (uses Django settings)
- Log files may contain sensitive data - secure appropriately
- Ensure proper file permissions on production servers

---

**Last Updated**: September 2025  
**Maintainer**: SRE Team