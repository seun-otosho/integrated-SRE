#!/usr/bin/env python
"""
Cron job script for syncing Sentry data.

To set up periodic syncing every 3 hours, add this to your crontab:
0 */3 * * * /path/to/your/project/apps/sentry/cron.py

Or create a systemd timer, or use any other scheduling system.
"""

import os
import sys
import django

# Add the project root to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from apps.sentry.tasks import sync_sentry_data, cleanup_old_events, cleanup_old_sync_logs

if __name__ == '__main__':
    try:
        # Sync Sentry data
        sync_sentry_data()
        
        # Optional: Clean up old data (run less frequently)
        import random
        if random.randint(1, 24) == 1:  # Run cleanup roughly once per day
            cleanup_old_events(days_to_keep=30)
            cleanup_old_sync_logs(days_to_keep=90)
            
    except Exception as e:
        print(f"Cron job failed: {str(e)}")
        sys.exit(1)