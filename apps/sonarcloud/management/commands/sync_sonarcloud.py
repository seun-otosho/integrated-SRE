from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from apps.sonarcloud.models import SonarCloudOrganization
from apps.sonarcloud.services import sync_sonarcloud_organization, sync_all_sonarcloud_organizations


class Command(BaseCommand):
    help = 'Sync data from SonarCloud API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization name to sync (if not provided, syncs all enabled organizations)',
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
        parser.add_argument(
            '--test-connection',
            action='store_true',
            help='Test connection to SonarCloud organizations',
        )

    def handle(self, *args, **options):
        org_name = options.get('org')
        force = options.get('force', False)
        dry_run = options.get('dry_run', False)
        test_connection = options.get('test_connection', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual syncing will occur'))

        if test_connection:
            self._test_connections(org_name)
            return

        if org_name:
            # Sync specific organization
            try:
                org = SonarCloudOrganization.objects.get(name__icontains=org_name)
                if not org.sync_enabled and not force:
                    raise CommandError(f'Organization {org_name} has sync disabled. Use --force to override.')
                
                if not force and org.last_sync:
                    time_since_sync = timezone.now() - org.last_sync
                    min_interval = timedelta(hours=org.sync_interval_hours)
                    if time_since_sync < min_interval:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Organization {org_name} was synced {time_since_sync} ago. '
                                f'Minimum interval is {org.sync_interval_hours}h. Use --force to override.'
                            )
                        )
                        return

                if dry_run:
                    self.stdout.write(f'Would sync organization: {org.name}')
                    return

                self.stdout.write(f'Syncing organization: {org.name}')
                sync_log = sync_sonarcloud_organization(org.id)
                
                if sync_log:
                    if sync_log.status == 'success':
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Successfully synced {org.name}: '
                                f'{sync_log.projects_synced} projects, '
                                f'{sync_log.measures_synced} measures, '
                                f'{sync_log.issues_synced} issues '
                                f'({sync_log.duration_seconds:.1f}s)'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Sync failed for {org.name}: {sync_log.error_message}'
                            )
                        )
                else:
                    self.stdout.write(self.style.ERROR(f'Failed to create sync log for {org.name}'))
                    
            except SonarCloudOrganization.DoesNotExist:
                raise CommandError(f'Organization matching "{org_name}" does not exist')
        
        else:
            # Sync all enabled organizations
            organizations = SonarCloudOrganization.objects.filter(sync_enabled=True)
            
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
                    self.stdout.write(f'  - {org.name} - Last sync: {last_sync}')
                return

            self.stdout.write(f'Syncing {len(organizations)} organizations...')
            
            sync_logs = sync_all_sonarcloud_organizations()
            
            success_count = 0
            failed_count = 0
            
            for sync_log in sync_logs:
                if sync_log.status == 'success':
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {sync_log.sonarcloud_organization.name}: '
                            f'{sync_log.projects_synced}p, '
                            f'{sync_log.measures_synced}m, '
                            f'{sync_log.issues_synced}i '
                            f'({sync_log.duration_seconds:.1f}s)'
                        )
                    )
                else:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ {sync_log.sonarcloud_organization.name}: {sync_log.error_message}'
                        )
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSync completed: {success_count} successful, {failed_count} failed'
                )
            )

    def _test_connections(self, org_name=None):
        """Test SonarCloud API connections"""
        if org_name:
            try:
                orgs = [SonarCloudOrganization.objects.get(name__icontains=org_name)]
            except SonarCloudOrganization.DoesNotExist:
                raise CommandError(f'Organization matching "{org_name}" does not exist')
        else:
            orgs = SonarCloudOrganization.objects.all()

        self.stdout.write('Testing SonarCloud connections...\n')

        for org in orgs:
            try:
                from apps.sonarcloud.client import SonarCloudAPIClient
                client = SonarCloudAPIClient(org.api_token)
                success, message = client.test_connection()
                
                # Update connection status
                org.last_connection_test = timezone.now()
                if success:
                    org.connection_status = 'connected'
                    org.connection_error = ''
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ {org.name}: {message}')
                    )
                else:
                    org.connection_status = 'failed'
                    org.connection_error = message
                    self.stdout.write(
                        self.style.ERROR(f'✗ {org.name}: {message}')
                    )
                org.save()
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ {org.name}: Connection test failed - {str(e)}')
                )