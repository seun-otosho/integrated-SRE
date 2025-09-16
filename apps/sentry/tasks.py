import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings

from .models import SentryOrganization
from .services import sync_all_organizations

logger = logging.getLogger(__name__)


def sync_sentry_data():
    """
    Periodic task to sync Sentry data.
    This function can be called by cron jobs, Celery, or other task schedulers.
    """
    logger.info("Starting periodic Sentry sync")
    
    # Get organizations that need syncing
    now = timezone.now()
    organizations = SentryOrganization.objects.filter(sync_enabled=True)
    
    eligible_orgs = []
    for org in organizations:
        if not org.last_sync:
            # Never synced before
            eligible_orgs.append(org)
        else:
            # Check if enough time has passed
            time_since_sync = now - org.last_sync
            min_interval = timedelta(hours=org.sync_interval_hours)
            if time_since_sync >= min_interval:
                eligible_orgs.append(org)
    
    if not eligible_orgs:
        logger.info("No organizations need syncing")
        return
    
    logger.info(f"Syncing {len(eligible_orgs)} organizations")
    
    # Sync eligible organizations
    sync_logs = []
    for org in eligible_orgs:
        try:
            from .services import SentrySyncService
            service = SentrySyncService(org)
            sync_log = service.sync_all()
            sync_logs.append(sync_log)
            
            if sync_log.status == 'success':
                logger.info(
                    f"Successfully synced {org.slug}: "
                    f"{sync_log.projects_synced} projects, "
                    f"{sync_log.issues_synced} issues, "
                    f"{sync_log.events_synced} events"
                )
            else:
                logger.error(f"Sync failed for {org.slug}: {sync_log.error_message}")
                
        except Exception as e:
            logger.error(f"Failed to sync organization {org.slug}: {str(e)}")
    
    success_count = sum(1 for log in sync_logs if log.status == 'success')
    failed_count = len(sync_logs) - success_count
    
    logger.info(f"Periodic sync completed: {success_count} successful, {failed_count} failed")
    
    return sync_logs


def cleanup_old_events(days_to_keep=30):
    """
    Clean up old Sentry events to prevent database bloat.
    Keeps events from the last N days.
    """
    from .models import SentryEvent
    
    cutoff_date = timezone.now() - timedelta(days=days_to_keep)
    
    old_events = SentryEvent.objects.filter(date_created__lt=cutoff_date)
    count = old_events.count()
    
    if count > 0:
        old_events.delete()
        logger.info(f"Cleaned up {count} old Sentry events (older than {days_to_keep} days)")
    
    return count


def cleanup_old_sync_logs(days_to_keep=90):
    """
    Clean up old sync logs to prevent database bloat.
    Keeps sync logs from the last N days.
    """
    from .models import SentrySyncLog
    
    cutoff_date = timezone.now() - timedelta(days=days_to_keep)
    
    old_logs = SentrySyncLog.objects.filter(started_at__lt=cutoff_date)
    count = old_logs.count()
    
    if count > 0:
        old_logs.delete()
        logger.info(f"Cleaned up {count} old sync logs (older than {days_to_keep} days)")
    
    return count