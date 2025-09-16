# 🔍 Sentry Management System

A Django-based local management system for your Sentry projects that automatically syncs data every 3 hours.

## 🌟 Features

- **📊 Local Dashboard**: View all your Sentry organizations, projects, and issues in one place
- **🔄 Automatic Sync**: Configurable periodic syncing (default: every 3 hours)
- **🎯 Issue Management**: Track and manage issues with detailed views
- **📈 Statistics**: Project statistics and issue trends
- **⚙️ Admin Interface**: Full Django admin integration for data management
- **🧹 Data Cleanup**: Automatic cleanup of old events and logs
- **🔐 Multi-Organization**: Support for multiple Sentry organizations

## 🚀 Quick Setup

1. **Run the setup script:**
   ```bash
   python setup_sentry_system.py
   ```

2. **Start the development server:**
   ```bash
   python manage.py runserver
   ```

3. **Access the system:**
   - Dashboard: http://localhost:8000/sentry/
   - Admin: http://localhost:8000/admin/sentry/

## 📋 Manual Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Create Superuser
```bash
python manage.py createsuperuser
```

### 4. Add Sentry Organization
1. Go to http://localhost:8000/admin/sentry/sentryorganization/
2. Click "Add Sentry Organization"
3. Fill in your organization details and API token

## 🔑 Getting Your Sentry API Token

1. Go to https://sentry.io/settings/account/api/auth-tokens/
2. Click "Create New Token"
3. Give it a name like "Local Management System"
4. Select scopes: `org:read`, `project:read`, `event:read`
5. Copy the generated token

## 🔄 Setting Up Periodic Sync

### Option 1: Cron Job (Recommended)
Add to your crontab (`crontab -e`):
```bash
# Sync every 3 hours
0 */3 * * * /usr/bin/python3 /path/to/your/project/apps/sentry/cron.py
```

### Option 2: Systemd Timer
Create `/etc/systemd/system/sentry-sync.service`:
```ini
[Unit]
Description=Sentry Data Sync
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /path/to/your/project/apps/sentry/cron.py
User=your-user
WorkingDirectory=/path/to/your/project
```

Create `/etc/systemd/system/sentry-sync.timer`:
```ini
[Unit]
Description=Run Sentry sync every 3 hours
Requires=sentry-sync.service

[Timer]
OnCalendar=*-*-* 00/3:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable sentry-sync.timer
sudo systemctl start sentry-sync.timer
```

## 🎛️ Management Commands

### Sync Commands
```bash
# Sync all enabled organizations
python manage.py sync_sentry

# Sync specific organization
python manage.py sync_sentry --org myorg

# Force sync even if recently synced
python manage.py sync_sentry --force

# Dry run (show what would be synced)
python manage.py sync_sentry --dry-run
```

### Manual Cleanup
```bash
# Clean up old events (older than 30 days)
python -c "
import django; django.setup()
from apps.sentry.tasks import cleanup_old_events
cleanup_old_events(days_to_keep=30)
"

# Clean up old sync logs (older than 90 days)
python -c "
import django; django.setup()
from apps.sentry.tasks import cleanup_old_sync_logs
cleanup_old_sync_logs(days_to_keep=90)
"
```

## 📊 Data Models

The system stores the following data:

- **Organizations**: Your Sentry organizations with API configuration
- **Projects**: Projects within each organization
- **Issues**: Issues/errors from your projects
- **Events**: Individual event occurrences for each issue
- **Sync Logs**: History of sync operations

## 🔧 Configuration

### Organization Settings
- **Sync Enabled**: Enable/disable automatic syncing
- **Sync Interval**: How often to sync (default: 3 hours)
- **API Token**: Your Sentry API token
- **API URL**: Sentry API endpoint (default: https://sentry.io/api/0/)

### Data Retention
- Events older than 30 days are automatically cleaned up
- Sync logs older than 90 days are automatically cleaned up
- Configurable in the cleanup tasks

## 🎯 Usage Examples

### View Recent Issues
```python
from apps.sentry.models import SentryIssue

# Get unresolved issues from last 24 hours
recent_issues = SentryIssue.objects.filter(
    status='unresolved',
    last_seen__gte=timezone.now() - timedelta(hours=24)
).order_by('-last_seen')
```

### Check Sync Status
```python
from apps.sentry.models import SentrySyncLog

# Get latest sync logs
latest_syncs = SentrySyncLog.objects.order_by('-started_at')[:5]
for sync in latest_syncs:
    print(f"{sync.organization.name}: {sync.status}")
```

### Trigger Manual Sync
```python
from apps.sentry.services import sync_organization

# Sync specific organization
org_id = 1
sync_log = sync_organization(org_id)
print(f"Sync completed: {sync_log.status}")
```

## 🛠️ Troubleshooting

### Common Issues

1. **API Token Invalid**
   - Check token permissions: needs `org:read`, `project:read`
   - Verify token isn't expired
   - Test with: `/sentry/test-connection/`

2. **Sync Not Running**
   - Check organization has `sync_enabled=True`
   - Verify cron job is set up correctly
   - Check sync logs in admin for errors

3. **Missing Data**
   - Ensure API token has access to the organization
   - Check project permissions in Sentry
   - Run sync with `--force` flag

### Debug Mode
Enable debug logging in your Django settings:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'sentry_sync.log',
        },
    },
    'loggers': {
        'apps.sentry': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

## 🔒 Security Notes

- Store API tokens securely (consider using environment variables)
- Restrict access to the admin interface
- Regularly rotate API tokens
- Monitor sync logs for suspicious activity

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📄 License

This project is part of your Django application and follows the same licensing terms.