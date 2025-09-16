from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from apps.sentry.models import SentryOrganization
from apps.sentry.services import sync_organization, sync_all_organizations


class Command(BaseCommand):
    help = 'Sync data from Sentry API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug to sync (if not provided, syncs all enabled organizations)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if last sync was recent',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually syncing',
        )

    def handle(self, *args, **options):
        org_slug = options.get('org')
        force = options.get('force', False)
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual syncing will occur'))

        if org_slug:
            # Sync specific organization
            try:
                org = SentryOrganization.objects.get(slug=org_slug)
                if not org.sync_enabled and not force:
                    raise CommandError(f'Organization {org_slug} has sync disabled. Use --force to override.')
                
                if not force and org.last_sync:
                    time_since_sync = timezone.now() - org.last_sync
                    min_interval = timedelta(hours=org.sync_interval_hours)
                    if time_since_sync < min_interval:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Organization {org_slug} was synced {time_since_sync} ago. '
                                f'Minimum interval is {org.sync_interval_hours}h. Use --force to override.'
                            )
                        )
                        return

                if dry_run:
                    self.stdout.write(f'Would sync organization: {org.name} ({org.slug})')
                    return

                self.stdout.write(f'Syncing organization: {org.name} ({org.slug})')
                sync_log = sync_organization(org.id)
                
                if sync_log:
                    if sync_log.status == 'success':
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Successfully synced {org.slug}: '
                                f'{sync_log.projects_synced} projects, '
                                f'{sync_log.issues_synced} issues, '
                                f'{sync_log.events_synced} events '
                                f'({sync_log.duration_seconds:.1f}s)'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Sync failed for {org.slug}: {sync_log.error_message}'
                            )
                        )
                else:
                    self.stdout.write(self.style.ERROR(f'Failed to create sync log for {org.slug}'))
                    
            except SentryOrganization.DoesNotExist:
                raise CommandError(f'Organization "{org_slug}" does not exist')
        
        else:
            # Sync all enabled organizations
            organizations = SentryOrganization.objects.filter(sync_enabled=True)
            
            if not force:
                # Filter organizations that need syncing
                eligible_orgs = []
                for org in organizations:
                    if not org.last_sync:
                        eligible_orgs.append(org)
                    else:
                        time_since_sync = timezone.now() - org.last_sync
                        min_interval = timedelta(hours=org.sync_interval_hours)
                        if time_since_sync >= min_interval:
                            eligible_orgs.append(org)
                organizations = eligible_orgs

            if not organizations:
                self.stdout.write(self.style.WARNING('No organizations need syncing'))
                return

            if dry_run:
                self.stdout.write(f'Would sync {len(organizations)} organizations:')
                for org in organizations:
                    last_sync = org.last_sync.strftime('%Y-%m-%d %H:%M') if org.last_sync else 'Never'
                    self.stdout.write(f'  - {org.name} ({org.slug}) - Last sync: {last_sync}')
                return

            self.stdout.write(f'Syncing {len(organizations)} organizations...')
            
            sync_logs = sync_all_organizations()
            
            success_count = 0
            failed_count = 0
            
            for sync_log in sync_logs:
                if sync_log.status == 'success':
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {sync_log.organization.slug}: '
                            f'{sync_log.projects_synced}p, '
                            f'{sync_log.issues_synced}i, '
                            f'{sync_log.events_synced}e '
                            f'({sync_log.duration_seconds:.1f}s)'
                        )
                    )
                else:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ {sync_log.organization.slug}: {sync_log.error_message}'
                        )
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSync completed: {success_count} successful, {failed_count} failed'
                )
            )